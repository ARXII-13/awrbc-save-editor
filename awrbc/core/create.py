"""Make a maps file where there is none.

Everything else in this package edits a file the game wrote. This builds one
from the format description in ``typetable.json`` - class definitions only,
member names and types, the same schema set out in docs/format.md. No map
content and no creator names.

It exists because of what a console save actually looks like. A profile whose
owner has never opened the Design Room has ``gameState`` and
``gameStateBackup`` and no ``maps`` at all: the game allocates that file the
first time there is a custom map to put in it. Telling such a player to go
and make a map by hand before a map-importing tool will speak to them is a
poor answer, so the tool makes the file instead.

Two things make this less alarming than "we write save files now" sounds.
The whole test suite already runs against documents built by this code - it
was `tests/fixture.py` until it had a reason to ship. And a created file is
read straight back through the ordinary reader before anything is claimed
about it, so a file this cannot produce correctly is a failure here rather
than a surprise on a console.

What it is **not**: a substitute for the normal path. Once the file exists,
every later change goes through ``savefile.add_map``, which models new
records on what the document already holds. This is only ever the first
write.
"""
import json
import os
import sys

from . import derive
from .builder import VALUE_TYPES
from .model import Map, Unit
from .nrbf import Parser, Rec
from .nrbf import write as nrbf_write

def _table_path():
    """Where the format description is, from a checkout or from a bundle.

    PyInstaller keeps data beside the frozen modules under `sys._MEIPASS`,
    and `__file__` for a module in the archive already points there - but
    being explicit costs a line and the failure it prevents only appears on
    somebody else's machine, opening a console save with no maps in it.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        at = os.path.join(bundled, "awrbc", "core", "typetable.json")
        if os.path.exists(at):
            return at
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "typetable.json")


#: The format description. Ships with the package; `tools/extract_types.py`
#: regenerates it from a save.
TABLE = _table_path()

LIBRARY_ID = 2

#: NRBF primitive type code for Int32.
INT32 = 8

#: The game allocates in powers of two and never smaller than this.
MIN_FILE_SIZE = 16384


def load_table(path=TABLE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _mtypes(entry):
    """JSON turns the (bt, extra) pairs into lists; restore the shapes."""
    out = []
    for bt, ex in entry["types"]:
        if bt == 4 and isinstance(ex, list):
            ex = (ex[0], ex[1])
        out.append((bt, ex))
    return out


class Builder:
    """Assembles a whole document; each class is defined once, then reused."""

    def __init__(self, table):
        self.table = table
        self.next = 1
        self.defined = {}          # class name -> object id of its definition
        self.records = []

    def _id(self, name):
        value = self.next
        self.next += 1
        return -value if name in VALUE_TYPES else value

    def instance(self, name, values, top_level=True):
        entry = self.table["classes"][name]
        mnames, mtypes = entry["members"], _mtypes(entry)
        oid = self._id(name)
        ordered = [values[m] for m in mnames]
        if name in self.defined:
            rec = Rec(1, oid=oid, mid=self.defined[name], name=name,
                      mnames=mnames, mtypes=mtypes, values=ordered)
        else:
            self.defined[name] = oid
            rec = Rec(5, oid=oid, name=name, mnames=list(mnames),
                      mtypes=mtypes, libid=LIBRARY_ID, values=ordered)
        if top_level:
            self.records.append(rec)
        return rec

    def enum(self, name, value, top_level=False):
        return self.instance(name, {"value__": value}, top_level=top_level)

    def coord(self, x=0, y=0, top_level=False):
        return self.instance("AW.Coordinates", {"X": x, "Y": y},
                             top_level=top_level)

    def string(self, text):
        """An inline string. NOT appended: a record embedded as a member
        value must not also be emitted at top level, or it is written twice
        under the same id."""
        return Rec(6, oid=self._id("string"), val=text)

    def string_ref(self, text):
        rec = self.string(text)
        self.records.append(rec)
        return self.ref(rec)

    def array(self, key, items, lens):
        shape = self.table["arrays"][key]
        ex = shape["ex"]
        rec = Rec(7, oid=self._id("array"), at=shape["at"], rank=shape["rank"],
                  lens=list(lens), lb=None, bt=shape["bt"],
                  ex=(ex[0], ex[1]) if isinstance(ex, list) else ex,
                  items=items)
        self.records.append(rec)
        return rec

    def ref(self, rec):
        return Rec(9, idref=rec.d["oid"])

    def empty_int_list(self):
        """A List<int> with nothing in it, which several unit members want."""
        name = next(n for n in self.table["classes"]
                    if n.startswith("System.Collections.Generic.List")
                    and "System.Int32" in n)
        return self.instance(name, {"_items": Rec(10), "_size": 0,
                                    "_version": 0})


def _tile(b, t):
    return b.instance("SerializableTile", {
        "type": b.enum("TileType", t.type),
        "flags": b.enum("TileFlags", t.flags),
        "teamID": Rec(10) if t.team is None else b.enum("TeamID", t.team),
        "capturePoints": t.capture_points,
        "hp": t.hp,
        # A tile belonging to a multi-tile structure points back at the
        # structure's primary tile. Writing (0,0) for every tile loses that
        # and was invisible until a real map with one went through: five of
        # six came back identical and the sixth differed by one cell.
        "offsetFromPrimaryTile": (b.coord(t.offset.x, t.offset.y)
                                  if t.offset else b.coord()),
        "hasLaunched": bool(t.has_launched),
    })


def _unit(b, u: Unit):
    """One predeployed unit.

    The record carries eighteen members and the model carries nine of them;
    the rest are the state of a unit mid-battle, which a map being imported
    does not have. They are written as the game writes them on a fresh unit.

    Leaving these out is what the first version of this builder did - every
    cell null - and it was invisible, because a map with no units round-trips
    perfectly through a builder that cannot write units.
    """
    # Encoded exactly as the game encodes it, read off a real save rather
    # than inferred from the member types. Three of these are not what the
    # type table alone would suggest:
    #
    #   hp, gas, ammo   boxed - MemberPrimitiveTyped, not a bare int
    #   transportID     0 for "none", not -1
    #   aiID            an empty string, and aiStartingWaypointID a
    #                   *reference to that same string object*
    # Embedded as aiID's value and referenced by aiStartingWaypointID, the
    # way the game writes it. Not appended: a record that is a member value
    # must not also be emitted at top level, or it goes into the stream
    # twice under one id - which savefile.add_map then refuses, rightly.
    empty = Rec(6, oid=b._id("string"), val="")

    return b.instance("SerializableUnit", {
        "type": b.enum("UnitType", u.type),
        "teamID": Rec(10) if u.team is None else b.enum("TeamID", u.team),
        "movedThisTurn": bool(u.moved_this_turn),
        "flashing": False,
        "isCapturing": bool(u.is_capturing),
        "isDiving": bool(u.is_diving),
        "isPredeployed": bool(u.is_predeployed),
        "hp": Rec(8, pt=INT32, val=u.hp),
        "gas": Rec(8, pt=INT32, val=u.gas),
        "ammo": Rec(8, pt=INT32, val=u.ammo),
        "deployedThisTurn": False,
        "preDeployedBehavior": b.enum("AW.PreDeployedBehavior", 0),
        "aiID": empty,
        "aiStartingWaypointID": b.ref(empty),
        "startCoordinates": b.coord(),
        "transportID": 0,
        "loadedUnits": b.ref(b.empty_int_list()),
        "visibleTransportUnits": b.ref(b.empty_int_list()),
    })


def _level(b, m: Map, slot: str):
    # Column-major, because the arrays are rank-2 [cols, rows]: see
    # docs/format.md, and savefile._reshape, which reads them back.
    tiles = [b.ref(_tile(b, m.tiles[x][y]))
             for x in range(m.cols) for y in range(m.rows)]
    tiles_arr = b.array("LevelSaveData.SerializableTiles", tiles,
                        [m.cols, m.rows])

    units = []
    for x in range(m.cols):
        for y in range(m.rows):
            u = m.units[x][y] if m.units else None
            units.append(Rec(10) if u is None else b.ref(_unit(b, u)))
    units_arr = b.array("LevelSaveData.SerializableUnits", units,
                        [m.cols, m.rows])

    waypoints = b.array("LevelSaveData.AIWaypoints", [], [0])

    magma = b.instance("MagmaTargets", {
        "OddDayTargets": b.ref(b.array("MagmaTargets.OddDayTargets", [], [0])),
        "EvenDayTargets": b.ref(b.array("MagmaTargets.EvenDayTargets", [], [0])),
    })
    list_name = next(n for n in b.table["classes"]
                     if n.startswith("System.Collections.Generic.List")
                     and "SerializableUnit" in n)
    transported = b.instance(list_name, {
        "_items": b.ref(b.array("%s._items" % list_name, [], [0])),
        "_size": 0, "_version": 0,
    })

    return b.instance("LevelSaveData", {
        "Name": b.string_ref(slot),
        "SerializableTiles": b.ref(tiles_arr),
        "SerializableUnits": b.ref(units_arr),
        "TransportedUnits": b.ref(transported),
        "HasFogOfWar": bool(m.fog),
        "AIWaypoints": b.ref(waypoints),
        "MagmaTargets": b.ref(magma),
        "m_WaterColorIndex": m.water_color,
    })


def _metadata(b, m: Map, slot: str):
    values = derive.metadata(m)
    fields = {"Name": b.string_ref(slot),
              "TeamsPlaying": b.enum("TeamIDFlag", values["TeamsPlaying"])}
    for key, value in values.items():
        if key != "TeamsPlaying":
            fields[key] = value
    return b.instance("AW.UserMapMetadata", fields)


def build_document(maps, creator=None) -> bytes:
    """Serialize a complete maps file holding ``maps``."""
    table = load_table()
    b = Builder(table)
    b.records.append(Rec(0, root=0, hdr=-1, maj=1, min=0))
    b.records.append(Rec(12, id=LIBRARY_ID, name=table["library"]))

    root_id = b.next
    b.next += 1

    map_recs, meta_recs = [], []
    for index, m in enumerate(maps):
        slot = str(index)
        level = _level(b, m, slot)
        map_recs.append(b.instance("AW.CustomMap", {
            "LevelSaveData": b.ref(level),
            # The map's own creator, not this tool's name. An imported map
            # keeps whoever made it.
            "Creator": b.string(m.creator or creator or ""),
            "Name": b.string(m.name or "Untitled"),
            "IsNew": False,
            "IsDownload": False,
            "LastCursorPosition": b.coord(),
            "LastTileType": b.enum("TileType", 1),
            "LastUnitType": Rec(10),
            "LastTeamID": b.enum("TeamID", -1),
        }))
        meta_recs.append(_metadata(b, m, slot))

    maps_arr = b.array("AW.UserGeneratedContent.CustomMaps",
                       [b.ref(r) for r in map_recs], [len(map_recs)])
    sets_arr = b.array("AW.UserGeneratedContent.CustomMapSets", [], [0])
    meta_arr = b.array("AW.UserGeneratedContent.CustomMapMetadata",
                       [b.ref(r) for r in meta_recs], [len(meta_recs)])

    entry = table["classes"]["AW.UserGeneratedContent"]
    root = Rec(5, oid=root_id, name="AW.UserGeneratedContent",
               mnames=list(entry["members"]), mtypes=_mtypes(entry),
               libid=LIBRARY_ID,
               values=[{"CustomMaps": b.ref(maps_arr),
                        "CustomMapSets": b.ref(sets_arr),
                        "CustomMapMetadata": b.ref(meta_arr),
                        "CurrentSaveVersionNumber": table["saveVersion"] or 0
                        }[n] for n in entry["members"]])
    # The root has to appear before anything references it.
    b.records.insert(2, root)
    b.records[0] = Rec(0, root=root_id, hdr=-1, maj=1, min=0)
    b.records.append(Rec(11))

    parser = Parser(b"")
    parser.records = b.records
    stream = nrbf_write(parser)

    # Padded the way the game pads: powers of two from 16 KiB up. Borrowed
    # from savefile rather than restated, because a second copy of the rule
    # is a thing to get wrong - and the first version of this did get it
    # wrong, padding only to the 16 KiB floor and leaving a 455 KiB document
    # at its own length, which is not a size any save the game wrote has.
    from .savefile import _file_size_for
    return stream + b"\0" * (_file_size_for(len(stream), None) - len(stream))
