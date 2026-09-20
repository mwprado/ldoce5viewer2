# LDOCE5 Viewer (PySide6, Python 3, Qt6)

The LDOCE5 Viewer is an alternative dictionary viewer for the Longman Dictionary of Contemporary English 5th Edition (LDOCE 5).

![image](https://cloud.githubusercontent.com/assets/15828926/24585732/efb068a4-17bb-11e7-8294-7241f73d9ed8.png)

It runs on macOS (Intel and Apple Silicon), Linux and Microsoft Windows.

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
