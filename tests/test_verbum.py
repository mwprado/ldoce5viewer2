import tempfile
import unittest
from pathlib import Path
from verbum.core import Registry

class VerbumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Registry(self.tmp.name)
        self.meta = dict(title="Synthetic test", language="pt-br", origin="test", function="general", license="CC0")

    def test_import_and_search(self):
        result = self.registry.import_entries(self.meta, [
            {"lemma": "Água", "definition": "líquido"},
            {"lemma": "água", "definition": "outro sentido"},
            {"lemma": "aguaceiro"},
        ])
        self.assertEqual(result["entries"], 3)
        self.assertTrue(Path(result["path"]).is_file())
        self.assertEqual(len(self.registry.search("A\u0301GUA", mode="exact")), 2)
        self.assertEqual(len(self.registry.search("águ")), 2)
        self.assertEqual(len(self.registry.search("líquido", mode="fulltext")), 1)
        self.assertEqual(self.registry.search("água", language="en"), [])
        self.assertEqual(len(Registry(self.tmp.name).list()), 1)
        with self.assertRaises(Exception):
            self.registry.import_entries(self.meta, [{"lemma":"duplicate"}])
        self.assertEqual(len(self.registry.search("água", mode="exact")), 2)

    def test_failed_import(self):
        with self.assertRaises(ValueError):
            self.registry.import_entries(self.meta, [{"lemma":"ok"}, {}])
        self.assertEqual(self.registry.list(), [])
        self.assertFalse(list(Path(self.tmp.name).rglob("*.vlf")))

    def test_independent_languages(self):
        self.registry.import_entries(self.meta, [{"lemma":"água"}])
        self.registry.import_entries(dict(self.meta, language="en", origin="test-en"), [{"lemma":"water"}])
        self.assertEqual(len(self.registry.list()), 2)
        self.assertEqual(len(self.registry.search("water", language="en")), 1)

    def test_catalog(self):
        from verbum.catalog import catalog_list
        rows = catalog_list(self.registry, origin="longman")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["installed"])
        self.assertTrue(rows[0]["distribution"]["requires_original"])
        self.assertFalse(rows[0]["distribution"]["redistributable"])
        self.assertEqual(rows[0]["id"], catalog_list(self.registry, origin="longman")[0]["id"])

    def test_distribution_policy(self):
        from verbum.catalog import distribution_info
        with self.assertRaises(ValueError):
            distribution_info(dict(license_type="proprietary", distribution={"method":"download", "redistributable":True}))
        with self.assertRaises(ValueError):
            distribution_info(dict(license_type="open", distribution={"method":"download", "redistributable":True}))
        policy = distribution_info(dict(license_type="public-domain", license_reference="synthetic test", distribution={"method":"download", "redistributable":True, "url":"https://example.org/test.vlf", "sha256":"a"*64}))
        self.assertEqual(policy["method"], "download")

    def test_proprietary_json_rejected(self):
        from verbum.importers import import_dictionary
        with self.assertRaises(ValueError):
            import_dictionary(self.registry, dict(self.meta, license_type="proprietary"), "unused.json")

    def test_cli_import_without_attestation(self):
        import contextlib
        import io
        from verbum.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "entries.json").write_text('[{"lemma":"sample"}]', encoding="utf-8")
            (root / "manifest.toml").write_text(
                'title="Demo"\nlanguage="en"\norigin="demo"\nfunction="general"\nlicense="CC0"\n',
                encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--root", str(root / "data"), "import",
                             str(root / "entries.json"), "--manifest", str(root / "manifest.toml")])
            self.assertEqual(code, 0)
            self.assertEqual(len(Registry(root / "data").list()), 1)

    def test_import_progress_cancel_and_duplicate(self):
        from threading import Event
        from verbum.core import ImportCancelled, DictionaryAlreadyInstalled
        events = []
        cancel = Event()
        def report(stage, count, total):
            events.append((stage, count, total))
            if stage == "index" and count == 128:
                cancel.set()
        with self.assertRaises(ImportCancelled):
            self.registry.import_entries(self.meta, ({"lemma":str(i)} for i in range(200)),
                                         total=200, progress=report, cancel=cancel)
        self.assertEqual(self.registry.list(), [])
        self.assertFalse(list(Path(self.tmp.name).rglob("*.vlf")))
        self.assertIn(("index", 128, 200), events)
        events.clear()
        self.registry.import_entries(self.meta, [{"lemma":"original"}], total=1,
                                     progress=lambda *args: events.append(args))
        self.assertIn(("verify", 1, 1), events)
        self.assertIn(("publish", 1, 1), events)
        def should_not_read():
            self.fail("Duplicate import consumed entries")
            yield {}
        with self.assertRaises(DictionaryAlreadyInstalled):
            self.registry.import_entries(self.meta, should_not_read())
        self.assertEqual(len(self.registry.search("original")), 1)

    def test_rebuild_preserves_identity_and_old_on_failure(self):
        original = self.registry.import_entries(self.meta, [{"lemma":"old"}])
        slug = original["slug"]
        with self.assertRaises(ValueError):
            self.registry.import_entries(self.meta, [{}], rebuild=slug)
        self.assertEqual(len(self.registry.search("old")), 1)
        new = self.registry.import_entries(self.meta, [{"lemma":"new"}], rebuild=slug)
        self.assertEqual(original["id"], new["id"])
        self.assertNotEqual(original["path"], new["path"])
        self.assertEqual(len(self.registry.list()), 1)
        self.assertEqual(self.registry.search("old"), [])
        self.assertEqual(len(self.registry.search("new")), 1)
        self.assertTrue(Path(original["path"]).exists())
        with self.assertRaises(ValueError):
            self.registry.import_entries(dict(self.meta, origin="other"), [{"lemma":"bad"}], rebuild=slug)

    def test_smart_search(self):
        self.registry.import_entries(dict(self.meta, language="en"), [
            {"lemma":"home"}, {"lemma":"homework"}, {"lemma":"house"}, {"lemma":"hone"},
            {"lemma":"receive"}, {"lemma":"water"}, {"lemma":"Água"}])
        hits = self.registry.search("home")
        self.assertEqual(hits[0]["match"], "exact")
        self.assertEqual(hits[0]["entry"]["lemma"], "home")
        self.assertEqual(hits[1]["entry"]["lemma"], "homework")
        self.assertIn("hone", [h["entry"]["lemma"] for h in hits])
        self.assertEqual(self.registry.search("recieve")[0]["entry"]["lemma"], "receive")
        self.assertEqual(self.registry.search("agua")[0]["entry"]["lemma"], "Água")
        self.assertEqual(self.registry.search("home", mode="exact")[0]["entry"]["lemma"], "home")

if __name__ == "__main__":
    unittest.main()
