# Fedora / EPEL 10. Requires Python >= 3.11 and GTK 4/libadwaita.
# Override upstream_repo if building before the GitHub repository is renamed.
%{!?upstream_repo:%global upstream_repo verbum}
# Source release tag must exist before building the SRPM.
%global appid io.github.mwprado.Verbum

Name:           verbum
Version:        0.4.3
Release:        1%{?dist}
Summary:        Multilingual dictionary and lexical service for GNOME

License:        GPL-3.0-or-later
URL:            https://github.com/mwprado/%{upstream_repo}
Source0:        %{url}/archive/refs/tags/verbum-%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-lxml
BuildRequires:  python3-gobject
BuildRequires:  gtk4
BuildRequires:  libadwaita
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
BuildRequires:  shared-mime-info

Requires:       python3 >= 3.11
Requires:       python3-lxml
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gstreamer1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       hicolor-icon-theme
Requires:       shared-mime-info
Requires:       desktop-file-utils
Requires:       xdg-utils
# PyGlossary is not guaranteed to exist in the target repositories.
Recommends:     (python3dist(pyglossary) >= 5 with python3dist(pyglossary) < 6)

%description
Verbum is a multilingual lexical service and native GNOME dictionary
application. It imports local dictionaries into Verbum Lexical Format
(VLF), a SQLite-based storage format, and supports ranked lexical
search, spelling suggestions, and contextual Longman audio.

Babylon BGL import requires the optional PyGlossary 5.x dependency.
Dictionary contents are not distributed with this package.

%prep
%autosetup -n %{upstream_repo}-verbum-%{version}

%build
# Pure Python application; no Qt build or network access needed.

%install
install -d %{buildroot}%{python3_sitelib}/verbum
install -pm0644 verbum/*.py verbum/catalog.toml %{buildroot}%{python3_sitelib}/verbum/

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/verbum <<'EOF'
#!%{__python3}
from verbum.__main__ import main
raise SystemExit(main())
EOF
chmod 0755 %{buildroot}%{_bindir}/verbum

desktop-file-install --dir=%{buildroot}%{_datadir}/applications data/%{appid}.desktop
install -Dm0644 data/%{appid}.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
install -Dm0644 data/%{appid}.xml %{buildroot}%{_datadir}/mime/packages/%{appid}.xml
install -Dm0644 data/%{appid}.metainfo.xml %{buildroot}%{_datadir}/metainfo/%{appid}.metainfo.xml

%check
%{__python3} -m unittest discover -s tests -p 'test_verbum*.py' -v
%{__python3} -c 'from verbum.gtk import Application; from verbum import idmreader'
desktop-file-validate %{buildroot}%{_datadir}/applications/%{appid}.desktop
appstream-util validate-relax --nonet %{buildroot}%{_datadir}/metainfo/%{appid}.metainfo.xml
# Test MIME compilation outside the buildroot.
mkdir -p mime-check/packages
cp data/%{appid}.xml mime-check/packages/
update-mime-database mime-check

%files
%license COPYING.txt LICENSE.txt
%doc docs/VERBUM.md
%{_bindir}/verbum
%{python3_sitelib}/verbum/
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
%{_datadir}/mime/packages/%{appid}.xml
%{_datadir}/metainfo/%{appid}.metainfo.xml

%changelog
* Sat Nov 14 2026 Moacyr Prado - 0.4.3-1
- Initial independent Verbum RPM packaging
- Include GNOME launcher, SVG icon, AppStream metadata and BGL MIME integration
- Isolate Longman archive reader from legacy Qt viewer
