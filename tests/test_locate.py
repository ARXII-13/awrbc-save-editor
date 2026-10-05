"""Finding a save, whatever put it there.

The tool is not an emulator's accessory. A save can come from Ryujinx, from
anything in the yuzu family, or off a modded console through JKSV - and the
one thing it must never do is only work for the emulator it was written on.
"""
import os
import shutil
import tempfile
import unittest
import unittest.mock

from awrbc.core import identify, locate


def touch(path, size=16384):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)
    return path


class TheTitleId(unittest.TestCase):
    def test_both_modules_mean_the_same_game(self):
        """locate spells it as a path component and identify as an integer.
        Two spellings of one fact is a thing that drifts."""
        self.assertEqual(int(locate.TITLE_ID_HEX, 16), identify.TITLE_ID)


class TheRyujinxLayout(unittest.TestCase):
    """The save id says nothing about which game it is, so every one is
    looked at."""

    def test_it_finds_a_save(self):
        with tempfile.TemporaryDirectory() as d:
            maps = touch(os.path.join(d, "bis", "user", "save", "0001",
                                      "profileA", "SaveData", "maps"))
            found = locate.scan_ryujinx_root(d, emulator="Ryujinx")
            self.assertEqual([c.path for c in found], [maps])
            self.assertEqual(found[0].profile, "profileA")
            self.assertEqual(found[0].emulator, "Ryujinx")

    def test_it_finds_every_profile(self):
        with tempfile.TemporaryDirectory() as d:
            for profile in ("alpha", "beta"):
                touch(os.path.join(d, "bis", "user", "save", "0001", profile,
                                   "SaveData", "maps"))
            self.assertEqual(len(locate.scan_ryujinx_root(d)), 2)


class TheYuzuLayout(unittest.TestCase):
    """This one puts the title id in the path, so the game's save is gone to
    directly rather than searched for."""

    def save(self, root, user="user1", title=None):
        return touch(os.path.join(root, "nand", "user", "save",
                                  "0000000000000000", user,
                                  title or locate.TITLE_ID_HEX, "maps"))

    def test_it_finds_our_game(self):
        with tempfile.TemporaryDirectory() as d:
            maps = self.save(d)
            found = locate.scan_yuzu_root(d, emulator="Sudachi")
            self.assertEqual([c.path for c in found], [maps])
            self.assertEqual(found[0].emulator, "Sudachi")
            self.assertEqual(found[0].source, "yuzu")

    def test_it_ignores_another_game(self):
        """The whole point of the title id being in the path."""
        with tempfile.TemporaryDirectory() as d:
            self.save(d, title="0100000000010000")      # Super Mario Odyssey
            self.assertEqual(locate.scan_yuzu_root(d), [])

    def test_it_finds_our_game_beside_others(self):
        with tempfile.TemporaryDirectory() as d:
            self.save(d, title="0100000000010000")
            ours = self.save(d)
            self.assertEqual([c.path for c in locate.scan_yuzu_root(d)], [ours])

    def test_each_user_is_its_own_save(self):
        with tempfile.TemporaryDirectory() as d:
            self.save(d, user="user1")
            self.save(d, user="user2")
            self.assertEqual(len(locate.scan_yuzu_root(d)), 2)

    def test_an_empty_root_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(locate.scan_yuzu_root(d), [])


class WhatItIsCalled(unittest.TestCase):
    def test_the_emulator_is_named_when_we_know_it(self):
        c = locate.SaveCandidate(path="x", profile="abcdef0123456789",
                                 emulator="Ryujinx")
        self.assertIn("Ryujinx", c.label)

    def test_a_long_profile_id_is_shortened(self):
        """It is a GUID. It exists to tell two profiles apart, and its first
        few characters do that as well as all of it."""
        c = locate.SaveCandidate(path="x", profile="abcdef0123456789",
                                 emulator="yuzu")
        self.assertIn("abcdef01", c.label)
        self.assertNotIn("0123456789", c.label)

    def test_an_unrecognised_source_still_says_something(self):
        c = locate.SaveCandidate(path="x", source="directory")
        self.assertEqual(c.label, "directory")


class PointingItSomewhere(unittest.TestCase):
    """What somebody with a console dump, or a portable install, does."""

    def test_a_maps_file_directly(self):
        with tempfile.TemporaryDirectory() as d:
            maps = touch(os.path.join(d, "maps"))
            self.assertEqual([c.path for c in locate.from_directory(maps)],
                             [maps])

    def test_a_jksv_dump(self):
        with tempfile.TemporaryDirectory() as d:
            maps = touch(os.path.join(d, "maps"))
            self.assertEqual([c.path for c in locate.from_directory(d)], [maps])

    def test_a_portable_emulator_folder_either_layout(self):
        with tempfile.TemporaryDirectory() as d:
            maps = touch(os.path.join(d, "nand", "user", "save", "0", "u",
                                      locate.TITLE_ID_HEX, "maps"))
            self.assertEqual([c.path for c in locate.from_directory(d)], [maps])

    def test_a_folder_with_nothing_in_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(locate.from_directory(d), [])


class WhichEmulatorsAreInstalled(unittest.TestCase):
    def test_only_folders_that_exist(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "Ryujinx"))
            os.makedirs(os.path.join(d, "sudachi"))
            with unittest.mock.patch.object(locate, "_data_dirs",
                                            lambda: [d]):
                names = {n for n, _r, _l in locate.emulator_roots()}
            self.assertEqual(names, {"Ryujinx", "Sudachi"})

    def test_each_one_carries_its_layout(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "Ryujinx"))
            os.makedirs(os.path.join(d, "yuzu"))
            with unittest.mock.patch.object(locate, "_data_dirs",
                                            lambda: [d]):
                got = {n: layout for n, _r, layout in locate.emulator_roots()}
            self.assertEqual(got, {"Ryujinx": "ryujinx", "yuzu": "yuzu"})


class DiscoveryUsesTheRightLayoutForEach(unittest.TestCase):
    """The wiring, not the two scanners.

    Tested because a mutant that dropped the yuzu branch from find_saves and
    scanned every root the Ryujinx way passed the whole suite: both scanners
    had their own tests, and nothing checked that discovery called the right
    one.
    """

    def roots(self, d):
        os.makedirs(os.path.join(d, "Ryujinx"), exist_ok=True)
        os.makedirs(os.path.join(d, "yuzu"), exist_ok=True)
        ryu = touch(os.path.join(d, "Ryujinx", "bis", "user", "save", "0001",
                                 "profileA", "SaveData", "maps"))
        yz = touch(os.path.join(d, "yuzu", "nand", "user", "save",
                                "0000000000000000", "user1",
                                locate.TITLE_ID_HEX, "maps"))
        return ryu, yz

    def test_it_finds_saves_in_both(self):
        with tempfile.TemporaryDirectory() as d:
            ryu, yz = self.roots(d)
            with unittest.mock.patch.object(locate, "_data_dirs", lambda: [d]):
                found = locate.find_saves()
            self.assertEqual({c.path for c in found}, {ryu, yz})

    def test_each_is_labelled_with_its_own_emulator(self):
        with tempfile.TemporaryDirectory() as d:
            self.roots(d)
            with unittest.mock.patch.object(locate, "_data_dirs", lambda: [d]):
                found = locate.find_saves()
            self.assertEqual({c.emulator for c in found}, {"Ryujinx", "yuzu"})

    def test_an_explicit_path_still_overrides_everything(self):
        with tempfile.TemporaryDirectory() as d:
            self.roots(d)
            elsewhere = os.path.join(d, "dump")
            maps = touch(os.path.join(elsewhere, "maps"))
            with unittest.mock.patch.object(locate, "_data_dirs", lambda: [d]):
                found = locate.find_saves(elsewhere)
            self.assertEqual([c.path for c in found], [maps])


class KnowingTheGameIsRunning(unittest.TestCase):
    """The guard that refuses to write while a game holds the save.

    It matched "ryujinx" and nothing else, so for anybody on another emulator
    it answered "not running" every time - a guard that was not guarding.
    Writing underneath a loaded game is the one failure a backup does not
    make pleasant, because the game flushes its own copy over the top.
    """

    def test_every_emulator_we_can_find_a_save_for_is_also_watched_for(self):
        """Otherwise the tool knows where your save is and not when it is
        in use, which is the worse half to be missing."""
        for _name, folder, _layout in locate.EMULATORS:
            self.assertIn(folder.lower(), locate.EMULATOR_PROCESSES)

    def test_it_matches_a_process_list(self):
        for name in locate.EMULATOR_PROCESSES:
            listing = "\n".join(["explorer.exe", name + ".exe", "chrome.exe"])
            self.assertTrue(
                any(p in listing for p in locate.EMULATOR_PROCESSES),
                "%s running should be noticed" % name)

    def test_an_unrelated_process_list_matches_nothing(self):
        listing = "\n".join(["explorer.exe", "chrome.exe", "code.exe"])
        self.assertFalse(any(p in listing for p in locate.EMULATOR_PROCESSES))


class TellingTheSavesApart(unittest.TestCase):
    """What each save is called, once the whole list is known.

    A real machine offered four, of which two read "Ryujinx profile 0" and
    two read "Ryujinx profile 1". The save id was the only thing that
    differed and the only thing not shown. Two of them were not saves the
    game reads at all - they sat under `0000000000000001_backup`, a folder
    somebody made by hand, 16 KiB against the real ones' 4 MiB. Importing
    into one would look like it worked and the game would never see it.
    """

    def slot(self, save_id="0000000000000001", profile="0", emulator="Ryujinx"):
        return locate.SaveCandidate(
            path="%s/%s/maps" % (save_id, profile), save_id=save_id,
            profile=profile, source="ryujinx", emulator=emulator)

    def test_a_real_save_id_is_a_slot(self):
        self.assertTrue(self.slot().is_slot)

    def test_a_hand_made_folder_is_not(self):
        self.assertFalse(self.slot(save_id="0000000000000001_backup").is_slot)

    def test_a_short_id_is_not_a_slot_either(self):
        self.assertFalse(self.slot(save_id="0001").is_slot)

    def test_a_copy_says_so(self):
        got = locate.describe([self.slot(save_id="0000000000000001_backup")])
        self.assertIn("(copy)", got[0].display)

    def test_a_real_slot_does_not(self):
        got = locate.describe([self.slot()])
        self.assertNotIn("copy", got[0].display)
        self.assertEqual(got[0].display, "Ryujinx profile 0")

    def test_two_saves_never_read_the_same(self):
        """The bug exactly: same emulator, same profile number, different
        save id."""
        got = locate.describe([self.slot(save_id="0000000000000001"),
                               self.slot(save_id="0000000000000002")])
        self.assertEqual(len({c.display for c in got}), 2,
                         [c.display for c in got])

    def test_the_save_id_is_what_tells_them_apart(self):
        got = locate.describe([self.slot(save_id="0000000000000001"),
                               self.slot(save_id="0000000000000002")])
        self.assertTrue(any("0000000000000002" in c.display for c in got),
                        [c.display for c in got])

    def test_copies_come_after_the_real_saves(self):
        """Not hidden - somebody may genuinely want to open one - but not at
        the top of the list pretending to be the save the game reads."""
        got = locate.describe([
            self.slot(save_id="0000000000000001_backup", profile="0"),
            self.slot(save_id="0000000000000001", profile="0"),
        ])
        self.assertTrue(got[0].is_slot)
        self.assertFalse(got[1].is_slot)

    def test_the_four_from_a_real_machine(self):
        """Two profiles in the live save and two in a folder copy, which is
        what this machine actually has."""
        got = locate.describe([
            self.slot(save_id="0000000000000001", profile="0"),
            self.slot(save_id="0000000000000001", profile="1"),
            self.slot(save_id="0000000000000001_backup", profile="0"),
            self.slot(save_id="0000000000000001_backup", profile="1"),
        ])
        self.assertEqual(len({c.display for c in got}), 4,
                         [c.display for c in got])
        self.assertEqual([c.is_slot for c in got],
                         [True, True, False, False])

    def test_a_hand_picked_folder_is_not_called_a_copy(self):
        """It has no save id because it is not in an emulator's tree at all,
        and that is not evidence of anything."""
        got = locate.describe([locate.SaveCandidate(path="D:/dump/maps",
                                                    source="directory")])
        self.assertNotIn("copy", got[0].display)


class ASaveCopiedOffAConsole(unittest.TestCase):
    """What somebody with a Switch actually has in front of them.

    Measured against a real console over USB. The save sits at
    `Switch\\7: Saves\\Installed games\\Advance Wars 1+2 Re-Boot Camp\\<user>\\
    SaveData`, and holds `gameState` and `gameStateBackup` - and no `maps`,
    because that profile had never made a custom map. The game allocates
    `maps` only when there is one to put in it.

    So "no Advance Wars save data here" is both true and useless: they are
    looking at the right folder.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def console_save(self, with_maps=False, nested=True):
        """A copy of what the console actually holds."""
        root = os.path.join(self.tmp, "ARX II-13")
        where = os.path.join(root, "SaveData") if nested else root
        os.makedirs(where, exist_ok=True)
        for name in ("gameState", "gameStateBackup"):
            with open(os.path.join(where, name), "wb") as fh:
                fh.write(b"\0" * 1015808)
        if with_maps:
            with open(os.path.join(where, "maps"), "wb") as fh:
                fh.write(b"\0" * 16384)
        return root

    def test_a_console_save_without_maps_is_still_a_save_folder(self):
        self.assertTrue(locate.is_save_folder(self.console_save()))

    def test_it_is_recognised_without_the_savedata_wrapper(self):
        """JKSV and Checkpoint dump the contents, not the folder above."""
        self.assertTrue(locate.is_save_folder(
            self.console_save(nested=False)))

    def test_a_folder_of_something_else_is_not(self):
        other = os.path.join(self.tmp, "photos")
        os.makedirs(other)
        with open(os.path.join(other, "holiday.jpg"), "wb") as fh:
            fh.write(b"x")
        self.assertFalse(locate.is_save_folder(other))

    def test_an_empty_folder_is_not(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertFalse(locate.is_save_folder(empty))

    def test_a_path_that_is_not_there_is_not(self):
        self.assertFalse(locate.is_save_folder(
            os.path.join(self.tmp, "nowhere")))
        self.assertFalse(locate.is_save_folder(""))

    def test_once_the_maps_file_exists_it_is_found_normally(self):
        """The whole point of the message: come back when you have one."""
        root = self.console_save(with_maps=True)
        found = locate.from_directory(root)
        self.assertEqual([os.path.basename(c.path) for c in found], ["maps"])


class WhereverTheTitleIdSits(unittest.TestCase):
    """The yuzu family does not agree with itself about the layout.

    yuzu wrote `save/<account>/<user>/<title id>/`. Eden documents
    `save/0000000000000001/<title id>/0/` - title id one level up, a user
    index below it. The first version of this scan hardcoded the yuzu shape
    and would have found nothing at all on Eden.

    Neither shape is assumed now: a maps file with the title id somewhere
    above it is ours.
    """

    OTHER_GAME = "0100000000010000"

    def yuzu_style(self, root, user="user1", title=None):
        return touch(os.path.join(root, "nand", "user", "save",
                                  "0000000000000000", user,
                                  title or locate.TITLE_ID_HEX, "maps"))

    def eden_style(self, root, index="0", title=None):
        return touch(os.path.join(root, "nand", "user", "save",
                                  "0000000000000001",
                                  title or locate.TITLE_ID_HEX, index, "maps"))

    def test_the_yuzu_shape(self):
        with tempfile.TemporaryDirectory() as d:
            maps = self.yuzu_style(d)
            self.assertEqual([c.path for c in locate.scan_yuzu_root(d)], [maps])

    def test_the_eden_shape(self):
        with tempfile.TemporaryDirectory() as d:
            maps = self.eden_style(d)
            self.assertEqual([c.path for c in locate.scan_yuzu_root(d)], [maps])

    def test_both_at_once(self):
        """Somebody with two emulators pointed at one data folder is not a
        case to be clever about, but it should not lose either."""
        with tempfile.TemporaryDirectory() as d:
            a = self.yuzu_style(d)
            b = self.eden_style(d)
            self.assertEqual(sorted(c.path for c in locate.scan_yuzu_root(d)),
                             sorted([a, b]))

    def test_another_game_is_still_ignored_in_either_shape(self):
        with tempfile.TemporaryDirectory() as d:
            self.yuzu_style(d, title=self.OTHER_GAME)
            self.eden_style(d, title=self.OTHER_GAME)
            self.assertEqual(locate.scan_yuzu_root(d), [])

    def test_ours_is_found_beside_another_game(self):
        with tempfile.TemporaryDirectory() as d:
            self.eden_style(d, title=self.OTHER_GAME)
            ours = self.eden_style(d)
            self.assertEqual([c.path for c in locate.scan_yuzu_root(d)], [ours])

    def test_two_users_stay_apart(self):
        with tempfile.TemporaryDirectory() as d:
            self.eden_style(d, index="0")
            self.eden_style(d, index="1")
            got = locate.scan_yuzu_root(d)
            self.assertEqual(len(got), 2)
            self.assertEqual(sorted(c.profile for c in got), ["0", "1"])

    def test_the_profile_tells_two_of_the_same_shape_apart(self):
        with tempfile.TemporaryDirectory() as d:
            self.yuzu_style(d, user="alice")
            self.yuzu_style(d, user="bob")
            got = locate.describe(locate.scan_yuzu_root(d))
            self.assertEqual(len({c.display for c in got}), 2,
                             [c.display for c in got])

    def test_a_lowercase_title_id_is_the_same_game(self):
        with tempfile.TemporaryDirectory() as d:
            maps = self.eden_style(d, title=locate.TITLE_ID_HEX.lower())
            self.assertEqual([c.path for c in locate.scan_yuzu_root(d)], [maps])

    def test_eden_is_one_of_the_emulators_we_look_for(self):
        names = {n for n, _folder, _layout in locate.EMULATORS}
        self.assertIn("Eden", names)
        for name, _folder, layout in locate.EMULATORS:
            if name == "Eden":
                self.assertEqual(layout, "yuzu")


if __name__ == "__main__":
    unittest.main()
