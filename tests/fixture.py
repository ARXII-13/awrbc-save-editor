"""Map helpers for the tests.

The document builder this used to hold now ships, in `awrbc/core/create.py`,
because a console save with no maps file needs one made - see that module.
It is re-exported here so the suite reads as it always did.
"""
from awrbc.core.create import (Builder, LIBRARY_ID, TABLE, _level, _metadata,
                               _mtypes, _tile, _unit, build_document,
                               load_table)
from awrbc.core.model import BASE, HQ, Map, Tile

__all__ = ["Builder", "LIBRARY_ID", "TABLE", "build_document", "load_table",
           "simple_map", "write_fixture_save", "_level", "_metadata",
           "_mtypes", "_tile", "_unit"]


def simple_map(cols=8, rows=6, name="Fixture") -> Map:
    """A small, valid, two-player map."""
    tiles = [[Tile(type=1) for _ in range(rows)] for _ in range(cols)]
    units = [[None for _ in range(rows)] for _ in range(cols)]
    m = Map(name=name, creator="fixture", cols=cols, rows=rows,
            tiles=tiles, units=units)
    m.tiles[0][0] = Tile(type=HQ, team=0, capture_points=20)
    m.tiles[1][0] = Tile(type=BASE, team=0, capture_points=20)
    m.tiles[cols - 1][rows - 1] = Tile(type=HQ, team=1, capture_points=20)
    m.tiles[cols - 2][rows - 1] = Tile(type=BASE, team=1, capture_points=20)
    return m


def write_fixture_save(path, maps=None):
    data = build_document(maps or [simple_map()])
    with open(path, "wb") as fh:
        fh.write(data)
    return path
