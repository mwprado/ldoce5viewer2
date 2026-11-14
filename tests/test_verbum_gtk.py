import os
import tempfile
import unittest

@unittest.skipUnless(os.environ.get("VERBUM_GTK_TEST") == "1", "requires GTK display")
class GtkTests(unittest.TestCase):
    def test_window_and_entry(self):
        from verbum.gtk import Application, Window
        from gi.repository import Gtk
        with tempfile.TemporaryDirectory() as root:
            app = Application(root)
            self.assertTrue(app.register(None))
            app.registry.import_entries(dict(title="Demo", language="en", origin="demo",
                function="general", license="CC0"), [{"lemma":"sample","definition":"Synthetic entry"}])
            win = Window(app, app.registry)
            self.assertEqual(win.dictionary.get_model().get_n_items(), 2)
            hit = app.registry.search("sample", dictionary="en-demo-general")[0]
            row = Gtk.ListBoxRow()
            row.hit = hit
            win.select_result(win.results, row)
            self.assertEqual(win.detail.get_first_child().get_text(), "sample")
            win.show_catalog()
            self.assertEqual(win.detail.get_first_child().get_text(), "Biblioteca de dicionários")
            self.assertEqual(win.import_button.get_label(), "Importar")
            win.show_import_dialog()
            self.assertEqual(win.import_format.get_model().get_n_items(), 3)
            win.import_format.set_selected(1)
            self.assertIn("TOML", win.import_description.get_text())
            win.import_dialog.response("cancel")
            self.assertIsNone(win.import_dialog)
            self.assertFalse(win.import_panel.get_visible())
            win.importing = True
            from threading import Event
            win.import_cancel = Event()
            win.import_stage = ("index", 25, 100)
            win.render_import_progress()
            self.assertEqual(win.import_progress.get_fraction(), 0.25)
            win.cancel_import()
            self.assertTrue(win.import_cancel.is_set())
            win.importing = False
            win.on_close()
            win.destroy()
