"""Starting the desktop app.

None of this is about maps. It is about the ways a packaged build fails where
a source checkout does not, all of which are invisible until somebody
double-clicks the thing:

Finding its own files. Frozen, `web/` is wherever PyInstaller unpacked it, not
three directories above this source file.

Saying so when it cannot start. The packaged build has `console=False`, so
stderr goes nowhere - a diagnostic that exists precisely so a person can act
on it would be written into the void.

Saying the *right* thing. v0.1.0-rc.1 blamed a missing WebView2 runtime for
every failure to open a window. The real cause was that Windows marks files
extracted from a downloaded zip as Internet-zone and .NET then refuses to load
the bundled assembly - so the first person to run it was sent to install a
runtime they already had.

pywebview is an optional dependency and is not installed on CI, so it is faked
here rather than imported.
"""
import builtins
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from awrbc.desktop import __main__ as app


@contextlib.contextmanager
def quiet():
    """These paths write to stdout and stderr on purpose; the suite does not
    need to read it back."""
    with contextlib.redirect_stderr(io.StringIO()), \
            contextlib.redirect_stdout(io.StringIO()):
        yield


class WhereTheEditorIs(unittest.TestCase):
    def setUp(self):
        self.had = getattr(sys, "_MEIPASS", None)
        self.addCleanup(self.restore)

    def restore(self):
        if self.had is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = self.had

    def test_from_a_checkout_it_is_web_at_the_repository_root(self):
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
        got = app.web_dir()
        self.assertTrue(got.endswith(os.path.join("", "web")) or
                        got.endswith("web"), got)
        self.assertTrue(os.path.exists(os.path.join(got, app.PAGE)),
                        "the checkout's own page should be there: %s" % got)

    def test_packaged_it_is_wherever_pyinstaller_unpacked_it(self):
        sys._MEIPASS = os.path.join("C:", os.sep, "somewhere", "_internal")
        self.assertEqual(app.web_dir(),
                         os.path.join(sys._MEIPASS, "web"))


class FindingThePage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_it_returns_the_save_editors_own_page(self):
        """Not index.html. That is the map editor, and loading it is how the
        first packaged build came to contain archive submission."""
        index = os.path.join(self.tmp, app.PAGE)
        with open(index, "w", encoding="utf-8") as fh:
            fh.write("<!doctype html>")
        self.assertEqual(app.entry_point(self.tmp), index)

    def test_a_build_with_no_editor_in_it_says_so(self):
        """Rather than opening a window onto nothing."""
        with self.assertRaises(SystemExit) as caught:
            app.entry_point(self.tmp)
        self.assertIn("cannot find the editor", str(caught.exception))
        self.assertIn(app.PAGE, str(caught.exception))


class SayingSoWithoutAConsole(unittest.TestCase):
    """`report` is what stands between a silent failure and a diagnosis."""

    def test_it_writes_to_the_box_it_is_given(self):
        shown = []
        with quiet():
            app.report("something went wrong\n", box=shown.append)
        self.assertEqual(shown, ["something went wrong\n"])

    def test_a_box_that_itself_fails_does_not_take_the_app_down(self):
        """Reporting a failure must not become a second failure."""
        def broken(_):
            raise RuntimeError("no window manager")
        with quiet():
            app.report("the original problem\n", box=broken)


class ZoneMarkedFiles(unittest.TestCase):
    """Windows stamps a Zone.Identifier stream on anything extracted from a
    downloaded zip, and .NET will not load an assembly carrying one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name, zone=None):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(b"not really a dll")
        if zone is not None:
            # The stream is written by opening `file:Zone.Identifier`, which
            # is how Explorer marks a download and how this is detected.
            with open(path + ":Zone.Identifier", "wb") as fh:
                fh.write(b"[ZoneTransfer]\r\nZoneId=%d\r\n" % zone)
        return path

    @unittest.skipUnless(sys.platform == "win32",
                         "alternate data streams are an NTFS thing")
    def test_it_finds_a_marked_assembly(self):
        self.write("clean.dll")
        marked = self.write("downloaded.dll", zone=3)
        count, example = app.blocked_files(self.tmp)
        self.assertEqual((count, example), (1, marked))

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_local_zone_mark_is_not_a_problem(self):
        """Zone 1 is the local intranet and loads fine; only 3 is the
        internet. Reporting every stream would cry wolf."""
        self.write("intranet.dll", zone=1)
        self.assertEqual(app.blocked_files(self.tmp)[0], 0)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_it_ignores_files_dotnet_would_never_load(self):
        self.write("notes.txt", zone=3)
        self.assertEqual(app.blocked_files(self.tmp)[0], 0)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_it_names_the_assembly_dotnet_actually_refuses(self):
        """A bundle has dozens of api-ms-win-core-*.dll in it and none of them
        explain anything. The first dialog listed three of those and buried
        the one file a reader could act on."""
        self.write("api-ms-win-core-console-l1-1-0.dll", zone=3)
        wanted = self.write("Python.Runtime.dll", zone=3)
        self.write("api-ms-win-core-debug-l1-1-0.dll", zone=3)

        count, example = app.blocked_files(self.tmp)
        self.assertEqual(count, 3)
        self.assertEqual(example, wanted)

    def test_nothing_to_find_is_not_an_error(self):
        self.assertEqual(app.blocked_files(self.tmp), (0, ""))
        self.assertEqual(app.blocked_files(os.path.join(self.tmp, "gone")),
                         (0, ""))
        self.assertEqual(app.blocked_files(""), (0, ""))


class WhatItSaysWhenNoWindowOpens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_an_unexplained_failure_still_suggests_webview2(self):
        said = app.why_no_window(RuntimeError("no idea"), self.tmp)
        self.assertIn("WebView2", said)
        self.assertIn("no idea", said, "the real error has to be in there")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_zone_marked_bundle_is_named_as_the_cause(self):
        path = os.path.join(self.tmp, "Python.Runtime.dll")
        with open(path, "wb") as fh:
            fh.write(b"x")
        with open(path + ":Zone.Identifier", "wb") as fh:
            fh.write(b"[ZoneTransfer]\r\nZoneId=3\r\n")

        said = app.why_no_window(RuntimeError("Failed to resolve"), self.tmp)
        self.assertNotIn("WebView2", said,
                         "blaming the runtime here is what sent somebody to "
                         "install one they already had")
        self.assertIn("Unblock-File", said, "it has to say how to fix it")
        self.assertIn("Python.Runtime.dll", said, "and which files")


class FakeWebview:
    """Enough of pywebview to let main() reach its check."""
    def __init__(self):
        self.started = False

    def create_window(self, *args, **kwargs):
        return object()

    def start(self, **kwargs):
        self.started = True


class Starting(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWebview()
        self.had = sys.modules.get("webview")
        sys.modules["webview"] = self.fake
        self.addCleanup(self.restore)

    def restore(self):
        if self.had is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = self.had

    def test_check_starts_everything_except_the_window(self):
        """What a packaged build is verified with. It has to exercise the
        imports and the file lookup, or it checks nothing worth checking."""
        with quiet():
            self.assertEqual(app.main(["--check"]), 0)
        self.assertFalse(self.fake.started,
                         "--check must not open a window")

    def test_without_the_flag_it_opens_one(self):
        with quiet():
            self.assertEqual(app.main([]), 0)
        self.assertTrue(self.fake.started)

    def test_a_missing_editor_is_reported_rather_than_raised(self):
        """SystemExit out of a packaged app is a window that never appears."""
        shown = []
        where = app.WEB
        app.WEB = os.path.join(tempfile.mkdtemp(), "nothing-here")
        self.addCleanup(setattr, app, "WEB", where)

        # entry_point's default was bound at import, so point the module's
        # own lookup at the empty folder the way main() reaches it.
        original = app.entry_point
        app.entry_point = lambda folder=app.WEB: original(folder)
        self.addCleanup(setattr, app, "entry_point", original)

        with quiet():
            self.assertEqual(app.main(["--check"], box=shown.append), 1)
        self.assertTrue(shown, "it has to say something")
        self.assertIn("cannot find the editor", shown[0])


class WhenPywebviewIsMissing(unittest.TestCase):
    def test_it_names_what_to_install(self):
        import builtins
        real = builtins.__import__

        def no_webview(name, *args, **kwargs):
            if name == "webview":
                raise ImportError("no module named webview")
            return real(name, *args, **kwargs)

        builtins.__import__ = no_webview
        self.addCleanup(setattr, builtins, "__import__", real)

        shown = []
        with quiet():
            self.assertEqual(app.main([], box=shown.append), 1)
        self.assertIn("pywebview", shown[0])


if __name__ == "__main__":
    unittest.main()


class UnblockingItself(unittest.TestCase):
    """The app takes the Internet-zone mark off its own files at startup.

    Without this, a downloaded zip produces a dialog asking the person to
    paste a PowerShell command before a map editor will open, which is a
    thing almost nobody will do.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name, zone=None):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(b"not really a dll")
        if zone is not None:
            with open(path + ":Zone.Identifier", "wb") as fh:
                fh.write(b"[ZoneTransfer]\r\nZoneId=%d\r\n" % zone)
        return path

    def marked(self, path):
        try:
            with open(path + ":Zone.Identifier", "rb") as fh:
                return b"ZoneId=3" in fh.read(512)
        except OSError:
            return False

    @unittest.skipUnless(sys.platform == "win32",
                         "alternate data streams are an NTFS thing")
    def test_it_clears_the_mark(self):
        path = self.write("Python.Runtime.dll", zone=3)
        self.assertTrue(self.marked(path), "the test set it up wrong")

        cleared, refused = app.unblock_self(self.tmp)

        self.assertEqual((cleared, refused), (1, 0))
        self.assertFalse(self.marked(path))
        self.assertEqual(app.blocked_files(self.tmp)[0], 0,
                         "the check that produces the dialog should now "
                         "find nothing")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_the_file_itself_survives(self):
        """Clearing the mark must not disturb what it was attached to."""
        path = self.write("Python.Runtime.dll", zone=3)
        app.unblock_self(self.tmp)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"not really a dll")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_it_leaves_alone_what_dotnet_would_not_refuse(self):
        """Only the mark that actually blocks anything. A zone-1 file loads
        fine, and stripping marks for their own sake is not this function's
        business."""
        intranet = self.write("intranet.dll", zone=1)
        app.unblock_self(self.tmp)
        with open(intranet + ":Zone.Identifier", "rb") as fh:
            self.assertIn(b"ZoneId=1", fh.read())

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_it_ignores_files_dotnet_would_never_load(self):
        notes = self.write("notes.txt", zone=3)
        self.assertEqual(app.unblock_self(self.tmp), (0, 0))
        self.assertTrue(self.marked(notes))

    def test_nothing_to_do_is_not_an_error(self):
        self.write("clean.dll")
        self.assertEqual(app.unblock_self(self.tmp), (0, 0))
        self.assertEqual(app.unblock_self(os.path.join(self.tmp, "gone")),
                         (0, 0))
        self.assertEqual(app.unblock_self(""), (0, 0))

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_file_it_cannot_write_is_counted_not_raised(self):
        """The read-only install case. It has to survive it and say so,
        because that is the one time the dialog still has to appear."""
        self.write("Python.Runtime.dll", zone=3)
        real_remove = os.remove

        def refuse(path, *a, **kw):
            if path.endswith(":Zone.Identifier"):
                raise PermissionError("read-only")
            return real_remove(path, *a, **kw)

        with mock.patch("os.remove", refuse):
            cleared, refused = app.unblock_self(self.tmp)
        self.assertEqual((cleared, refused), (0, 1))


class UnblockingHappensBeforeDotNet(unittest.TestCase):
    """Order is the whole point.

    Once .NET has refused an assembly, clearing the mark afterwards does not
    help this process - it has to happen before anything imports the backend.
    """

    def test_it_runs_before_webview_is_imported(self):
        order = []

        def watched(folder):
            order.append("unblock")
            return (0, 0)

        real_import = builtins.__import__

        def noting(name, *a, **kw):
            if name == "webview":
                order.append("import webview")
                raise ImportError("not here")
            return real_import(name, *a, **kw)

        with mock.patch.object(app, "unblock_self", watched), \
                mock.patch.object(builtins, "__import__", noting), quiet():
            app.main([], box=lambda _: None)

        self.assertEqual(order, ["unblock", "import webview"],
                         "clearing the mark after .NET has already refused "
                         "an assembly is too late for this process")


class TheAppsOwnExecutable(unittest.TestCase):
    """A marked .exe is not a reason to tell anybody anything.

    Found on a real machine: after the bundle unblocked itself, 35 of 36
    files were clear and one was not - awrbc.exe, because Windows will not
    release the stream of a running executable. Its mark never blocked
    anything, .NET refuses assemblies. But it left blocked_files answering 1
    forever, so the next failure from any cause at all would have been
    diagnosed as a zone mark.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name, zone=3):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(b"x")
        with open(path + ":Zone.Identifier", "wb") as fh:
            fh.write(b"[ZoneTransfer]\r\nZoneId=%d\r\n" % zone)
        return path

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_marked_exe_is_not_counted_as_blocking(self):
        self.write("awrbc.exe")
        self.assertEqual(app.blocked_files(self.tmp)[0], 0)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_it_is_not_reported_as_a_file_we_failed_to_clear(self):
        """Otherwise every single run ends with refused=1."""
        self.write("awrbc.exe")
        self.assertEqual(app.unblock_self(self.tmp), (0, 0))

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_marked_exe_alone_does_not_produce_the_zone_dialog(self):
        self.write("awrbc.exe")
        said = app.why_no_window(RuntimeError("something else entirely"),
                                 self.tmp)
        self.assertNotIn("Unblock-File", said,
                         "a running exe keeps its mark on every machine; "
                         "blaming it would send everybody to a fix that "
                         "changes nothing")
        self.assertIn("something else entirely", said)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_a_marked_assembly_beside_it_still_is(self):
        self.write("awrbc.exe")
        self.write("Python.Runtime.dll")
        self.assertEqual(app.blocked_files(self.tmp)[0], 1)
        self.assertIn("Unblock-File", app.why_no_window(RuntimeError("x"),
                                                        self.tmp))
