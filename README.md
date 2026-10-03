# Advance Wars 1+2: Re-Boot Camp — save editor

Reads and writes the custom-map slots in a Re-Boot Camp save, as a desktop app
or from a terminal. Open your save, see the maps in it, put new ones in, take
them out, roll back to a backup.

**Not affiliated with Nintendo or WayForward.** This reads and writes a save
file that already exists on your machine. It contains no game code and nothing
extracted from a cartridge.

## The desktop app

Download the Windows zip from
[Releases](https://github.com/ARXII-13/awrbc-save-editor/releases), unzip, run
`awrbc.exe`.

**Unblock the zip before extracting** — right-click → Properties → tick
Unblock. Windows marks files from a downloaded zip as internet-sourced, and
.NET refuses to load an assembly marked that way, which stops the window
opening. The app says so if it happens, with the command that fixes it.

From a checkout instead:

```bash
pip install -e ".[desktop]"
python -m awrbc.desktop
```

## The command line

```bash
pip install .

awrbc doctor                      find save data and say what is readable
awrbc list                        the maps in the save
awrbc export 3 --out map.json     write one out
awrbc import map.json             put one in
awrbc remove 3                    take one out
awrbc backup                      snapshot the save
awrbc restore [name]              list snapshots, or roll one back
```

Every write takes a backup first, and refuses while the game is running — a
loaded title flushes its own copy of the save over anything put underneath it,
so that is data loss rather than an inconvenience.

## Where maps come from

Not from here. This tool imports a map someone already made: a `.json`, or an
Export bundle `.zip`. Making maps, and sharing them, is a separate tool in a
separate repository — which is the point. A tool that edits your own save file
and a public archive of maps are different things with different risks, and
nothing in this repository knows the archive exists.

What the two share is the renderer, because a save manager has to show which
map is which, and drawing a map is drawing a map.

## What is in here

```
awrbc/core/      the save format: MS-NRBF codec, schema, validation, backups
awrbc/cli/       the terminal interface
awrbc/desktop/   the app, and the bridge it exposes to its page
web/             the page it loads, and the renderer that draws maps
tools/           packaging, and the diagnostics used to work the format out
```

`tools/desktop_payload.py` decides what the packaged app may contain, and
`tests/test_desktop_payload.py` fails if anything from the map editor gets
into it. That is a test rather than a convention because the convention
already failed once: an early build shipped the whole map editor, archive
submission included, and nothing noticed.

## Sprite art

`web/sprites/` holds terrain and unit art built from
[Commander Wars](https://github.com/Robosturm/Commander_Wars), which is
Advance Wars derived. It ships with the app so previews look like the game.
Without a pack, terrain draws as a letter on flat colour, which still works
and is still readable.

## Tests

```bash
python -m unittest discover -s . -t . -q    # the codec, schema, app
node --test web/test/*.test.mjs             # the page's modules
```

The suite builds its own saves from the type table, so it runs on a machine
with no game and no save. Set `AWRBC_TEST_SAVE` to a real save file to turn on
the fidelity tests that compare against what the game itself wrote.
