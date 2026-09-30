"""Exercise host source snapshots without building or activating a system."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WRAPPER = Path(sys.argv.pop(1))
IGNORE = Path(sys.argv.pop(1))
SYNC = Path(sys.argv.pop(1))
CHECK_ALL = Path(sys.argv.pop(1))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repo = self.directory / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        self.wrapper = self.repo / "scripts/with-local-flake.sh"
        shutil.copyfile(WRAPPER, self.wrapper)
        shutil.copyfile(SYNC, self.repo / "scripts/sync-checkout.sh")
        shutil.copyfile(CHECK_ALL, self.repo / "scripts/check-all.sh")
        shutil.copyfile(IGNORE, self.repo / ".gitignore")
        self.tracked = self.repo / "tracked.txt"
        self.tracked.write_text("original")
        self.git("init", "--quiet")
        self.git("add", ".")
        self.index = (self.repo / ".git/index").read_bytes()
        self.capture = self.directory / "capture.py"
        self.capture.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "url = sys.argv[2]\n"
            "root = Path(url.removeprefix('path:').split('#', 1)[0])\n"
            "files = {str(p.relative_to(root)): p.read_text() "
            "for p in root.rglob('*') if p.is_file()}\n"
            "modes = {str(p.relative_to(root)): p.stat().st_mode & 0o777 "
            "for p in root.rglob('*') if p.is_file()}\n"
            "Path(sys.argv[1]).write_text(json.dumps("
            "{'url': url, 'root': str(root), 'files': files, 'modes': modes}))\n"
            "sys.exit(int(sys.argv[3]))\n"
        )
        self.output = self.directory / "result.json"

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def snapshot(self, *, argument=".#lib.fixture", exit_code=0):
        return subprocess.run(
            [
                "bash",
                str(self.wrapper),
                sys.executable,
                str(self.capture),
                str(self.output),
                argument,
                str(exit_code),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_untracked_source_and_tracked_edits_are_included_without_staging(self):
        (self.repo / "lib").mkdir()
        (self.repo / "lib/palette.json").write_text('{"base": "#171717"}')
        unusual = "scripts/helper space\nand newline.py"
        (self.repo / unusual).write_text("# fixture")
        self.tracked.write_text("modified")
        result = self.snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.output.read_text())
        self.assertEqual(captured["files"]["lib/palette.json"], '{"base": "#171717"}')
        self.assertEqual(captured["files"][unusual], "# fixture")
        self.assertEqual(captured["files"]["tracked.txt"], "modified")
        self.assertTrue(captured["url"].endswith("#lib.fixture"))
        self.assertFalse(Path(captured["root"]).exists())
        self.assertEqual((self.repo / ".git/index").read_bytes(), self.index)

    def test_ignored_credentials_and_outputs_are_excluded_with_settings_exception(self):
        for name in [".env", "private.key", "password.hash", "result-system", "nvim.log"]:
            (self.repo / name).write_text("private fixture")
        settings = self.repo / "installation.json"
        settings.write_text('{"fixture": true}')
        settings.chmod(0o600)
        result = self.snapshot(argument="@local-flake@")
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.output.read_text())
        self.assertEqual(captured["files"]["installation.json"], '{"fixture": true}')
        self.assertEqual(captured["modes"]["installation.json"], 0o600)
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)
        for name in [".env", "private.key", "password.hash", "result-system", "nvim.log"]:
            self.assertNotIn(name, captured["files"])
        self.assertFalse(any(name.startswith(".git/") for name in captured["files"]))

    def test_failure_code_is_preserved_and_temporary_snapshot_is_removed(self):
        result = self.snapshot(exit_code=7)
        self.assertEqual(result.returncode, 7, result.stderr)
        captured = json.loads(self.output.read_text())
        self.assertFalse(Path(captured["root"]).exists())
        self.assertFalse(Path(captured["root"]).parent.exists())

    def test_unstaged_deletion_and_rename_use_current_working_tree(self):
        self.tracked.unlink()
        source = self.repo / "scripts/old name\n.py"
        source.write_text("# original")
        self.git("add", str(source.relative_to(self.repo)))
        source.rename(self.repo / "scripts/new name\n.py")
        result = self.snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.output.read_text())["files"]
        self.assertNotIn("tracked.txt", captured)
        self.assertNotIn("scripts/old name\n.py", captured)
        self.assertEqual(captured["scripts/new name\n.py"], "# original")

    def test_credentials_and_arbitrary_untracked_files_never_enter_snapshot(self):
        names = [
            ".env.local",
            ".env.production",
            "private.pem",
            "private.p12",
            "private.pfx",
            "identity.agekey",
        ]
        for name in names:
            (self.repo / name).write_text("synthetic secret")
        # Even force-added credential names must be filtered.
        self.git("add", "--force", ".env.local", "private.pem")
        (self.repo / "scripts/credentials.txt").write_text("synthetic secret")
        (self.repo / "arbitrary-secret").write_text("synthetic secret")
        result = self.snapshot()
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.output.read_text())["files"]
        for name in [*names, "scripts/credentials.txt", "arbitrary-secret"]:
            self.assertNotIn(name, captured)

    def test_snapshot_only_requires_a_new_destination(self):
        destination = self.directory / "snapshot"
        args = ["bash", str(self.wrapper), "--snapshot-only", str(destination)]
        first = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((destination / "tracked.txt").read_text(), "original")
        self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)

    def test_resumed_checkout_matches_source_and_preserves_previous_changes(self):
        destination = self.directory / "workstation"
        args = [
            "bash",
            str(self.repo / "scripts/sync-checkout.sh"),
            str(self.repo),
            str(destination),
        ]
        subprocess.run(args, check=True, capture_output=True)
        subprocess.run(args, check=True, capture_output=True)
        self.assertEqual(list(self.directory.glob("workstation.before-resume.*")), [])
        (destination / "local-note.txt").write_text("keep my changes")
        (self.repo / "installation.json").write_text('{"fixture": "updated"}')
        self.tracked.write_text("fixed source")
        subprocess.run(args, check=True, capture_output=True)
        self.assertEqual((destination / "tracked.txt").read_text(), "fixed source")
        self.assertEqual((destination / "installation.json").read_text(), '{"fixture": "updated"}')
        backups = list(self.directory.glob("workstation.before-resume.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "tracked.txt").read_text(), "original")
        self.assertEqual((backups[0] / "local-note.txt").read_text(), "keep my changes")
        self.assertTrue((destination / ".git/index").is_file())

    def test_install_copies_frozen_source_instead_of_changed_live_files(self):
        source = self.directory / "frozen"
        subprocess.run(["bash", str(self.wrapper), "--snapshot-only", str(source)], check=True)
        self.tracked.write_text("changed after build")
        (self.repo / "installation.json").write_text('{"userName": "bob"}')
        destination = self.directory / "installed"
        subprocess.run(
            [
                "bash",
                str(self.repo / "scripts/sync-checkout.sh"),
                str(self.repo),
                str(destination),
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        self.assertEqual((destination / "tracked.txt").read_text(), "original")
        self.assertFalse((destination / "installation.json").exists())
        self.assertEqual((destination / ".git/index").read_bytes(), self.index)

    def test_live_checkout_cannot_be_passed_as_a_filtered_snapshot(self):
        destination = self.directory / "installed"
        result = subprocess.run(
            [
                "bash",
                str(self.repo / "scripts/sync-checkout.sh"),
                str(self.repo),
                str(destination),
                str(self.repo),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("filtered installation source snapshot", result.stderr)
        self.assertFalse(destination.exists())

    def test_whole_flake_checks_include_new_source_without_an_installation_disk(self):
        commands = self.directory / "bin"
        commands.mkdir()
        nix = commands / "nix"
        nix.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\nfrom pathlib import Path\n"
            "assert sys.argv[1:3] == ['flake', 'check']\n"
            "root = Path(sys.argv[3].removeprefix('path:'))\n"
            f"Path({str(self.output)!r}).write_text(json.dumps({{"
            "'root': str(root), 'source': (root / 'lib/new.nix').read_text()}))\n"
        )
        nix.chmod(0o755)
        (self.repo / "lib").mkdir()
        (self.repo / "lib/new.nix").write_text("{ newSource = true; }")
        result = subprocess.run(
            [
                "bash",
                str(self.wrapper),
                "nix",
                "flake",
                "check",
                "@local-flake@",
                "--no-update-lock-file",
            ],
            env=os.environ | {"PATH": str(commands) + os.pathsep + os.environ["PATH"]},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.output.read_text())
        self.assertEqual(captured["source"], "{ newSource = true; }")
        self.assertFalse(Path(captured["root"]).exists())
        self.assertEqual((self.repo / ".git/index").read_bytes(), self.index)

    def test_settings_symlink_is_rejected_before_running_command(self):
        target = self.directory / "private-settings.json"
        target.write_text("private fixture")
        (self.repo / "installation.json").symlink_to(target)
        result = self.snapshot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installation.json must be a regular file", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(target.read_text(), "private fixture")

    def check_all(self, *, failed_check="", discovery_failure=False):
        commands = self.directory / "bin"
        commands.mkdir()
        nix = commands / "nix"
        nix.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\nfrom pathlib import Path\n"
            f"log = Path({str(self.output)!r})\n"
            "calls = json.loads(log.read_text()) if log.exists() else []\n"
            "target = next(arg for arg in sys.argv if arg.startswith('path:'))\n"
            "root = Path(target.removeprefix('path:').split('#', 1)[0])\n"
            "calls.append({'args': sys.argv[1:], 'root': str(root), "
            "'source': (root / 'tracked.txt').read_text(), "
            "'policy': (root / 'SECURITY.md').read_text()})\n"
            "log.write_text(json.dumps(calls))\n"
            "assert '--no-update-lock-file' in sys.argv\n"
            "if sys.argv[1] == 'eval':\n"
            "    if target.endswith('#lib.checkGroups'):\n"
            "        print('fast\\nmatrix')\n"
            "        sys.exit(0)\n"
            f"    if {discovery_failure!r}: sys.exit(31)\n"
            "    print('alpha\\nbeta\\nfast\\ngamma\\nmatrix')\n"
            "else:\n"
            "    assert '--no-link' in sys.argv\n"
            "    assert sys.argv[-5:] == ['--max-jobs', '2', '--cores', '4', '-L']\n"
            f"    Path({str(self.tracked)!r}).write_text('changed during checks')\n"
            f"    if target.endswith('.{failed_check}') and {failed_check!r}: sys.exit(23)\n"
        )
        nix.chmod(0o755)
        # A new root policy file must be captured without changing the index.
        (self.repo / "SECURITY.md").write_text("# Reporting policy")
        result = subprocess.run(
            [
                "bash",
                str(self.wrapper),
                "bash",
                str(self.repo / "scripts/check-all.sh"),
                ".#checks.x86_64-linux",
                "--max-jobs",
                "2",
                "--cores",
                "4",
                "-L",
            ],
            env=os.environ | {"PATH": str(commands) + os.pathsep + os.environ["PATH"]},
            capture_output=True,
            text=True,
        )
        calls = json.loads(self.output.read_text())
        self.assertEqual(len({call["root"] for call in calls}), 1)
        self.assertTrue(all(call["source"] == "original" for call in calls))
        self.assertTrue(all(call["policy"] == "# Reporting policy" for call in calls))
        self.assertFalse(Path(calls[0]["root"]).exists())
        self.assertEqual((self.repo / ".git/index").read_bytes(), self.index)
        targets = [
            next(arg for arg in call["args"] if arg.startswith("path:")).rsplit(".", 1)[1]
            for call in calls
            if call["args"][0] == "build"
        ]
        return result, targets

    def test_all_checks_discover_outputs_and_reuse_one_source(self):
        result, targets = self.check_all()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(targets, ["fast", "alpha", "beta", "gamma"])

    def test_all_checks_stop_on_failure_and_preserve_its_status(self):
        result, targets = self.check_all(failed_check="beta")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(targets, ["fast", "alpha", "beta"])

    def test_all_checks_stop_when_output_discovery_fails(self):
        result, targets = self.check_all(discovery_failure=True)
        self.assertEqual(result.returncode, 31, result.stderr)
        self.assertEqual(targets, ["fast"])


if __name__ == "__main__":
    # Do not let ambient Git configuration change the isolated fixture policy.
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    unittest.main()
