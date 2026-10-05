# End-to-end test

A pass through everything this tool does, in the order somebody would meet
it. Written to be followed start to finish, but each part stands alone if you
only want to re-check one.

**Before you start.** Close Advance Wars, and close the emulator as well —
the tool refuses to write while an emulator process is up, and it cannot tell
a loaded game from an emulator sitting on its game list.

**What is at risk.** Every write takes a backup first, so the save you point
it at is recoverable. The console is the exception: nothing the tool does
reaches a Switch, so a copy you push back by hand is yours to get right. Keep
an untouched copy of any console save before you send one back.

---

## 1. It opens, and finds your saves

1. Unzip `awrbc-windows.zip` anywhere and run `awrbc.exe`.
2. SmartScreen will warn — *More info* → *Run anyway*. The executable is not
   signed, so this is expected and will happen for anyone who downloads it.
3. A window opens, titled *Advance Wars 1+2 map tool*.

**Expect:** the maps in your save, each with a picture. Above them a row of
buttons, and below it a **Save** row naming which save is open.

**Check:**
- [ ] The window opens without a zip-blocked dialog. If you get one saying
      Windows has it blocked, the app could not clear its own mark — which
      happens in a folder it may not write to, such as Program Files. Move it
      somewhere you own.
- [ ] The map pictures look like the game, not letters on flat colour. Letters
      mean the sprite pack did not load, and the header will say so.
- [ ] The **Save** dropdown lists every profile it found. A save folder you
      made a copy of by hand shows as `(copy)` and sorts below the live ones.

---

## 2. Looking at a map

1. Click any map's picture.

**Expect:** the map fills the window at a readable size, with its name and
author underneath.

**Check:**
- [ ] Escape closes it. So does the **Close** button, and so does clicking the
      dark area around the map.
- [ ] Clicking the map itself does **not** close it.
- [ ] A very large map (40×30 or bigger) is scrollable rather than squashed.

---

## 3. Importing maps, and the staging model

Nothing is written until you press **Save changes**. This is the part most
worth exercising, because it is where the tool changed most recently.

1. Press **Import map files…** and pick one or more `.json` maps. There are
   six exported from a real save in
   `scratch-testpack/for-console/` if you need some.
2. They appear at the bottom of the list as cards with a dashed border and a
   **will be added** badge.
3. Press **Remove** on a map already in the save. It dims, says **will be
   removed**, and the button becomes **Keep**.

**Expect:** a bar across the top saying what is pending, with **Discard** and
**Save changes**.

**Check:**
- [ ] Nothing has been written yet — the bar is the only thing that changed.
- [ ] **Keep** puts a marked map back.
- [ ] **Discard** clears everything pending and leaves the save alone.
- [ ] **Save changes** asks first, and names what it is about to do.
- [ ] After saving, the list reflects it and the alert names the backup.
- [ ] Importing a map that is not playable refuses the **whole batch** and
      says why. Nothing in that batch lands.

---

## 4. Backups

1. Press **Back up now**. It names the snapshot it took.
2. Press **Restore…**.

**Expect:** a numbered list of snapshots, newest first, with `1` pre-filled.

**Check:**
- [ ] `1` is the most recent backup, not the oldest.
- [ ] Restoring asks for confirmation and says what it put back.
- [ ] The list on screen matches the restored save afterwards.
- [ ] If you had something staged before restoring, it is gone afterwards —
      staged marks are positions in a list that no longer exists.

---

## 5. A save the tool did not find

This is the path for a console save, a portable install, or anything else.

1. In the **Save** dropdown, choose **Choose a folder or maps file…**.
2. Point it at a folder holding a `maps` file, or at the file itself.

**Check:**
- [ ] It opens, and joins the dropdown under **Opened by hand**.
- [ ] You can switch back to a detected save and return to it.
- [ ] Cancelling the dialog leaves the dropdown where it was.
- [ ] Pointing it at a folder with no Advance Wars save in it says so clearly.

---

## 6. A save that has never held a custom map

The case a new player is in. The game only creates the `maps` file once a save
holds a custom map, so a fresh profile has none.

There is a real example to test against, copied off a console before anything
was written to it:
`scratch-testpack/console-backup-20261004-165639/`

1. Choose **Choose a folder or maps file…** and point it at that folder.

**Expect:** not an error. A blue note saying the save has no maps file and
that importing some will make one, naming the folder.

**Check:**
- [ ] **Back up now** and **Restore…** are greyed out — there is nothing to
      back up yet.
- [ ] Import a few maps. They stage as usual, and the button reads
      **Create maps file**.
- [ ] Pressing it asks first, naming the folder.
- [ ] Afterwards the save opens normally and the maps are in it.
- [ ] You can then add another map to it the ordinary way.

---

## 7. The guard against writing under a running game

1. Start your emulator — you do not need to load the game.
2. Try to save any change.

**Check:**
- [ ] It refuses, and says an emulator is running.
- [ ] Closing the emulator lets the same write through.

This is a net, not a guarantee: it matches the emulator process, so it cannot
tell a loaded game from an emulator sitting idle, and it allows the write if
it cannot read the process list at all. Closing the game is still the actual
instruction.

---

## 8. On real hardware

Only if you want the full loop. Nothing in the tool talks to a Switch — a
Switch over USB is a portable device, not a drive, so files on it cannot be
opened directly.

1. Copy the game's save folder off the console to your PC.
2. **Keep an untouched copy of it**, separately.
3. Point the tool at the working copy and import maps as above.
4. Copy the folder back to the console.
5. Open the game and look in the Design Room.

**Check:**
- [ ] The maps are there, with their names and authors.
- [ ] Maps with predeployed units have them, in the right places.
- [ ] The maps are playable.

---

## The command line

Everything above has a terminal equivalent, which is also the quickest way to
check what a save holds without opening anything:

```
awrbc doctor                     what it found, and whether it can read it
awrbc list                       the maps in the save
awrbc export <n> --out map.json  write one out
awrbc import map.json            add one
awrbc remove <n>                 delete one
awrbc backup                     take a snapshot
awrbc restore [name]             list snapshots, or roll one back
```

Add `--save-dir <path>` to point any of them somewhere specific, and `--json`
for machine-readable output.

---

## If something goes wrong

Backups live outside the save, and `awrbc restore` lists them. The alert after
every write names the backup it took first, so the thing to write down is that
name.

A map that renders as letters on flat colour is a missing sprite pack, not a
broken map. River and shoal have no art yet and draw as flat colour by design.
