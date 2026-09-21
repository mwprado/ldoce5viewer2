"""Toolkit-neutral configuration storage for LDOCE5 Viewer."""

import os
import os.path
import pickle
import shutil
import sys
import tempfile
import threading

__config = None


def get_config():
    global __config
    if __config is None:
        __config = Config()
    return __config


class Config:
    """Persistent application configuration without GUI-toolkit dependencies."""

    def __init__(self, debug=False):
        self.debug = debug
        self._dict = {}
        self._prepare_dir()
        self._remove_tmps()
        self._lock = threading.RLock()

    def __getitem__(self, key):
        with self._lock:
            return self._dict[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._dict[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def pop(self, key, default=None):
        with self._lock:
            return self._dict.pop(key, default)

    def __contains__(self, key):
        with self._lock:
            return key in self._dict

    def __str__(self):
        with self._lock:
            return "Config({})".format(
                ", ".join("{}: {}".format(k, v) for (k, v) in self._dict.items())
            )

    @property
    def _config_dir(self):
        if sys.platform.startswith("win"):
            if "LOCALAPPDATA" in os.environ:
                return os.path.join(os.environ["LOCALAPPDATA"], "LDOCE5Viewer")
            return os.path.join(os.environ["APPDATA"], "LDOCE5Viewer")
        if sys.platform.startswith("darwin"):
            return os.path.expanduser("~/Library/Application Support/LDOCE5Viewer")

        base = os.path.join(os.path.expanduser("~"), ".config")
        try:
            import xdg.BaseDirectory

            base = xdg.BaseDirectory.xdg_config_home
        except ImportError:
            if "XDG_CONFIG_HOME" in os.environ:
                base = os.environ["XDG_CONFIG_HOME"]
        return os.path.join(base, "ldoce5viewer")

    @property
    def _data_dir(self):
        if sys.platform.startswith(("win", "darwin")):
            return self._config_dir

        base = os.path.join(os.path.expanduser("~"), ".local", "share")
        try:
            import xdg.BaseDirectory

            base = xdg.BaseDirectory.xdg_data_home
        except ImportError:
            if "XDG_DATA_HOME" in os.environ:
                base = os.environ["XDG_DATA_HOME"]
        return os.path.join(base, "ldoce5viewer")

    @property
    def app_name(self):
        return "LDOCE5 Viewer"

    @property
    def _config_path(self):
        return os.path.join(self._config_dir, "config.pickle")

    @property
    def filemap_path(self):
        return os.path.join(self._data_dir, "filemap.cdb")

    @property
    def variations_path(self):
        return os.path.join(self._data_dir, "variations.cdb")

    @property
    def incremental_path(self):
        return os.path.join(self._data_dir, "incremental.db")

    @property
    def fulltext_hwdphr_path(self):
        return os.path.join(self._data_dir, "fulltext_hp")

    @property
    def fulltext_defexa_path(self):
        return os.path.join(self._data_dir, "fulltext_de")

    @property
    def scan_tmp_path(self):
        return os.path.join(self._data_dir, "scan" + self.tmp_suffix)

    @property
    def tmp_suffix(self):
        return ".tmp"

    def _prepare_dir(self):
        os.makedirs(self._config_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def _remove_tmps(self):
        for directory in (self._config_dir, self._data_dir):
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for name in names:
                if not name.endswith(self.tmp_suffix):
                    continue
                path = os.path.join(directory, name)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        shutil.rmtree(path)
                except OSError:
                    pass

    def load(self):
        with self._lock:
            try:
                with open(self._config_path, "rb") as f:
                    data = pickle.load(f)
            except (OSError, EOFError, pickle.PickleError):
                self._dict.clear()
            else:
                self._dict.clear()
                if isinstance(data, dict):
                    self._dict.update(data)

    def save(self):
        with self._lock:
            if sys.platform == "win32":
                with open(self._config_path, "wb") as f:
                    pickle.dump(self._dict, f)
                return

            with tempfile.NamedTemporaryFile(
                dir=self._config_dir, delete=False, suffix=self.tmp_suffix
            ) as f:
                pickle.dump(self._dict, f, protocol=0)
                tmp_name = f.name
            os.replace(tmp_name, self._config_path)
