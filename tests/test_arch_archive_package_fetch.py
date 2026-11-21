"""Offline exact-version Arch archive pool download and refusal contract."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "packaging/linux/archive-package-fetch.sh"
SNAPSHOT = json.loads((ROOT / "packaging/linux/release.json").read_text())["arch_snapshot"]


class ArchivePackageFetchTests(unittest.TestCase):
    def mock(self, filename, *, snapshot=SNAPSHOT, host="umea.archive.pkgbuild.com",
             fail_first=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            curl.write_text("""#!/usr/bin/env bash
set -euo pipefail
url=''
while (($#)); do
    if [[ $1 == '-o' ]]; then
        printf 'fixed bytes' > "$2"
        shift 2
    else
        url=$1
        shift
    fi
done
printf '%s\\n' "$url" >> "$TRACE"
if [[ $FAIL_FIRST == 1 && $(wc -l < "$TRACE") == 1 ]]; then
    exit 22
fi
""")
            curl.chmod(0o755)
            output = root / "output.part"
            trace = root / "urls"
            uri = f"https://{host}/repos/{snapshot}/core/os/x86_64/{filename}"
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       TRACE=str(trace), FAIL_FIRST="1" if fail_first else "0")
            proc = subprocess.run(["bash", str(FETCH), uri, str(output)], env=env,
                                  text=True, capture_output=True, timeout=10)
            return proc, trace.read_text().splitlines() if trace.exists() else [], output.exists()

    def test_exact_version_from_archive_pool(self):
        p, urls, exists = self.mock("glibc-2.44+r50+g1848099f063e-1-x86_64.pkg.tar.zst")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(exists)
        self.assertEqual(urls, [
            "https://umea.archive.pkgbuild.com/packages/g/glibc/"
            "glibc-2.44+r50+g1848099f063e-1-x86_64.pkg.tar.zst"
        ])

    def test_hyphenated_package_signature(self):
        p, urls, exists = self.mock("linux-firmware-intel-20260927-1-any.pkg.tar.zst.sig")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(exists)
        self.assertEqual(urls, [
            "https://umea.archive.pkgbuild.com/packages/l/linux-firmware-intel/"
            "linux-firmware-intel-20260927-1-any.pkg.tar.zst.sig"
        ])

    def test_same_filename_when_primary_pool_unavailable(self):
        p, urls, exists = self.mock("pcre2-10.49-1-x86_64.pkg.tar.zst.sig",
                                    fail_first=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(exists)
        self.assertEqual(urls, [
            "https://umea.archive.pkgbuild.com/packages/p/pcre2/pcre2-10.49-1-x86_64.pkg.tar.zst.sig",
            "https://archive.archlinux.org/packages/p/pcre2/pcre2-10.49-1-x86_64.pkg.tar.zst.sig",
        ])

    def test_repository_database_stays_pinned(self):
        p, urls, exists = self.mock("core.db")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(exists)
        self.assertEqual(urls, [
            f"https://umea.archive.pkgbuild.com/repos/{SNAPSHOT}/core/os/x86_64/core.db"
        ])

    def test_rejects_unreviewed_snapshot_or_host(self):
        for date, host in [("2026/11/21", "umea.archive.pkgbuild.com"),
                           (SNAPSHOT, "evil.invalid")]:
            p, urls, exists = self.mock("pcre2-10.49-1-x86_64.pkg.tar.zst",
                                         snapshot=date, host=host)
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertIn("PHIOS_ARCH_FETCH_REFUSED", p.stderr)
            self.assertFalse(exists)
            self.assertFalse(urls)

    def test_rejects_unknown_object_type(self):
        p, urls, exists = self.mock("unsafe.txt")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(exists)
        self.assertFalse(urls)


if __name__ == "__main__":
    unittest.main()
