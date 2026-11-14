# DictViewer — Cangaço

Development branch for a multilingual, offline-first dictionary service and GNOME client. Preserve the existing LDOCE viewer on master.

## Architecture

- Independent databases, one per dictionary edition, using a versioned SQLite-based CDF format.
- Import service: identify source, extract records, classify, validate, index, register atomically. Source-specific importers are plugins.
- Registry: stable dictionary UUID, human-readable ID, languages (BCP 47), language scope, lexical origin, authors, publisher, title, edition, year, functions, temporal coverage, domains, access (local/web/hybrid), license and capabilities.
- Naming: language-origin-function-edition.cdf; edition omitted only when unknown. Manifest is authoritative; filename is not a primary key.
- Local and web providers share the query contract. Remote access must be explicitly enabled.
- Core is independent of any GUI. Preserve original spelling and source identifiers, distinguish homographs and senses, support optional structured data and media.
- GTK4/libadwaita client; WebKitGTK 6.0 for HTML; Gio/GDBus for IPC.
- Proposed bus name: io.github.mwprado.DictViewer; query interface io.github.mwprado.DictViewer.Dictionary1; import interface io.github.mwprado.DictViewer.Import1.
- GNOME Shell integration: org.gnome.Shell.SearchProvider2; register a desktop file, D-Bus activation and search provider INI. Search must not open windows until result activation.
- LibreOffice UNO extension is a separate client.

## Initial implementation milestones

1. Manifest, registry, CDF schema, JSON/JSONL importer, CLI, synthetic tests.
2. Import trusted local PKLZ data and Longman IDM/SKN using the existing reader. Do not load arbitrary pickle files.
3. GTK4 frontend and safe rendering/media handling.
4. D-Bus lookup/import service and GNOME search provider.
5. LibreOffice integration and RPM packaging.

## Licensing

Distribute code and synthetic test data only. Do not commit proprietary dictionary content or derived indices. Users supply their own source files and must have authorization for import and use. Preserve source license and provenance.

## References

- https://developer.gnome.org/documentation/tutorials/search-provider.html
- https://developer.gnome.org/documentation/introduction/overview/libraries.html
