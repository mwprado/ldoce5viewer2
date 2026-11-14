"""Native GTK4/libadwaita frontend for Verbum."""
import concurrent.futures
import tempfile
import tomllib
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .core import Registry, ImportCancelled, DictionaryAlreadyInstalled
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
        # GNOME split-view pattern: distinct sidebar and content header bars.
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(outer)
        self.set_content(self.toast_overlay)
        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=300, vexpand=True, hexpand=True)
        pane.add_css_class("sidebar-pane")
        outer.append(pane)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.add_css_class("sidebar")
        left.set_size_request(240, -1)
        pane.set_start_child(left)
        pane.set_resize_start_child(False)
        pane.set_shrink_start_child(False)
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_header.set_title_widget(Adw.WindowTitle(title="Verbum"))
        left.append(sidebar_header)
        library = Gtk.Button(icon_name="view-list-symbolic", tooltip_text="Biblioteca")
        library.connect("clicked", self.show_catalog)
        sidebar_header.pack_start(library)
        self.import_button = button("Importar", self.show_import_dialog)
        sidebar_header.pack_end(self.import_button)
        filters = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                          margin_start=12, margin_end=12, margin_top=6, margin_bottom=8)
        left.append(filters)
        self.search = Gtk.SearchEntry(placeholder_text="Pesquisar palavra…")
        filters.append(self.search)
        self.dictionary = Gtk.DropDown()
        filters.append(self.dictionary)
        self.mode = Gtk.DropDown.new_from_strings(["Prefixo", "Exata", "Texto integral"])
        filters.append(self.mode)
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.results.add_css_class("navigation-sidebar")
        self.results.connect("row-selected", self.select_result)
        sc = scroll(self.results)
        sc.set_vexpand(True)
        left.append(sc)
        self.status = label("Consulte os dicionários locais.", "dim-label")
        self.status.set_selectable(False)
        self.status.set_margin_start(12)
        self.status.set_margin_end(12)
        self.status.set_margin_top(8)
        self.status.set_margin_bottom(12)
        left.append(self.status)
        self.import_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                    margin_start=12, margin_end=12, margin_bottom=12)
        self.import_panel.set_visible(False)
        left.append(self.import_panel)
        self.import_title = label("", "heading")
        self.import_title.set_selectable(False)
        self.import_panel.append(self.import_title)
        self.import_progress = Gtk.ProgressBar(show_text=False)
        self.import_panel.append(self.import_progress)
        self.import_status = label("", "dim-label")
        self.import_status.set_selectable(False)
        self.import_panel.append(self.import_status)
        self.cancel_import_button = button("Cancelar importação", self.cancel_import)
        self.import_panel.append(self.cancel_import_button)
        self.import_timer = 0
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        pane.set_end_child(right)
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        self.content_title = Adw.WindowTitle(title="Dicionário")
        header.set_title_widget(self.content_title)
        right.append(header)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                              margin_start=24, margin_end=24, margin_top=24, margin_bottom=32)
        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=580)
        clamp.set_child(self.detail)
        content_scroll = scroll(clamp)
        content_scroll.set_vexpand(True)
        right.append(content_scroll)
        self.set_default_widget(self.search)
        self.search.connect("search-changed", self.schedule_search)
        self.dictionary.connect("notify::selected", self.schedule_search)
        self.mode.connect("notify::selected", self.schedule_search)
        self.refresh_dictionaries()
        self.show_empty()

    def show_empty(self, title="Pesquisar palavras", description="Digite uma palavra ou importe um dicionário para começar."):
        self.reset_detail()
        self.content_title.set_title("Dicionário")
        page = Adw.StatusPage(icon_name="system-search-symbolic", title=title, description=description)
        self.detail.append(page)

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
            self.show_empty()
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
                word = label(hit["entry"]["lemma"])
                word.set_selectable(False)
                box.append(word)
                source = label(next((m["title"] for m in self.manifests if m["slug"] == hit["dictionary"]), hit["dictionary"]), "dim-label")
                source.set_selectable(False)
                box.append(source)
                row.set_child(box)
                self.results.append(row)
            self.status.set_text(f"{len(hits)} resultado(s), máximo 100.")
            if hits:
                self.results.select_row(self.results.get_row_at_index(0))
            else:
                self.show_empty("Nenhum resultado", "Tente outra palavra ou modo de pesquisa.")
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
        self.content_title.set_title("Verbum")
        self.detail.append(label(e["lemma"], "title-1"))
        self.detail.append(label(next((m["title"] for m in self.manifests if m["slug"] == hit["dictionary"]), hit["dictionary"]), "dim-label"))
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
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, homogeneous=False, row_spacing=6, column_spacing=6, halign=Gtk.Align.START)
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
                control = Gtk.Button(tooltip_text=title)
                content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                content.append(Gtk.Image.new_from_icon_name("audio-volume-high-symbolic" if archive != "picture" else "image-x-generic-symbolic"))
                content.append(Gtk.Label(label=title))
                control.set_child(content)
                control.add_css_class("flat")
                control.connect("clicked", lambda _, i=index: self.load_media(hit, i))
                flow.insert(control, -1)
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
                    self.detail.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
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
        self.content_title.set_title("Biblioteca")
        self.detail.append(label("Biblioteca de dicionários", "title-1"))
        group = Adw.PreferencesGroup(title="Dicionários disponíveis")
        self.detail.append(group)
        for m in catalog_list(self.registry):
            d = m["distribution"]
            state = "Instalado" if m["installed"] else ("Importável" if d.get("importer") in {fmt["id"] for fmt in IMPORT_FORMATS} else "Planejado")
            row = Adw.ActionRow(title=GLib.markup_escape_text(m["title"]), subtitle=f'{m["language"]} · {m["origin"]} · {m["function"]}')
            suffix = Gtk.Label(label=state, valign=Gtk.Align.CENTER)
            suffix.add_css_class("dim-label")
            row.add_suffix(suffix)
            group.add(row)
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
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(title="Formato")
        self.import_format.set_valign(Gtk.Align.CENTER)
        row.add_suffix(self.import_format)
        group.add(row)
        box.append(group)
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

    def cancel_import(self, *_):
        if self.importing and self.import_stage[0] != "publish":
            self.import_cancel.set()
            self.cancel_import_button.set_sensitive(False)
            self.import_status.set_text("Cancelando…")

    def render_import_progress(self):
        if not self.importing:
            self.import_timer = 0
            return GLib.SOURCE_REMOVE
        stage, count, total = self.import_stage
        if stage == "publish":
            self.cancel_import_button.set_sensitive(False)
        if self.import_cancel.is_set() and stage != "publish":
            self.import_status.set_text("Cancelando…")
            return GLib.SOURCE_CONTINUE
        if stage == "index" and total:
            self.import_progress.set_fraction(min(1.0, count / total))
            self.import_status.set_text(f"{count:n} de {total:n} verbetes indexados")
        else:
            self.import_progress.pulse()
            messages = {"prepare": "Lendo arquivos da fonte…",
                        "index": f"{count:n} verbetes indexados",
                        "verify": "Verificando a integridade da base…",
                        "publish": "Registrando o dicionário…"}
            self.import_status.set_text(messages.get(stage, "Importando…"))
        return GLib.SOURCE_CONTINUE

    def start_import(self, fmt, path, manifest=None):
        if self.importing:
            return
        self.importing = True
        self.import_cancel = threading.Event()
        self.import_stage = ("prepare", 0, None)
        self.import_button.set_sensitive(False)
        self.cancel_import_button.set_sensitive(True)
        self.import_title.set_text("Importando " + fmt["title"])
        self.import_progress.set_fraction(0)
        self.import_status.set_text("Lendo arquivos da fonte…")
        self.import_panel.set_visible(True)
        self.import_timer = GLib.timeout_add(120, self.render_import_progress)
        def complete(result, error):
            self.importing = False
            if self.import_timer:
                GLib.source_remove(self.import_timer)
                self.import_timer = 0
            self.import_panel.set_visible(False)
            self.import_button.set_sensitive(True)
            if isinstance(error, ImportCancelled):
                self.toast_overlay.add_toast(Adw.Toast.new("Importação cancelada"))
            elif isinstance(error, DictionaryAlreadyInstalled):
                self.refresh_dictionaries()
                self.toast_overlay.add_toast(Adw.Toast.new("Dicionário já instalado"))
                self.show_catalog()
            elif error:
                dialog = Adw.MessageDialog(transient_for=self, heading="Não foi possível importar",
                                           body=str(error))
                dialog.add_response("close", "Fechar")
                dialog.set_close_response("close")
                dialog.present()
            else:
                self.refresh_dictionaries()
                self.toast_overlay.add_toast(Adw.Toast.new(f'Dicionário importado: {result["entries"]:n} verbetes'))
        def report(stage, count, total):
            # Immutable snapshot; the GTK main thread alone updates widgets.
            self.import_stage = (stage, count, total)
        def run():
            metadata = None
            if manifest:
                with Path(manifest).open("rb") as stream:
                    metadata = tomllib.load(stream)
            return import_dictionary(self.registry, metadata, path, fmt["id"],
                                     progress=report, cancel=self.import_cancel)
        self.work(run, complete)

    def on_close(self, *_):
        if self.importing:
            self.import_panel.set_visible(True)
            self.import_status.set_text("Cancele a importação ou aguarde a conclusão.")
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
