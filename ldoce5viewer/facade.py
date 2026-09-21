"""GUI-neutral application façade for LDOCE5 Viewer."""

from dataclasses import dataclass
from importlib.resources import files
import mimetypes
import os
from urllib.parse import parse_qs, urlsplit

from . import fulltext, incremental
from .config import get_config
from .ldoce5 import ArchiveError, FilemapError, LDOCE5, NotFoundError
from .utils.text import MATCH_CLOSE_TAG, MATCH_OPEN_TAG

_INCREMENTAL_LIMIT = 500
_FULLTEXT_LIMIT = 10000


@dataclass(frozen=True)
class SearchResult:
    label: str
    path: str
    sort_key: str
    priority: int
    highlight: str | None = None

    @property
    def plain_label(self):
        value = MATCH_OPEN_TAG.sub("", self.label)
        return MATCH_CLOSE_TAG.sub("", value)

    @property
    def uri(self):
        return "dict://" + self.path


@dataclass(frozen=True)
class Resource:
    data: bytes
    mime_type: str


class ViewerFacade:
    """Stable boundary between dictionary/search services and GUI frontends."""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.config.load()
        self._incremental = None
        self._fulltext_hwdphr = None
        self._fulltext_defexa = None
        self._dictionary = LDOCE5(
            self.config.get("dataDir", ""),
            self.config.filemap_path,
        )

    def close(self):
        for name in ("_incremental", "_fulltext_hwdphr", "_fulltext_defexa"):
            obj = getattr(self, name)
            if obj is not None:
                obj.close()
                setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def data_dir(self):
        return self.config.get("dataDir", "")

    def index_state(self):
        return {
            "data_dir": self.data_dir,
            "filemap": os.path.isfile(self.config.filemap_path),
            "incremental": os.path.isfile(self.config.incremental_path),
            "fulltext_headwords": os.path.isdir(self.config.fulltext_hwdphr_path),
            "fulltext_definitions": os.path.isdir(self.config.fulltext_defexa_path),
        }

    def search(self, query, incremental_limit=_INCREMENTAL_LIMIT, fulltext_limit=_FULLTEXT_LIMIT):
        query = query.strip()
        if not query:
            return ()

        contains_wildcard = any(c in query for c in "*?")
        incremental_results = ()
        if not contains_wildcard:
            searcher = self._get_incremental()
            if searcher is not None:
                try:
                    incremental_results = tuple(
                        searcher.search(query, limit=incremental_limit)
                    )
                except (EnvironmentError, incremental.IndexError):
                    incremental_results = ()

        fulltext_results = ()
        searcher = self._get_fulltext_hwdphr()
        if searcher is not None:
            collector = searcher.make_collector(fulltext_limit + 1)
            itemtypes = ("hm",) if contains_wildcard else ()
            try:
                fulltext_results = tuple(
                    searcher.search(
                        collector,
                        query_str1=query,
                        itemtypes=itemtypes,
                        highlight=False,
                    )
                )
            except (EnvironmentError, fulltext.IndexError):
                fulltext_results = ()

        merged = []
        seen_paths = set()
        for item in incremental_results + fulltext_results:
            path = item[1]
            if path in seen_paths:
                continue
            seen_paths.add(path)
            merged.append(SearchResult(*item))
        return tuple(merged)

    def spelling_suggestions(self, query, limit=5):
        query = query.strip()
        if not query or len(query.split()) != 1:
            return ()
        searcher = self._get_fulltext_hwdphr()
        if searcher is None:
            return ()
        return tuple(searcher.correct(query, limit=limit))

    def dictionary_content(self, path):
        return self._dictionary.get_content(path)

    def static_content(self, filename):
        resource = files("ldoce5viewer").joinpath("static")
        for part in filename.lstrip("/").split("/"):
            if part:
                resource = resource.joinpath(part)
        data = resource.read_bytes()
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return data, mime

    def resolve_uri(self, uri):
        parsed = urlsplit(uri)
        scheme = parsed.scheme.lower()

        if scheme in ("dict", "audio"):
            data, mime = self.dictionary_content(parsed.path)
            if data is None:
                raise NotFoundError(parsed.path)
            return Resource(data, mime or "application/octet-stream")

        if scheme == "static":
            data, mime = self.static_content(parsed.path)
            return Resource(data, mime)

        raise NotFoundError("unsupported URI scheme: {}".format(scheme))

    @staticmethod
    def lookup_query(uri):
        parsed = urlsplit(uri)
        if parsed.scheme.lower() != "lookup":
            return None
        values = parse_qs(parsed.query)
        query = values.get("q", [None])[0]
        return query.replace("+", " ") if query else None

    def error_page(self, exc):
        if isinstance(exc, FilemapError):
            message = "File-location map not available."
        elif isinstance(exc, ArchiveError):
            message = "Dictionary data not available."
        else:
            message = "Content not found."
        return Resource(
            ("<html><body><h2>{}</h2></body></html>".format(message)).encode("utf-8"),
            "text/html;charset=utf-8",
        )

    def _get_incremental(self):
        if self._incremental is None:
            try:
                self._incremental = incremental.Searcher(self.config.incremental_path)
            except (EnvironmentError, incremental.IndexError):
                return None
        return self._incremental

    def _get_fulltext_hwdphr(self):
        if self._fulltext_hwdphr is None:
            try:
                self._fulltext_hwdphr = fulltext.Searcher(
                    self.config.fulltext_hwdphr_path,
                    self.config.variations_path,
                )
            except (EnvironmentError, fulltext.IndexError):
                return None
        return self._fulltext_hwdphr

    def _get_fulltext_defexa(self):
        if self._fulltext_defexa is None:
            try:
                self._fulltext_defexa = fulltext.Searcher(
                    self.config.fulltext_defexa_path,
                    self.config.variations_path,
                )
            except (EnvironmentError, fulltext.IndexError):
                return None
        return self._fulltext_defexa
