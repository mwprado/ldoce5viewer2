# LDOCE5 Viewer

The LDOCE5 Viewer is an alternative dictionary viewer for the Longman Dictionary of Contemporary English 5th Edition (LDOCE 5).

![image](https://cloud.githubusercontent.com/assets/15828926/24585732/efb068a4-17bb-11e7-8294-7241f73d9ed8.png)

It runs on macOS (Intel and Apple Silicon), Linux and Microsoft Windows.

## Frontends

The application is being split behind a toolkit-neutral façade:

- `ldoce5viewer` — existing PySide6/Qt6 frontend.
- `ldoce5viewer-gnome` — experimental GTK4/libadwaita frontend.

Both frontends use the same dictionary indexes and configuration. The façade lives in
`ldoce5viewer/facade.py`; dictionary, incremental-search, and full-text-search code
remain independent of either GUI toolkit.

The GNOME frontend currently covers the first proof-of-concept path: incremental/full-text
lookup, dictionary HTML rendering, custom `dict:`/`static:`/`lookup:` URI handling,
navigation, and pronunciation audio. Advanced search and index creation still use the Qt
frontend and are intentionally left for later migration.

## Installation

The application uses modern Python packaging through `pyproject.toml`.

```bash
python3 -m pip install .
ldoce5viewer
```

For an isolated development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
ldoce5viewer
```

On a system with the GTK4, libadwaita, PyGObject, and WebKitGTK 6 introspection
bindings installed, the experimental native GNOME frontend can be started with:

```bash
ldoce5viewer-gnome
```

## Architecture

```text
                  +------------------+
                  |  ViewerFacade    |
                  +---------+--------+
                            |
             +--------------+---------------+
             |              |               |
        incremental      fulltext          LDOCE5
             |              |               |
             +--------------+---------------+
                            |
             +--------------+---------------+
             |                              |
        PySide6 / Qt6                 GTK4 / libadwaita
        ldoce5viewer                  ldoce5viewer-gnome
```

The façade must not import PySide6, GTK, libadwaita, or WebKit. Frontends own event-loop,
widget, media, and web-view integration; the façade owns dictionary/search access and the
stable data contract between those layers.

## Tests

The façade contract can be checked without starting either GUI:

```bash
python3 -m unittest discover -s tests
```

## Building distributions

Install the Python build frontend and create both the source distribution and wheel:

```bash
python -m pip install build
python -m build
```

The PyInstaller application bundle remains available separately:

```bash
make bundle
```

The LDOCE dictionary data is not distributed with this project.

This software is free and open source software licensed under the terms of GPLv3 or later.
