"""Source-specific import adapters. No arbitrary pickle deserialization."""
import json
from pathlib import Path

def json_entries(source):
    path = Path(source)
    with path.open(encoding="utf-8") as f:
        if path.suffix.lower() == ".jsonl":
            for line in f:
                if line.strip():
                    yield json.loads(line)
        else:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON source must contain an array of entries")
            yield from data

def import_dictionary(registry, metadata, source, source_format="json"):
    if source_format not in ("json", "jsonl"):
        raise ValueError("Unsupported source format: " + source_format)
    return registry.import_entries(metadata, json_entries(source))
