"""Babylon BGL adapter using optional PyGlossary 5.x."""
from contextlib import contextmanager
from pathlib import Path
import re
import unicodedata
from html.parser import HTMLParser

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("br", "p", "div", "li", "tr", "hr") and not self.hidden:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden-1)
        elif tag in ("p", "div", "li", "tr") and not self.hidden:
            self.parts.append("\n")
    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)

def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    parser.close()
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())

def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "babylon"

def language_code(value):
    value = str(value or "").strip().lower().replace("_", "-")
    known = {"portuguese":"pt", "brazilian portuguese":"pt-br", "english":"en",
             "spanish":"es", "french":"fr", "german":"de", "italian":"it",
             "russian":"ru", "japanese":"ja", "chinese":"zh", "latin":"la"}
    return known.get(value, value if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]+)*", value) else "und")

def validate_source(source):
    path = Path(source).expanduser().resolve()
    with path.open("rb") as stream:
        header = stream.read(6)
    if len(header) != 6 or header[:3] != b"\x12\x34\x00" or header[3] not in (1,2):
        raise ValueError("Arquivo Babylon BGL inválido.")
    return path

@contextmanager
def open_glossary(path):
    try:
        from pyglossary import Glossary
    except ImportError as exc:
        raise ValueError("BGL requer PyGlossary: instale com pip install 'pyglossary>=5,<6' no ambiente do Verbum.") from exc
    Glossary.init()
    glossary = Glossary()
    try:
        if not glossary.read(str(path), format="BabylonBgl"):
            raise ValueError("Não foi possível ler o arquivo Babylon BGL.")
        yield glossary
    finally:
        glossary.clear()

def metadata(path, glossary, override=None):
    from .catalog import read_catalog
    title = glossary.getInfo("name") or glossary.getInfo("title") or path.stem
    source_lang = language_code(glossary.getInfo("sourceLang"))
    target_lang = language_code(glossary.getInfo("targetLang"))
    if "aurelio" in slugify(path.stem) or "aurelio" in slugify(title):
        result = next(dict(m) for m in read_catalog() if m["origin"] == "aurelio")
    else:
        origin = slugify(title)
        function = "bilingual" if source_lang != "und" and target_lang != "und" and source_lang != target_lang else "general"
        result = dict(title=title, language=source_lang, origin=origin,
                      function=function, license="unverified", license_type="unspecified",
                      access="local", distribution={"method":"import","importer":"bgl","requires_original":True})
        if function == "bilingual":
            result["languages"] = [target_lang]
    if override:
        result.update(override)
    result.update(source_path=str(path), source_format="bgl",
                  capabilities=["definitions", "variants", "source-html"])
    return result

def entries(glossary, cancel=None):
    from .core import check_cancel
    for item in glossary:
        check_cancel(cancel)
        if item.isData():
            continue
        terms = getattr(item, "l_term", None)
        if terms is None:
            terms = item.l_word
        terms = list(dict.fromkeys(t.strip() for t in terms if isinstance(t,str) and t.strip()))
        if not terms:
            continue
        definition = item.defi
        fmt = item.defiFormat
        text = plain_text(definition) if fmt in ("h","x") else definition
        yield dict(lemma=terms[0], variants=terms[1:], definitions=[text],
                   source={"format":"bgl","definition":definition,"definition_format":fmt})

def import_bgl(registry, source, override=None, *, progress=None, cancel=None, rebuild=None):
    path = validate_source(source)
    with open_glossary(path) as glossary:
        m = metadata(path, glossary, override)
        return registry.import_entries(m, entries(glossary, cancel), progress=progress, cancel=cancel, rebuild=rebuild)
