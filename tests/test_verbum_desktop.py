import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from verbum.desktop import install_desktop, APP_ID, MIME

class DesktopTests(unittest.TestCase):
    def test_install(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"XDG_DATA_HOME":tmp}), patch("verbum.desktop.shutil.which", return_value="/bin/test"), patch("verbum.desktop.subprocess.run") as run:
            install_desktop(default_bgl=True)
            desktop = (Path(tmp)/"applications"/(APP_ID+".desktop")).read_text()
            self.assertIn("gui -- %F", desktop)
            self.assertIn("MimeType="+MIME+";", desktop)
            self.assertTrue((Path(tmp)/"mime/packages"/(APP_ID+".xml")).is_file())
            run.assert_any_call(["xdg-mime","default",APP_ID+".desktop",MIME],check=True)
