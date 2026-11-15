"""Export LDOCE5 entries as JSON Lines for external consumers.

This module is part of the GPL-licensed ldoce5viewer package. It reads the
user's original IDM/SKN archives and writes normalized lexical records to
stdout. Dictionary data is never modified.
"""
import argparse
import json
import sys
from pathlib import Path

from lxml import etree

from .ldoce5 import idmreader


def validate_source(source):
    path = Path(source).expanduser().resolve()
    fs = path / "fs.skn"
    required = (
        "dirs.skn/config.cft",
        "dirs.skn/NAME.tda",
        "dirs.skn/dirs.dat",
        "files.skn/config.cft",
        "files.skn/NAME.tda",
        "files.skn/files.dat",
        "files.skn/CONTENT.tda",
        "files.skn/CONTENT.tda.tdz",
    )
    missing = [name for name in required if not (fs / name).is_file()]
    if missing:
        raise ValueError(
            "Not an LDOCE5 data directory; missing: " + ", ".join(missing)
        )
    return path


def _text(node):
    if node is None:
        return ""
    parts = []

    def visit(element):
        if not isinstance(element.tag, str):
            return
        if element.tag in ("OBJECT", "GLOSS", "Audio"):
            return
        if element.text:
            parts.append(element.text)
        for child in element:
            visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(node)
    return "".join(parts).strip()


def _texts(nodes):
    return list(dict.fromkeys(text for text in map(_text, nodes) if text))


def parse_entry(data, source_name):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(data, parser)
    head = root.find("Head")
    lemma = _text(root.find("Head/HWD/BASE"))
    source_id = root.get("id")
    if head is None or not lemma or not source_id:
        raise ValueError("missing Longman headword or ID")

    senses = []
    for node in root.xpath(".//Sense | .//Subsense"):
        def owned(tag):
            return [
                element
                for element in node.iter(tag)
                if next(
                    (
                        ancestor
                        for ancestor in element.iterancestors()
                        if ancestor.tag in ("Sense", "Subsense")
                    ),
                    None,
                )
                is node
            ]

        senses.append(
            {
                "id": node.get("id"),
                "definitions": _texts(owned("DEF")),
                "examples": _texts(
                    example.find("BASE")
                    if example.find("BASE") is not None
                    else example
                    for example in owned("EXAMPLE")
                ),
            }
        )

    return {
        "lemma": lemma,
        "language": "en",
        "source_id": source_id,
        "homograph": _text(head.find("HOMNUM")) or _text(head.find("HWD/HOMNUM")),
        "grammar": {
            "pos": _texts(head.findall("POS")),
            "notes": _texts(head.findall("GRAM")),
        },
        "variants": _texts(head.xpath(".//INFLX | .//ABBR")),
        "senses": senses,
        "definitions": _texts(root.iter("DEF")),
        "examples": _texts(
            example.find("BASE")
            if example.find("BASE") is not None
            else example
            for example in root.iter("EXAMPLE")
        ),
        "source": {"archive": "fs", "file": source_name},
    }


def entries(source):
    path = validate_source(source)
    seen = set()
    with idmreader.ArchiveReader(str(path), "fs") as archive:
        for dirs, name, location in idmreader.list_files(str(path), "fs"):
            source_name = "/".join((*dirs, name))
            try:
                raw = archive.read(location)
                if len(raw) != location[3] or not raw:
                    raise ValueError("truncated or empty record")
                entry = parse_entry(raw, source_name)
            except (etree.XMLSyntaxError, ValueError) as exc:
                raise ValueError(f"Longman record {source_name}: {exc}") from exc
            if entry["source_id"] in seen:
                raise ValueError(
                    "duplicate Longman entry ID: " + entry["source_id"]
                )
            seen.add(entry["source_id"])
            yield entry


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ldoce5-verbum-export",
        description="Export original LDOCE5 IDM/SKN data as JSON Lines",
    )
    parser.add_argument("source", help="Original LDOCE5 data directory")
    args = parser.parse_args(argv)
    try:
        for entry in entries(args.source):
            print(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ldoce5-verbum-export: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
