import base64
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from verbum.core import Registry
from verbum.importers import import_dictionary
from verbum.longman import parse_entry

XML = b'<Entry id="synthetic.1"><Head><HWD><BASE>sample</BASE><INFLX>samples</INFLX></HWD><POS>noun</POS><Audio resource="GB_HWD_PRON" topic="x/sample.mp3"/></Head><Sense id="s1"><DEF>synthetic definition</DEF><EXAMPLE><BASE>a sample</BASE></EXAMPLE><Subsense id="s2"><DEF>nested definition</DEF></Subsense></Sense><ILLUSTRATION thumb="x/sample.jpg"/></Entry>'

def archive(root, xml=XML, archive_name="fs", filename="synthetic.xml", dirname="root"):
    fs = root / (archive_name + ".skn")
    d, f = fs / "dirs.skn", fs / "files.skn"
    d.mkdir(parents=True)
    f.mkdir()
    (d / "config.cft").write_text("[DAT]\n$parent=ULONG\n")
    (d / "NAME.tda").write_bytes(dirname.encode() + b"\0")
    (d / "dirs.dat").write_bytes(struct.pack("<I", 0))
    (f / "config.cft").write_text("[DAT]\n$content=ULONG\n$a_dirs=ULONG\n")
    (f / "NAME.tda").write_bytes(filename.encode() + b"\0")
    (f / "files.dat").write_bytes(struct.pack("<II", 0, 0))
    data = xml + b"\0"
    compressed = zlib.compress(data)
    (f / "CONTENT.tda").write_bytes(compressed)
    (f / "CONTENT.tda.tdz").write_bytes(struct.pack("<II", len(data), len(compressed)))

class LongmanTests(unittest.TestCase):
    def test_parser(self):
        e = parse_entry(XML, "synthetic.xml")
        self.assertEqual(e["lemma"], "sample")
        self.assertEqual(e["variants"], ["samples"])
        self.assertEqual(e["senses"][0]["definitions"], ["synthetic definition"])
        self.assertEqual(e["senses"][1]["definitions"], ["nested definition"])
        self.assertEqual(e["media"][0]["archive"], "gb_hwd_pron")
        self.assertEqual(base64.b64decode(e["source"]["xml_base64"]), XML)

    def test_native_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "original"
            archive(original)
            reg = Registry(root / "data")
            result = import_dictionary(reg, None, original, "longman")
            self.assertEqual(result["slug"], "en-longman-learner-5")
            self.assertEqual(result["entries"], 1)
            self.assertFalse(result["distribution"]["redistributable"])
            self.assertEqual(reg.search("sample", mode="exact")[0]["entry"]["source_id"], "synthetic.1")
            self.assertEqual(len(reg.search("nested definition", mode="fulltext")), 1)
            self.assertTrue((original / "fs.skn/files.skn/CONTENT.tda").exists())

    def test_invalid_record_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive(root / "original", b"<broken>")
            reg = Registry(root / "data")
            with self.assertRaises(ValueError):
                import_dictionary(reg, None, root / "original", "longman")
            self.assertEqual(reg.list(), [])
            self.assertFalse(list((root / "data").rglob("*.vlf")))

    def test_media_on_demand(self):
        from verbum.media import entry_media, get_media, read_longman_media
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "original"
            archive(original)
            audio = b"ID3synthetic-audio"
            image = b"\xff\xd8\xffsynthetic-image"
            archive(original, audio, "gb_hwd_pron", "sample.mp3")
            archive(original, image, "picture", "sample.jpg", "thumbnail")
            reg = Registry(root / "data")
            result = import_dictionary(reg, None, original, "longman")
            slug = result["slug"]
            hit = reg.search("sample", mode="exact")[0]
            eid = hit["entry_id"]
            self.assertEqual(len(entry_media(reg, slug, eid)[1]), 2)
            self.assertEqual(get_media(reg, slug, eid, 0), (audio, "audio/mpeg"))
            self.assertEqual(get_media(reg, slug, eid, 1), (image, "image/jpeg"))
            with self.assertRaises(ValueError):
                get_media(reg, slug, eid, -1)
            with self.assertRaises(ValueError):
                read_longman_media(original, "picture", "../sample.jpg")
            with self.assertRaises(ValueError):
                get_media(reg, slug, eid, 1, fullsize=True)
