"""Making a maps file where the game has not made one.

A console save whose owner has never opened the Design Room holds gameState
and gameStateBackup and no `maps` at all - the game allocates that file the
first time there is a custom map to put in it. Asking a player to go and
build a map by hand before a map-importing tool will speak to them is a poor
answer, so this builds the file.

Which means this module writes save files for real hardware, and the bar is
higher than "our reader accepts it". Everything here checks that a map put in
comes back out *unchanged*, by the same content hash the archive uses for
identity - because our reader accepting our own writer proves very little,
and both of the bugs found while writing this were invisible to a
round-trip that only counted maps.
"""
import os
import tempfile
import unittest

from awrbc.core import create, identity, savefile, schema
from awrbc.core.model import BASE, HQ, Coord, Map, Tile, Unit

INFANTRY, TANK, LANDER = 9, 17, 10


def a_map(name="Fixture", cols=8, rows=6, units=None, offsets=None,
          creator="somebody", fog=False, flags=None, water_color=0):
    tiles = [[Tile(type=1) for _ in range(rows)] for _ in range(cols)]
    tiles[0][0] = Tile(type=HQ, team=0, capture_points=20)
    tiles[1][0] = Tile(type=BASE, team=0, capture_points=20)
    tiles[cols - 1][rows - 1] = Tile(type=HQ, team=1, capture_points=20)
    tiles[cols - 2][rows - 1] = Tile(type=BASE, team=1, capture_points=20)
    for (x, y), off in (offsets or {}).items():
        tiles[x][y] = Tile(type=1, offset=Coord(*off))

    grid = [[None for _ in range(rows)] for _ in range(cols)]
    for (x, y), unit in (units or {}).items():
        grid[x][y] = unit

    for (x, y), value in (flags or {}).items():
        tiles[x][y] = Tile(type=tiles[x][y].type, flags=value)

    return Map(name=name, creator=creator, cols=cols, rows=rows, fog=fog,
               water_color=water_color, tiles=tiles, units=grid)


def through_a_created_file(maps):
    """Write them into a brand-new file and read them back."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "maps")
        with open(path, "wb") as fh:
            fh.write(create.build_document(maps))
        return savefile.read(path), os.path.getsize(path)


def unchanged(before: Map, after: Map) -> bool:
    """Same map, by the hash the archive uses to tell maps apart."""
    return (identity.content_hash(schema.to_json(before, author="x"))
            == identity.content_hash(schema.to_json(after, author="x")))


class TheFileItMakes(unittest.TestCase):
    def test_our_reader_accepts_it(self):
        doc, _size = through_a_created_file([a_map()])
        self.assertEqual([m.name for m in doc.maps], ["Fixture"])

    def test_it_identifies_as_this_game(self):
        """Otherwise the tool would refuse its own output."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document([a_map()]))
            savefile.read(path)          # raises WrongGame if it does not

    def test_it_is_at_least_the_size_the_game_allocates(self):
        _doc, size = through_a_created_file([a_map()])
        self.assertGreaterEqual(size, savefile.MIN_FILE_SIZE)

    def test_it_is_a_power_of_two_like_every_save_the_game_writes(self):
        """16 KiB doubling until it fits. A big document was being left at
        its own length, which is not a size any real save has."""
        for maps in ([a_map()], [a_map() for _ in range(40)]):
            _doc, size = through_a_created_file(maps)
            self.assertEqual(size & (size - 1), 0,
                             "%d is not a power of two" % size)
            self.assertGreaterEqual(size, savefile.MIN_FILE_SIZE)

    def test_it_holds_several_maps_in_order(self):
        doc, _ = through_a_created_file(
            [a_map(name="One"), a_map(name="Two"), a_map(name="Three")])
        self.assertEqual([m.name for m in doc.maps], ["One", "Two", "Three"])

    def test_the_map_keeps_whoever_made_it(self):
        """Not the name of this tool: an imported map keeps its creator."""
        doc, _ = through_a_created_file([a_map(creator="debbie")])
        self.assertEqual(doc.maps[0].creator, "debbie")


class WhatSurvivesBeingWritten(unittest.TestCase):
    """Each of these is a thing that can be lost silently."""

    def test_a_plain_map_comes_back_unchanged(self):
        before = a_map()
        doc, _ = through_a_created_file([before])
        self.assertTrue(unchanged(before, doc.maps[0]))

    def test_units_survive(self):
        """The first version of this builder wrote every unit cell as null.
        It was invisible, because a map with no units round-trips perfectly
        through a builder that cannot write units."""
        before = a_map(units={
            (2, 2): Unit(type=INFANTRY, team=0, hp=100000000, gas=99),
            (3, 3): Unit(type=TANK, team=1, hp=50000000, gas=70, ammo=9),
        })
        doc, _ = through_a_created_file([before])
        after = doc.maps[0]
        self.assertTrue(unchanged(before, after))
        self.assertEqual(after.units[2][2].type, INFANTRY)
        self.assertEqual(after.units[3][3].ammo, 9)

    def test_a_units_exact_state_survives(self):
        before = a_map(units={(1, 1): Unit(
            type=LANDER, team=1, hp=73000000, gas=42, ammo=3,
            is_capturing=True, is_diving=False, is_predeployed=True)})
        doc, _ = through_a_created_file([before])
        u = doc.maps[0].units[1][1]
        self.assertEqual(
            (u.type, u.team, u.hp, u.gas, u.ammo, u.is_capturing,
             u.is_predeployed),
            (LANDER, 1, 73000000, 42, 3, True, True))

    def test_a_tile_offset_survives(self):
        """A tile in a multi-tile structure points back at its primary tile.
        Writing (0,0) for every tile lost that, and it showed up as one map
        in six differing by a single cell."""
        before = a_map(offsets={(4, 2): (0, 1), (4, 3): (1, 0)})
        doc, _ = through_a_created_file([before])
        after = doc.maps[0]
        self.assertTrue(unchanged(before, after))
        self.assertEqual((after.tiles[4][2].offset.x,
                          after.tiles[4][2].offset.y), (0, 1))

    def test_fog_survives(self):
        before = a_map(fog=True)
        doc, _ = through_a_created_file([before])
        self.assertTrue(doc.maps[0].fog)
        self.assertTrue(unchanged(before, doc.maps[0]))

    def test_a_map_that_is_not_square_keeps_its_shape(self):
        """The arrays are rank-2 [cols, rows] and a transposed square map
        still round-trips, so only an oblong proves the order."""
        before = a_map(cols=12, rows=5,
                       units={(11, 4): Unit(type=INFANTRY, team=1)})
        doc, _ = through_a_created_file([before])
        after = doc.maps[0]
        self.assertEqual((after.cols, after.rows), (12, 5))
        self.assertIsNotNone(after.units[11][4])
        self.assertTrue(unchanged(before, after))

    def test_several_maps_each_keep_their_own_units(self):
        a = a_map(name="A", units={(2, 2): Unit(type=INFANTRY, team=0)})
        b = a_map(name="B", units={(3, 3): Unit(type=TANK, team=1)})
        doc, _ = through_a_created_file([a, b])
        self.assertTrue(unchanged(a, doc.maps[0]))
        self.assertTrue(unchanged(b, doc.maps[1]))


class AndThenItBehavesLikeAnyOtherSave(unittest.TestCase):
    """The created file is only ever the first write. Everything after it
    goes through the ordinary path, which models new records on what the
    document already holds."""

    def test_a_map_can_be_added_normally_afterwards(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document([a_map(name="First")]))
            doc = savefile.read(path)
            savefile.add_map(doc, a_map(name="Second"))
            savefile.write(doc, path)
            self.assertEqual([m.name for m in savefile.read(path).maps],
                             ["First", "Second"])

    def test_a_map_with_units_can_be_added_normally_afterwards(self):
        """add_map copies records from what is already there, so a created
        file has to carry the unit definitions as well as the tile ones."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document(
                    [a_map(name="First",
                           units={(2, 2): Unit(type=INFANTRY, team=0)})]))
            doc = savefile.read(path)
            later = a_map(name="Second",
                          units={(1, 1): Unit(type=TANK, team=1, ammo=5)})
            savefile.add_map(doc, later)
            savefile.write(doc, path)

            again = savefile.read(path)
            self.assertTrue(unchanged(later, again.maps[1]))

    def test_one_can_be_removed_normally_afterwards(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document(
                    [a_map(name="One"), a_map(name="Two")]))
            doc = savefile.read(path)
            savefile.remove_map(doc, 0)
            savefile.write(doc, path)
            self.assertEqual([m.name for m in savefile.read(path).maps],
                             ["Two"])


class TheMembersWeDoNotModel(unittest.TestCase):
    """Nine of a unit's eighteen members are battle state a map does not
    have, and our reader ignores them - so a round-trip cannot see them at
    all. They are asserted against the encoding directly, read off a real
    save, because a wrong value here would reach a console unnoticed.
    """

    def unit_record(self):
        from awrbc.core import nrbf
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document(
                    [a_map(units={(2, 2): Unit(type=INFANTRY, team=0,
                                               hp=100000000, gas=99)})]))
            p = nrbf.Parser(open(path, "rb").read())
            p.parse()
        for rec in p.records:
            d = getattr(rec, "d", {})
            if d.get("name") == "SerializableUnit" and d.get("mnames"):
                return dict(zip(d["mnames"], d["values"]))
        self.fail("no unit was written at all")

    def test_transport_id_is_zero_for_a_unit_in_nothing(self):
        """The game writes 0, not -1. Nothing we read would notice."""
        self.assertEqual(self.unit_record()["transportID"], 0)

    def test_hp_gas_and_ammo_are_boxed(self):
        """MemberPrimitiveTyped, not bare ints - what the member type says
        and what the game writes differ here."""
        got = self.unit_record()
        for name in ("hp", "gas", "ammo"):
            self.assertEqual(got[name].rt, 8, name)
            self.assertEqual(got[name].d["pt"], create.INT32, name)

    def test_the_ai_fields_share_one_empty_string(self):
        """aiID holds the string and aiStartingWaypointID references it,
        which is what a real save does."""
        got = self.unit_record()
        self.assertEqual(got["aiID"].rt, 6)
        self.assertEqual(got["aiID"].d["val"], "")
        self.assertEqual(got["aiStartingWaypointID"].rt, 9)
        self.assertEqual(got["aiStartingWaypointID"].d["idref"],
                         got["aiID"].d["oid"])

    def test_the_mid_battle_flags_are_all_off(self):
        got = self.unit_record()
        self.assertEqual(got["flashing"], False)
        self.assertEqual(got["deployedThisTurn"], False)


class TheFieldsTheHashCannotSee(unittest.TestCase):
    """`unchanged()` compares content hashes, and `identity.HASHED_FIELDS`
    deliberately leaves out tile flags - two maps that differ only in how
    their roads connect are the same map for de-duplication.

    Which means every test in the class above is blind to flags, and flags
    are what the game reads to choose a sprite. Worse, the fixture used to
    build every tile with the default `flags=0`, so even a direct comparison
    would have been satisfied by a writer that wrote zero: the fixture
    agreed with the broken answer.

    These assert the fields directly, with values that are not the default.
    """

    def tiles_of(self, m):
        return [m.tiles[x][y] for x in range(m.cols) for y in range(m.rows)]

    def test_tile_flags_survive(self):
        """A map whose flags were dropped renders as disconnected rubble on
        a console and passes every hash comparison on the way there."""
        marks = {(1, 1): 0x1E, (2, 1): 0x0A, (3, 2): 0x1F000}
        before = a_map(flags=marks)
        doc, _ = through_a_created_file([before])
        after = doc.maps[0]
        for (x, y), value in marks.items():
            self.assertEqual(after.tiles[x][y].flags, value,
                             "flags lost at (%d,%d)" % (x, y))

    def test_every_flag_bit_makes_the_round_trip(self):
        """Not just the ones a fixture happens to use."""
        before = a_map(cols=8, rows=6,
                       flags={(0, 1): 0xFFFF, (1, 1): 0x1FFFF})
        doc, _ = through_a_created_file([before])
        after = doc.maps[0]
        self.assertEqual(after.tiles[0][1].flags, 0xFFFF)
        self.assertEqual(after.tiles[1][1].flags, 0x1FFFF)

    def test_the_water_colour_survives(self):
        """Hashed, but the fixture never had a non-zero one."""
        before = a_map(water_color=3)
        doc, _ = through_a_created_file([before])
        self.assertEqual(doc.maps[0].water_color, 3)

    def test_a_launched_silo_stays_launched(self):
        before = a_map()
        before.tiles[2][2] = Tile(type=1, has_launched=True)
        doc, _ = through_a_created_file([before])
        self.assertTrue(doc.maps[2 - 2].tiles[2][2].has_launched)

    def test_a_units_own_flags_survive(self):
        """`moved_this_turn` and `is_diving` were named in an assertion and
        then left out of the tuple it checked."""
        before = a_map(units={(1, 1): Unit(
            type=LANDER, team=0, moved_this_turn=True, is_diving=True,
            is_capturing=True, is_predeployed=True)})
        doc, _ = through_a_created_file([before])
        u = doc.maps[0].units[1][1]
        self.assertEqual(
            (u.moved_this_turn, u.is_diving, u.is_capturing, u.is_predeployed),
            (True, True, True, True))

    def test_flags_survive_a_later_add_too(self):
        """add_map models its records on the created file, so the created
        file has to have got them right first."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "maps")
            with open(path, "wb") as fh:
                fh.write(create.build_document(
                    [a_map(name="First", flags={(1, 1): 0x1E})]))
            doc = savefile.read(path)
            savefile.add_map(doc, a_map(name="Second", flags={(2, 2): 0x0A}))
            savefile.write(doc, path)

            again = savefile.read(path)
            self.assertEqual(again.maps[0].tiles[1][1].flags, 0x1E)
            self.assertEqual(again.maps[1].tiles[2][2].flags, 0x0A)


if __name__ == "__main__":
    unittest.main()
