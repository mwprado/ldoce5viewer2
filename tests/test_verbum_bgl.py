import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
from verbum.core import Registry
from verbum.bgl import plain_text, entries, metadata, validate_source

class FakeGlossary:
    def getInfo(self, key):
        return {"name":"Aurélio", "sourceLang":"Portuguese", "targetLang":"Portuguese"}.get(key,"")
    def __iter__(self):
        yield SimpleNamespace(isData=lambda:False, l_term=["água","agua"], defi="<b>Água</b><br>Líquido &amp; vida", defiFormat="h")
        yield SimpleNamespace(isData=lambda:True)
        yield SimpleNamespace(isData=lambda:False, l_term=["água"], defi="Outro sentido", defiFormat="m")

class BglTests(unittest.TestCase):
    def test_text(self):
        self.assertEqual(plain_text("<b>Água</b><br>Líquido &amp; vida<script>bad</script>"), "Água\nLíquido & vida")
    def test_import(self):
        from verbum.importers import import_dictionary
        @contextmanager
        def fake(path):
            yield FakeGlossary()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Aurelio_pt_pt.BGL"
            path.write_bytes(b"\x12\x34\x00\x01\x00\x06")
            reg = Registry(root / "data")
            with patch("verbum.bgl.open_glossary", fake):
                result = import_dictionary(reg, None, path, "bgl")
                self.assertEqual(result["slug"], "pt-br-aurelio-general")
                self.assertEqual(result["entries"], 2)
                hits = reg.search("água", mode="exact")
                self.assertEqual(len(hits), 2)
                self.assertEqual(hits[0]["entry"]["variants"], ["agua"])
                self.assertIn("<b>", hits[0]["entry"]["source"]["definition"])
                self.assertEqual(result["source_format"], "bgl")
                self.assertEqual(import_dictionary(reg,None,path,"bgl",rebuild=result["slug"])["id"], result["id"])
            self.assertTrue(path.exists())
    def test_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"invalid.bgl"
            path.write_bytes(b"invalid")
            with self.assertRaises(ValueError):
                validate_source(path)
