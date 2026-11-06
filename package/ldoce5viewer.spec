Name:           ldoce5viewer
Version:        2013.04.24
Release:        7%{?dist}
Summary:        Dictionary viewer for the Longman Dictionary of Contemporary English 5th Edition

License:        GPL-3.0-or-later AND LicenseRef-Fedora-Public-Domain
URL:            https://github.com/mwprado/ldoce5viewer2
Source0:        %{url}/archive/refs/heads/master.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils
# Do not require pyside6-tools just to generate the Python UI/resource files.
# Qt's native uic/rcc support Python generation with "-g python" and are
# available through qt6-qtbase-devel on Fedora, EPEL 9 and EPEL 10.
BuildRequires:  qt6-qtbase-devel

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
# building the wheel. Use the Qt6 tools directly instead of pyside6-tools;
# this removes an unnecessary build-time dependency that is absent in EPEL 9.
%{_qt6_libexecdir}/uic -g python \
    ldoce5viewer/qtgui/ui/advanced.ui \
    -o ldoce5viewer/qtgui/ui/advanced.py
%{_qt6_libexecdir}/uic -g python \
    ldoce5viewer/qtgui/ui/indexer.ui \
    -o ldoce5viewer/qtgui/ui/indexer.py
%{_qt6_libexecdir}/uic -g python \
    ldoce5viewer/qtgui/ui/main.ui \
    -o ldoce5viewer/qtgui/ui/main.py
%{_qt6_libexecdir}/rcc -g python \
    ldoce5viewer/qtgui/resources/resource.qrc \
    -o ldoce5viewer/qtgui/resources/__init__.py

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
* Fri Nov 06 2026 Moacyr Prado - 2013.04.24-7
- Replace pyside6-tools build dependency with qt6-qtbase-devel
- Generate PySide6-compatible Python UI files with Qt6 uic -g python
- Generate Qt resource Python code with Qt6 rcc -g python
- Allow the build to pass the pyside6-tools dependency stage on EPEL 9

* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-6
- Load packaged static assets with importlib.resources
- Remove obsolete py2exe/frozen-runtime handling

* Sun Sep 20 2026 Moacyr Prado - 2013.04.24-5
- Replace the removed Python imp module with importlib machinery
- Restore compatibility with Python 3.14 import smoke tests

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
