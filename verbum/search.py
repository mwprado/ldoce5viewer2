"""Ranked lexical search, with a bounded cached spelling index."""
from collections import defaultdict
from functools import lru_cache
from contextlib import closing
import sqlite3
import unicodedata

def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))

def grams(text):
    return {text[i:i+2] for i in range(len(text)-1)}

def distance(a, b):
    # Optimal string alignment distance, including adjacent transposition.
    prevprev = None
    prev = list(range(len(b)+1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            v = min(row[j-1]+1, prev[j]+1, prev[j-1]+(x != y))
            if i > 1 and j > 1 and x == b[j-2] and a[i-2] == y:
                v = min(v, prevprev[j-2]+1)
            row.append(v)
        prevprev, prev = prev, row
    return prev[-1]

@lru_cache(maxsize=4)
def spelling_index(path, signature):
    from .core import connect_read
    words = defaultdict(list)
    buckets = defaultdict(set)
    with closing(connect_read(path)) as db:
        for (word,) in db.execute("SELECT DISTINCT normalized FROM entries"):
            key = fold(word)
            words[key].append(word)
            for gram in grams(key):
                buckets[gram].add(key)
    return words, buckets

def similar(path, key, limit=20):
    if len(key) < 3 or len(key) > 80:
        return []
    stat = path.stat()
    words, buckets = spelling_index(str(path), (stat.st_ino, stat.st_size, stat.st_mtime_ns))
    query = fold(key)
    threshold = 1 if len(query) <= 4 else 2
    candidates = defaultdict(int)
    for gram in grams(query):
        for word in buckets.get(gram, ()):
            if abs(len(word)-len(query)) <= threshold:
                candidates[word] += 1
    # Short words may share no bigram after a single typo.
    if len(query) <= 4:
        for word in words:
            if abs(len(word)-len(query)) <= threshold:
                candidates.setdefault(word, 0)
    ranked = []
    for word, _ in sorted(candidates.items(), key=lambda x:(-x[1], abs(len(x[0])-len(query)), x[0]))[:4000]:
        d = distance(query, word)
        if d <= threshold:
            for original in words[word]:
                if original != key and not original.startswith(key):
                    ranked.append((d, original))
    return sorted(ranked)[:limit]

def ranked_search(registry, query, selected, paths, limit):
    from .core import connect_read, normalize
    import json
    from pathlib import Path
    key = normalize(query)
    result = []
    seen = set()
    def add(manifest, rows, kind, score=0):
        for eid, payload in rows:
            ident = (manifest["slug"], eid)
            if ident in seen:
                continue
            seen.add(ident)
            result.append((score, {"dictionary":manifest["slug"], "entry_id":eid,
                                   "entry":json.loads(payload), "match":kind}))
    # Exact results across all selected dictionaries before any completions.
    escaped = key.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    for m in selected:
        with closing(connect_read(paths[m["id"]])) as db:
            add(m, db.execute("SELECT id,payload FROM entries WHERE normalized=? ORDER BY id LIMIT ?", (key, limit)), "exact")
    if len(result) >= limit:
        return [hit for _, hit in result[:limit]]
    for m in selected:
        with closing(connect_read(paths[m["id"]])) as db:
            add(m, db.execute("SELECT id,payload FROM entries WHERE normalized LIKE ? ESCAPE '!' AND normalized<>? ORDER BY normalized,id LIMIT ?", (escaped+"%",key,limit)), "prefix", 1)
    # Keep completions ahead of suggestions, but reserve room for typo matches
    # when there are no exact results.
    exact = [r for r in result if r[1]["match"] == "exact"]
    prefix = sorted((r for r in result if r[1]["match"] == "prefix"), key=lambda r:normalize(r[1]["entry"]["lemma"]))
    if len(key) >= 3 and (len(result) < limit or not exact):
        for m in selected:
            path = Path(paths[m["id"]])
            with closing(connect_read(path)) as db:
                for d, word in similar(path, key):
                    add(m, db.execute("SELECT id,payload FROM entries WHERE normalized=? ORDER BY id LIMIT ?", (word,limit)), "similar", 2+d)
    fuzzy = sorted((r for r in result if r[1]["match"] == "similar"), key=lambda r:(r[0],normalize(r[1]["entry"]["lemma"])))
    if not exact and fuzzy and len(prefix) >= limit:
        prefix = prefix[:max(0,limit-min(10,len(fuzzy)))]
    return [hit for _,hit in (exact+prefix+fuzzy)[:limit]]
