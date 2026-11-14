"""Compact search result labels, independent of the GUI."""

def result_labels(hits):
    """Return lemma and grammatical class separately for native GTK styling."""
    result = []
    for hit in hits:
        entry = hit["entry"]
        grammar = entry.get("grammar")
        pos = grammar.get("pos") if isinstance(grammar, dict) else None
        if not pos:
            pos = entry.get("pos")
        if isinstance(pos, str):
            pos = [pos]
        classes = ", ".join(dict.fromkeys(p.strip() for p in pos if isinstance(p, str) and p.strip())) if isinstance(pos, list) else ""
        result.append((entry["lemma"], classes))
    return result
