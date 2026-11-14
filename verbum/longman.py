"""Native LDOCE5 import; reads the original IDM/SKN archives, never modifies them."""
import base64
from pathlib import Path
from .catalog import read_catalog

def metadata(source):
    m = next(m for m in read_catalog() if m["slug"] == "en-longman-learner-5")
    m["source_format"] = "idm-skn"
    m["source_path"] = str(Path(source).expanduser().resolve())
    m["capabilities"] = ["definitions", "examples", "grammar", "variants",
                         "source-xml", "media-references"]
    return m

def _reader():
    try:
        from ldoce5viewer.ldoce5 import idmreader
        from lxml import etree
    except ImportError as exc:
        raise ValueError("Longman requires the existing LDOCE5 reader and python3-lxml") from exc
    return idmreader, etree

def validate_source(source):
    path = Path(source).expanduser().resolve()
    fs = path / "fs.skn"
    required = ("dirs.skn/config.cft", "dirs.skn/NAME.tda", "dirs.skn/dirs.dat",
                "files.skn/config.cft", "files.skn/NAME.tda", "files.skn/files.dat",
                "files.skn/CONTENT.tda", "files.skn/CONTENT.tda.tdz")
    if not all((fs / name).is_file() for name in required):
        raise ValueError("Not an LDOCE5 data directory: missing fs.skn archive files")
    return path

def _text(node):
    if node is None:
        return ""
    parts = []
    def visit(e):
        if not isinstance(e.tag, str) or e.tag in ("span", "OBJECT", "GLOSS", "Audio"):
            return
        if e.text:
            parts.append(e.text)
        for c in e:
            visit(c)
            if c.tail:
                parts.append(c.tail)
    visit(node)
    return "".join(parts).strip()

def _texts(nodes):
    return list(dict.fromkeys(t for t in map(_text, nodes) if t))

def parse_entry(data, source_name):
    _, etree = _reader()
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(data, parser)
    head = root.find("Head")
    lemma = _text(root.find("Head/HWD/BASE"))
    source_id = root.get("id")
    if head is None or not lemma or not source_id:
        raise ValueError("Missing Longman headword or ID: " + source_name)
    senses = []
    for node in root.xpath(".//Sense | .//Subsense"):
        # Exclude definitions/examples belonging to nested senses.
        def owned(tag):
            return [e for e in node.iter(tag)
                    if next((a for a in e.iterancestors() if a.tag in ("Sense", "Subsense")), None) is node]
        senses.append({"id": node.get("id"), "definitions": _texts(owned("DEF")),
                       "examples": _texts(e.find("BASE") if e.find("BASE") is not None else e
                                          for e in owned("EXAMPLE"))})
    media = []
    for node in root.iter("Audio"):
        resource, topic = node.get("resource"), node.get("topic")
        if resource and topic:
            media.append({"type":"audio", "archive":resource.lower(), "name":topic.split("/")[-1]})
    for node in root.iter("ILLUSTRATION"):
        thumb = node.get("thumb")
        if thumb:
            media.append({"type":"image", "archive":"picture", "name":"thumbnail/" + thumb.split("/")[-1],
                          "fullsize":"fullsize/" + thumb.split("/")[-1]})
    variants = _texts(head.xpath(".//INFLX | .//ABBR"))
    return {"lemma": lemma, "language":"en", "source_id":source_id,
            "homograph":_text(head.find("HOMNUM")),
            "grammar":{"pos":_texts(head.findall("POS")), "notes":_texts(head.findall("GRAM"))},
            "variants":variants, "senses":senses,
            "definitions":_texts(root.iter("DEF")),
            "examples":_texts(e.find("BASE") if e.find("BASE") is not None else e for e in root.iter("EXAMPLE")),
            "media":media,
            "source":{"archive":"fs", "file":source_name, "xml_base64":base64.b64encode(data).decode("ascii")}}

def locations(source, cancel=None):
    from .core import check_cancel
    path = validate_source(source)
    reader, _ = _reader()
    result = []
    for location in reader.list_files(str(path), "fs"):
        check_cancel(cancel)
        result.append(location)
    return result

def entries(source, locations=None):
    path = validate_source(source)
    reader, etree = _reader()
    seen = set()
    with reader.ArchiveReader(str(path), "fs") as archive:
        for dirs, name, location in (locations if locations is not None else reader.list_files(str(path), "fs")):
            source_name = "/".join((*dirs, name))
            try:
                raw = archive.read(location)
                if len(raw) != location[3] or not raw:
                    raise ValueError("Truncated or empty record")
                entry = parse_entry(raw, source_name)
            except (etree.XMLSyntaxError, ValueError) as exc:
                raise ValueError("Longman record " + source_name + ": " + str(exc)) from exc
            if entry["source_id"] in seen:
                raise ValueError("Duplicate Longman entry ID: " + entry["source_id"])
            seen.add(entry["source_id"])
            yield entry
