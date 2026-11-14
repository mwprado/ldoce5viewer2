"""Command-line interface: python3 -m verbum."""
import argparse
import json
import sys
import sqlite3
import tomllib
from pathlib import Path
from .core import Registry
from .importers import import_dictionary

def main(argv=None):
    parser = argparse.ArgumentParser(prog="verbum")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("source")
    imp.add_argument("--manifest", required=True)
    imp.add_argument("--format", choices=["json", "jsonl"], default="json")
    imp.add_argument("--authorized", action="store_true", help="Confirm authorization to import this source")
    for name in ("list", "search"):
        p = sub.add_parser(name)
        for key in ("language", "origin", "function"):
            p.add_argument("--" + key)
        if name == "search":
            p.add_argument("query")
            p.add_argument("--mode", choices=["prefix", "exact", "fulltext"], default="prefix")
            p.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        registry = Registry(args.root)
        if args.command == "import":
            if not args.authorized:
                parser.error("Import requires --authorized")
            with Path(args.manifest).open("rb") as f:
                metadata = tomllib.load(f)
            result = import_dictionary(registry, metadata, args.source, args.format)
        else:
            filters = {key: getattr(args, key) for key in ("language", "origin", "function")}
            result = registry.list(**filters) if args.command == "list" else registry.search(args.query, **filters, mode=args.mode, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("verbum: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
