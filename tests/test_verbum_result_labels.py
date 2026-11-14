import unittest
from verbum.result_labels import result_labels

class ResultLabelsTests(unittest.TestCase):
    def test_compact_labels(self):
        entries = [
            {"lemma":"home", "homograph":"1", "grammar":{"pos":["noun"]}},
            {"lemma":"home", "homograph":"2", "grammar":{"pos":["adjective", "adverb"]}},
            {"lemma":"home", "grammar":{"pos":["verb"]}},
            {"lemma":"home", "grammar":{"pos":["verb"]}},
            {"lemma":"home run"},
        ]
        hits = [{"entry":entry, "dictionary":"demo"} for entry in entries]
        self.assertEqual(result_labels(hits), [
            "home 1 (noun)", "home 2 (adjective, adverb)",
            "home (verb) · 1", "home (verb) · 2", "home run"])
    def test_unknown_grammar(self):
        self.assertEqual(result_labels([{"entry":{"lemma":"home","grammar":None}}]), ["home"])
    def test_source_is_not_part_of_label(self):
        hits = [{"dictionary":d,"entry":{"lemma":"home","pos":"noun"}} for d in ("a","b")]
        self.assertEqual(result_labels(hits), ["home (noun) · 1", "home (noun) · 2"])
