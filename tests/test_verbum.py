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

if __name__ == "__main__":
    unittest.main()
