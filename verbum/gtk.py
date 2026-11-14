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
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .core import Registry, ImportCancelled, DictionaryAlreadyInstalled
from .catalog import catalog_list
from .importers import IMPORT_FORMATS, import_dictionary
from .media import get_media
from .result_labels import result_labels

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
        # Nautilus-inspired navigation: one sidebar and a content header.
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(outer)
        self.set_content(self.toast_overlay)
        self.preferences = None
        self.history = []
        self.history_position = -1
        self.restoring_history = False
        self.refreshing_filters = False
        self.pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=250,
                              vexpand=True, hexpand=True)
        outer.append(self.pane)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar = left
        left.add_css_class("sidebar")
        left.set_size_request(200, -1)
        self.pane.set_start_child(left)
        self.pane.set_resize_start_child(False)
        self.pane.set_shrink_start_child(False)
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        self.content_title = Adw.WindowTitle(title="Verbum")
        sidebar_header.set_title_widget(self.content_title)
        left.append(sidebar_header)
        heading = label("Dicionários", "heading")
        heading.set_selectable(False)
        heading.set_margin_start(16)
        heading.set_margin_top(12)
        heading.set_margin_bottom(6)
        left.append(heading)
        self.dictionary = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.dictionary.add_css_class("navigation-sidebar")
        self.dictionary.connect("row-selected", self.on_dictionary_selected)
        sc = scroll(self.dictionary)
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
        self.pane.set_end_child(right)
        header = Adw.HeaderBar()
        self.header = header
        header.set_show_start_title_buttons(False)
        self.back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Consulta anterior", sensitive=False)
        self.forward = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Próxima consulta", sensitive=False)
        self.back.connect("clicked", lambda *_: self.navigate_history(-1))
        self.forward.connect("clicked", lambda *_: self.navigate_history(1))
        header.pack_start(self.back)
        header.pack_start(self.forward)
        self.search = Gtk.SearchEntry(placeholder_text="Pesquisar palavra…", hexpand=True,
                                      width_chars=24)
        header.set_title_widget(self.search)
        menu = Gio.Menu()
        def add_action(name, callback):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            return action
        self.import_action = add_action("import", self.show_import_dialog)
        add_action("preferences", self.show_preferences)
        add_action("new-window", lambda *_: self.get_application().new_window())
        add_action("about", self.show_about)
        add_action("fullscreen", lambda *_: self.unfullscreen() if self.is_fullscreen() else self.fullscreen())
        sidebar_action = Gio.SimpleAction.new_stateful("sidebar", None, GLib.Variant.new_boolean(True))
        def toggle_sidebar(action, _):
            visible = not action.get_state().get_boolean()
            self.sidebar.set_visible(visible)
            action.set_state(GLib.Variant.new_boolean(visible))
        sidebar_action.connect("activate", toggle_sidebar)
        self.add_action(sidebar_action)
        for items in [
            [("Nova janela", "win.new-window"), ("Importar dicionário…", "win.import")],
            [("Mostrar barra lateral", "win.sidebar"), ("Tela cheia", "win.fullscreen")],
            [("Preferências", "win.preferences"), ("Sobre o Verbum", "win.about")],
        ]:
            section = Gio.Menu()
            for title, action in items:
                section.append(title, action)
            menu.append_section(None, section)
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                          tooltip_text="Menu principal")
        header.pack_end(self.menu_button)
        right.append(header)
        self.filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                               margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        self.language = Gtk.DropDown()
        self.language.set_tooltip_text("Idioma dos dicionários")
        self.kind = Gtk.DropDown()
        self.kind.set_tooltip_text("Tipo de dicionário")
        self.filters.append(self.language)
        self.filters.append(self.kind)
        right.append(self.filters)
        right.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        # Flow of compact selectable results above the entry, never another sidebar.
        self.results = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                   min_children_per_line=1, max_children_per_line=8,
                                   row_spacing=4, column_spacing=4,
                                   margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        self.results.connect("selected-children-changed", self.on_result_selected)
        result_scroll = Gtk.ScrolledWindow(max_content_height=132, propagate_natural_height=True)
        result_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        result_scroll.set_child(self.results)
        self.result_scroll = result_scroll
        result_scroll.set_visible(False)
        right.append(result_scroll)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                              margin_start=24, margin_end=24, margin_top=24, margin_bottom=32)
        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=580)
        clamp.set_child(self.detail)
        content_scroll = scroll(clamp)
        content_scroll.set_vexpand(True)
        right.append(content_scroll)
        self.search.connect("search-changed", self.schedule_search)
        self.language.connect("notify::selected", self.on_filter_changed)
        self.kind.connect("notify::selected", self.on_filter_changed)
        self.search.connect("activate", lambda *_: self.run_search_now())
        self.refresh_dictionaries()
        self.show_empty()

    def show_empty(self, title="Pesquisar palavras", description="Digite uma palavra ou importe um dicionário para começar."):
        self.reset_detail()
        self.content_title.set_title("Verbum")
        page = Adw.StatusPage(icon_name="system-search-symbolic", title=title, description=description)
        self.detail.append(page)

    LANGUAGE_NAMES = {"en":"Inglês", "pt":"Português", "pt-br":"Português (Brasil)",
                      "pt-pt":"Português (Portugal)", "es":"Espanhol", "fr":"Francês",
                      "it":"Italiano", "de":"Alemão", "la":"Latim", "tupi":"Tupi"}
    KIND_NAMES = {"general":"Definições", "learner":"Aprendizagem", "orthographic":"Ortográficos",
                  "synonyms":"Sinônimos e antônimos", "bilingual":"Bilíngues",
                  "etymological":"Etimológicos", "regency":"Regência", "phonetic":"Fonéticos",
                  "encyclopedic":"Enciclopédicos"}

    def filter_value(self, widget, keys):
        index = widget.get_selected()
        return keys[index] if index < len(keys) else None

    def selected_dictionary(self):
        row = self.dictionary.get_selected_row()
        return getattr(row, "slug", None)

    def refresh_dictionaries(self):
        old_language = self.filter_value(self.language, getattr(self, "language_keys", []))
        old_kind = self.filter_value(self.kind, getattr(self, "kind_keys", []))
        old_dictionary = self.selected_dictionary()
        self.manifests = self.registry.list()
        self.refreshing_filters = True
        self.language_keys = [None] + sorted({v for m in self.manifests for v in [m["language"], *m.get("languages", [])]})
        self.kind_keys = [None] + sorted({v for m in self.manifests for v in [m["function"], *m.get("functions", [])]})
        self.language.set_model(Gtk.StringList.new(["Todos os idiomas"] + [self.LANGUAGE_NAMES.get(v,v) for v in self.language_keys[1:]]))
        self.kind.set_model(Gtk.StringList.new(["Todos os tipos"] + [self.KIND_NAMES.get(v,v) for v in self.kind_keys[1:]]))
        self.language.set_selected(self.language_keys.index(old_language) if old_language in self.language_keys else 0)
        self.kind.set_selected(self.kind_keys.index(old_kind) if old_kind in self.kind_keys else 0)
        self.refreshing_filters = False
        self.populate_sidebar(old_dictionary)

    def populate_sidebar(self, preferred=None):
        language = self.filter_value(self.language, self.language_keys)
        kind = self.filter_value(self.kind, self.kind_keys)
        self.refreshing_filters = True
        clear(self.dictionary)
        selected = None
        for m in [None] + self.registry.list(language=language, function=kind):
            row = Gtk.ListBoxRow()
            row.slug = m["slug"] if m else None
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
            box.append(Gtk.Image.new_from_icon_name("x-office-address-book-symbolic" if m else "view-list-symbolic"))
            title = Gtk.Label(label=m["title"] if m else "Todos", xalign=0, ellipsize=Pango.EllipsizeMode.END)
            box.append(title)
            row.set_child(box)
            self.dictionary.append(row)
            if row.slug == preferred:
                selected = row
        self.dictionary.select_row(selected or self.dictionary.get_row_at_index(0))
        self.refreshing_filters = False
        self.schedule_search()

    def on_filter_changed(self, *_):
        if not self.refreshing_filters:
            self.populate_sidebar(self.selected_dictionary())

    def on_dictionary_selected(self, *_):
        if not self.refreshing_filters:
            self.schedule_search()

    def on_result_selected(self, box):
        children = box.get_selected_children()
        if children:
            self.select_result(box, children[0])

    def run_search_now(self):
        if self.timeout:
            GLib.source_remove(self.timeout)
            self.timeout = 0
        self.generation += 1
        self.run_search()

    def remember_hit(self, hit):
        if self.restoring_history:
            return
        state = (self.search.get_text(), hit)
        if self.history_position >= 0:
            last = self.history[self.history_position]
            if last[0] == state[0] and last[1]["dictionary"] == hit["dictionary"] and last[1]["entry_id"] == hit["entry_id"]:
                return
        self.history = self.history[:self.history_position+1] + [state]
        self.history_position = len(self.history)-1
        self.update_history_buttons()

    def update_history_buttons(self):
        self.back.set_sensitive(self.history_position > 0)
        self.forward.set_sensitive(self.history_position + 1 < len(self.history))

    def navigate_history(self, direction):
        target = self.history_position + direction
        if not 0 <= target < len(self.history):
            return
        self.history_position = target
        query, hit = self.history[target]
        self.restoring_history = True
        try:
            self.search.set_text(query)
            if self.timeout:
                GLib.source_remove(self.timeout)
                self.timeout = 0
            self.generation += 1
            clear(self.results)
            self.result_scroll.set_visible(False)
            row = Gtk.FlowBoxChild()
            row.hit = hit
            self.select_result(self.results, row)
        finally:
            self.restoring_history = False
        self.update_history_buttons()

    def show_about(self, *_):
        from . import __version__
        dialog = Adw.AboutWindow(transient_for=self, application_name="Verbum",
                                 application_icon=APP_ID,
                                 version=__version__, developer_name="Verbum",
                                 website="https://github.com/mwprado/verbum")
        dialog.present()

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
        selected = self.selected_dictionary()
        language = self.filter_value(self.language, self.language_keys)
        kind = self.filter_value(self.kind, self.kind_keys)
        if not query:
            clear(self.results)
            self.result_scroll.set_visible(False)
            self.show_empty()
            self.status.set_text("Digite uma palavra.")
            return GLib.SOURCE_REMOVE
        self.status.set_text("Pesquisando…")
        def find():
            return self.registry.search(query, mode="smart", limit=100, dictionary=selected, language=language, function=kind)
        def complete(hits, error):
            if generation != self.generation:
                return
            clear(self.results)
            if error:
                self.status.set_text(str(error))
                return
            for hit, (lemma, pos) in zip(hits, result_labels(hits)):
                row = Gtk.FlowBoxChild()
                row.hit = hit
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                              margin_start=10, margin_end=10, margin_top=8, margin_bottom=8)
                word = Gtk.Label(label=lemma, xalign=0)
                word.set_ellipsize(Pango.EllipsizeMode.END)
                box.append(word)
                if pos:
                    grammar = Gtk.Label(xalign=0)
                    grammar.set_markup("<i>(" + GLib.markup_escape_text(pos) + ")</i>")
                    grammar.add_css_class("dim-label")
                    grammar.set_ellipsize(Pango.EllipsizeMode.END)
                    box.append(grammar)
                source = next((m["title"] for m in self.manifests if m["slug"] == hit["dictionary"]), hit["dictionary"])
                row.set_tooltip_text(lemma + (" (" + pos + ")" if pos else "") + "\n" + source)
                row.set_child(box)
                self.results.insert(row, -1)
            if hits and all(h.get("match") == "similar" for h in hits):
                self.status.set_text("Palavras semelhantes encontradas.")
            else:
                self.status.set_text(f"{len(hits)} resultado(s), máximo 100.")
            if hits:
                self.result_scroll.set_visible(True)
                self.results.select_child(self.results.get_child_at_index(0))
            else:
                self.result_scroll.set_visible(False)
                self.show_empty("Nenhum resultado", "Tente outra grafia ou palavra.")
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
        self.active_media_area = None
        clear(self.detail)

    def select_result(self, _list, row):
        if row is None:
            return
        self.reset_detail()
        hit = row.hit
        self.remember_hit(hit)
        e = hit["entry"]
        if isinstance(e.get("source"), dict) and e["source"].get("archive") == "fs":
            from .longman import presentation_entry
            e = presentation_entry(e)
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
        if not isinstance(media, list):
            media = []
        self.active_media_area = None
        used = set()
        pronunciations = e.get("pronunciation_indices")
        if pronunciations is None:
            pronunciations = [i for i, ref in enumerate(media) if isinstance(ref, dict)
                              and ref.get("archive") in ("gb_hwd_pron", "us_hwd_pron")]
        def controls(indices, parent, *, compact=False):
            valid = [i for i in indices if isinstance(i, int) and 0 <= i < len(media)
                     and isinstance(media[i], dict)]
            if not valid:
                return
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                               homogeneous=False, row_spacing=4, column_spacing=4, halign=Gtk.Align.START)
            area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            names = {"gb_hwd_pron":"Britânico", "us_hwd_pron":"Americano",
                     "exa_pron":"Ouvir exemplo", "sfx":"Ouvir som", "sound":"Ouvir áudio",
                     "picture":"Ver imagem"}
            for index in valid:
                ref = media[index]
                archive = ref.get("archive")
                if archive not in names:
                    continue
                used.add(index)
                title = names[archive]
                control = Gtk.Button(tooltip_text=title)
                content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                content.append(Gtk.Image.new_from_icon_name("image-x-generic-symbolic" if archive == "picture"
                                                            else "audio-volume-high-symbolic"))
                if not compact:
                    content.append(Gtk.Label(label=title))
                control.set_child(content)
                control.add_css_class("flat")
                control.update_property([Gtk.AccessibleProperty.LABEL], [title])
                control.connect("clicked", lambda _, i=index: self.load_media(hit, i, area=area))
                flow.insert(control, -1)
                if archive == "picture" and ref.get("fullsize"):
                    flow.insert(button("Imagem integral", lambda _, i=index: self.load_media(hit, i, True, area=area)), -1)
            if flow.get_first_child():
                parent.append(flow)
                parent.append(area)
        controls(pronunciations, self.detail)
        def render_examples(details, fallback):
            if not isinstance(details, list):
                details = [{"text":t, "audio_indices":[]} for t in values(fallback)]
            for example in details:
                if not isinstance(example, dict) or not example.get("text"):
                    continue
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                text = label("• " + example["text"], "dim-label")
                text.set_hexpand(True)
                line.append(text)
                audio = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                controls(example.get("audio_indices", []), audio, compact=True)
                if audio.get_first_child():
                    # Keep the button beside the example, and the player below it.
                    flow = audio.get_first_child()
                    audio.remove(flow)
                    line.append(flow)
                self.detail.append(line)
                if audio.get_first_child():
                    self.detail.append(audio)
        senses = e.get("senses", [])
        rendered = False
        if isinstance(senses, list):
            for n, sense in enumerate(senses, 1):
                if not isinstance(sense, dict):
                    continue
                definitions = values(sense.get("definitions"))
                examples = values(sense.get("examples"))
                if definitions or examples or sense.get("example_details"):
                    rendered = True
                    self.detail.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
                    self.detail.append(label(f"Acepção {n}", "heading"))
                    for text in definitions:
                        self.detail.append(label(text))
                    render_examples(sense.get("example_details"), examples)
        if not rendered:
            for text in values(e.get("definition")) + values(e.get("definitions")):
                self.detail.append(label(text))
            render_examples(e.get("example_details"), e.get("examples"))
        elif e.get("unassigned_examples"):
            self.detail.append(label("Outros exemplos", "heading"))
            render_examples(e["unassigned_examples"], [])
        remaining = [i for i, ref in enumerate(media) if i not in used and isinstance(ref, dict)]
        if remaining:
            self.detail.append(label("Outros recursos", "heading"))
            controls(remaining, self.detail)

    def load_media(self, hit, index, fullsize=False, *, area):
        generation = self.detail_generation
        self.media_generation = getattr(self, "media_generation", 0) + 1
        request = self.media_generation
        self.stop_audio()
        if self.active_media_area is not None and self.active_media_area is not area:
            clear(self.active_media_area)
        self.active_media_area = area
        clear(area)
        area.append(label("Carregando recurso…"))
        def complete(result, error):
            if generation != self.detail_generation or request != self.media_generation:
                return
            clear(area)
            if error:
                area.append(label(str(error)))
                return
            data, mime = result
            try:
                if mime.startswith("audio/"):
                    with tempfile.NamedTemporaryFile(dir=self.temp.name, suffix=".mp3", delete=False) as out:
                        out.write(data)
                        self.audio_path = Path(out.name)
                    self.audio = Gtk.MediaFile.new_for_filename(str(self.audio_path))
                    controls = Gtk.MediaControls(media_stream=self.audio)
                    area.append(controls)
                    self.audio.connect("notify::error", self.audio_error)
                    self.audio.play()
                elif mime.startswith("image/"):
                    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                    picture = Gtk.Picture.new_for_paintable(texture)
                    picture.set_can_shrink(True)
                    picture.set_size_request(-1, 180)
                    area.append(picture)
            except Exception as exc:
                area.append(label(str(exc)))
        self.work(lambda: get_media(self.registry, hit["dictionary"], hit["entry_id"], index, fullsize), complete)

    def audio_error(self, stream, _):
        if stream is self.audio and stream.get_error():
            self.status.set_text(str(stream.get_error()))

    def show_preferences(self, *_):
        if self.preferences is None:
            self.preferences = Adw.PreferencesWindow(transient_for=self, modal=False,
                                                     title="Preferências", default_width=640, default_height=540,
                                                     hide_on_close=True)
        self.populate_preferences()
        self.preferences.present()

    def populate_preferences(self):
        if self.preferences is None:
            return
        old = getattr(self, "preferences_page", None)
        if old is not None:
            self.preferences.remove(old)
        page = Adw.PreferencesPage(title="Dicionários", icon_name="view-list-symbolic")
        self.preferences_page = page
        self.preferences.add(page)
        installed = Adw.PreferencesGroup(title="Dicionários instalados")
        page.add(installed)
        import_row = Adw.ActionRow(title="Importar dicionário")
        import_control = button("Importar", lambda *_: (self.preferences.hide(), self.show_import_dialog()))
        import_control.set_valign(Gtk.Align.CENTER)
        import_control.set_sensitive(not self.importing)
        import_row.add_suffix(import_control)
        installed.add(import_row)
        self.rebuild_buttons = []
        self.remove_buttons = []
        manifests = self.registry.list()
        for m in manifests:
            row = Adw.ActionRow(title=GLib.markup_escape_text(m["title"]),
                                subtitle=GLib.markup_escape_text(m["language"] + " · " + m["origin"]))
            control = button("Reconstruir", lambda _, item=m: self.rebuild_dictionary(item))
            control.set_valign(Gtk.Align.CENTER)
            control.set_sensitive(not self.importing)
            self.rebuild_buttons.append(control)
            row.add_suffix(control)
            remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remover dicionário",
                                valign=Gtk.Align.CENTER, sensitive=not self.importing)
            remove.add_css_class("flat")
            remove.connect("clicked", lambda _, item=m: self.confirm_remove(item))
            self.remove_buttons.append(remove)
            row.add_suffix(remove)
            installed.add(row)
        if not manifests:
            installed.add(Adw.ActionRow(title="Nenhum dicionário instalado"))
        group = Adw.PreferencesGroup(title="Dicionários disponíveis")
        page.add(group)
        for m in catalog_list(self.registry):
            if m["installed"]:
                continue
            d = m["distribution"]
            state = "Importável" if d.get("importer") in {fmt["id"] for fmt in IMPORT_FORMATS} else "Planejado"
            row = Adw.ActionRow(title=GLib.markup_escape_text(m["title"]), subtitle=f'{m["language"]} · {m["origin"]} · {m["function"]}')
            suffix = Gtk.Label(label=state, valign=Gtk.Align.CENTER)
            suffix.add_css_class("dim-label")
            row.add_suffix(suffix)
            group.add(row)

    def confirm_remove(self, m):
        if self.importing:
            return
        dialog = Adw.MessageDialog(transient_for=self.preferences or self, heading="Remover dicionário?",
            body=m["title"] + "\n\nA base será retirada da biblioteca. Os arquivos originais não serão alterados.")
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("remove", "Remover")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, choice):
            if choice != "remove" or self.importing:
                return
            try:
                self.registry.remove_dictionary(m["slug"])
            except Exception as exc:
                error = Adw.MessageDialog(transient_for=self.preferences or self,
                                          heading="Não foi possível remover", body=str(exc))
                error.add_response("close", "Fechar")
                error.set_close_response("close")
                error.present()
                return
            self.generation += 1
            clear(self.results)
            self.show_empty()
            self.refresh_dictionaries()
            self.populate_preferences()
            self.toast_overlay.add_toast(Adw.Toast.new("Dicionário removido"))
        dialog.connect("response", response)
        dialog.present()

    def show_import_dialog(self, *_, rebuild=None):
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
                self.choose_source(fmt, rebuild)
        dialog.connect("response", response)
        dialog.present()

    def rebuild_dictionary(self, m):
        if self.importing:
            return
        if self.preferences is not None:
            self.preferences.hide()
        fmt_id = "longman" if m.get("source_format") == "idm-skn" else m.get("source_format")
        fmt = next((v for v in IMPORT_FORMATS if v["id"] == fmt_id), None)
        if fmt is None:
            fmt = next((v for v in IMPORT_FORMATS if v["id"] == m.get("distribution", {}).get("importer")), None)
        if fmt is None:
            # Older JSON bases did not record the input format; choose it explicitly.
            self.show_import_dialog(rebuild=m["slug"])
            return
        path = m.get("source_path")
        if path and Path(path).exists():
            self.confirm_import(fmt, path, rebuild=m["slug"], metadata=m if fmt["manifest"] else None)
        else:
            self.choose_source(fmt, rebuild=m["slug"])

    def choose_source(self, fmt, rebuild=None):
        action = Gtk.FileChooserAction.SELECT_FOLDER if fmt["directory"] else Gtk.FileChooserAction.OPEN
        self.choose_file("Selecione a fonte — " + fmt["title"], action,
                         lambda path: self.choose_manifest(fmt, path, rebuild) if fmt["manifest"]
                         else self.confirm_import(fmt, path, rebuild=rebuild))

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

    def choose_manifest(self, fmt, path, rebuild=None):
        self.choose_file("Selecione o manifesto TOML", Gtk.FileChooserAction.OPEN,
                         lambda manifest: self.confirm_import(fmt, path, manifest, rebuild=rebuild))

    def open_bgl(self, path):
        from .bgl import validate_source
        path = str(validate_source(path))
        fmt = next(f for f in IMPORT_FORMATS if f["id"] == "bgl")
        return self.confirm_import(fmt, path)

    def confirm_import(self, fmt, path, manifest=None, *, rebuild=None, metadata=None):
        heading = "Reconstruir dicionário?" if rebuild else "Confirmar importação"
        message = ("A base instalada será substituída após a validação da nova. Os arquivos originais permanecerão inalterados."
                   if rebuild else "Importar esta fonte para a biblioteca do Verbum? Os arquivos originais permanecerão inalterados.")
        dialog = Adw.MessageDialog(transient_for=self, heading=heading,
            body=fmt["title"] + "\n" + path + "\n\n" + message)
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("import", "Reconstruir" if rebuild else "Importar")
        if rebuild:
            dialog.add_response("source", "Escolher outra fonte")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, choice):
            if choice == "import":
                self.start_import(fmt, path, manifest, rebuild=rebuild, metadata=metadata)
            elif choice == "source":
                self.choose_source(fmt, rebuild=rebuild)
        dialog.connect("response", response)
        dialog.present()
        return dialog

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

    def start_import(self, fmt, path, manifest=None, *, rebuild=None, metadata=None):
        if self.importing:
            return
        self.importing = True
        self.import_cancel = threading.Event()
        self.import_stage = ("prepare", 0, None)
        self.import_action.set_enabled(False)
        self.cancel_import_button.set_sensitive(True)
        for control in getattr(self, "rebuild_buttons", []) + getattr(self, "remove_buttons", []):
            control.set_sensitive(False)
        self.import_title.set_text(("Reconstruindo " if rebuild else "Importando ") + fmt["title"])
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
            self.import_action.set_enabled(True)
            for control in getattr(self, "rebuild_buttons", []) + getattr(self, "remove_buttons", []):
                control.set_sensitive(True)
            if isinstance(error, ImportCancelled):
                self.toast_overlay.add_toast(Adw.Toast.new("Importação cancelada"))
            elif isinstance(error, DictionaryAlreadyInstalled):
                self.refresh_dictionaries()
                self.toast_overlay.add_toast(Adw.Toast.new("Dicionário já instalado"))
                self.populate_preferences()
            elif error:
                dialog = Adw.MessageDialog(transient_for=self, heading="Não foi possível importar",
                                           body=str(error))
                dialog.add_response("close", "Fechar")
                dialog.set_close_response("close")
                dialog.present()
            else:
                self.refresh_dictionaries()
                self.populate_preferences()
                if rebuild:
                    self.generation += 1
                    clear(self.results)
                    self.populate_preferences()
                self.toast_overlay.add_toast(Adw.Toast.new(f'Dicionário {"reconstruído" if rebuild else "importado"}: {result["entries"]:n} verbetes'))
        def report(stage, count, total):
            # Immutable snapshot; the GTK main thread alone updates widgets.
            self.import_stage = (stage, count, total)
        def run():
            selected_metadata = metadata
            if manifest:
                with Path(manifest).open("rb") as stream:
                    selected_metadata = tomllib.load(stream)
            return import_dictionary(self.registry, selected_metadata, path, fmt["id"],
                                     progress=report, cancel=self.import_cancel, rebuild=rebuild)
        self.work(run, complete)

    def on_close(self, *_):
        if self.importing:
            self.import_panel.set_visible(True)
            self.import_status.set_text("Cancele a importação ou aguarde a conclusão.")
            return True
        self.closed = True
        if self.preferences is not None:
            self.preferences.destroy()
            self.preferences = None
        if self.timeout:
            GLib.source_remove(self.timeout)
        self.stop_audio()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.temp.cleanup()
        return False

class Application(Adw.Application):
    def __init__(self, root=None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        self.registry = Registry(root)

    def new_window(self):
        window = Window(self, self.registry)
        window.present()
        return window

    def do_activate(self):
        window = self.get_active_window()
        if isinstance(window, Window):
            window.present()
        else:
            self.new_window()

    def do_open(self, files, n_files, hint):
        # Separate confirmation for every local file; never import on activation.
        for file in files:
            window = self.new_window()
            try:
                path = file.get_path()
                if path is None:
                    raise ValueError("Selecione um arquivo BGL local.")
                window.open_bgl(path)
            except (ValueError, OSError) as exc:
                dialog = Adw.MessageDialog(transient_for=window,
                    heading="Não foi possível abrir o dicionário", body=str(exc))
                dialog.add_response("close", "Fechar")
                dialog.set_close_response("close")
                dialog.present()

def main(root=None, files=None):
    return Application(root).run(["verbum", "--", *(files or [])])

if __name__ == "__main__":
    raise SystemExit(main())
