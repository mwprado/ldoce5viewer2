"""Distribution policy and a catalog of installable dictionary descriptions.

License claims are metadata, not a legal determination. Default to no redistribution.
"""
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

def distribution_info(metadata):
    access = metadata.get("access", "local")
    if access not in ("local", "web", "hybrid"):
        raise ValueError("Invalid access")
    license_type = metadata.get("license_type", "unspecified")
    if license_type not in ("proprietary", "public-domain", "open", "restricted", "unspecified"):
        raise ValueError("Invalid license type")
    d = metadata.get("distribution", {})
    if not isinstance(d, dict):
        raise ValueError("distribution must be a table")
    method = d.get("method", "web" if access == "web" else "import")
    if method not in ("import", "download", "web"):
        raise ValueError("Invalid distribution method")
    redistributable = d.get("redistributable", False)
    if type(redistributable) is not bool:
        raise ValueError("redistributable must be boolean")
    if redistributable and license_type not in ("open", "public-domain"):
        raise ValueError("Redistribution requires a verified open or public-domain license")
    if redistributable and not str(metadata.get("license_reference", "")).strip():
        raise ValueError("Redistribution requires a license reference")
    if method == "download" and not redistributable:
        raise ValueError("Download requires explicit redistribution permission")
    if method == "web" and access not in ("web", "hybrid"):
        raise ValueError("Web method requires web access")
    if access == "web" and method != "web":
        raise ValueError("Web-only source cannot use a local installation method")
    if license_type == "proprietary" and method == "import" and d.get("requires_original", True) is not True:
        raise ValueError("Proprietary import requires original files")
    original = d.get("requires_original", method == "import")
    if type(original) is not bool or (method != "import" and original):
        raise ValueError("Invalid requires_original")
    if method in ("download", "web"):
        url = d.get("url", "")
        if not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
            raise ValueError("HTTPS source URL required")
    if method == "download" and not re.fullmatch(r"[a-fA-F0-9]{64}", str(d.get("sha256", ""))):
        raise ValueError("Download requires SHA-256")
    return dict(d, method=method, redistributable=redistributable,
                requires_original=original)

def read_catalog(path=None):
    from .core import manifest_info
    path = Path(path) if path else Path(__file__).with_name("catalog.toml")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    if raw.get("version") != 1:
        raise ValueError("Unsupported catalog version")
    records = []
    slugs = set()
    for item in raw.get("dictionaries", []):
        m = manifest_info(item, catalog=True)
        if m["slug"] in slugs:
            raise ValueError("Duplicate catalog slug")
        slugs.add(m["slug"])
        records.append(m)
    return records

def catalog_list(registry, path=None, language=None, origin=None, function=None, method=None):
    installed = {m["slug"] for m in registry.list()}
    result = []
    for m in read_catalog(path):
        if language and language not in [m["language"], *m.get("languages", [])]:
            continue
        if origin and origin != m["origin"]:
            continue
        if function and function not in [m["function"], *m.get("functions", [])]:
            continue
        if method and method != m["distribution"]["method"]:
            continue
        result.append(dict(m, installed=m["slug"] in installed))
    return result
