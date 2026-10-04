"""What the desktop app exposes to the page.

This is the save-access half of the tool, and it exists only here. The hosted
build of the editor has no object like this and no code path to a file system
(decision #52) - a browser *cannot* read your save, rather than promising not
to. Which build you are running decides what you can touch.

Everything returns plain data and never raises across the bridge: pywebview
turns a Python exception into an unhelpful rejection in the page, so every
call answers ``{"ok": False, "error": ...}`` instead. The UI gets something it
can show a person.

No rendering happens here. Maps come back as the same documents the editor
already draws, so the picture in the save list is drawn by `render.js` with
whatever sprite pack is loaded - one renderer, as everywhere else.
"""
import os
import traceback

from ..core import backup, derive, locate, savefile, schema, validate
from ..core.errors import AwrbcError


def _fail(exc):
    """A failure the page can show, rather than a rejected promise."""
    if isinstance(exc, AwrbcError):
        return {"ok": False, "error": str(exc), "kind": type(exc).__name__}
    # Unexpected: keep the detail for a log, give the page something plain.
    traceback.print_exc()
    return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
            "kind": "Unexpected"}


def _guard(fn):
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:                        # noqa: BLE001
            return _fail(exc)
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


class SaveApi:
    """The bridge object. Every public method is callable from the page."""

    def __init__(self, game_running=None):
        # Injected so a test does not have to own a process table, and so the
        # check can be stubbed where a developer has the emulator open.
        self._game_running = game_running or (lambda: False)
        self._path = None
        # Set once the window exists, because the file dialog belongs to it.
        # Absent in tests and in --check, where there is no window and
        # browsing is not what is being exercised.
        self._window = None

    def use_window(self, window):
        """Hand over the window, so a file dialog has something to sit on."""
        self._window = window

    # --- finding a save --------------------------------------------------

    @_guard
    def find_saves(self, save_dir=None):
        """Every save this machine has, most likely first."""
        found = []
        for c in locate.find_saves(save_dir or None):
            found.append({
                "path": c.path, "profile": c.profile, "saveId": c.save_id,
                "source": c.source, "size": c.size,
                # describe() set this and made it unique in the list;
                # `label` alone repeated itself across profiles.
                "label": c.display or c.label,
                "isSlot": c.is_slot,
            })
        return {"ok": True, "saves": found}

    @_guard
    def browse_for_save(self, kind="folder"):
        """Let somebody point at a save themselves.

        The emulator list covers the common case and cannot cover the other
        one: a save off a modded console arrives by whichever route its owner
        chose - FTP, SD card, JKSV over USB - and lands wherever they put it.
        Guessing at that is hopeless, so this asks.

        A folder or the file itself, because both are things people end up
        holding. `locate.from_directory` already accepts either, including a
        folder that turns out to be a whole emulator data root.
        """
        if self._window is None:
            raise AwrbcError("there is no window to open a file dialog on")

        import webview
        dialog = (webview.FOLDER_DIALOG if kind == "folder"
                  else webview.OPEN_DIALOG)
        picked = self._window.create_file_dialog(dialog, allow_multiple=False)
        if not picked:
            return {"ok": True, "cancelled": True, "saves": []}

        chosen = picked[0] if isinstance(picked, (list, tuple)) else picked

        # A Switch connected by USB appears in Explorer as a portable device
        # rather than a drive. Its items carry shell ids, not paths, and
        # nothing that opens a file can use one. Worth saying plainly: "no
        # save data here" is a baffling answer about a folder you can see.
        if not os.path.exists(chosen):
            return {"ok": False, "kind": "NotAFolder",
                    "error": "%s is not a folder this tool can read.\n\n"
                             "A Switch connected by USB is a portable "
                             "device, not a drive, and files on it cannot be "
                             "opened directly. Copy the save folder to your "
                             "PC first, then choose the copy." % chosen}

        found = locate.describe(locate.from_directory(chosen))
        if not found:
            if locate.is_save_folder(chosen):
                return {"ok": False, "kind": "NoMapsYet",
                        "error": "%s is an Advance Wars save, but the game "
                                 "has not made a maps file in it yet.\n\n"
                                 "That file appears once the save holds a "
                                 "custom map. Make one in the Design Room on "
                                 "the console, save it, then copy the folder "
                                 "across again." % chosen}
            return {"ok": False, "kind": "SaveNotFound",
                    "error": "no Advance Wars save data in %s.\n\nPick the "
                             "folder holding the 'maps' file, or that file "
                             "itself." % chosen}
        return {"ok": True, "cancelled": False, "saves": [
            {"path": c.path, "profile": c.profile, "saveId": c.save_id,
             "source": c.source, "size": c.size,
             "label": c.display or c.label, "isSlot": c.is_slot}
            for c in found]}

    @_guard
    def open_save(self, path):
        """Read a save and describe every map in it.

        The documents come back whole, so the page can draw each map with the
        same renderer it uses for editing. A save holds a handful of maps, so
        there is no paging to be clever about.
        """
        doc = savefile.read(path)
        self._path = path

        maps = []
        for index, m in enumerate(doc.maps):
            built = schema.build_document(m, save_version=doc.save_version)
            report = validate.check(m)
            maps.append({
                "index": index,
                "slot": m.slot,
                "name": m.name,
                "document": built,
                "id": built["id"],
                "derived": derive.derived_block(m),
                "playable": m.is_playable,
                "warnings": [vars(f) for f in report.warnings],
            })

        return {"ok": True, "path": path, "saveVersion": doc.save_version,
                "size": os.path.getsize(path), "maps": maps}

    # --- changing it -----------------------------------------------------

    def _refuse_if_running(self):
        if self._game_running():
            raise AwrbcError(
                "an emulator is running. A loaded game keeps its own copy "
                "of the save and writes it back over anything put underneath "
                "it, so close the game and let it shut down properly first.")

    @_guard
    def apply_changes(self, path, removes=None, adds=None):
        """Every pending change, in one write.

        The only path that modifies a save; `import_map` and `remove_map` are
        this with a list of one. A tool that wrote once per map took a backup
        per map too, so clearing out five of them left five snapshots and five
        chances for the game to be reopened midway.

        Order matters and is not the caller's problem. Removals happen first
        and from the back, because every one of them shifts the indices after
        it - taking 1 then 3 from a four-map save otherwise deletes 1 and the
        map that used to be 4.

        Nothing is written unless every addition is playable. A batch that
        half-applied would leave somebody reading a success message with no
        way to know which half, and the save is the one thing here that
        cannot be re-derived.
        """
        self._refuse_if_running()
        removes = sorted(set(removes or []), reverse=True)
        adds = list(adds or [])
        if not removes and not adds:
            return {"ok": True, "added": [], "removed": [], "bytes": 0,
                    "backup": None, "warnings": [], "nothing": True}

        doc = savefile.read(path)

        for index in removes:
            if not 0 <= index < len(doc.maps):
                raise AwrbcError("no map at %d; the save holds %d"
                                 % (index, len(doc.maps)))

        # Validated before anything is touched, so a bad map in the queue
        # stops the batch rather than landing half of it.
        prepared, warnings = [], []
        for entry in adds:
            document = entry.get("document") if isinstance(entry, dict) else entry
            name = entry.get("name") if isinstance(entry, dict) else None
            m = schema.from_json(document)
            report = validate.check(m)
            if report.errors:
                return {"ok": False,
                        "error": "%s is not playable" % (
                            name or m.name or "that map"),
                        "kind": "ValidationFailed",
                        "findings": [vars(f) for f in report.errors]}
            warnings.extend(vars(f) for f in report.warnings)
            prepared.append((m, name))

        snap = backup.snapshot(path)
        taken = [doc.maps[i].name for i in removes]
        for index in removes:
            savefile.remove_map(doc, index)
        slots = [savefile.add_map(doc, m, name=name) for m, name in prepared]
        written = savefile.write(doc, path)

        return {"ok": True, "added": slots, "removed": taken,
                "bytes": written, "backup": snap.path, "warnings": warnings}

    @_guard
    def import_map(self, path, document, name=None):
        """Add one map. The batch path with a list of one."""
        got = self.apply_changes(path, [], [{"document": document,
                                             "name": name}])
        if got.get("ok"):
            got["slot"] = (got["added"] or [None])[0]
        return got

    @_guard
    def remove_map(self, path, index):
        """Remove one map. The batch path with a list of one."""
        got = self.apply_changes(path, [index], [])
        if got.get("ok"):
            got["removed"] = (got["removed"] or [None])[0]
        return got

    # --- backups ---------------------------------------------------------

    @_guard
    def snapshots(self, path):
        return {"ok": True, "snapshots": [
            {"name": s.name, "size": s.size, "taken": s.taken, "path": s.path}
            for s in backup.snapshots(path)]}

    @_guard
    def backup_now(self, path):
        snap = backup.snapshot(path)
        return {"ok": True, "backup": snap.path, "name": snap.name}

    @_guard
    def restore(self, path, snapshot_name):
        self._refuse_if_running()
        match = [s for s in backup.snapshots(path)
                 if s.name == snapshot_name or s.taken == snapshot_name]
        if not match:
            raise AwrbcError("no snapshot called %r" % snapshot_name)
        # The current state is kept too, so restoring is itself undoable.
        backup.snapshot(path)
        n = backup.restore(match[0].path, path)
        return {"ok": True, "restored": match[0].name, "bytes": n}

