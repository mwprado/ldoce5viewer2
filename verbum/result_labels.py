"""Compact search result labels, independent of the GUI."""
from collections import Counter, defaultdict

def _classes(entry):
    grammar = entry.get("grammar")
    pos = grammar.get("pos") if isinstance(grammar, dict) else None
    if not pos:
        pos = entry.get("pos")
    if isinstance(pos, str):
        pos = [pos]
    if not isinstance(pos, list):
        return ""
    return ", ".join(dict.fromkeys(p.strip() for p in pos if isinstance(p, str) and p.strip()))

def result_labels(hits):
    """Keep distinct entries; number identical visible labels only when needed."""
    base = []
    for hit in hits:
        entry = hit["entry"]
        lemma = entry["lemma"]
        homograph = entry.get("homograph")
        if isinstance(homograph, (str, int)) and str(homograph).strip():
            lemma += " " + str(homograph).strip()
        pos = _classes(entry)
        base.append((lemma, pos))
    counts = Counter(base)
    occurrence = defaultdict(int)
    result = []
    for key in base:
        lemma, pos = key
        occurrence[key] += 1
        text = lemma + (" (" + pos + ")" if pos else "")
        if counts[key] > 1:
            text += " · " + str(occurrence[key])
        result.append(text)
    return result
