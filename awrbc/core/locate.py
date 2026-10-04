"""Find save data.

Pure path logic — no parsing, no I/O beyond existence checks. Returns candidates
with enough context for ``doctor`` to explain what it found and why.

Three shapes are supported, and none of them is one emulator's business:

* the **Ryujinx layout**, ``bis/user/save/<id>/<profile>/SaveData/maps``, where
  the title id is not in the path at all - every save id has to be looked at
* the **yuzu layout**, ``nand/user/save/<account>/<user>/<title id>/maps``,
  where the title id *is* in the path, so the game's save can be gone to
  directly instead of searched for
* a directory holding a ``maps`` file, which is what a JKSV or Checkpoint dump
  off real hardware looks like

The emulator list is a convenience, not a gate. Anything not on it still works
by pointing the tool at a folder, which is also the answer for portable
installs and for a save copied off a modded console.
"""
import os
from dataclasses import dataclass
from typing import Optional

MAPS_FILE = "maps"
SAVE_SUBPATH = os.path.join("bis", "user", "save")
NAND_SUBPATH = os.path.join("nand", "user", "save")

#: Advance Wars 1+2: Re-Boot Camp, as it appears in a yuzu-layout path.
#: Duplicated from identify.TITLE_ID as a string because this module is path
#: logic and does not parse anything; the test pins them equal.
TITLE_ID_HEX = "0100300012F2A000"

#: Emulators we know where to look for, and which layout each one uses.
#: A name here only saves somebody a trip through a folder picker.
EMULATORS = (
    ("Ryujinx", "Ryujinx", "ryujinx"),
    ("Ryubing", "Ryubing", "ryujinx"),
    ("yuzu", "yuzu", "yuzu"),
    ("Suyu", "suyu", "yuzu"),
    ("Sudachi", "sudachi", "yuzu"),
    ("Citron", "citron", "yuzu"),
)

#: Process names that mean an emulator is up, derived from the same list so
#: the two cannot drift. Used by the guard that refuses to write while the
#: game is running - which looked for "ryujinx" alone and so did nothing at
#: all for anybody on the others. Doing nothing there means writing
#: underneath a loaded game, which is the one failure a backup does not make
#: pleasant. Matching the emulator rather than the title is deliberate and
#: errs toward refusing: see the callers.
EMULATOR_PROCESSES = tuple(folder.lower() for _name, folder, _l in EMULATORS)


@dataclass
class SaveCandidate:
    """One maps file we could operate on."""

    path: str            #: the maps file itself
    profile: Optional[str] = None
    save_id: Optional[str] = None
    source: str = "unknown"   #: "ryujinx" | "yuzu" | "directory" | "explicit"
    size: int = 0
    emulator: Optional[str] = None   #: display name, when we recognised one

    @property
    def label(self) -> str:
        """What to call this save in front of a person.

        The profile is a GUID or a 32-character account id, so it is shortened
        rather than shown - it exists to tell two profiles apart, and its first
        few characters do that as well as all of it does.
        """
        who = self.emulator or self.source
        if self.profile:
            return "%s profile %s" % (who, self.profile[:8])
        return who


def _data_dirs() -> list:
    """Where applications keep their data on this platform."""
    dirs = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(appdata)
    home = os.path.expanduser("~")
    dirs.append(os.path.join(home, ".local", "share"))
    dirs.append(os.path.join(home, ".config"))
    dirs.append(os.path.join(home, "Library", "Application Support"))
    return dirs


def emulator_roots() -> list:
    """``[(display name, root, layout)]`` for every emulator folder present.

    Only folders that actually exist, so the caller does not have to care
    which of these is installed. Portable installs put their data beside the
    executable and will not be here - that is what an explicit path is for.
    """
    found = []
    for base in _data_dirs():
        if not os.path.isdir(base):
            continue
        for name, folder, layout in EMULATORS:
            root = os.path.join(base, folder)
            if os.path.isdir(root):
                found.append((name, root, layout))
    return found


def scan_yuzu_root(root: str, emulator: str = None) -> list:
    """The game's maps file under a yuzu-layout root.

    This layout puts the title id in the path, so there is nothing to search:
    the game's own folder is either there or it is not. That is the whole
    advantage of it over the Ryujinx layout, where the save id is opaque and
    every one has to be opened to find out what game it belongs to.
    """
    base = os.path.join(root, NAND_SUBPATH)
    if not os.path.isdir(base):
        return []
    found = []
    for account in sorted(os.listdir(base)):
        account_dir = os.path.join(base, account)
        if not os.path.isdir(account_dir):
            continue
        for user in sorted(os.listdir(account_dir)):
            maps = os.path.join(account_dir, user, TITLE_ID_HEX, MAPS_FILE)
            if os.path.isfile(maps):
                found.append(SaveCandidate(
                    path=maps, profile=user, save_id=TITLE_ID_HEX,
                    source="yuzu", emulator=emulator,
                    size=os.path.getsize(maps)))
    return found


def scan_ryujinx_root(root: str, emulator: str = None) -> list:
    """Every maps file under one Ryujinx data root."""
    base = os.path.join(root, SAVE_SUBPATH)
    if not os.path.isdir(base):
        return []
    found = []
    for save_id in sorted(os.listdir(base)):
        save_dir = os.path.join(base, save_id)
        if not os.path.isdir(save_dir):
            continue
        for profile in sorted(os.listdir(save_dir)):
            maps = os.path.join(save_dir, profile, "SaveData", MAPS_FILE)
            if os.path.isfile(maps):
                found.append(SaveCandidate(
                    path=maps, profile=profile, save_id=save_id,
                    source="ryujinx", emulator=emulator,
                    size=os.path.getsize(maps)))
    return found


def from_directory(path: str) -> list:
    """Accept a directory holding a maps file, or the maps file itself.

    Covers JKSV dumps from real hardware, which are just the SaveData contents.
    """
    if os.path.isfile(path):
        return [SaveCandidate(path=path, source="explicit",
                              size=os.path.getsize(path))]
    direct = os.path.join(path, MAPS_FILE)
    if os.path.isfile(direct):
        return [SaveCandidate(path=direct, source="directory",
                              size=os.path.getsize(direct))]
    nested = os.path.join(path, "SaveData", MAPS_FILE)
    if os.path.isfile(nested):
        return [SaveCandidate(path=nested, source="directory",
                              size=os.path.getsize(nested))]
    # Not a save folder itself - try it as an emulator data root, either
    # layout, so pointing at a portable install works the same way.
    return scan_ryujinx_root(path) or scan_yuzu_root(path)


def find_saves(save_dir: Optional[str] = None) -> list:
    """All candidates, best first.

    ``save_dir`` overrides discovery entirely — needed for portable Ryujinx
    installs and for hardware dumps in arbitrary locations.
    """
    if save_dir:
        return from_directory(save_dir)
    out = []
    for name, root, layout in emulator_roots():
        if layout == "yuzu":
            out.extend(scan_yuzu_root(root, emulator=name))
        else:
            out.extend(scan_ryujinx_root(root, emulator=name))
    return out


def select(candidates: list, profile: Optional[str] = None) -> Optional[SaveCandidate]:
    """Pick one candidate, optionally by profile. None if the choice is empty."""
    if not candidates:
        return None
    if profile is None:
        return candidates[0]
    for c in candidates:
        if c.profile == profile:
            return c
    return None
