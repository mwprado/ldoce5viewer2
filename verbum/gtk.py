"""Native GTK4/libadwaita frontend for Verbum."""
import concurrent.futures
import tempfile
import tomllib
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .core import Registry
from .catalog import catalog_list
from .importers import IMPORT_FORMATS, import_dictionary
from .media import get_media

APP_ID = "io.github.mwprado.Verbum"

def label(text="", css=None):
    w = Gtk.Label(label=str(text), xalign=0, wrap=True, selectable=True)
    if css:
        w.add_css_class(css)
    return w

def scroll(child):
    w = Gtk.ScrolledWindow()
    w.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    w.set_child(child)
    return w

def button(text, callback):
    w = Gtk.Button(label=text)
    w.connect("clicked", callback)
    return w

def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())

def values(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []

class Window(Adw.ApplicationWindow):
    def __init__(self, app, registry):
        super().__init__(application=app, title="Verbum", default_width=1100, default_height=740)
        self.registry = registry
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.generation = 0
        self.detail_generation = 0
        self.timeout = 0
        self.closed = False
        self.importing = False
        self.audio = None
        self.audio_path = None
        self.temp = tempfile.TemporaryDirectory(prefix="verbum-audio-")
        self.connect("close-request", self.on_close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(outer)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Verbum"))
        header.pack_start(button("Biblioteca", self.show_catalog))
        self.import_button = button("Importar", self.show_import_dialog)
        header.pack_end(self.import_button)
        outer.append(header)
        self.status = label("Consulte os dicionários locais.")
        self.status.set_margin_start(12)
        self.status.set_margin_end(12)
        self.status.set_margin_bottom(8)
        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=320, vexpand=True)
        outer.append(pane)
        outer.append(self.status)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12, margin_top=12, margin_bottom=12)
        pane.set_start_child(left)
        pane.set_resize_start_child(False)
        pane.set_shrink_start_child(False)
        self.search = Gtk.SearchEntry(placeholder_text="Pesquisar palavra…")
        left.append(self.search)
        self.dictionary = Gtk.DropDown()
        left.append(self.dictionary)
        self.mode = Gtk.DropDown.new_from_strings(["Prefixo", "Exata", "Texto integral"])
        left.append(self.mode)
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.results.add_css_class("boxed-list")
        self.results.connect("row-selected", self.select_result)
        sc = scroll(self.results)
        sc.set_vexpand(True)
        left.append(sc)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_start=24, margin_end=24, margin_top=20, margin_bottom=20)
        pane.set_end_child(scroll(self.detail))
        self.search.connect("search-changed", self.schedule_search)
        self.dictionary.connect("notify::selected", self.schedule_search)
        self.mode.connect("notify::selected", self.schedule_search)
        self.refresh_dictionaries()
        self.detail.append(label("Pesquise uma palavra ou importe um dicionário.", "title-2"))

    def refresh_dictionaries(self):
        self.manifests = self.registry.list()
        self.dictionary.set_model(Gtk.StringList.new(["Todos os dicionários"] + [m["title"] for m in self.manifests]))
        self.dictionary.set_selected(0)

    def work(self, fn, done):
        future = self.pool.submit(fn)
        def finish(f):
            def deliver():
                if not self.closed:
                    try:
                        result = f.result()
                    except Exception as exc:
                        done(None, exc)
                    else:
                        done(result, None)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(deliver)
        future.add_done_callback(finish)

    def schedule_search(self, *_):
        self.generation += 1
        if self.timeout:
            GLib.source_remove(self.timeout)
        self.timeout = GLib.timeout_add(180, self.run_search)

    def run_search(self):
        self.timeout = 0
        query = self.search.get_text().strip()
        generation = self.generation
        idx = self.dictionary.get_selected()
        selected = self.manifests[idx-1]["slug"] if 0 < idx <= len(self.manifests) else None
        mode = ("prefix", "exact", "fulltext")[self.mode.get_selected()]
        if not query:
            clear(self.results)
            self.status.set_text("Digite uma palavra.")
            return GLib.SOURCE_REMOVE
        self.status.set_text("Pesquisando…")
        def find():
            return self.registry.search(query, mode=mode, limit=100, dictionary=selected)
        def complete(hits, error):
            if generation != self.generation:
                return
            clear(self.results)
            if error:
                self.status.set_text(str(error))
                return
            for hit in hits:
                row = Gtk.ListBoxRow()
                row.hit = hit
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_start=10, margin_end=10, margin_top=6, margin_bottom=6)
                box.append(label(hit["entry"]["lemma"], "heading"))
                box.append(label(hit["dictionary"], "dim-label"))
                row.set_child(box)
                self.results.append(row)
            self.status.set_text(f"{len(hits)} resultado(s), máximo 100.")
            if hits:
                self.results.select_row(self.results.get_row_at_index(0))
            else:
                self.reset_detail()
                self.detail.append(label("Nenhum resultado encontrado."))
        self.work(find, complete)
        return GLib.SOURCE_REMOVE

    def stop_audio(self):
        if self.audio:
            self.audio.pause()
            self.audio = None
        if self.audio_path:
            self.audio_path.unlink(missing_ok=True)
            self.audio_path = None

    def reset_detail(self):
        self.detail_generation += 1
        self.stop_audio()
        clear(self.detail)

    def select_result(self, _list, row):
        if row is None:
            return
        self.reset_detail()
        hit = row.hit
        e = hit["entry"]
        self.detail.append(label(e["lemma"], "title-1"))
        self.detail.append(label(hit["dictionary"], "dim-label"))
        grammar = e.get("grammar", {})
        if isinstance(grammar, dict):
            parts = values(grammar.get("pos")) + values(grammar.get("notes"))
            if parts:
                self.detail.append(label(" · ".join(parts), "caption"))
        variants = values(e.get("variants"))
        if variants:
            self.detail.append(label("Variantes: " + ", ".join(variants)))
        media = e.get("media", [])
        if isinstance(media, list) and media:
            self.detail.append(label("Pronúncias e imagens", "heading"))
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3)
            self.detail.append(flow)
            self.media_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for index, ref in enumerate(media):
                if not isinstance(ref, dict):
                    continue
                archive = ref.get("archive")
                names = {"gb_hwd_pron":"Ouvir britânico", "us_hwd_pron":"Ouvir americano", "exa_pron":"Ouvir exemplo", "sfx":"Ouvir som", "sound":"Ouvir áudio", "picture":"Ver imagem"}
                if archive not in names:
                    continue
                title = names[archive]
                if archive in ("exa_pron", "picture"):
                    title += f" {index+1}"
                flow.insert(button(title, lambda _, i=index: self.load_media(hit, i)), -1)
                if archive == "picture" and ref.get("fullsize"):
                    flow.insert(button("Imagem integral", lambda _, i=index: self.load_media(hit, i, True)), -1)
            self.detail.append(self.media_area)
        senses = e.get("senses", [])
        rendered = False
        if isinstance(senses, list):
            for n, sense in enumerate(senses, 1):
                if not isinstance(sense, dict):
                    continue
                definitions = values(sense.get("definitions"))
                examples = values(sense.get("examples"))
                if definitions or examples:
                    rendered = True
                    self.detail.append(label(f"Acepção {n}", "heading"))
                    for text in definitions:
                        self.detail.append(label(text))
                    for text in examples:
                        self.detail.append(label("• " + text, "dim-label"))
        if not rendered:
            for text in values(e.get("definition")) + values(e.get("definitions")):
                self.detail.append(label(text))
            for text in values(e.get("examples")):
                self.detail.append(label("• " + text, "dim-label"))

    def load_media(self, hit, index, fullsize=False):
        generation = self.detail_generation
        self.media_generation = getattr(self, "media_generation", 0) + 1
        request = self.media_generation
        self.stop_audio()
        clear(self.media_area)
        self.media_area.append(label("Carregando recurso…"))
        def complete(result, error):
            if generation != self.detail_generation or request != self.media_generation:
                return
            clear(self.media_area)
            if error:
                self.media_area.append(label(str(error)))
                return
            data, mime = result
            try:
                if mime.startswith("audio/"):
                    with tempfile.NamedTemporaryFile(dir=self.temp.name, suffix=".mp3", delete=False) as out:
                        out.write(data)
                        self.audio_path = Path(out.name)
                    self.audio = Gtk.MediaFile.new_for_filename(str(self.audio_path))
                    controls = Gtk.MediaControls(media_stream=self.audio)
                    self.media_area.append(controls)
                    self.audio.connect("notify::error", self.audio_error)
                    self.audio.play()
                elif mime.startswith("image/"):
                    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                    picture = Gtk.Picture.new_for_paintable(texture)
                    picture.set_can_shrink(True)
                    picture.set_size_request(-1, 180)
                    self.media_area.append(picture)
            except Exception as exc:
                self.media_area.append(label(str(exc)))
        self.work(lambda: get_media(self.registry, hit["dictionary"], hit["entry_id"], index, fullsize), complete)

    def audio_error(self, stream, _):
        if stream is self.audio and stream.get_error():
            self.status.set_text(str(stream.get_error()))

    def show_catalog(self, *_):
        self.generation += 1
        if self.timeout:
            GLib.source_remove(self.timeout)
            self.timeout = 0
        self.reset_detail()
        self.detail.append(label("Biblioteca de dicionários", "title-1"))
        for m in catalog_list(self.registry):
            self.detail.append(label(m["title"], "heading"))
            d = m["distribution"]
            state = "Instalado" if m["installed"] else ("Importável" if d.get("importer") in {fmt["id"] for fmt in IMPORT_FORMATS} else "Planejado")
            self.detail.append(label(f'{m["language"]} · {m["origin"]} · {m["function"]} · {state}', "dim-label"))
        self.detail.append(label("As fontes web e os demais importadores ainda não estão ativos."))

    def show_import_dialog(self, *_):
        if self.importing:
            return
        if getattr(self, "import_dialog", None):
            self.import_dialog.present()
            return
        dialog = Adw.MessageDialog(transient_for=self, heading="Importar dicionário",
            body="Selecione o formato da fonte que deseja importar.")
        self.import_dialog = dialog
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.import_format = Gtk.DropDown.new_from_strings([fmt["title"] for fmt in IMPORT_FORMATS])
        box.append(self.import_format)
        self.import_description = label(IMPORT_FORMATS[0]["description"], "dim-label")
        box.append(self.import_description)
        self.import_format.connect("notify::selected", lambda *_:
            self.import_description.set_text(IMPORT_FORMATS[self.import_format.get_selected()]["description"]))
        pending = [m["title"] for m in catalog_list(self.registry, method="import")
                   if m["distribution"].get("importer") not in {fmt["id"] for fmt in IMPORT_FORMATS}]
        if pending:
            box.append(label("Importadores em desenvolvimento: " + ", ".join(pending), "caption"))
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("next", "Continuar")
        dialog.set_default_response("next")
        dialog.set_close_response("cancel")
        def response(_, choice):
            fmt = IMPORT_FORMATS[self.import_format.get_selected()]
            self.import_dialog = None
            if choice == "next":
                self.choose_source(fmt)
        dialog.connect("response", response)
        dialog.present()

    def choose_source(self, fmt):
        action = Gtk.FileChooserAction.SELECT_FOLDER if fmt["directory"] else Gtk.FileChooserAction.OPEN
        self.choose_file("Selecione a fonte — " + fmt["title"], action,
                         lambda path: self.choose_manifest(fmt, path) if fmt["manifest"]
                         else self.confirm_import(fmt, path))

    def choose_file(self, title, action, callback):
        chooser = Gtk.FileChooserNative(title=title, transient_for=self, action=action,
                                        accept_label="Selecionar", cancel_label="Cancelar")
        self.source_chooser = chooser
        def response(dialog, code):
            file = dialog.get_file() if code == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            dialog.destroy()
            self.source_chooser = None
            if path:
                callback(path)
        chooser.connect("response", response)
        chooser.show()

    def choose_manifest(self, fmt, path):
        self.choose_file("Selecione o manifesto TOML", Gtk.FileChooserAction.OPEN,
                         lambda manifest: self.confirm_import(fmt, path, manifest))

    def confirm_import(self, fmt, path, manifest=None):
        dialog = Adw.MessageDialog(transient_for=self, heading="Confirmar importação",
            body=fmt["title"] + "\n" + path +
            "\n\nImportar esta fonte para a biblioteca do Verbum? Os arquivos originais permanecerão inalterados.")
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("import", "Importar")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _, response: self.start_import(fmt, path, manifest)
                       if response == "import" else None)
        dialog.present()

    def start_import(self, fmt, path, manifest=None):
        if self.importing:
            return
        self.importing = True
        self.import_button.set_sensitive(False)
        self.status.set_text("Importando e indexando " + fmt["title"] + "…")
        def complete(result, error):
            self.importing = False
            self.import_button.set_sensitive(True)
            if error:
                self.status.set_text(str(error))
            else:
                self.refresh_dictionaries()
                self.status.set_text(f'Importação concluída: {result["entries"]} entradas.')
        def run():
            metadata = None
            if manifest:
                with Path(manifest).open("rb") as stream:
                    metadata = tomllib.load(stream)
            return import_dictionary(self.registry, metadata, path, fmt["id"])
        self.work(run, complete)

    def on_close(self, *_):
        if self.importing:
            self.status.set_text("Aguarde a conclusão da importação antes de fechar.")
            return True
        self.closed = True
        if self.timeout:
            GLib.source_remove(self.timeout)
        self.stop_audio()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.temp.cleanup()
        return False

class Application(Adw.Application):
    def __init__(self, root=None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.registry = Registry(root)

    def do_activate(self):
        window = self.get_active_window() or Window(self, self.registry)
        window.present()

def main(root=None):
    return Application(root).run(["verbum"])

if __name__ == "__main__":
    raise SystemExit(main())
