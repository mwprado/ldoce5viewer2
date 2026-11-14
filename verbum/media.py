"""Resolve media references on demand from a locally installed native dictionary."""
from contextlib import closing
from functools import lru_cache
from pathlib import Path
import json
import zlib
from .core import connect_read
from .longman import _reader, validate_source

AUDIO_ARCHIVES = frozenset(("gb_hwd_pron", "us_hwd_pron", "exa_pron", "sfx", "sound"))
MEDIA_ARCHIVES = AUDIO_ARCHIVES | {"picture"}

def _archive_signature(source, archive):
    base = Path(source) / (archive + ".skn")
    files = [base / directory / name for directory, names in (
        ("dirs.skn", ("config.cft", "NAME.tda", "dirs.dat")),
        ("files.skn", ("config.cft", "NAME.tda", "files.dat", "CONTENT.tda", "CONTENT.tda.tdz")),
    ) for name in names]
    return tuple((p.stat().st_size, p.stat().st_mtime_ns) for p in files)

@lru_cache(maxsize=8)
def _locations(source, archive, signature):
    reader, _ = _reader()
    result = {}
    for dirs, name, location in reader.list_files(source, archive):
        key = dirs[0] + "/" + name if archive == "picture" else name
        if key in result and result[key] != location:
            # Do not resolve an ambiguous resource to an arbitrary file.
            result[key] = None
        else:
            result[key] = location
    return result

def read_longman_media(source, archive, name):
    if archive not in MEDIA_ARCHIVES:
        raise ValueError("Unsupported media archive")
    source = str(validate_source(source))
    if not isinstance(name, str) or not name or "\\" in name or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("Invalid media name")
    if archive == "picture":
        if len(name.split("/")) != 2 or name.split("/")[0] not in ("thumbnail", "fullsize"):
            raise ValueError("Invalid picture name")
    elif "/" in name:
        raise ValueError("Invalid audio name")
    signature = _archive_signature(source, archive)
    location = _locations(source, archive, signature).get(name)
    if location is None:
        raise ValueError("Missing or ambiguous media resource: " + archive + "/" + name)
    if any(n < 0 for n in location) or location[3] > 64 * 1024 * 1024:
        raise ValueError("Invalid media record size")
    reader, _ = _reader()
    try:
        with reader.ArchiveReader(source, archive) as ar:
            data = ar.read(location)
    except zlib.error as exc:
        raise ValueError("Corrupt media record") from exc
    if not data or len(data) != location[3]:
        raise ValueError("Empty or truncated media record")
    if archive == "picture":
        if data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data.startswith((b"GIF87a", b"GIF89a")):
            mime = "image/gif"
        else:
            raise ValueError("Unsupported picture encoding")
    else:
        mime = "audio/mpeg"
    return data, mime

def entry_media(registry, dictionary, entry_id):
    manifest, path = registry.dictionary(dictionary)
    with closing(connect_read(path)) as db:
        row = db.execute("SELECT payload FROM entries WHERE id=?", (entry_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown entry ID")
    entry = json.loads(row[0])
    return manifest, entry.get("media", [])

def get_media(registry, dictionary, entry_id, index, fullsize=False):
    manifest, resources = entry_media(registry, dictionary, entry_id)
    if not isinstance(index, int) or not 0 <= index < len(resources):
        raise ValueError("Unknown media index")
    if manifest.get("source_format") != "idm-skn":
        raise ValueError("No media provider for this dictionary")
    ref = resources[index]
    if fullsize and ref.get("type") != "image":
        raise ValueError("Fullsize applies only to pictures")
    name = ref.get("fullsize") if fullsize else ref["name"]
    if not name:
        raise ValueError("Full-size picture unavailable")
    return read_longman_media(manifest["source_path"], ref["archive"], name)
