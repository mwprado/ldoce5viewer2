"""Install per-user XDG desktop integration for a source checkout."""
import os
from pathlib import Path
import subprocess
import sys
import shutil

APP_ID = "io.github.mwprado.Verbum"
MIME = "application/x-babylon-bgl"

def desktop_quote(value):
    # Desktop Entry Exec has two escaping layers (string and argument).
    value = str(value).replace("%", "%%")
    value = "".join("\\" + c if c in '\\"$`' else c for c in value)
    return '"' + value.replace("\\", "\\\\") + '"'

def install_desktop(default_bgl=False):
    root = Path(__file__).resolve().parent.parent
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home()/".local/share")
    apps = data / "applications"
    mime = data / "mime"
    icons = data / "icons/hicolor/scalable/apps"
    for directory in (apps, mime/"packages", icons):
        directory.mkdir(parents=True, exist_ok=True)
    for command in ("update-mime-database", "update-desktop-database", *(["xdg-mime"] if default_bgl else [])):
        if not shutil.which(command):
            raise ValueError("Comando necessário não encontrado: " + command)
    source = root / "data"
    if not (source/(APP_ID+".desktop")).is_file():
        # RPM installation already supplies the desktop entry and MIME definition.
        installed = Path("/usr/share/applications")/(APP_ID+".desktop")
        if not installed.is_file():
            raise ValueError("Arquivos de integração não encontrados.")
        if default_bgl:
            subprocess.run(["xdg-mime", "default", APP_ID+".desktop", MIME], check=True)
        print("Verbum já registrado pelo pacote do sistema.")
        return
    desktop = (source/(APP_ID+".desktop")).read_text(encoding="utf-8")
    command = " ".join([desktop_quote(sys.executable), "-m", "verbum", "gui", "--", "%F"])
    # Path is a Desktop Entry string, not an Exec argument.
    workdir = str(root).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    desktop = desktop.replace("Exec=verbum gui %F", "Exec="+command+"\nPath="+workdir)
    (apps/(APP_ID+".desktop")).write_text(desktop, encoding="utf-8")
    shutil.copyfile(source/(APP_ID+".xml"), mime/"packages"/(APP_ID+".xml"))
    shutil.copyfile(source/(APP_ID+".svg"), icons/(APP_ID+".svg"))
    subprocess.run(["update-mime-database", str(mime)], check=True)
    subprocess.run(["update-desktop-database", str(apps)], check=True)
    if default_bgl:
        subprocess.run(["xdg-mime", "default", APP_ID+".desktop", MIME], check=True)
    print("Verbum registrado no ambiente gráfico.")
