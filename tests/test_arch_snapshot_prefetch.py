import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "packaging/linux/prefetch-snapshot-packages.sh"
BUILDER = ROOT / "packaging/linux/build-linux.sh"


class ArchSnapshotPrefetchTests(unittest.TestCase):
    def mock(self, failures, packages=("python", "archiso")):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            pacman = bindir / "pacman"
            pacman.write_text("""#!/bin/bash
n=$(cat "$COUNTER" 2>/dev/null || echo 0)
n=$((n+1))
echo "$n" > "$COUNTER"
echo "$*" >> "$CALLS"
if ((n<=FAILURES)); then exit 28; fi
exit 0
""")
            pacman.chmod(0o755)
            sleeper = bindir / "sleep"
            sleeper.write_text("#!/bin/sh\necho slept >> \"$SLEEPS\"\n")
            sleeper.chmod(0o755)
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                       COUNTER=str(root/"count"), CALLS=str(root/"calls"),
                       SLEEPS=str(root/"sleeps"), FAILURES=str(failures),
                       SCRIPT=str(HELPER))
            cmd = ["bash", "-c", 'set -euo pipefail; source "$SCRIPT"; phios_prefetch_snapshot_packages "$@"',
                   "bash", *packages]
            p = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=15)
            log = (root/"calls").read_text().splitlines() if (root/"calls").exists() else []
            sleeps = (root/"sleeps").read_text().splitlines() if (root/"sleeps").exists() else []
            return p.returncode, p.stdout+p.stderr, log, sleeps

    def test_build_order_and_syntax(self):
        for path in (HELPER, BUILDER):
            subprocess.run(["bash", "-n", str(path)], check=True)
        script = BUILDER.read_text()
        self.assertIn("archive.archlinux.org/repos/$snapshot/", script)
        self.assertIn('phios_prefetch_snapshot_packages "${snapshot_packages[@]}"', script)
        self.assertIn('pacman --disable-download-timeout -S --needed --noconfirm "${snapshot_packages[@]}"', script)
        self.assertLess(script.index("phios_prefetch_snapshot_packages"), script.index("pacman --disable-download-timeout -S"))

    def test_archiso_uses_same_signed_snapshot_but_survives_slow_archive(self):
        profile = (ROOT / "packaging/linux/prepare_profile.py").read_text()
        self.assertIn("DisableDownloadTimeout", profile)
        self.assertIn("SigLevel = Required DatabaseOptional", profile)
        self.assertIn("archive.archlinux.org/repos/{snapshot}/$repo/os/$arch", profile)
        self.assertIn("ParallelDownloads = 5", profile)
        self.assertNotIn("SigLevel = Never", profile)

    def test_success_first_attempt(self):
        code, out, log, sleeps = self.mock(0)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(log), 1)
        self.assertFalse(sleeps)
        self.assertIn("-Sw --needed --noconfirm", log[0])
        self.assertIn("--disable-download-timeout", log[0])
        self.assertNotIn("--skippgpcheck", log[0])

    def test_temporary_network_problem_retries(self):
        code, out, log, sleeps = self.mock(2)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(log), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(len(set(log)), 1)
        self.assertIn("PHIOS_ARCH_PREFETCH_OK: attempt 3/3", out)

    def test_repeated_failure_holds_build(self):
        code, out, log, sleeps = self.mock(9)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(log), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertIn("PHIOS_ARCH_PREFETCH_FAILED", out)

    def test_no_packages_rejected(self):
        code, out, log, sleeps = self.mock(0, ())
        self.assertEqual(code, 2, out)
        self.assertEqual(log, [])
        self.assertEqual(sleeps, [])
        self.assertIn("PHIOS_ARCH_PREFETCH_REFUSED", out)


if __name__ == "__main__":
    unittest.main()
