# PyInstaller spec for the desktop app.
#
# --onedir in a zip: unzip and run, no installer (decision #55). A --onefile
# build unpacks itself to a temp directory on every launch, which is slower
# and is what antivirus software notices; a folder is also something a person
# can look inside, which matters for a tool that writes to their save.
#
#     python tools/build_desktop.py
#
# Not run by CI. It needs a machine of the target platform and PyInstaller,
# and the thing it produces is a release artifact rather than a test.

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.getcwd())
WEB = os.path.join(ROOT, "web")

if not os.path.exists(os.path.join(WEB, "save.html")):
    raise SystemExit("run this from the repository root; no web/save.html "
                     "under %s" % ROOT)

# What ships is decided in tools/desktop_payload.py, which a test reads too.
# In this repository the map editor is not merely excluded, it is absent -
# but the list stays, because it is also what keeps editor code from being
# copied back in later.
sys.path.insert(0, os.path.join(ROOT, "tools"))
from desktop_payload import payload                       # noqa: E402

web_files = payload(WEB)

# The format description that awrbc/core/create.py reads to make a maps file
# where the game has not made one. A frozen build has no source tree to find
# it in, and its absence would only show up on the one machine that needed
# it - somebody opening a console save with no custom maps yet.
TABLE = os.path.join(ROOT, "awrbc", "core", "typetable.json")
if not os.path.exists(TABLE):
    raise SystemExit("the type table is missing: %s" % TABLE)
web_files = web_files + [(TABLE, os.path.join("awrbc", "core"))]

a = Analysis(
    # tools/desktop_entry.py, not awrbc/desktop/__main__.py - see that file.
    # Pointed straight at __main__.py, PyInstaller runs it as `__main__` with
    # no parent package and its relative imports fail on the first line.
    [os.path.join(ROOT, "tools", "desktop_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=web_files,
    # pywebview loads its platform backend by name, so static analysis does
    # not see it and the window never opens.
    hiddenimports=collect_submodules("webview"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PIL", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="awrbc",
    debug=False,
    strip=False,
    upx=False,
    # A console window beside the app reads as a fault. The cost is that
    # stderr goes nowhere, so `report()` in __main__ puts startup failures -
    # the WebView2 one above all - into a message box as well.
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="awrbc",
)
