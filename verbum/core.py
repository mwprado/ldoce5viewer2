"""VLF v1: one SQLite database per dictionary; local, read-only queries."""
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
import uuid
from contextlib import closing
from pathlib import Path
from .catalog import distribution_info

SCHEMA = """
PRAGMA user_version=1;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE entries (
 id INTEGER PRIMARY KEY, lemma TEXT NOT NULL, normalized TEXT NOT NULL,
 language TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX entries_normalized ON entries(normalized);
CREATE VIRTUAL TABLE search_index USING fts5(lemma, body, tokenize='unicode61 remove_diacritics 0');
"""
REGISTRY = """
CREATE TABLE IF NOT EXISTS dictionaries (
 id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, path TEXT NOT NULL,
 manifest TEXT NOT NULL
);
"""

def normalize(text):
    return unicodedata.normalize("NFC", text).casefold().strip()

def token(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError("Invalid identifier: %r" % value)
    return value

def manifest_info(m, *, catalog=False):
    m = dict(m)
    for key in ("title", "origin", "language", "function", "license"):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ValueError("Missing metadata: " + key)
    for key in ("language", "origin", "function"):
        token(m[key])
    parts = [m["language"], m["origin"], m["function"]]
    if m.get("edition"):
        parts.append(token(str(m["edition"])))
    m["slug"] = "-".join(parts)
    m["id"] = str(uuid.UUID(m["id"])) if m.get("id") else str(uuid.uuid5(uuid.NAMESPACE_URL, "verbum:catalog:" + m["slug"])) if catalog else str(uuid.uuid4())
    m["access"] = m.get("access", "local")
    m["distribution"] = distribution_info(m)
    if not catalog and m["access"] != "local":
        raise ValueError("VLF v1 imports local sources only")
    m["format_version"] = 1
    if not catalog and m["distribution"]["method"] == "web":
        raise ValueError("Web sources cannot be imported as VLF")
    return m

class ImportCancelled(Exception):
    """Import cancelled before publication."""

class DictionaryAlreadyInstalled(ValueError):
    """The dictionary identity is already registered or its file exists."""

def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ImportCancelled("Importação cancelada")

def default_root():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "verbum"

def connect_read(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)

class Registry:
    def __init__(self, root=None):
        self.root = Path(root or default_root()).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "registry.sqlite"
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(REGISTRY)

    def list(self, language=None, origin=None, function=None):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT manifest FROM dictionaries ORDER BY slug").fetchall()
        result = [json.loads(row[0]) for row in rows]
        return [m for m in result if
                (not language or language in [m["language"], *m.get("languages", [])])
                and (not origin or origin == m["origin"])
                and (not function or function in [m["function"], *m.get("functions", [])])]

    def dictionary(self, identifier):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT manifest,path FROM dictionaries WHERE slug=? OR id=?",
                             (identifier, identifier)).fetchone()
        if row is None:
            raise ValueError("Unknown dictionary: " + identifier)
        return json.loads(row[0]), Path(row[1])

    def import_entries(self, metadata, entries, *, total=None, progress=None, cancel=None, rebuild=None):
        check_cancel(cancel)
        m = manifest_info(metadata)
        previous = None
        if rebuild:
            old, previous = self.dictionary(rebuild)
            if old["slug"] != m["slug"]:
                raise ValueError("A fonte selecionada não corresponde à edição instalada.")
            m["id"] = old["id"]
        def report(stage, count):
            if progress:
                progress(stage, count, total)
        with closing(sqlite3.connect(self.path)) as registry:
            if not rebuild and registry.execute("SELECT 1 FROM dictionaries WHERE id=? OR slug=?", (m["id"], m["slug"])).fetchone():
                raise DictionaryAlreadyInstalled("Dicionário já instalado: " + m["title"])
        directory = self.root / "dictionaries" / m["language"] / m["origin"]
        if rebuild:
            directory = directory / "generations" / uuid.uuid4().hex
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / (m["slug"] + ".vlf")
        if target.exists():
            raise DictionaryAlreadyInstalled("Já existe uma base VLF neste caminho: " + str(target))
        fd, name = tempfile.mkstemp(dir=directory, suffix=".tmp")
        os.close(fd)
        temp = Path(name)
        published = False
        try:
            with closing(sqlite3.connect(temp)) as db:
                db.executescript(SCHEMA)
                db.execute("INSERT INTO metadata VALUES (?,?)", ("manifest", json.dumps(m, ensure_ascii=False)))
                count = 0
                report("index", count)
                for entry in entries:
                    check_cancel(cancel)
                    if not isinstance(entry, dict):
                        raise ValueError("Entry must be an object")
                    lemma = entry.get("lemma")
                    if not isinstance(lemma, str) or not lemma.strip():
                        raise ValueError("Missing lemma")
                    language = entry.get("language", m["language"])
                    token(language)
                    payload = dict(entry, language=language)
                    data = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                    cursor = db.execute("INSERT INTO entries(lemma,normalized,language,payload) VALUES (?,?,?,?)",
                                        (lemma, normalize(lemma), language, data))
                    searchable = json.dumps({k:v for k,v in payload.items() if k not in ("source", "media")}, ensure_ascii=False)
                    db.execute("INSERT INTO search_index(rowid,lemma,body) VALUES (?,?,?)",
                               (cursor.lastrowid, lemma, searchable))
                    count += 1
                    if count % 128 == 0:
                        report("index", count)
                check_cancel(cancel)
                report("verify", count)
                if not count:
                    raise ValueError("Empty dictionary")
                db.commit()
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Invalid VLF database")
            check_cancel(cancel)
            with closing(sqlite3.connect(self.path)) as registry:
                registry.execute("BEGIN IMMEDIATE")
                check_cancel(cancel)
                report("publish", count)
                try:
                    if rebuild:
                        changed = registry.execute("UPDATE dictionaries SET path=?,manifest=? WHERE id=? AND slug=? AND path=?",
                            (str(target), json.dumps(m, ensure_ascii=False), m["id"], m["slug"], str(previous)))
                        if changed.rowcount != 1:
                            raise ValueError("O dicionário foi alterado por outra operação.")
                    else:
                        registry.execute("INSERT INTO dictionaries VALUES (?,?,?,?)",
                                         (m["id"], m["slug"], str(target), json.dumps(m, ensure_ascii=False)))
                except sqlite3.IntegrityError as exc:
                    raise DictionaryAlreadyInstalled("Dicionário já instalado: " + m["title"]) from exc
                # Hard link refuses to overwrite an existing dictionary.
                try:
                    os.link(temp, target)
                except FileExistsError as exc:
                    raise DictionaryAlreadyInstalled("Já existe uma base VLF neste caminho: " + str(target)) from exc
                published = True
                registry.commit()
            return dict(m, entries=count, path=str(target))
        except BaseException:
            if published:
                target.unlink(missing_ok=True)
            raise
        finally:
            temp.unlink(missing_ok=True)
            if rebuild and not published:
                try:
                    directory.rmdir()
                except OSError:
                    pass

    def search(self, query, language=None, origin=None, function=None, limit=50, mode="prefix", dictionary=None):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        key = normalize(query)
        if not key:
            return []
        if mode not in ("prefix", "exact", "fulltext"):
            raise ValueError("Invalid search mode")
        selected = self.list(language, origin, function)
        if dictionary:
            selected = [m for m in selected if dictionary in (m["slug"], m["id"])]
        with closing(sqlite3.connect(self.path)) as registry:
            paths = dict(registry.execute("SELECT id,path FROM dictionaries"))
        result = []
        for m in selected:
            with closing(connect_read(paths[m["id"]])) as db:
                if mode == "fulltext":
                    expression = '"' + query.replace('"', '""') + '"'
                    rows = db.execute("SELECT e.id,e.payload FROM search_index s JOIN entries e ON e.id=s.rowid WHERE search_index MATCH ? LIMIT ?", (expression, limit)).fetchall()
                elif mode == "exact":
                    rows = db.execute("SELECT id,payload FROM entries WHERE normalized=? ORDER BY id LIMIT ?", (key, limit)).fetchall()
                else:
                    escaped = key.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                    rows = db.execute("SELECT id,payload FROM entries WHERE normalized LIKE ? ESCAPE '!' ORDER BY normalized,id LIMIT ?", (escaped+"%", limit)).fetchall()
                result.extend({"dictionary": m["slug"], "entry_id": row[0], "entry": json.loads(row[1])} for row in rows)
        return result[:limit]
