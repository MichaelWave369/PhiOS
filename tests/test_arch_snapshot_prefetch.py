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
        self.assertIn("phios_prefetch_snapshot_upgrade", script)
        self.assertIn('phios_prefetch_archiso_profile_packages "$work/profile/pacman.conf" "$work/profile/packages.x86_64"', script)
        self.assertLess(script.index("phios_prefetch_archiso_profile_packages"), script.index("mkarchiso -v"))
        self.assertIn("pacman --disable-download-timeout -Suu --noconfirm", script)
        self.assertLess(
            script.index("phios_prefetch_snapshot_upgrade"),
            script.index("pacman --disable-download-timeout -Suu --noconfirm"),
        )
        self.assertLess(
            script.index("phios_prefetch_snapshot_packages"),
            script.index('pacman --disable-download-timeout -S --needed --noconfirm'),
        )

    def test_archiso_uses_same_signed_snapshot_but_survives_slow_archive(self):
        profile = (ROOT / "packaging/linux/prepare_profile.py").read_text()
        self.assertIn("DisableDownloadTimeout", profile)
        self.assertIn("SigLevel = Required DatabaseOptional", profile)
        self.assertIn("archive.archlinux.org/repos/{snapshot}/$repo/os/$arch", profile)
        self.assertIn("ParallelDownloads = 2", profile)
        self.assertNotIn("SigLevel = Never", profile)

    def mock_profile(self, failures=0, packages=("linux", "linux-firmware", "phios"), *,
                     profile_cache="/var/cache/pacman/pkg/"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            (root / "profile.conf").write_text(
                "[options]\nSigLevel = Required DatabaseOptional\n"
                "ParallelDownloads = 2\n"
                "[core]\nServer = https://archive.archlinux.org/repos/2026/09/30/$repo/os/$arch\n"
            )
            (root / "packages").write_text("\n".join(packages) + "\n")
            pacman = bindir / "pacman"
            pacman.write_text("""#!/bin/bash
n=$(cat "$COUNTER" 2>/dev/null || echo 0)
n=$((n+1))
echo "$n" > "$COUNTER"
printf '%s\\n' "$*" >> "$CALLS"
if ((n<=FAILURES)); then exit 28; fi
exit 0
""")
            pacman.chmod(0o755)
            conf = bindir / "pacman-conf"
            conf.write_text("""#!/bin/bash
if [[ "$1" == "--config" ]]; then
  printf '%s\\n' "$PROFILE_CACHE"
else
  printf '%s\\n' /var/cache/pacman/pkg/
fi
""")
            conf.chmod(0o755)
            sleeper = bindir / "sleep"
            sleeper.write_text("#!/bin/sh\necho slept >> \"$SLEEPS\"\n")
            sleeper.chmod(0o755)
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                       COUNTER=str(root/"count"), CALLS=str(root/"calls"),
                       SLEEPS=str(root/"sleeps"), FAILURES=str(failures),
                       PROFILE_CACHE=profile_cache, SCRIPT=str(HELPER),
                       CONFIG=str(root/"profile.conf"), PACKAGES=str(root/"packages"))
            run = subprocess.run(["bash", "-c",
                                  'set -euo pipefail; source "$SCRIPT"; '
                                  'phios_prefetch_archiso_profile_packages "$CONFIG" "$PACKAGES"'],
                                 env=env, capture_output=True, text=True, timeout=15)
            log = (root/"calls").read_text().splitlines() if (root/"calls").exists() else []
            sleeps = (root/"sleeps").read_text().splitlines() if (root/"sleeps").exists() else []
            return run.returncode, run.stdout + run.stderr, log, sleeps

    def test_archiso_profile_signed_prefetch_retry_then_success(self):
        status, output, calls, sleeps = self.mock_profile(failures=2)
        self.assertEqual(status, 0, output)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(len(set(calls)), 1)
        self.assertIn("PHIOS_ARCHISO_PREFETCH_OK: attempt 3/3", output)
        self.assertIn("--disable-download-timeout", calls[0])
        self.assertIn("-Syw --noconfirm linux linux-firmware phios", calls[0])
        self.assertNotIn("--needed", calls[0])
        self.assertNotIn("--skippgpcheck", calls[0])
        self.assertNotIn("--dbonly", calls[0])

    def test_archiso_profile_signed_prefetch_fails_closed(self):
        status, output, calls, sleeps = self.mock_profile(failures=10)
        self.assertEqual(status, 1, output)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)
        self.assertIn("PHIOS_ARCHISO_PREFETCH_FAILED", output)

    def test_archiso_profile_uses_exact_list_even_for_builder_installed_packages(self):
        status, output, calls, _ = self.mock_profile(packages=("base", "linux", "phios", "phishell"))
        self.assertEqual(status, 0, output)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("base linux phios phishell"))
        self.assertNotIn("--needed", calls[0])

    def test_archiso_profile_rejects_empty_malformed_or_incompatible_cache(self):
        for options in (
            {"packages": ()},
            {"packages": ("linux", "bad;touch /tmp/pwned")},
            {"profile_cache": "/tmp/private-pacman-cache/"},
        ):
            status, output, calls, _ = self.mock_profile(**options)
            self.assertEqual(status, 2, output)
            self.assertEqual(calls, [])
            self.assertIn("PHIOS_ARCHISO_PREFETCH_REFUSED", output)

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
