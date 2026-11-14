"""Native VLF binary resources; no source-format dependencies."""
import hashlib
import json
from contextlib import closing
from .core import check_cancel, connect_read

def embed_resources(db, payload, loader, cache, cancel=None):
    """Embed referenced resources by content hash; keep original reference indices."""
    refs = []
    def embed(archive, name):
        check_cancel(cancel)
        key = (archive, name)
        if key not in cache:
            content, mime = loader(archive, name)
            if not isinstance(content, bytes) or not content or len(content) > 64*1024*1024:
                raise ValueError("Invalid resource size: " + str(name))
            if not isinstance(mime, str) or not mime.startswith(("audio/", "image/")):
                raise ValueError("Invalid resource MIME: " + str(name))
            digest = hashlib.sha256(content).hexdigest()
            db.execute("INSERT OR IGNORE INTO resources VALUES (?,?,?)", (digest, mime, content))
            if db.execute("SELECT mime FROM resources WHERE sha256=?", (digest,)).fetchone()[0] != mime:
                raise ValueError("Conflicting resource MIME: " + str(name))
            cache[key] = digest
        return cache[key]
    for original in payload.get("media", []):
        ref = dict(original)
        ref["sha256"] = embed(ref["archive"], ref["name"])
        if ref.get("fullsize"):
            ref["fullsize_sha256"] = embed(ref["archive"], ref["fullsize"])
        refs.append(ref)
    return dict(payload, media=refs)

def get_embedded_media(registry, dictionary, entry_id, index, fullsize=False):
    _, path = registry.dictionary(dictionary)
    with closing(connect_read(path)) as db:
        row = db.execute("SELECT payload FROM entries WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown entry ID")
        refs = json.loads(row[0]).get("media", [])
        if not isinstance(index, int) or not 0 <= index < len(refs):
            raise ValueError("Unknown media index")
        ref = refs[index]
        if fullsize and ref.get("type") != "image":
            raise ValueError("Fullsize applies only to pictures")
        digest = ref.get("fullsize_sha256" if fullsize else "sha256")
        if not digest:
            raise ValueError("Recurso não incorporado; converta a base original para VLF v2.")
        row = db.execute("SELECT content,mime FROM resources WHERE sha256=?", (digest,)).fetchone()
        if row is None:
            raise ValueError("Missing VLF resource")
        return row[0], row[1]
