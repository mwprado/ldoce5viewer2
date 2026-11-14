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

    def import_entries(self, metadata, entries):
        m = manifest_info(metadata)
        directory = self.root / "dictionaries" / m["language"] / m["origin"]
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / (m["slug"] + ".vlf")
        fd, name = tempfile.mkstemp(dir=directory, suffix=".tmp")
        os.close(fd)
        temp = Path(name)
        published = False
        try:
            with closing(sqlite3.connect(temp)) as db:
                db.executescript(SCHEMA)
                db.execute("INSERT INTO metadata VALUES (?,?)", ("manifest", json.dumps(m, ensure_ascii=False)))
                count = 0
                for entry in entries:
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
                    db.execute("INSERT INTO search_index(rowid,lemma,body) VALUES (?,?,?)",
                               (cursor.lastrowid, lemma, data))
                    count += 1
                if not count:
                    raise ValueError("Empty dictionary")
                db.commit()
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Invalid VLF database")
            with closing(sqlite3.connect(self.path)) as registry:
                registry.execute("BEGIN IMMEDIATE")
                registry.execute("INSERT INTO dictionaries VALUES (?,?,?,?)",
                                 (m["id"], m["slug"], str(target), json.dumps(m, ensure_ascii=False)))
                # Hard link refuses to overwrite an existing dictionary.
                os.link(temp, target)
                published = True
                registry.commit()
            return dict(m, entries=count, path=str(target))
        except BaseException:
            if published:
                target.unlink(missing_ok=True)
            raise
        finally:
            temp.unlink(missing_ok=True)

    def search(self, query, language=None, origin=None, function=None, limit=50, mode="prefix"):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        key = normalize(query)
        if not key:
            return []
        if mode not in ("prefix", "exact", "fulltext"):
            raise ValueError("Invalid search mode")
        selected = self.list(language, origin, function)
        with closing(sqlite3.connect(self.path)) as registry:
            paths = dict(registry.execute("SELECT id,path FROM dictionaries"))
        result = []
        for m in selected:
            with closing(connect_read(paths[m["id"]])) as db:
                if mode == "fulltext":
                    expression = '"' + query.replace('"', '""') + '"'
                    rows = db.execute("SELECT e.payload FROM search_index s JOIN entries e ON e.id=s.rowid WHERE search_index MATCH ? LIMIT ?", (expression, limit)).fetchall()
                elif mode == "exact":
                    rows = db.execute("SELECT payload FROM entries WHERE normalized=? ORDER BY id LIMIT ?", (key, limit)).fetchall()
                else:
                    escaped = key.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                    rows = db.execute("SELECT payload FROM entries WHERE normalized LIKE ? ESCAPE '!' ORDER BY normalized,id LIMIT ?", (escaped+"%", limit)).fetchall()
                result.extend({"dictionary": m["slug"], "entry": json.loads(row[0])} for row in rows)
        return result[:limit]
