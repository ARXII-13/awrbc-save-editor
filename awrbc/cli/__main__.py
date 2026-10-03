"""Command line entry point.

All presentation lives here. core returns values and raises typed errors; this
module is the only place that formats text, picks exit codes, or writes to a
stream.
"""
import argparse
import json
import os
import re
import subprocess
import sys

from ..core import (backup, identify, locate, savefile, schema, validate)
from ..core.errors import (AwrbcError, MapNotFound, SaveInUse,
                           SaveNotFound, ValidationFailed)

EXIT_OK = 0
EXIT_USAGE = 1


def _resolve(args):
    """Pick the save to operate on, or raise SaveNotFound with a useful message."""
    candidates = locate.find_saves(args.save_dir)
    if not candidates:
        where = args.save_dir or "the default Ryujinx locations"
        raise SaveNotFound(
            "no save data found in %s.\n"
            "Pass --save-dir pointing at a Ryujinx data folder, a JKSV dump, or "
            "a maps file directly." % where)
    chosen = locate.select(candidates, args.profile)
    if chosen is None:
        have = ", ".join(str(c.profile) for c in candidates)
        raise SaveNotFound("no profile %r; found: %s" % (args.profile, have))
    return chosen, candidates


def _game_running():
    """Is the title running? It flushes its own copy over external writes.

    Only a loaded game holds the save; the emulator sitting open with no title
    is fine, so this must not refuse merely because Ryujinx is on screen.

    Asks the platform's own process list. This used to shell out to `tasklist`
    unconditionally, which meant that on macOS and Linux the command did not
    exist, the exception was swallowed, and the check silently answered "not
    running" every time - turning a guard against the emulator overwriting our
    write into a no-op on two of the three platforms.

    It still answers False when it cannot tell, because refusing to write
    because `ps` is missing would be worse than the risk. That is a deliberate
    fail-open, not an oversight.
    """
    if os.environ.get("AWRBC_SKIP_PROCESS_CHECK"):
        return False
    if sys.platform == "win32":
        argv = ["tasklist"]
    else:
        argv = ["ps", "-A", "-o", "comm="]
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=10).stdout.lower()
    except Exception:                               # noqa: BLE001
        return False
    return "ryujinx" in out


def cmd_doctor(args, out):
    candidates = locate.find_saves(args.save_dir)
    result = {"candidates": [], "ok": False}
    if not candidates:
        where = args.save_dir or "default Ryujinx locations"
        if args.json:
            json.dump(result, out, indent=2)
            out.write("\n")
        else:
            out.write("No save data found in %s.\n\n" % where)
            out.write("Looked in:\n")
            for r in locate.ryujinx_roots():
                out.write("  %s\n" % r)
            out.write("\nUse --save-dir to point at a Ryujinx folder, a JKSV "
                      "dump, or a maps file.\n")
        return SaveNotFound.exit_code

    for c in candidates:
        row = {"path": c.path, "profile": c.profile, "source": c.source,
               "size": c.size, "readable": False}
        try:
            doc = savefile.read(c.path)
            row.update(readable=True, save_version=doc.save_version,
                       maps=len(doc.maps),
                       titleId=None if doc.title_id is None
                       else "%016X" % doc.title_id,
                       game=identify.TITLE_NAME)
        except AwrbcError as exc:
            row["error"] = str(exc)
        result["candidates"].append(row)
    result["ok"] = any(r["readable"] for r in result["candidates"])

    if args.json:
        json.dump(result, out, indent=2)
        out.write("\n")
        return EXIT_OK if result["ok"] else SaveNotFound.exit_code

    out.write("Found %d save%s:\n\n" % (len(candidates),
                                        "" if len(candidates) == 1 else "s"))
    for r in result["candidates"]:
        out.write("  %s\n" % r["path"])
        out.write("    source   %s%s\n" % (
            r["source"],
            "" if r["profile"] is None else ", profile %s" % r["profile"]))
        out.write("    size     %s bytes\n" % format(r["size"], ","))
        if r["readable"]:
            out.write("    game     %s\n" % r["game"])
            out.write("    title id %s\n"
                      % (r["titleId"] or "not present (bare SaveData dump)"))
            out.write("    version  %s (supported)\n" % r["save_version"])
            out.write("    maps     %d\n" % r["maps"])
        else:
            out.write("    ERROR    %s\n" % r.get("error"))
        out.write("\n")
    return EXIT_OK if result["ok"] else SaveNotFound.exit_code


def cmd_list(args, out):
    chosen, _ = _resolve(args)
    doc = savefile.read(chosen.path)

    rows = []
    for i, m in enumerate(doc.maps):
        counts = m.per_team()
        rows.append({
            "index": i, "name": m.name, "slot": m.slot, "creator": m.creator,
            "cols": m.cols, "rows": m.rows, "fog": m.fog,
            "teams": m.teams, "playable": m.is_playable,
            "units": sum(c.units for c in counts.values()),
            "perTeam": {str(t): vars(c) for t, c in counts.items()},
        })

    if args.json:
        json.dump({"path": chosen.path, "saveVersion": doc.save_version,
                   "maps": rows}, out, indent=2)
        out.write("\n")
        return EXIT_OK

    if not rows:
        out.write("No custom maps in %s\n" % chosen.path)
        return EXIT_OK

    out.write("%s  (%s)\n\n" % (chosen.path, chosen.label))
    out.write("  #  %-24s %-7s %-6s %-8s %s\n"
              % ("name", "size", "teams", "units", "playable"))
    for r in rows:
        out.write("  %-2d %-24s %-7s %-6s %-8s %s\n" % (
            r["index"], r["name"][:24], "%dx%d" % (r["cols"], r["rows"]),
            len(r["teams"]), r["units"], "yes" if r["playable"] else "NO"))
    out.write("\n%d map%s\n" % (len(rows), "" if len(rows) == 1 else "s"))
    return EXIT_OK


def _safe_name(text, fallback):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (text or "").strip()).strip("-")
    return slug[:60] or fallback


def cmd_export(args, out):
    chosen, _ = _resolve(args)
    doc = savefile.read(chosen.path)

    if args.all:
        targets = list(enumerate(doc.maps))
    else:
        if args.index is None:
            raise MapNotFound("give a map index, or --all (see `awrbc list`)")
        if not 0 <= args.index < len(doc.maps):
            raise MapNotFound("no map at index %d; the save holds %d"
                              % (args.index, len(doc.maps)))
        targets = [(args.index, doc.maps[args.index])]

    written = []
    for index, m in targets:
        built = schema.build_document(
            m, author=args.author, keep_creator=args.keep_creator,
            save_version=doc.save_version)
        report = validate.check(m)

        if args.all:
            directory = args.output or "."
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, "%s-%s.json"
                                % (_safe_name(m.name, "map"), built["id"][:8]))
        elif args.output:
            path = args.output
        else:
            path = "%s-%s.json" % (_safe_name(m.name, "map"), built["id"][:8])

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(built, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        written.append({"index": index, "name": m.name, "id": built["id"],
                        "path": path, "playable": m.is_playable,
                        "findings": [vars(f) for f in report.findings]})

    if args.json:
        json.dump({"exported": written}, out, indent=2)
        out.write("\n")
        return EXIT_OK

    for w in written:
        out.write("%s\n" % w["path"])
        out.write("  %-24s id %s\n" % (w["name"][:24], w["id"]))
        for f in w["findings"]:
            out.write("  %-7s %-18s %s\n"
                      % (f["severity"], f["code"], f["message"]))
    out.write("\nexported %d map%s\n"
              % (len(written), "" if len(written) == 1 else "s"))
    # Export is advisory: a work-in-progress map still exports.
    return EXIT_OK


def _import_source(args, out):
    """The map being imported: a file on disk.

    This tool reads a save and writes a save. Where a map came from - the
    editor, a friend, an archive - happened before it got here, and fetching
    one by name is the other tool's job.
    """
    # Whatever the editor produced, bundle or bare JSON. A bundle's preview is
    # ignored - a save has no use for it - but refusing the file over it would
    # make people pick the right export before they know there is a choice.
    doc, _preview = _read_submission(args.file)
    return doc, None


def cmd_import(args, out):
    chosen, _ = _resolve(args)
    doc_json, origin = _import_source(args, out)

    m = schema.from_json(doc_json)
    report = validate.check(m)
    if report.errors and not args.force:
        for f in report.errors:
            sys.stderr.write("error: %-18s %s\n" % (f.code, f.message))
        raise ValidationFailed(report)

    if _game_running() and not args.force:
        raise SaveInUse(
            "the emulator appears to be running. Close the game first, or pass "
            "--force if no title is loaded.")

    doc = savefile.read(chosen.path)
    slot = savefile.add_map(doc, m, name=args.name)
    data = savefile.serialize(doc, os.path.getsize(chosen.path))

    if args.dry_run:
        if args.json:
            json.dump({"dryRun": True, "slot": slot, "bytes": len(data),
                       "name": args.name or m.name}, out, indent=2)
            out.write("\n")
        else:
            out.write("dry run: would add %r as slot %s (%s bytes)\n"
                      % (args.name or m.name, slot, format(len(data), ",")))
        return EXIT_OK

    snap = backup.snapshot(chosen.path)
    written = savefile.write(doc, chosen.path)

    if args.json:
        json.dump({"slot": slot, "bytes": written, "backup": snap.path,
                   "name": args.name or m.name, "from": origin,
                   "warnings": [vars(f) for f in report.warnings]}, out, indent=2)
        out.write("\n")
        return EXIT_OK

    out.write("imported %r as slot %s\n" % (args.name or m.name, slot))
    for f in report.warnings:
        out.write("  warning %-18s %s\n" % (f.code, f.message))
    if origin:
        # Somebody else's map just went into this save. Saying whose, and which
        # version, is the difference between a download and an unlabelled file.
        out.write("  from    %s\n" % origin)
    out.write("  save    %s (%s bytes)\n" % (chosen.path, format(written, ",")))
    out.write("  backup  %s\n" % snap.path)
    return EXIT_OK


def _read_submission(path):
    """Read a map from a .json file, a bundle directory, or a .zip of one.

    Returns ``(document, preview_bytes_or_None)``. The editor's bundle carries a
    preview drawn by its own renderer, which is a better picture than anything
    this package can produce - it has the icons, and Python does not.
    """
    if os.path.isdir(path):
        with open(os.path.join(path, "map.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        shot = os.path.join(path, "preview.png")
        if os.path.exists(shot):
            with open(shot, "rb") as fh:
                return doc, fh.read()
        return doc, None

    if path.lower().endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            # Tolerate a zip that wraps its contents in a folder, which is what
            # a round trip through a file manager usually produces.
            entry = next((n for n in names
                          if n.rsplit("/", 1)[-1] == "map.json"), None)
            if entry is None:
                raise MapNotFound("%s has no map.json in it" % path)
            doc = json.loads(z.read(entry).decode("utf-8"))
            stem = entry[:-len("map.json")]
            shot = stem + "preview.png"
            return doc, (z.read(shot) if shot in names else None)

    with open(path, encoding="utf-8") as fh:
        return json.load(fh), None


def _write_warnings(out, report):
    for f in report.warnings:
        out.write("  warning %-18s %s\n" % (f.code, f.message))


def _facts(entry):
    v = entry.get("versions", [{}])[-1]
    bits = ["%dp" % v.get("players", 0),
            "%dx%d" % (v.get("cols", 0), v.get("rows", 0))]
    bits += [k for k in ("predeployed", "navy", "structures", "fog")
             if v.get(k)]
    bits += list(v.get("tags", []))
    return bits


def cmd_remove(args, out):
    chosen, _ = _resolve(args)
    if _game_running() and not args.force:
        raise SaveInUse("the emulator appears to be running; close the game first")
    doc = savefile.read(chosen.path)
    if not 0 <= args.index < len(doc.maps):
        raise MapNotFound("no map at index %d; the save holds %d"
                          % (args.index, len(doc.maps)))
    name = doc.maps[args.index].name
    slot = savefile.remove_map(doc, args.index)
    if args.dry_run:
        if args.json:
            json.dump({"dryRun": True, "removed": name, "slot": slot},
                      out, indent=2)
            out.write("\n")
        else:
            out.write("dry run: would remove %r (slot %s)\n" % (name, slot))
        return EXIT_OK
    snap = backup.snapshot(chosen.path)
    savefile.write(doc, chosen.path)
    if args.json:
        json.dump({"removed": name, "slot": slot, "backup": snap.path,
                   "remaining": len(doc.maps)}, out, indent=2)
        out.write("\n")
    else:
        out.write("removed %r (slot %s)\n  backup %s\n" % (name, slot, snap.path))
    return EXIT_OK


def cmd_backup(args, out):
    chosen, _ = _resolve(args)
    snap = backup.snapshot(chosen.path)
    if args.json:
        json.dump({"backup": snap.path, "save": chosen.path}, out, indent=2)
        out.write("\n")
    else:
        out.write("%s\n" % snap.path)
    return EXIT_OK


def cmd_restore(args, out):
    chosen, _ = _resolve(args)
    snaps = backup.snapshots(chosen.path)

    if args.name is None:
        # Naming no snapshot is how you ask what there is, so an empty list is
        # a successful answer rather than an error.
        if args.json:
            json.dump({"save": chosen.path,
                       "snapshots": [{"name": s.name, "size": s.size,
                                      "taken": s.taken} for s in snaps]},
                      out, indent=2)
            out.write("\n")
        elif not snaps:
            out.write("no snapshots for %s\n" % chosen.path)
        else:
            out.write("snapshots for %s\n\n" % chosen.path)
            for s in snaps:
                out.write("  %-28s %s bytes\n" % (s.name, format(s.size, ",")))
            out.write("\nawrbc restore <name> to roll back\n")
        return EXIT_OK

    match = [s for s in snaps if s.name == args.name or s.taken == args.name]
    if not match:
        raise MapNotFound("no snapshot named %r" % args.name)
    if _game_running() and not args.force:
        raise SaveInUse("the emulator appears to be running; close the game first")
    backup.snapshot(chosen.path)        # snapshot the current state too
    n = backup.restore(match[0].path, chosen.path)
    if args.json:
        json.dump({"restored": match[0].name, "bytes": n,
                   "save": chosen.path}, out, indent=2)
        out.write("\n")
    else:
        out.write("restored %s (%s bytes)\n" % (match[0].name, format(n, ",")))
    return EXIT_OK


def _common(suppress):
    """Global flags, accepted before OR after the subcommand.

    The subcommand copies use SUPPRESS: with a real default, an unset flag on the
    subparser silently overwrites the value already parsed from before the
    subcommand. That bug sent a write to the wrong save file.
    """
    c = argparse.ArgumentParser(add_help=False)
    default = argparse.SUPPRESS if suppress else None
    c.add_argument("--save-dir", default=default,
                   help="Ryujinx data folder, JKSV dump, or maps file")
    c.add_argument("--profile", default=default,
                   help="profile id when a save has several")
    c.add_argument("--json", action="store_true",
                   default=argparse.SUPPRESS if suppress else False,
                   help="emit structured output")
    return c


def build_parser():
    common = _common(suppress=True)
    p = argparse.ArgumentParser(
        prog="awrbc", parents=[_common(suppress=False)],
        description="Custom map tools for Advance Wars 1+2: Re-Boot Camp. "
                    "Not affiliated with Nintendo or WayForward.")
    sub = p.add_subparsers(dest="command")


    sub.add_parser("doctor", parents=[common],
                   help="find save data and report what is readable")
    sub.add_parser("list", parents=[common],
                   help="list the custom maps in a save")

    ex = sub.add_parser("export", parents=[common],
                        help="write a map out as JSON")
    ex.add_argument("index", nargs="?", type=int, help="map index from `list`")
    ex.add_argument("--all", action="store_true", help="export every map")
    ex.add_argument("-o", "--output", help="output file, or directory with --all")
    ex.add_argument("--author", help="author name to publish")
    ex.add_argument("--keep-creator", action="store_true",
                    help="publish the console profile name (often a real name)")

    im = sub.add_parser("import", parents=[common],
                        help="add a map from JSON into the save")
    im.add_argument("file", metavar="FILE",
                    help="a map JSON or an Export bundle zip on disk")
    im.add_argument("--name", help="name to give the map in game")
    im.add_argument("--dry-run", action="store_true", help="build but do not write")
    im.add_argument("--force", action="store_true",
                    help="import despite validation errors or a running emulator")


    rm = sub.add_parser("remove", parents=[common], help="delete a map")
    rm.add_argument("index", type=int, help="map index from `list`")
    rm.add_argument("--dry-run", action="store_true")
    rm.add_argument("--force", action="store_true")

    sub.add_parser("backup", parents=[common], help="snapshot the save")

    rs = sub.add_parser("restore", parents=[common],
                        help="list snapshots, or roll back to one")
    rs.add_argument("name", nargs="?", help="snapshot name from `restore`")
    rs.add_argument("--force", action="store_true")
    return p


def main(argv=None, out=None):
    out = out or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(out)
        return EXIT_USAGE

    handlers = {"doctor": cmd_doctor, "list": cmd_list, "export": cmd_export,
                "import": cmd_import, "remove": cmd_remove,
                "backup": cmd_backup, "restore": cmd_restore}
    try:
        return handlers[args.command](args, out)
    except AwrbcError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
