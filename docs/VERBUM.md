# Verbum 0.1.0 — Projeto Cangaço

Verbum replaces the provisional DictViewer name on this development branch.
The existing Longman application remains unchanged.

## VLF v1

One SQLite file per dictionary edition, with embedded JSON manifest, entries and FTS5 index. Filename: language-origin-function[-edition].vlf. The manifest contains a permanent UUID, language, origin, function, title and license; optional languages, functions, authors, publisher, edition, year, scope, period, domains and capabilities. Preserve spelling, homographs and source-specific fields in the JSON entry payload. Access is local in this version.

## Quick start

Python 3.11+ and SQLite with FTS5. From the repository root:

    python3 -m verbum --help
    python3 -m unittest discover -s tests -p test_verbum.py

Create a manifest TOML:

    title = "Synthetic dictionary"
    language = "pt-br"
    origin = "demo"
    function = "general"
    license = "CC0"

Create entries.json with synthetic entries:

    [{"lemma":"teste","definition":"Entrada de demonstração"}]

Run:

    python3 -m verbum import entries.json --manifest manifest.toml --authorized
    python3 -m verbum list --language pt-br
    python3 -m verbum search teste --mode exact
    python3 -m verbum search demonstração --mode fulltext

Default data directory: XDG_DATA_HOME/verbum or ~/.local/share/verbum. Use --root before the command for isolated testing. Import refuses duplicate slug/UUID and publishes a validated database without overwriting an existing one. The registry and file publication are not crash-atomic across both resources; recovery and update workflows are future work.

## Native-source import policy

Importers must consume the original files supplied by the user (installation directories, native archives, publisher files, or original documents). VLF is the canonical output; PKLZ is an optional compatibility input, never a prerequisite. Preserve original spelling, source identifiers, edition, provenance and licensing. Detect source formats by their structure, not filenames alone. Keep the original source unchanged. For proprietary sources, require authorization and do not distribute extracted data or indices. JSON/JSONL remains supported for open structured sources and synthetic tests.

## Next milestones

Native Longman IDM/SKN importer first, followed by native VOLP and other verified source formats; optional trusted PKLZ compatibility; structured sense/media schema; GTK4/libadwaita and WebKitGTK; Gio D-Bus query/import interfaces; GNOME Shell SearchProvider2; LibreOffice UNO; RPM packaging. No proprietary content or indices are distributed. Import only authorized sources.

Proposed application ID: io.github.mwprado.Verbum.
