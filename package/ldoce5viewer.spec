Name:           ldoce5viewer
Version:        2013.04.24
Release:        4%{?dist}
Summary:        Dictionary viewer for the Longman Dictionary of Contemporary English 5th Edition

License:        GPL-3.0-or-later AND LicenseRef-Fedora-Public-Domain
URL:            https://github.com/mwprado/ldoce5viewer2
Source0:        %{url}/archive/refs/heads/master.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  pyside6-tools

%description
LDOCE5 Viewer is a desktop dictionary viewer for the Longman Dictionary
of Contemporary English 5th Edition (LDOCE 5). It uses Python 3,
PySide6/Qt 6, Whoosh for full-text search, and lxml for XML processing.

The LDOCE dictionary data itself is not distributed with this package.

%generate_buildrequires
%pyproject_buildrequires -r

%prep
%autosetup -n ldoce5viewer2-master

%build
# Generate Python modules from the Qt Designer and resource files before
# building the wheel. These modules are imported by the application at runtime.
pyside6-uic ldoce5viewer/qtgui/ui/advanced.ui -o ldoce5viewer/qtgui/ui/advanced.py
pyside6-uic ldoce5viewer/qtgui/ui/indexer.ui -o ldoce5viewer/qtgui/ui/indexer.py
pyside6-uic ldoce5viewer/qtgui/ui/main.ui -o ldoce5viewer/qtgui/ui/main.py
pyside6-rcc ldoce5viewer/qtgui/resources/resource.qrc -o ldoce5viewer/qtgui/resources/__init__.py

%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l ldoce5viewer

install -Dm0644 ldoce5viewer.desktop \
    %{buildroot}%{_datadir}/applications/ldoce5viewer.desktop

install -Dm0644 ldoce5viewer.appdata.xml \
    %{buildroot}%{_datadir}/metainfo/ldoce5viewer.appdata.xml

install -Dm0644 ldoce5viewer/qtgui/resources/ldoce5viewer.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/ldoce5viewer.svg

%check
# icongen.py is a development-time icon generator and requires Pillow; it is
# not imported by the application at runtime.
%pyproject_check_import -e 'ldoce5viewer.qtgui.resources.icons.icongen'
desktop-file-validate %{buildroot}%{_datadir}/applications/ldoce5viewer.desktop

%files -f %{pyproject_files}
%license COPYING.txt LICENSE.txt
%doc README.md
%{_bindir}/ldoce5viewer
%{_datadir}/applications/ldoce5viewer.desktop
%{_datadir}/metainfo/ldoce5viewer.appdata.xml
%{_datadir}/icons/hicolor/scalable/apps/ldoce5viewer.svg

%changelog
* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-4
- Generate PySide6 UI and resource Python modules before building the wheel
- Add pyside6-tools as a build dependency
- Keep the import smoke test while excluding the development-only icon generator
- Support Python 3.14 configparser API in the IDM reader

* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-3
- Temporarily build from the current master branch instead of a pinned commit
- Simplify the release tag while tracking a moving branch

* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-2.20260920gitbd9df46
- Fix PEP 517 build requirement generation by making the project version static
- Avoid setuptools importing the top-level ldoce5viewer.py launcher during metadata evaluation
- Update Source0 to the corrected source commit

* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-1.20260920git6f7e6d7
- Add initial Fedora RPM packaging for the PySide6/Qt6 port
- Build with PEP 517/pyproject RPM macros
- Install desktop entry, AppStream metadata, and application icon
