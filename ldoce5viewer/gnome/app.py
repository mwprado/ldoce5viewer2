"""GTK4/libadwaita frontend built on the GUI-neutral façade."""

from concurrent.futures import ThreadPoolExecutor
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Adw, Gio, GLib, Gtk, WebKit

from ..facade import ViewerFacade
from ..ldoce5 import ArchiveError, FilemapError, NotFoundError


APP_ID = "io.github.mwprado.LDOCE5Viewer"


class ViewerWindow(Adw.ApplicationWindow):
    def __init__(self, application, facade):
        super().__init__(application=application)
        self.facade = facade
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ldoce-search")
        self._search_generation = 0
        self._search_timer = None

        self.set_title("LDOCE5 Viewer")
        self.set_default_size(1100, 720)
        self.set_size_request(720, 480)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search LDOCE5…")
        self.search_entry.set_hexpand(True)
        self.search_entry.set_size_request(360, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        header.set_title_widget(self.search_entry)

        back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        back.set_tooltip_text("Back")
        back.connect("clicked", lambda *_: self.web_view.go_back())
        header.pack_start(back)

        forward = Gtk.Button.new_from_icon_name("go-next-symbolic")
        forward.set_tooltip_text("Forward")
        forward.connect("clicked", lambda *_: self.web_view.go_forward())
        header.pack_start(forward)

        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_position(310)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)
        toolbar_view.set_content(paned)

        self.results = Gtk.ListBox()
        self.results.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.results.set_activate_on_single_click(True)
        self.results.connect("row-activated", self._on_row_activated)

        result_scroll = Gtk.ScrolledWindow()
        result_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        result_scroll.set_min_content_width(240)
        result_scroll.set_child(self.results)
        paned.set_start_child(result_scroll)

        self.web_context = WebKit.WebContext.get_default()
        for scheme in ("dict", "static", "audio", "lookup"):
            self.web_context.register_uri_scheme(scheme, self._on_uri_scheme_request)

        security = self.web_context.get_security_manager()
        for scheme in ("dict", "static", "audio", "lookup"):
            security.register_uri_scheme_as_local(scheme)
            security.register_uri_scheme_as_secure(scheme)

        self.web_view = WebKit.WebView.new_with_context(self.web_context)
        self.web_view.set_hexpand(True)
        self.web_view.set_vexpand(True)
        paned.set_end_child(self.web_view)

        state = self.facade.index_state()
        if not state["incremental"]:
            self.web_view.load_html(
                "<h2>LDOCE5 index not available</h2>"
                "<p>Create the dictionary index before using the GNOME frontend.</p>",
                None,
            )
        else:
            self.web_view.load_html(
                "<h2>LDOCE5 Viewer</h2><p>Type a word in the search field.</p>",
                None,
            )

        self.search_entry.grab_focus()

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
        return super().close()

    def _on_search_changed(self, entry):
        if self._search_timer is not None:
            GLib.source_remove(self._search_timer)
        self._search_timer = GLib.timeout_add(140, self._start_search)

    def _on_search_activate(self, entry):
        if self._search_timer is not None:
            GLib.source_remove(self._search_timer)
            self._search_timer = None
        self._start_search()

    def _start_search(self):
        self._search_timer = None
        query = self.search_entry.get_text().strip()
        self._search_generation += 1
        generation = self._search_generation

        if not query:
            self._replace_results(())
            return GLib.SOURCE_REMOVE

        future = self._executor.submit(self.facade.search, query)
        future.add_done_callback(
            lambda f: GLib.idle_add(self._finish_search, generation, f)
        )
        return GLib.SOURCE_REMOVE

    def _finish_search(self, generation, future):
        if generation != self._search_generation:
            return GLib.SOURCE_REMOVE

        try:
            results = future.result()
        except Exception as exc:
            self.web_view.load_html(
                "<h2>Search error</h2><pre>{}</pre>".format(
                    GLib.markup_escape_text(str(exc))
                ),
                None,
            )
            return GLib.SOURCE_REMOVE

        self._replace_results(results)
        if results:
            row = self.results.get_row_at_index(0)
            self.results.select_row(row)
            self._load_result(row)
        return GLib.SOURCE_REMOVE

    def _replace_results(self, results):
        while True:
            row = self.results.get_row_at_index(0)
            if row is None:
                break
            self.results.remove(row)

        for result in results:
            row = Gtk.ListBoxRow()
            row.ldoce_result = result

            label = Gtk.Label(label=result.plain_label)
            label.set_xalign(0.0)
            label.set_ellipsize(3)
            label.set_margin_top(7)
            label.set_margin_bottom(7)
            label.set_margin_start(10)
            label.set_margin_end(10)
            row.set_child(label)
            self.results.append(row)

    def _on_row_activated(self, listbox, row):
        self._load_result(row)

    def _load_result(self, row):
        result = getattr(row, "ldoce_result", None)
        if result is not None:
            self.web_view.load_uri(result.uri)

    def _on_uri_scheme_request(self, request):
        uri = request.get_uri()

        if uri.startswith("lookup:"):
            query = self.facade.lookup_query(uri)
            if query:
                GLib.idle_add(self._set_lookup_query, query)
            self._finish_request(
                request,
                b"<html><body></body></html>",
                "text/html;charset=utf-8",
            )
            return

        try:
            resource = self.facade.resolve_uri(uri)
        except (NotFoundError, FilemapError, ArchiveError) as exc:
            resource = self.facade.error_page(exc)

        if uri.startswith("audio:"):
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(resource.data))
            self._audio = Gtk.MediaFile.new_for_input_stream(stream)
            self._audio.play()
            self._finish_request(request, b"", "text/plain")
            return

        self._finish_request(request, resource.data, resource.mime_type)

    def _set_lookup_query(self, query):
        self.search_entry.set_text(query)
        self.search_entry.set_position(-1)
        self._start_search()
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _finish_request(request, data, mime_type):
        blob = GLib.Bytes.new(data)
        stream = Gio.MemoryInputStream.new_from_bytes(blob)
        request.finish(stream, len(data), mime_type)


class LDOCEApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.facade = None
        self.window = None

    def do_activate(self):
        if self.facade is None:
            self.facade = ViewerFacade()
        if self.window is None:
            self.window = ViewerWindow(self, self.facade)
        self.window.present()

    def do_shutdown(self):
        if self.facade is not None:
            self.facade.close()
        super().do_shutdown()


def main(argv=None):
    app = LDOCEApplication()
    return app.run(sys.argv if argv is None else argv)
