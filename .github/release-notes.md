**Windows only.** The save editor, shipped on its own.

## What this is

A tool for the custom-map slots in your Advance Wars 1+2: Re-Boot Camp save.
Open the save, see what is in it, put maps in, take them out, roll back.

It does not make maps and does not talk to any map archive — those are a
separate tool in a separate repository. This one reads and writes a file that
is already on your machine.

## Running it

Unzip anywhere and run `awrbc.exe`. SmartScreen will warn that the publisher
is unknown — *More info* → *Run anyway*. The executable is not signed, so
everyone sees this.

Windows also marks everything extracted from a downloaded zip as coming from
the internet, and .NET refuses to load an assembly marked that way. The app
clears that mark from its own files at startup, so there is nothing to do.
If it cannot — a folder it may not write to, such as Program Files — it says
so and gives the command that fixes it. Putting it somewhere you own avoids
the question.

## What works

- **Desktop app** — unzip, run `awrbc.exe`. Finds the maps in your save with
  a picture of each, and imports, removes, backs up and restores. It looks
  where the common emulators keep their saves, and you can point it at a
  folder yourself - which is the answer for a save copied off a console.
  A save that has never held a custom map has no maps file at all; it can
  make one.
- **Command line** — `pip install .` gives `awrbc`: `doctor`, `list`,
  `export`, `import`, `remove`, `backup`, `restore`.

Changes are staged and written in one go, with a backup taken first. Close
the game before writing: it keeps its own copy of the save while it runs and
puts that back over yours. The tool also refuses while an emulator is up - it
cannot tell a loaded game from an emulator sitting on its game list, so it
declines for both.

## New since rc.3

- **A save that has never held a custom map can be used.** The game only
  creates its maps file once there is a map to put in it, so a fresh profile
  has none at all. The tool makes the file now, with your maps in it. Verified
  on a real Switch.
- **Changes are staged and written once.** Mark maps to remove, queue several
  to import, then save in one go — one read, one backup, one write, instead of
  one of each per map.
- **Point it at any save.** It knows where Ryujinx, Ryubing, yuzu, Suyu,
  Sudachi, Citron, Eden and Torzu keep theirs, and you can browse to a folder
  yourself — which is the answer for a save copied off a console.
- **Click a map to see it full size.**
- Writes refuse while an emulator is running, not only Ryujinx.

## What does not work yet

- **macOS and Linux have no packaged build.** `pip install ".[desktop]"` and
  `python -m awrbc.desktop` work on both.
- **River and shoal** draw as flat colour — no sprites for them yet. Every
  other terrain has art, sea included.
- **Bundle `.zip` import** is not wired up; open the zip and import the
  `map.json` inside it.

## Before you run it

Needs the **WebView2 runtime**, which ships with Windows 11 and with Edge.

It writes to your save. It backs up before every write and keeps the backups,
but take your own first — this is a release candidate.

## Reporting something

Open an issue with what you did and what happened. `awrbc doctor` prints what
the tool can see, which is usually the fastest thing to paste.
