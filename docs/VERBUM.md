# Verbum 0.3.2 — Projeto Cangaço

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

    python3 -m verbum import entries.json --manifest manifest.toml
    python3 -m verbum list --language pt-br
    python3 -m verbum search teste --mode exact
    python3 -m verbum search demonstração --mode fulltext

Default data directory: XDG_DATA_HOME/verbum or ~/.local/share/verbum. Use --root before the command for isolated testing. Import refuses duplicate slug/UUID and publishes a validated database without overwriting an existing one. The registry and file publication are not crash-atomic across both resources; recovery and update workflows are future work.

## Native-source import policy

Importers must consume the original files supplied by the user (installation directories, native archives, publisher files, or original documents). VLF is the canonical output; PKLZ is an optional compatibility input, never a prerequisite. Preserve original spelling, source identifiers, edition, provenance and licensing. Detect source formats by their structure, not filenames alone. Keep the original source unchanged. For proprietary sources, do not distribute extracted data or indices. The application performs technical validation, not legal eligibility checks. JSON/JSONL remains supported for open structured sources and synthetic tests.

## Next milestones

Native VOLP and other verified source formats; optional trusted PKLZ compatibility; structured sense/media schema; GTK4/libadwaita and WebKitGTK; Gio D-Bus query/import interfaces; GNOME Shell SearchProvider2; LibreOffice UNO; RPM packaging. No proprietary content or indices are distributed. Users remain responsible for compliance with applicable source licenses.

Proposed application ID: io.github.mwprado.Verbum.

## Distribution catalog (0.1.1)

    python3 -m verbum catalog
    python3 -m verbum catalog --method import
    python3 -m verbum catalog --origin longman

The bundled catalog is metadata only, separate from installed dictionaries. An external TOML catalog can be supplied with --catalog-file. Access (local/web/hybrid) and distribution (import/download/web) are distinct. Redistribution defaults to false; downloads require explicit open/public-domain status, a license reference, HTTPS URL and SHA-256. These declarations still require human license verification. Proprietary JSON imports are rejected; the native Longman importer is available. Download installation and remote lookup are not implemented. The catalog's listed sources are descriptions, not a promise of availability.

## Native Longman import (0.2.0)

On Fedora install python3-lxml if needed. The existing LDOCE5 reader is reused without Qt.

    python3 -m verbum import ~/App/ldoce5.data --format longman
    python3 -m verbum search water --origin longman --mode exact
    python3 -m unittest discover -s tests -p 'test_verbum*.py' -v

No manifest is needed. This imports the fs.skn entry archive, retaining exact XML bytes in base64, source IDs, definitions, examples, grammar, variants and media references. Original audio/image files are not embedded; preserve the source directory. Version 0.2.1 resolves media on demand. Supplementary lexical archives are not yet served. Variants are searchable in fulltext, not exact/prefix yet. No proprietary dictionary data is committed. Synthetic IDM/SKN archive tests exercise the original reader; real edition validation requires a locally authorized copy.

## Media retrieval (0.2.1)

Search results now include the numeric entry_id. Use it with the dictionary slug:

    python3 -m verbum media en-longman-learner-5 ENTRY_ID
    python3 -m verbum media en-longman-learner-5 ENTRY_ID --index 0 --output /tmp/pronunciation.mp3

Indices are zero-based. For an image use --fullsize when available. The command refuses to overwrite an output file. Media is read from original archives only on explicit request. A process-local index cache accelerates repeated lookups; nothing is downloaded or permanently copied into VLF. Existing 0.2.0 databases are compatible. GTK playback and image display are available in 0.3.0. Synthetic media tests verify byte retrieval, not codec validity.

## Native GTK interface (0.3.0)

On Fedora, install the system Python bindings, GTK4 (which includes its media backend on Fedora 45), and GStreamer plugins:

    sudo dnf install python3-gobject gtk4 libadwaita python3-lxml gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good
    python3 -m verbum gui

The GUI supports incremental/exact/fulltext search, installed-dictionary selection, structured entry display, native Longman import with operational confirmation, and on-demand audio and image playback/display. Audio uses Gtk.MediaFile and Gtk.MediaControls; codec availability depends on the GStreamer installation. Temporary audio files are private and removed when replaced or on normal exit. No network requests or WebKit rendering in this version. Use the existing original Longman directory for media. The catalog shows unimplemented providers as planned.

GUI smoke test under Xvfb (system Python with GI installed):

    VERBUM_GTK_TEST=1 xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -p test_verbum_gtk.py -v

## Generic import dialog (0.3.1)

The header button is now Importar. Choose a supported format in the dialog: Longman (original directory), JSON, or JSON Lines (file plus TOML manifest). Other catalog importers are shown as in development, not selectable. All paths use the same import service and operational import confirmation.

## Import confirmation (0.3.2)

The graphical dialog confirms only the import operation and its source. It does not ask the user to attest to authorization to use the dictionary. CLI import requires no authorization flag; the old flag remains accepted for compatibility but has no effect. Distribution restrictions and technical source validation are unchanged.
