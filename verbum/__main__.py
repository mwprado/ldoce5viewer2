"""Command-line interface: python3 -m verbum."""
import argparse
import json
import sys
import sqlite3
import tomllib
from pathlib import Path
from .core import Registry
from .catalog import catalog_list
from .importers import import_dictionary

def main(argv=None):
    parser = argparse.ArgumentParser(prog="verbum")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("source")
    imp.add_argument("--manifest")
    imp.add_argument("--rebuild", metavar="DICTIONARY", help="Rebuild an installed dictionary by slug or UUID")
    imp.add_argument("--format", choices=["json", "jsonl", "longman", "bgl"], default="json")
    imp.add_argument("--authorized", action="store_true", help=argparse.SUPPRESS)  # Legacy compatibility; no attestation required.
    for name in ("list", "search", "catalog"):
        p = sub.add_parser(name)
        for key in ("language", "origin", "function"):
            p.add_argument("--" + key)
        if name == "catalog":
            p.add_argument("--catalog-file")
            p.add_argument("--method", choices=["import", "download", "web"])
        if name == "search":
            p.add_argument("query")
            p.add_argument("--mode", choices=["smart", "prefix", "exact", "fulltext"], default="smart")
            p.add_argument("--limit", type=int, default=50)
    sub.add_parser("gui", help="Launch the native GNOME interface")
    media = sub.add_parser("media", help="List or retrieve media from original sources")
    media.add_argument("dictionary")
    media.add_argument("entry_id", type=int)
    media.add_argument("--index", type=int)
    media.add_argument("--fullsize", action="store_true")
    media.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            try:
                from .gtk import main as gui_main
            except (ImportError, ValueError) as exc:
                raise ValueError("GTK4, libadwaita and PyGObject are required: " + str(exc)) from exc
            return gui_main(args.root)
        registry = Registry(args.root)
        if args.command == "import":
            metadata = None
            if args.manifest:
                with Path(args.manifest).open("rb") as f:
                    metadata = tomllib.load(f)
            result = import_dictionary(registry, metadata, args.source, args.format, rebuild=args.rebuild)
        elif args.command == "media":
            from .media import entry_media, get_media
            if args.index is None:
                if args.output or args.fullsize:
                    parser.error("--output and --fullsize require --index")
                _, result = entry_media(registry, args.dictionary, args.entry_id)
            else:
                if args.output is None:
                    parser.error("--index requires --output")
                data, mime = get_media(registry, args.dictionary, args.entry_id, args.index, args.fullsize)
                with args.output.open("xb") as out:
                    out.write(data)
                result = {"mime":mime, "bytes":len(data), "output":str(args.output)}
        else:
            filters = {key: getattr(args, key) for key in ("language", "origin", "function")}
            if args.command == "catalog":
                result = catalog_list(registry, path=args.catalog_file, method=args.method, **filters)
            elif args.command == "list":
                result = registry.list(**filters)
            else:
                result = registry.search(args.query, **filters, mode=args.mode, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("verbum: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
