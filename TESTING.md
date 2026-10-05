# Trying out the save editor

This walks through everything the tool does, in the order you would meet it.
Go start to finish, or pick the part you care about — each one stands on its
own.

You do not need to know anything technical. If a step does not make sense,
that is worth writing down: it means the tool is not explaining itself.

**What you need:** a Windows PC, the `awrbc-windows.zip` you were sent, and a
few map files (they end in `.json`) to import.

---

## Before you start

**Close the game, and close the emulator too.** Not just the game — the whole
emulator window. The tool will refuse to write while an emulator is open, and
it cannot tell whether you have a game loaded or are just sitting on the menu.

**Your save is backed up automatically** before every change, so you can undo
anything you do here.

**If you are testing with a Switch**, keep your own copy of the save folder
somewhere safe first. The tool never touches your console directly — you copy
files across yourself — so that copy is your safety net, not ours.

---

## 1. Opening it

1. Unzip `awrbc-windows.zip` wherever you like — Downloads is fine. Avoid
   Program Files.
2. Open the folder and run `awrbc.exe`.
3. Windows will warn you the publisher is unknown. Click **More info**, then
   **Run anyway**. This happens to everyone and is expected.

**You should see:** a window called *Advance Wars 1+2 map tool*, listing the
maps in your save with a small picture of each.

- [ ] The window opens.
- [ ] The maps have proper pictures — terrain that looks like the game, not
      letters on coloured squares.
- [ ] The row labelled **Save** names which save you are looking at.
- [ ] If you have more than one profile, you can pick between them there.

**If a message says Windows has it blocked:** move the whole folder somewhere
like your Desktop and try again. Tell us if that happens — the tool is meant
to sort this out by itself.

---

## 2. Looking at a map properly

1. Click the small picture of any map.

**You should see:** the map filling the window at a size you can actually
read, with its name and who made it underneath.

- [ ] Pressing **Escape** closes it.
- [ ] The **Close** button closes it.
- [ ] Clicking the dark area around the map closes it.
- [ ] Clicking the map itself does *not* close it.
- [ ] A big map is scrollable rather than squashed down to fit.

---

## 3. Adding and removing maps

This is the most important part. **Nothing is written to your save until you
press Save changes.** Everything before that is you deciding.

1. Press **Import map files…** and pick one or more `.json` map files. You can
   select several at once.
2. They appear at the bottom of the list with a dashed outline and a
   **will be added** label.
3. Now press **Remove** on a map already in your save. It fades, gets a
   **will be removed** label, and the button changes to **Keep**.

**You should see:** a bar across the top saying what is about to happen, with
**Discard** and **Save changes**.

- [ ] Your save has not changed yet — only the screen has.
- [ ] **Keep** undoes a removal.
- [ ] **Discard** throws away everything pending and leaves your save alone.
- [ ] **Save changes** asks you to confirm, and tells you what it will do.
- [ ] Afterwards the list matches what you asked for.
- [ ] The message afterwards names the backup it took.

**Worth trying:** import a map that is broken or unplayable. The whole batch
should be refused with a reason, and *none* of it should go in — not even the
good maps alongside it.

---

## 4. Backups and undo

1. Press **Back up now**. It tells you what it saved.
2. Press **Restore…**.

**You should see:** a numbered list of backups, newest at the top, with **1**
already filled in.

- [ ] **1** is the most recent backup.
- [ ] It asks you to confirm before replacing anything.
- [ ] Afterwards, the maps on screen match what you restored.
- [ ] Anything you had pending before restoring is gone afterwards — that is
      deliberate, since it referred to the old list.

---

## 5. Opening a save it did not find

If your save is somewhere unusual — a portable emulator install, or a copy you
took off a console — you point the tool at it yourself.

1. Open the **Save** dropdown and choose **Choose a folder or maps file…**.
2. Pick the folder your save is in.

- [ ] It opens, and appears in the dropdown under **Opened by hand**.
- [ ] You can switch back to your normal save and then return to it.
- [ ] Cancelling the folder picker changes nothing.
- [ ] Pointing it somewhere with no Advance Wars save says so in plain words.

**If you plug in a Switch over USB and try to pick it:** it should tell you
that a Switch is not a drive and you need to copy the save to your PC first.
That is a real limitation, not a bug.

---

## 6. A save with no custom maps in it yet

**This is the part we most want tested.**

Advance Wars only creates its custom-map file once you have made or received
your first map. So a fresh profile — or a console save from someone who has
never opened the Design Room — has nothing for the tool to open.

1. Choose **Choose a folder or maps file…** and point it at such a save.

**You should see:** not an error. A blue note saying the save has no map file
yet, and that importing some will create one.

- [ ] **Back up now** and **Restore…** are greyed out — there is nothing there
      to back up.
- [ ] Import a few maps. They queue up as before, and the button now reads
      **Create maps file**.
- [ ] It asks you to confirm, and names the folder it will write into.
- [ ] Afterwards the save opens normally with your maps in it.
- [ ] You can then add another map to it the ordinary way.

---

## 7. It should refuse while the emulator is open

1. Start your emulator. You do not need to load the game.
2. Try to save any change.

- [ ] It refuses, and says an emulator is running.
- [ ] Close the emulator, try the same thing, and it works.

This is a safety net rather than a guarantee: a running game writes its own
copy of your save over anything put underneath it, which is how you lose work.
Closing the game is still the real answer.

---

## 8. The whole loop, with a Switch

Only if you have a modded console and want to test the full journey.

1. Copy the game's save folder from the console to your PC.
2. **Make a second copy and put it somewhere safe.**
3. Point the tool at the first copy and add maps as above.
4. Copy the folder back to the console.
5. Open the game and look in the Design Room.

- [ ] The maps are there, with the right names.
- [ ] Maps that came with units have them, in the right places.
- [ ] They play properly.

---

## If something goes wrong

**Your save is recoverable.** Every change takes a backup first, and
**Restore…** lists them. The message after each change names the backup it
made, so that is the thing worth noting down.

**Maps drawn as letters on flat colour** means the artwork did not load, not
that the map is broken. River and shoal have no artwork yet and show as flat
colour on purpose.

**When reporting anything**, the useful things to say are: what you clicked,
what you expected, and what happened instead. A screenshot of the window is
worth more than a description.
