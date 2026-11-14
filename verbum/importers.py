"""Source-specific import adapters. No arbitrary pickle deserialization."""
import json
from pathlib import Path

def json_entries(source, source_format=None):
    path = Path(source)
    with path.open(encoding="utf-8") as f:
        if source_format == "jsonl" or (source_format is None and path.suffix.lower() == ".jsonl"):
            for line in f:
                if line.strip():
                    yield json.loads(line)
        else:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON source must contain an array of entries")
            yield from data

def import_dictionary(registry, metadata, source, source_format="json"):
    if source_format == "longman":
        from . import longman
        if metadata:
            raise ValueError("Longman uses its native catalog metadata; omit --manifest")
        path = longman.validate_source(source)
        return registry.import_entries(longman.metadata(path), longman.entries(path))
    if metadata is None:
        raise ValueError("JSON/JSONL requires --manifest")
    if source_format not in ("json", "jsonl"):
        raise ValueError("Unsupported source format: " + source_format)
    from .catalog import distribution_info
    policy = distribution_info(metadata)
    if metadata.get("license_type") == "proprietary" or metadata.get("license", "").lower() == "proprietary":
        raise ValueError("Proprietary sources require a native importer; JSON compatibility is not supported")
    if policy["method"] != "import":
        raise ValueError("Use the corresponding installation method")
    return registry.import_entries(metadata, json_entries(source, source_format))
