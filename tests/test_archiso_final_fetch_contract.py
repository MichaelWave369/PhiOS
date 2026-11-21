"""Verify the generated mkarchiso profile always uses the reviewed package-pool downloader."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "packaging/linux/archive-package-fetch.sh"
SCRIPT = ROOT / "packaging/linux/prepare_profile.py"


class ArchisoFinalFetchTests(unittest.TestCase):
    def test_generated_profile_fetches_all_new_root_dependencies_through_signed_archive(self):
        spec = importlib.util.spec_from_file_location("profile_under_test", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "releng"
            fixtures = {
                "profiledef.sh": "template\n",
                "efiboot/loader/entries/01-archiso-linux.conf":
                    "title Arch Linux\noptions archisobasedir=%INSTALL_DIR%\n",
                "airootfs/etc/mkinitcpio.conf.d/archiso.conf": "HOOKS=(base udev archiso filesystems)\n",
            }
            for name, content in fixtures.items():
                path = upstream / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            dest = root / "profile"
            module.prepare(upstream, dest, ROOT, root / "packages", smoke=False)
            config = (dest / "pacman.conf").read_text()
            profiledef = (dest / "profiledef.sh").read_text()

        snapshot = json.loads((ROOT / "packaging/linux/release.json").read_text())["arch_snapshot"]
        self.assertEqual(config.count("XferCommand = "), 1)
        self.assertIn(f"XferCommand = /usr/bin/bash {FETCH.resolve()} %u %o", config)
        for host in ("umea.archive.pkgbuild.com", "archive.archlinux.org"):
            self.assertEqual(config.count(f"Server = https://{host}/repos/{snapshot}/$repo/os/$arch"), 2)
        self.assertIn("SigLevel = Required DatabaseOptional", config)
        self.assertNotIn("SigLevel = Never", config)
        self.assertIn("LocalFileSigLevel = Optional", config)
        self.assertIn('pacman_conf="pacman.conf"', profiledef)
        build = (ROOT / "packaging/linux/build-linux.sh").read_text()
        self.assertLess(build.index("phios_prefetch_archiso_profile_packages"), build.index("mkarchiso -v"))


if __name__ == "__main__":
    unittest.main()
