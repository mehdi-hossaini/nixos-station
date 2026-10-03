"""Exercise installer safety and orchestration without touching real disks."""

import copy
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
installer_path = sys.argv.pop(1)
sys.path.insert(0, str(Path(installer_path).parent))
spec = importlib.util.spec_from_file_location("installer", installer_path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

DISK = {
    "name": "/dev/testdisk",
    "maj:min": "250:0",
    "size": 64 * 1024**3,
    "type": "disk",
    "model": "Test",
    "serial": "fixture",
    "ro": False,
    "mountpoints": [None],
    "by_id": "/dev/disk/by-id/test-fixture",
    "children": [{"type": "part", "mountpoints": [None]}],
}


class FrozenInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "settings.nix").write_text("# fixture")
        (self.repo / "scripts/prepare-install.sh").write_text("# frozen bootstrap")
        self.settings = {"disk": DISK["by_id"], "userName": "alice"}
        self.saved = self.repo / "installation.json"
        self.saved.write_text(json.dumps(self.settings))
        self.snapshots = installer.FlakeSnapshots()
        self.addCleanup(self.snapshots.close)
        self.process_run = subprocess.run
        self.enterContext(patch.object(installer, "REPO", self.repo))
        self.enterContext(patch.object(installer, "SNAPSHOTS", self.snapshots))

        def capture(args, **_kwargs):
            shutil.copytree(self.repo, args[-1])

        self.enterContext(patch.object(installer.subprocess, "run", side_effect=capture))

    def evaluate(self, *args, **_kwargs):
        saved = json.loads((self.snapshots.path / "installation.json").read_text())
        if "--file" in args:
            self.assertEqual(Path(args[args.index("--file") + 1]).parent, self.snapshots.path)
            return json.dumps(saved)
        self.snapshots.command(args)
        return json.dumps({"system": saved["disk"]})

    def test_settings_drift_before_freezing_fails_before_builds(self):
        self.saved.write_text(json.dumps(self.settings | {"disk": "/dev/disk/by-id/other"}))
        with patch.object(installer, "run", side_effect=self.evaluate) as run:
            with self.assertRaisesRegex(ValueError, "Settings changed"):
                installer.freeze_installation(self.settings)
        self.assertEqual(run.call_count, 1)

    def test_freezing_captures_source_edits_since_the_preview(self):
        self.snapshots.command(("nix", "eval", ".#preview"))
        preview = self.snapshots.path
        (self.repo / "scripts/prepare-install.sh").write_text("# revised bootstrap")
        with patch.object(installer, "run", side_effect=self.evaluate):
            source = installer.freeze_installation(self.settings)
        self.assertNotEqual(source, preview)
        self.assertEqual((preview / "scripts/prepare-install.sh").read_text(), "# frozen bootstrap")
        self.assertEqual((source / "scripts/prepare-install.sh").read_text(), "# revised bootstrap")

    def test_freezing_accepts_the_same_nix_secret_path_in_the_captured_source(self):
        secret = self.repo / "secrets/workstation.yaml"
        secret.parent.mkdir()
        secret.write_text("encrypted fixture")
        settings = self.settings | {"secretsFile": str(secret)}

        def evaluate(*args, **kwargs):
            if "--file" in args:
                return json.dumps(
                    settings
                    | {"secretsFile": str(self.snapshots.path / "secrets/workstation.yaml")}
                )
            return self.evaluate(*args, **kwargs)

        with patch.object(installer, "run", side_effect=evaluate):
            source = installer.freeze_installation(settings)
        self.assertEqual((source / "secrets/workstation.yaml").read_text(), secret.read_text())
        self.assertNotIn("secretsFile", json.loads((source / "installation.json").read_text()))

    def test_secret_relocation_does_not_hide_different_paths_or_contents(self):
        secret = self.repo / "secrets/workstation.yaml"
        secret.parent.mkdir()
        secret.write_text("encrypted fixture")
        for relative, content in (
            ("secrets/other.yaml", "encrypted fixture"),
            ("secrets/workstation.yaml", "different encrypted fixture"),
        ):

            def evaluate(*_args, relative=relative, content=content, **_kwargs):
                captured = self.snapshots.path / relative
                captured.write_text(content)
                return json.dumps(self.settings | {"secretsFile": str(captured)})

            with (
                self.subTest(relative=relative, content=content),
                patch.object(installer, "run", side_effect=evaluate),
                self.assertRaisesRegex(ValueError, "Settings changed"),
            ):
                installer.freeze_installation(self.settings | {"secretsFile": str(secret)})
            self.snapshots.frozen = False

    def test_bootstrap_uses_supplied_username_without_reading_live_nix_settings(self):
        commands = self.repo / "bin"
        commands.mkdir()
        scripts = {
            "id": "printf '0\\n'",
            "mountpoint": "exit 1",
            "nix": 'touch "$BOOTSTRAP_TEST_NIX_LOG"; exit 1',
        }
        for name, text in scripts.items():
            command = commands / name
            command.write_text(f"#!{shutil.which('bash')}\n" + text + "\n")
            command.chmod(0o755)
        marker = self.repo / "nix-called"
        result = self.process_run(
            [
                "bash",
                str(Path(installer_path).with_name("prepare-install.sh")),
                "alice",
                str(self.repo),
            ],
            env=os.environ
            | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "BOOTSTRAP_TEST_NIX_LOG": str(marker),
            },
            capture_output=True,
            text=True,
        )
        # Stop at the first unavailable mount, before creating credentials or
        # directories. Reaching this guard proves the helper accepted the
        # explicit username without invoking Nix on the mutable checkout.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing target mount: /mnt", result.stderr)
        self.assertFalse(marker.exists())

    def test_formatter_override_or_extra_disk_is_rejected(self):
        for disks in (
            {"system": "/dev/disk/by-id/other"},
            {"system": DISK["by_id"], "extra": "/dev/disk/by-id/other"},
        ):
            with (
                self.subTest(disks=disks),
                patch.object(self.snapshots, "freeze", return_value=self.repo),
                patch.object(
                    installer, "run", side_effect=[json.dumps(self.settings), json.dumps(disks)]
                ),
                self.assertRaisesRegex(ValueError, "formatter's disk configuration"),
            ):
                installer.freeze_installation(self.settings)

    def test_builds_confirmation_and_bootstrap_share_one_plan_despite_live_edits(self):
        with patch.object(installer, "run", side_effect=self.evaluate):
            source = installer.freeze_installation(self.settings)
        observed = []

        def build_command(*args, **_kwargs):
            rewritten = self.snapshots.command(args)
            observed.append(next(arg for arg in rewritten if arg.startswith("path:")))
            saved = json.loads((self.snapshots.path / "installation.json").read_text())
            self.assertEqual(saved, self.settings)
            # Simulate edits while the system build runs, before the formatter build.
            self.saved.write_text(
                json.dumps(self.settings | {"disk": "/dev/disk/by-id/other", "userName": "bob"})
            )
            return (
                "/nix/store/fixture-system"
                if len(observed) == 1
                else "/nix/store/fixture-formatter"
            )

        with (
            patch.object(installer, "run", side_effect=build_command),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
        ):
            system, formatter = installer.build()
        self.assertTrue(all(reference.startswith(f"path:{source}#") for reference in observed))

        def confirm(_selected):
            self.saved.unlink()
            # Changing a convenience output link must not change the executed artifact.
            (self.repo / "result-disko").symlink_to("/nix/store/other-formatter")

        with (
            patch.object(installer, "verify_target") as verify,
            patch.object(installer, "confirm_erase", side_effect=confirm),
            patch.object(installer, "verify_hardware_unchanged"),
            patch.object(installer, "run") as run,
        ):
            installer.confirm_and_format(DISK, {}, self.settings, [], formatter)
            run.assert_called_once_with("/nix/store/fixture-formatter")
            self.assertEqual(verify.call_count, 2)

        with (
            patch.object(installer, "verify_mounted_install"),
            patch.object(installer, "verify_disk_passphrase"),
            patch.object(installer, "run") as run,
        ):
            installer.finish(self.settings, system, source)
        self.assertEqual(
            run.call_args_list[0].args,
            (
                "bash",
                str(source / "scripts/prepare-install.sh"),
                "alice",
                str(self.repo),
            ),
        )
        self.assertEqual(
            run.call_args_list[1].args,
            (
                "nixos-install",
                "--no-root-passwd",
                "--system",
                "/nix/store/fixture-system",
            ),
        )
        self.assertEqual(json.loads((source / "installation.json").read_text()), self.settings)

    def test_confirmation_cannot_use_a_different_selected_disk(self):
        with (
            patch.object(installer, "run") as run,
            self.assertRaisesRegex(ValueError, "confirmed disk"),
        ):
            installer.confirm_and_format(
                DISK,
                {},
                {"disk": "/dev/disk/by-id/other"},
                [],
                Path("/nix/store/fixture-formatter"),
            )
        run.assert_not_called()

    def test_invalid_build_output_stops_before_formatter_build(self):
        with patch.object(installer, "run", side_effect=self.evaluate):
            installer.freeze_installation(self.settings)
        for output in (
            "",
            "/tmp/output",
            "/nix/store/one\n/nix/store/two",
            "/nix/store/one/subdirectory",
        ):
            with (
                self.subTest(output=output),
                patch.object(installer, "run", return_value=output) as run,
                patch.object(Path, "is_dir", return_value=True),
                self.assertRaisesRegex(ValueError, "built toplevel store path"),
            ):
                installer.build()
            self.assertEqual(run.call_count, 1)

    def test_builds_require_a_frozen_source(self):
        with patch.object(installer, "run") as run:
            with self.assertRaisesRegex(ValueError, "frozen installation source"):
                installer.build()
        run.assert_not_called()


class InstallerTests(unittest.TestCase):
    def test_installer_flake_reads_use_local_snapshot_and_locked_inputs(self):
        with patch.object(
            installer.subprocess, "run", return_value=SimpleNamespace(stdout="{}\n")
        ) as command:
            self.assertEqual(
                installer.run("nix", "eval", "--json", ".#lib.graphicsMetadata", capture=True),
                "{}",
            )
        invoked = command.call_args.args[0]
        self.assertEqual(
            invoked[:3], ("bash", str(installer.REPO / "scripts/with-local-flake.sh"), "nix")
        )
        self.assertIn("--no-update-lock-file", invoked)
        self.assertIn(".#lib.graphicsMetadata", invoked)

    def test_creates_private_settings_file_from_fresh_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            with patch.object(installer, "REPO", repo):
                installer.save_settings({"disk": DISK["by_id"]})
            destination = repo / "installation.json"
            self.assertEqual(json.loads(destination.read_text()), {"disk": DISK["by_id"]})
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_export_is_private_and_never_overwrites_a_file_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "installation.json").write_text('{"fixture": true}')
            destination = root / "recovery.json"
            with patch.object(installer, "REPO", root):
                installer.export_settings(destination)
                self.assertEqual(destination.read_text(), '{"fixture": true}')
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError):
                    installer.export_settings(destination)
                link = root / "link.json"
                link.symlink_to(destination)
                with self.assertRaises(FileExistsError):
                    installer.export_settings(link)
            self.assertEqual(list(root.glob(".workstation-settings-*")), [])

    def test_failed_export_removes_only_its_incomplete_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "installation.json").write_text('{"fixture": true}')
            destination = root / "recovery.json"
            with (
                patch.object(installer, "REPO", root),
                patch.object(installer.os, "fsync", side_effect=OSError("fixture write failure")),
            ):
                with self.assertRaises(OSError):
                    installer.export_settings(destination)
            self.assertFalse(destination.exists())

    def test_installer_reuses_snapshot_and_refreshes_after_settings_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "installation.json"
            settings.write_text('{"fixture": 1}')
            snapshots = installer.FlakeSnapshots()
            try:
                with (
                    patch.object(installer, "REPO", root),
                    patch.object(installer.subprocess, "run") as command,
                ):
                    first = snapshots.command(("nix", "eval", ".#lib.fixture"))
                    second = snapshots.command(("nix", "build", ".#lib.fixture"))
                    self.assertEqual(first[-1], second[-1])
                    self.assertEqual(command.call_count, 1)
                    settings.write_text('{"fixture": 2}')
                    third = snapshots.command(("nix", "eval", ".#lib.fixture"))
                    self.assertNotEqual(first[-1], third[-1])
                    self.assertEqual(command.call_count, 2)
            finally:
                snapshots.close()
            self.assertFalse(Path(snapshots.temporary.name).exists())

    def test_small_terminal_uses_plain_choices_and_bounded_input(self):
        with (
            patch.object(
                installer.ui.shutil, "get_terminal_size", return_value=os.terminal_size((30, 12))
            ),
            patch("builtins.input", return_value="2"),
            patch.object(installer.ui, "gum") as gum,
        ):
            self.assertFalse(installer.ui.enabled())
            self.assertEqual(installer.ui.geometry(), (26, 1))
            self.assertEqual(installer.ui.select("Disk", [("a", "First"), ("b", "Second")]), "b")
            self.assertEqual(
                installer.ui.checklist("Apps", [("a", "First"), ("b", "Second")], set()), {"b"}
            )
            gum.assert_not_called()

    def test_saves_public_answers_without_losing_other_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            destination = repo / "installation.json"
            destination.write_text('{"backupRepository": "sftp:fixture:/backups"}')
            with patch.object(installer, "REPO", repo):
                installer.save_settings(
                    {"userName": "alice", "disk": DISK["by_id"], "desktop": "niri-terminal"}
                )
            self.assertEqual(
                json.loads(destination.read_text()),
                {
                    "backupRepository": "sftp:fixture:/backups",
                    "userName": "alice",
                    "disk": DISK["by_id"],
                    "desktop": "niri-terminal",
                },
            )
            self.assertFalse((repo / "installation.json.tmp").exists())

    def test_settings_save_does_not_follow_predictable_temp_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            destination = repo / "installation.json"
            destination.write_text('{"backupRepository": "fixture"}')
            destination.chmod(0o640)
            victim = repo / "victim"
            victim.write_text("keep me")
            (repo / "installation.json.tmp").symlink_to(victim)
            with patch.object(installer, "REPO", repo):
                installer.save_settings({"userName": "alice"})
            self.assertEqual(victim.read_text(), "keep me")
            self.assertEqual(json.loads(destination.read_text())["userName"], "alice")
            self.assertEqual(stat.S_IMODE(os.stat(destination).st_mode), 0o640)

    def test_rejects_busy_disk_including_nested_mapper_and_swap(self):
        self.assertIsNone(installer.blocked_reason(DISK))
        for mountpoint in ("/", "/iso", "/mnt", "[SWAP]"):
            disk = copy.deepcopy(DISK)
            disk["children"][0]["mountpoints"] = [mountpoint]
            self.assertIsNotNone(installer.blocked_reason(disk))
        disk = copy.deepcopy(DISK)
        disk["children"][0]["children"] = [{"type": "crypt", "mountpoints": [None]}]
        self.assertIsNotNone(installer.blocked_reason(disk))

    def test_rejects_small_readonly_and_partition_targets(self):
        for change in ({"size": 1024}, {"ro": True}, {"type": "part"}):
            self.assertIsNotNone(installer.blocked_reason(DISK | change))

    def test_disk_topology_has_a_fixed_limit_and_rejects_cycles(self):
        root = {"type": "disk", "mountpoints": [None], "children": []}
        node = root
        for _ in range(installer.MAX_BLOCK_NODES):
            child = {"type": "part", "mountpoints": [None], "children": []}
            node["children"].append(child)
            node = child
        with self.assertRaisesRegex(ValueError, "supported limit"):
            installer.blocked_reason(DISK | {"children": root["children"]})
        wide = DISK | {"children": [{"type": "part"}] * installer.MAX_BLOCK_NODES}
        with self.assertRaisesRegex(ValueError, "supported limit"):
            installer.blocked_reason(wide)
        cyclic = {"type": "disk", "children": []}
        cyclic["children"].append(cyclic)
        with self.assertRaisesRegex(ValueError, "malformed"):
            list(installer.block_tree(cyclic))

    def test_wrong_confirmation_never_formats(self):
        with (
            patch.object(installer, "verify_target"),
            patch("builtins.input", return_value="yes"),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaises(ValueError):
                installer.confirm_and_format(
                    DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
                )
            run.assert_not_called()

    def test_short_confirmation_still_requires_deliberate_erase(self):
        for answer in ("", "yes", "test-fixture", "erase this disk"):
            with (
                self.subTest(answer=answer),
                patch.object(installer, "verify_target"),
                patch("builtins.input", return_value=answer),
                patch.object(installer, "run") as run,
            ):
                with self.assertRaises(ValueError):
                    installer.confirm_and_format(
                        DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
                    )
                run.assert_not_called()
        with (
            patch.object(installer, "verify_target") as verify,
            patch.object(installer, "verify_hardware_unchanged") as hardware,
            patch("builtins.input", return_value="ERASE"),
            patch.object(installer, "run") as run,
        ):
            installer.confirm_and_format(
                DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
            )
            self.assertEqual(verify.call_count, 2)
            hardware.assert_called_once()
            run.assert_called_once_with("/nix/store/fixture-formatter")

    def test_tui_cancel_never_formats(self):
        with (
            patch.object(installer, "verify_target"),
            patch.object(installer.ui, "text", side_effect=KeyboardInterrupt),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaises(KeyboardInterrupt):
                installer.confirm_and_format(
                    DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
                )
            run.assert_not_called()

    def test_tui_rejects_unknown_selections_and_inherited_confirmation_values(self):
        with (
            patch.object(installer.ui, "enabled", return_value=True),
            patch.object(installer.ui, "gum", return_value="unexpected disk"),
        ):
            with self.assertRaises(ValueError):
                installer.ui.select("Disk", [("safe", "Known disk")])
        with patch.dict(os.environ, {"GUM_INPUT_VALUE": "ERASE", "GUM_CHOOSE_TIMEOUT": "1ms"}):
            self.assertNotIn("GUM_INPUT_VALUE", installer.ui.environment())
            self.assertNotIn("GUM_CHOOSE_TIMEOUT", installer.ui.environment())

    @unittest.skipUnless(installer.shutil.which("gum"), "Gum is supplied by the installer shell")
    def test_real_progress_preserves_output_and_failed_exit_status(self):
        with patch.object(installer.ui, "enabled", return_value=True):
            for code in (0, 7):
                command = installer.ui.progress_command(
                    [sys.executable, "-c", f"import sys; print('BUILD_RESULT'); sys.exit({code})"],
                    capture=True,
                )
                result = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    env=installer.ui.environment(),
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, code)
                if code == 0:
                    self.assertEqual(result.stdout.strip(), "BUILD_RESULT")

    def test_demo_cannot_call_hardware_or_installation_operations(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            for name in (
                "require_live",
                "disk_inventory",
                "by_id_paths",
                "run",
                "save_settings",
                "build",
                "confirm_and_format",
                "finish",
            ):
                stack.enter_context(patch.object(installer, name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(installer.ui, "demo", False))
            stack.enter_context(patch.object(installer, "collect_settings", return_value={}))
            stack.enter_context(patch.object(installer, "show_plan"))
            stack.enter_context(patch("builtins.input", side_effect=["1", "ERASE"]))
            installer.demo()

    def test_target_checked_again_after_confirmation(self):
        with (
            patch.object(
                installer, "verify_target", side_effect=[None, ValueError("disk changed")]
            ) as verify,
            patch("builtins.input", return_value="ERASE"),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaises(ValueError):
                installer.confirm_and_format(
                    DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
                )
            self.assertEqual(verify.call_count, 2)
            run.assert_not_called()

    def test_changed_hardware_after_confirmation_never_formats(self):
        with (
            patch.object(installer, "verify_target") as verify_target,
            patch.object(installer, "verify_hardware_unchanged", side_effect=ValueError("changed")),
            patch("builtins.input", return_value="ERASE"),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                installer.confirm_and_format(
                    DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/fixture-formatter")
                )
            self.assertEqual(verify_target.call_count, 2)
            run.assert_not_called()

    def test_hardware_and_storage_change_rejected(self):
        hardware = {"cpu": "amd", "gpus": [{"address": "0000:01:00.0"}]}
        settings = {"disk": DISK["by_id"]}
        with (
            patch.object(installer, "detect_hardware", return_value={"cpu": "intel"}),
            patch.object(installer, "storage_modules") as storage_modules,
        ):
            with self.assertRaisesRegex(ValueError, "Hardware changed"):
                installer.verify_hardware_unchanged(hardware, settings, ["nvme"])
            storage_modules.assert_not_called()
        with (
            patch.object(installer, "detect_hardware", return_value=hardware),
            patch.object(installer, "storage_modules", return_value={"ahci"}),
        ):
            with self.assertRaisesRegex(ValueError, "Storage drivers changed"):
                installer.verify_hardware_unchanged(hardware, settings, ["nvme"])

    def test_changed_identity_rejected(self):
        for change in ({"serial": "other"}, {"size": 999}, {"maj:min": "250:1"}):
            with (
                patch.object(Path, "resolve", return_value=Path("/dev/testdisk")),
                patch.object(installer, "disk_inventory", return_value=[DISK | change]),
            ):
                with self.assertRaises(ValueError):
                    installer.verify_target(DISK)

    def test_resume_rejects_other_disk(self):
        with (
            patch.object(Path, "resolve", return_value=Path("/dev/testdisk")),
            patch.object(installer, "disk_inventory", return_value=[DISK]),
            patch.object(installer, "run", return_value="/dev/mapper/cryptroot\n/dev/otherdisk"),
        ):
            with self.assertRaises(ValueError):
                installer.verify_mounted_install({"disk": DISK["by_id"]})

    def test_resume_requires_exact_target_subvolumes(self):
        uuid = "fixture-uuid"
        expected = {
            "/mnt": f"btrfs {uuid} /@root",
            "/mnt/nix": f"btrfs {uuid} /@nix",
            "/mnt/persist": f"btrfs {uuid} /@persist",
            "/mnt/projects": f"btrfs {uuid} /@projects",
            "/mnt/local": f"btrfs {uuid} /@local",
        }

        def verify(mounts, esp_type="vfat"):
            def command(*args, **_kwargs):
                if args[0] == "blkid":
                    return uuid
                if args[0] == "lsblk":
                    return "/dev/mapper/cryptroot\n/dev/testdisk"
                if "FSTYPE,UUID,FSROOT" in args:
                    return mounts[args[-1]]
                if "SOURCE" in args:
                    return "/dev/testdisk1"
                if "FSTYPE" in args:
                    return esp_type
                self.fail(f"Unexpected command: {args}")

            with (
                patch.object(Path, "resolve", return_value=Path("/dev/testdisk")),
                patch.object(installer, "disk_inventory", return_value=[DISK]),
                patch.object(installer.os.path, "ismount", return_value=True),
                patch.object(installer, "run", side_effect=command),
            ):
                installer.verify_mounted_install({"disk": DISK["by_id"]})

        verify(expected)
        for wrong in (f"btrfs {uuid} /@persist", "btrfs other-uuid /@nix", f"ext4 {uuid} /@nix"):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "/mnt/nix"):
                verify(expected | {"/mnt/nix": wrong})
        with self.assertRaisesRegex(ValueError, "EFI partition"):
            verify(expected, esp_type="btrfs")

    def test_duplicate_partition_labels_rejected(self):
        other = DISK | {
            "name": "/dev/otherdisk",
            "children": [
                {"type": "part", "partlabel": "disk-system-encrypted"},
            ],
        }
        with (
            patch.object(Path, "resolve", return_value=Path("/dev/testdisk")),
            patch.object(installer, "disk_inventory", return_value=[DISK, other]),
        ):
            with self.assertRaisesRegex(ValueError, "partition labels"):
                installer.verify_target(DISK)

    def test_installer_builds_use_a_fixed_local_budget(self):
        with (
            patch.object(installer, "SNAPSHOTS", SimpleNamespace(frozen=True)),
            patch.object(
                installer,
                "run",
                side_effect=["/nix/store/fixture-system", "/nix/store/fixture-formatter"],
            ) as run,
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "is_file", return_value=True),
        ):
            installer.build()
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.args[:6], ("nix", "build", "--max-jobs", "2", "--cores", "4"))

    def test_mount_change_after_bootstrap_stops_install(self):
        with (
            patch.object(
                installer,
                "verify_mounted_install",
                side_effect=[None, ValueError("target changed")],
            ) as verify,
            patch.object(installer, "verify_disk_passphrase"),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaisesRegex(ValueError, "target changed"):
                installer.finish(
                    {"userName": "alice"},
                    Path("/nix/store/fixture-system"),
                    Path("/tmp/frozen-source"),
                )
        self.assertEqual(verify.call_count, 2)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["bash"])

    def exercise_flow(self, args, fail_build=False, fail_at=None, legacy=False):
        from contextlib import ExitStack

        events = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["install.py", *args]))
            stack.enter_context(patch("builtins.input", return_value="continue"))
            stack.enter_context(
                patch.object(
                    installer,
                    "run",
                    return_value=json.dumps(
                        {"graphics": None, "nvidia": False, "secretsFile": "/repo/secrets.yaml"}
                        if legacy
                        else {"graphics": {"profile": "mesa"}}
                    ),
                )
            )
            stack.enter_context(patch.object(installer, "choose_disk", return_value=DISK))
            stack.enter_context(
                patch.object(
                    installer, "collect_settings", return_value={"graphics": {"profile": "mesa"}}
                )
            )
            stack.enter_context(patch.object(installer, "detect_hardware", return_value={}))
            stack.enter_context(patch.object(installer, "hardware_defaults", return_value={}))
            stack.enter_context(
                patch.object(
                    installer, "validate_saved", side_effect=lambda s, r: s | {"graphics": r}
                )
            )
            for name in (
                "resolve_hardware_graphics",
                "verify_graphics_configuration",
                "freeze_installation",
                "require_live",
                "show_plan",
                "save_settings",
                "build",
                "confirm_and_format",
                "verify_mounted_install",
                "finish",
                "require_local_console",
                "check_hardware",
                "verify_storage_configuration",
                "configure_keyboard",
                "verify_built_graphics",
                "verify_hardware_unchanged",
            ):

                def record(*_args, label=name):
                    events.append(label)
                    if label == "save_settings" and legacy:
                        self.assertEqual(_args, ({"graphics": {"profile": "mesa"}},))
                    if label == fail_at:
                        raise ValueError("fixture failure")
                    if label == "resolve_hardware_graphics":
                        return {"profile": "mesa"}
                    if label == "build":
                        if fail_build:
                            raise subprocess.CalledProcessError(1, "nix")
                        return Path("/nix/store/fixture-system"), Path(
                            "/nix/store/fixture-formatter"
                        )
                    if label == "freeze_installation":
                        return Path("/tmp/frozen-source")

                stack.enter_context(patch.object(installer, name, side_effect=record))
            if fail_at:
                with self.assertRaises(ValueError):
                    installer.main()
            elif fail_build:
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.main()
            else:
                installer.main()
        return events

    def test_build_failure_never_formats(self):
        events = self.exercise_flow([], fail_build=True)
        self.assertNotIn("confirm_and_format", events)
        self.assertNotIn("finish", events)

    def test_preparation_failures_never_format(self):
        for stage in (
            "check_hardware",
            "resolve_hardware_graphics",
            "freeze_installation",
            "verify_graphics_configuration",
            "configure_keyboard",
            "verify_storage_configuration",
            "verify_built_graphics",
            "verify_hardware_unchanged",
        ):
            events = self.exercise_flow([], fail_at=stage)
            self.assertNotIn("confirm_and_format", events)
            self.assertNotIn("finish", events)

    def test_preview_has_no_mutations(self):
        self.assertEqual(
            self.exercise_flow(["--dry-run"]),
            ["require_live", "check_hardware", "resolve_hardware_graphics", "show_plan"],
        )

    def test_save_settings_never_builds_formats_or_changes_keyboard(self):
        events = self.exercise_flow(["--save-settings"])
        self.assertIn("save_settings", events)
        for stage in (
            "require_local_console",
            "configure_keyboard",
            "build",
            "confirm_and_format",
            "finish",
        ):
            self.assertNotIn(stage, events)

    def test_resume_never_formats(self):
        self.assertEqual(
            self.exercise_flow(["--resume"]),
            [
                "require_live",
                "require_local_console",
                "check_hardware",
                "resolve_hardware_graphics",
                "show_plan",
                "verify_mounted_install",
                "freeze_installation",
                "verify_graphics_configuration",
                "verify_storage_configuration",
                "configure_keyboard",
                "verify_mounted_install",
                "build",
                "verify_hardware_unchanged",
                "verify_built_graphics",
                "finish",
            ],
        )

    def test_legacy_resume_saves_only_the_graphics_migration(self):
        events = self.exercise_flow(["--resume"], legacy=True)
        self.assertIn("save_settings", events)
        self.assertNotIn("confirm_and_format", events)

    def test_normal_order(self):
        self.assertEqual(
            self.exercise_flow([]),
            [
                "require_live",
                "require_local_console",
                "check_hardware",
                "resolve_hardware_graphics",
                "show_plan",
                "save_settings",
                "freeze_installation",
                "verify_graphics_configuration",
                "verify_storage_configuration",
                "configure_keyboard",
                "build",
                "verify_hardware_unchanged",
                "verify_built_graphics",
                "confirm_and_format",
                "finish",
            ],
        )


class StorageSafetyTests(unittest.TestCase):
    def inventory(self):
        disk = copy.deepcopy(DISK)
        disk["children"][0].update(name="/dev/testdisk1", **{"maj:min": "250:1"})
        return [disk]

    def test_kernel_btrfs_membership_includes_secondary_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "features").mkdir()
            devices = root / "fixture-fsid/devices"
            devices.mkdir(parents=True)
            for name, number in (("sda1", "8:1"), ("sdb1", "8:17")):
                device = root / "block" / name
                device.mkdir(parents=True)
                (device / "dev").write_text(number + "\n")
                (devices / name).symlink_to(device)
            # Only UUID directories live in the real Btrfs sysfs root.
            sysfs = root / "btrfs"
            sysfs.mkdir()
            (sysfs / "features").mkdir()
            (sysfs / "fixture-fsid").symlink_to(root / "fixture-fsid")
            self.assertEqual(installer.mounted_btrfs_devices(sysfs), {"8:1", "8:17"})
            (root / "block/sdb1/dev").write_text("unknown\n")
            with self.assertRaisesRegex(ValueError, "Cannot identify"):
                installer.mounted_btrfs_devices(sysfs)
            (root / "block/sdb1/dev").unlink()
            with self.assertRaisesRegex(ValueError, "Cannot inspect"):
                installer.mounted_btrfs_devices(sysfs)
            self.assertEqual(installer.mounted_btrfs_devices(root / "absent"), set())

    def test_unreadable_btrfs_membership_fails_closed(self):
        with (
            patch.object(Path, "iterdir", side_effect=PermissionError("fixture")),
            self.assertRaisesRegex(ValueError, "Cannot inspect active Btrfs"),
        ):
            installer.mounted_btrfs_devices()

    def test_mounted_btrfs_secondary_member_is_unavailable_without_lsblk_mountpoint(self):
        with (
            patch.object(
                installer, "run", return_value=json.dumps({"blockdevices": self.inventory()})
            ),
            patch.object(installer, "mounted_btrfs_devices", return_value={"250:1"}),
            patch.object(installer, "storage_signature") as probe,
        ):
            disk = installer.disk_inventory()[0]
        self.assertIn("mounted Btrfs", installer.blocked_reason(disk))
        probe.assert_not_called()

    def test_inactive_lvm_and_zfs_members_require_manual_preparation(self):
        for signature in ("LVM2_member", "zfs_member"):
            with (
                self.subTest(signature=signature),
                patch.object(
                    installer, "run", return_value=json.dumps({"blockdevices": self.inventory()})
                ),
                patch.object(installer, "mounted_btrfs_devices", return_value=set()),
                patch.object(
                    installer, "storage_signature", side_effect=[None, signature]
                ) as probe,
            ):
                disk = installer.disk_inventory()[0]
            self.assertIn("entire volume group or pool", installer.blocked_reason(disk))
            self.assertEqual(
                [call.args[0] for call in probe.call_args_list], ["/dev/testdisk", "/dev/testdisk1"]
            )

    def test_probe_failures_make_candidate_unavailable(self):
        with (
            patch.object(
                installer, "run", return_value=json.dumps({"blockdevices": self.inventory()})
            ),
            patch.object(installer, "mounted_btrfs_devices", return_value=set()),
            patch.object(installer, "storage_signature", side_effect=ValueError("probe failed")),
        ):
            self.assertEqual(
                installer.blocked_reason(installer.disk_inventory()[0]), "probe failed"
            )

    def test_post_confirmation_guard_refreshes_membership_and_signatures(self):
        for change in ("btrfs", "lvm"):
            with (
                self.subTest(change=change),
                patch.object(Path, "resolve", return_value=Path("/dev/testdisk")),
                patch.object(Path, "exists", return_value=False),
                patch.object(installer.os.path, "ismount", return_value=False),
                patch.object(
                    installer, "run", return_value=json.dumps({"blockdevices": self.inventory()})
                ) as command,
                patch.object(
                    installer,
                    "mounted_btrfs_devices",
                    side_effect=[set(), {"250:1"} if change == "btrfs" else set()],
                ) as membership,
                patch.object(
                    installer,
                    "storage_signature",
                    side_effect=[None, None, None, "LVM2_member"],
                ) as probe,
                patch.object(installer, "confirm_erase"),
                patch.object(installer, "verify_hardware_unchanged"),
                self.assertRaisesRegex(ValueError, "now unavailable"),
            ):
                installer.confirm_and_format(
                    DISK, {}, {"disk": DISK["by_id"]}, [], Path("/nix/store/formatter")
                )
            self.assertEqual(membership.call_count, 2)
            self.assertEqual(probe.call_count, 2 if change == "btrfs" else 4)
            self.assertEqual(command.call_count, 2)
            self.assertTrue(all(call.args[0] == "lsblk" for call in command.call_args_list))

    def test_native_probe_errors_and_ambiguity_release_resources(self):
        for result in (-1, -2):
            library = Mock()
            library.blkid_new_probe_from_filename.return_value = 123
            library.blkid_do_safeprobe.return_value = result
            with (
                self.subTest(result=result),
                patch.dict(os.environ, {"WORKSTATION_BLKID_LIBRARY": "fixture"}),
                patch.object(installer.ctypes, "CDLL", return_value=library),
                self.assertRaisesRegex(ValueError, "failed or is ambiguous"),
            ):
                installer.storage_signature("/dev/testdisk")
            library.blkid_free_probe.assert_called_once_with(123)

    def test_missing_probe_environment_or_library_fails_closed(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ValueError, "installer environment"),
        ):
            installer.storage_signature("/dev/testdisk")
        with (
            patch.dict(os.environ, {"WORKSTATION_BLKID_LIBRARY": "/missing/library"}),
            self.assertRaisesRegex(ValueError, "Cannot load"),
        ):
            installer.storage_signature("/dev/testdisk")

    @unittest.skipUnless(
        os.environ.get("WORKSTATION_BLKID_LIBRARY"),
        "native probe library is supplied by the installer shell",
    )
    def test_real_native_probe_distinguishes_empty_missing_and_recognized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory) / "fixture"
            device.write_bytes(bytes(65536))
            self.assertIsNone(installer.storage_signature(device))
            with self.assertRaisesRegex(ValueError, "Cannot open"):
                installer.storage_signature(Path(directory) / "missing")
            swap = bytearray(65536)
            swap[1024:1028] = (1).to_bytes(4, "little")
            swap[1028:1032] = (15).to_bytes(4, "little")
            swap[4086:4096] = b"SWAPSPACE2"
            device.write_bytes(swap)
            self.assertEqual(installer.storage_signature(device), "swap")


class ConsoleSettingsTests(unittest.TestCase):
    def collect(self, answers, changes=None):
        from contextlib import redirect_stdout
        from io import StringIO

        defaults = dict(
            userName="dev",
            hostName="workstation",
            timeZone="Europe/Stockholm",
            keyboardLayout="se",
            cpu="amd",
            bluetooth=False,
            containers=False,
            richFilePreviews=False,
            graphicalNetworking=False,
            obtain=False,
            disk="/dev/old",
        ) | (changes or {})
        before = copy.deepcopy(defaults)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zones, xkb = root / "zoneinfo", root / "xkb"
            for name in ["Europe/Stockholm", "Europe/Berlin", "America/New_York", "Etc/UTC"]:
                path = zones / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (zones / "zone.tab").write_text(
                "# fixtures\nSE +00 Europe/Stockholm\nDE +00 Europe/Berlin\nUS +00 America/New_York\n"
            )
            (xkb / "symbols").mkdir(parents=True)
            for name in ["us", "se"]:
                (xkb / "symbols" / name).touch()
            (xkb / "rules").mkdir()
            (xkb / "rules/base.lst").write_text(
                "! model\n pc105 Generic\n! layout\n us English (US)\n se Swedish\n! variant\n test Other\n"
            )
            output = StringIO()
            with (
                patch.dict(
                    installer.os.environ,
                    {"WORKSTATION_ZONEINFO": str(zones), "WORKSTATION_XKB": str(xkb)},
                ),
                patch("builtins.input", side_effect=answers) as prompt,
                patch.object(installer, "run") as run,
                redirect_stdout(output),
            ):
                result = installer.collect_settings(defaults, DISK)
            run.assert_not_called()
            self.assertEqual(defaults, before)
            return result, prompt.call_count, output.getvalue()

    def test_one_enter_accepts_defaults_without_hardware_prompts(self):
        result, count, output = self.collect([""])
        self.assertEqual(count, 1)
        self.assertEqual(result["disk"], DISK["by_id"])
        self.assertEqual(result["cpu"], "amd")
        self.assertEqual(result["keyboardLayout"], "se")
        self.assertFalse(result["bluetooth"])
        self.assertFalse(result["containers"])
        self.assertFalse(result["richFilePreviews"])
        self.assertFalse(result["graphicalNetworking"])
        self.assertFalse(result["obtain"])
        self.assertIn("9. Obtain (install apps from GitHub releases): disabled", output)
        self.assertIn("8. Graphical network controls (tray applet): disabled", output)
        self.assertIn("6. Containers (Podman): disabled", output)
        self.assertIn("7. Rich file previews (media/PDF thumbnails): disabled", output)
        self.assertNotIn("desktop", result)
        self.assertNotIn("6. Desktop", output)
        self.assertIn("Graphics: Automatic", output)

    def test_saved_desktop_choice_is_ignored(self):
        for desktop in ["niri", "niri-terminal", "unknown", None]:
            with self.subTest(desktop=desktop):
                result, count, output = self.collect([""], {"desktop": desktop})
                self.assertNotIn("desktop", result)
                self.assertEqual(count, 1)
                self.assertNotIn("6. Desktop", output)

    def test_plan_always_shows_terminal_desktop_including_resume(self):
        from contextlib import redirect_stdout
        from io import StringIO

        settings, _, _ = self.collect([""])
        for legacy in [{}, {"desktop": "niri"}, {"desktop": "niri-terminal"}]:
            output = StringIO()
            with (
                patch.object(installer, "describe", return_value="Graphics"),
                redirect_stdout(output),
            ):
                installer.show_plan(settings | legacy | {"graphics": {}})
            self.assertIn("Desktop: Niri — terminal-first", output.getvalue())
            self.assertNotIn("standard desktop", output.getvalue())

    def test_number_toggles_bluetooth(self):
        result, count, _ = self.collect(["5", ""])
        self.assertTrue(result["bluetooth"])
        self.assertEqual(count, 2)

    def test_optional_tools_can_be_selected_independently(self):
        for answer, key, other in [
            ("6", "containers", "richFilePreviews"),
            ("7", "richFilePreviews", "containers"),
            ("8", "graphicalNetworking", "containers"),
            ("9", "obtain", "containers"),
        ]:
            with self.subTest(key=key):
                result, _, _ = self.collect([answer, ""])
                self.assertTrue(result[key])
                self.assertFalse(result[other])
                result, _, _ = self.collect([answer, answer, ""])
                self.assertFalse(result[key])

    def test_tui_checklist_saves_only_the_selected_apps(self):
        for chosen in ({"obtain", "graphicalNetworking"}, set()):
            with (
                self.subTest(chosen=chosen),
                patch.object(installer.ui, "enabled", return_value=True),
                patch.object(installer.ui, "screen"),
                patch.object(installer.ui, "select", side_effect=["extras", "continue"]),
                patch.object(installer.ui, "checklist", return_value=chosen),
            ):
                result, _, _ = self.collect([], {"containers": True, "richFilePreviews": True})
                for key in ("containers", "richFilePreviews", "graphicalNetworking", "obtain"):
                    self.assertEqual(result[key], key in chosen)

    def test_optional_tool_choices_are_saved_and_shown_on_resume(self):
        from contextlib import redirect_stdout
        from io import StringIO

        result, _, _ = self.collect(["6", "7", "8", "9", ""])
        with tempfile.TemporaryDirectory() as tmp, patch.object(installer, "REPO", Path(tmp)):
            installer.save_settings(result)
            saved = json.loads((Path(tmp) / "installation.json").read_text())
        reviewed, count, _ = self.collect([""], saved)
        self.assertEqual(count, 1)
        self.assertTrue(reviewed["containers"])
        self.assertTrue(reviewed["richFilePreviews"])
        self.assertTrue(reviewed["graphicalNetworking"])
        self.assertTrue(reviewed["obtain"])
        output = StringIO()
        with (
            patch.object(installer, "describe", return_value="Graphics"),
            redirect_stdout(output),
        ):
            installer.show_plan(saved | {"graphics": {}})
        self.assertIn("Containers (Podman): yes", output.getvalue())
        self.assertIn("Rich file previews (media/PDF thumbnails): yes", output.getvalue())
        self.assertIn("Graphical network controls (tray applet): yes", output.getvalue())
        self.assertIn("Obtain (install apps from GitHub releases): yes", output.getvalue())

    def test_optional_tools_reject_non_boolean_saved_values(self):
        for number, key in [
            ("6", "containers"),
            ("7", "richFilePreviews"),
            ("8", "graphicalNetworking"),
            ("9", "obtain"),
        ]:
            with self.subTest(key=key):
                result, _, output = self.collect(["", number, ""], {key: "false"})
                self.assertIn("Correct the marked settings", output)
                self.assertIs(result[key], False)

    def test_timezone_and_keyboard_choices_need_only_numbers(self):
        result, _, _ = self.collect(["3", "", "1", "4", "1", ""])
        self.assertEqual(result["timeZone"], "Europe/Berlin")
        self.assertEqual(result["keyboardLayout"], "us")

    def test_keyboard_search_uses_human_readable_names(self):
        result, _, _ = self.collect(["4", "Swedish", "1", ""], {"keyboardLayout": "us"})
        self.assertEqual(result["keyboardLayout"], "se")

    def test_invalid_defaults_cannot_be_accepted(self):
        result, _, output = self.collect(["", "1", "alice", ""], {"userName": "root"})
        self.assertEqual(result["userName"], "alice")
        self.assertIn("needs correction", output)
        self.assertIn("Correct the marked settings", output)

    def test_invalid_edits_still_require_validation(self):
        result, _, output = self.collect(
            ["99", "1", "root", "alice", "2", "bad host", "laptop", ""]
        )
        self.assertEqual(result["userName"], "alice")
        self.assertEqual(result["hostName"], "laptop")
        self.assertIn("Invalid value", output)

    def test_cancel_exits_review(self):
        with self.assertRaises(KeyboardInterrupt):
            self.collect(["q"])

    def test_choice_pages_search_and_keep(self):
        from contextlib import redirect_stdout
        from io import StringIO

        choices = {f"value{i}": f"Choice {i}" for i in range(26)}
        for answers, expected in [
            (["n", "2"], "value13"),
            (["n", "p", "1"], "value0"),
            (["missing", "Choice 25", "1"], "value25"),
            (["Choice 25", "/", "1"], "value0"),
            (["99", ""], "value4"),
        ]:
            with (
                self.subTest(answers=answers),
                patch("builtins.input", side_effect=answers),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(installer.ui.choose_value("Fixture", choices, "value4"), expected)


class ReadinessTests(unittest.TestCase):
    def hardware(self, **changes):
        return dict(
            architecture="x86_64",
            cpu="intel",
            secure_boot=False,
            bluetooth=False,
            gpus=[
                dict(
                    address="0000:00:02.0",
                    vendor=0x8086,
                    device=0x1234,
                    subvendor=0x8086,
                    subdevice=0,
                )
            ],
            **changes,
        )

    def settings(self, **changes):
        return dict(cpu="intel", nvidia=False, disk=DISK["by_id"]) | changes

    def test_secure_boot_requires_valid_firmware_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(installer.secure_boot_state(root))
            var = root / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
            for payload, expected in [
                (bytes(5), False),
                (bytes(4) + b"\x01", True),
                (bytes(4), None),
                (bytes(4) + b"\x02", None),
            ]:
                var.write_bytes(payload)
                self.assertIs(installer.secure_boot_state(root), expected)

    def test_sysfs_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cpu = root / "cpuinfo"
            cpu.write_text("vendor_id : AuthenticAMD\n")
            dev = root / "bus/pci/devices/0000:01:00.0"
            dev.mkdir(parents=True)
            for field, value in dict(
                vendor="0x1002",
                device="0x1234",
                subsystem_vendor="0x1002",
                subsystem_device="0x5678",
                modalias="pci:v00001002d00001234",
                **{"class": "0x030000"},
            ).items():
                (dev / field).write_text(value)
            (root / "class/bluetooth/hci0").mkdir(parents=True)
            with patch.object(installer.platform, "machine", return_value="x86_64"):
                hardware = installer.detect_hardware(root, cpu)
            self.assertEqual(hardware["cpu"], "amd")
            self.assertEqual(hardware["gpus"][0]["vendor"], 0x1002)
            self.assertTrue(hardware["bluetooth"])
            self.assertIsNone(hardware["secure_boot"])

    def test_hardware_rejections_happen_without_building(self):
        cases = [
            dict(architecture="aarch64"),
            dict(secure_boot=True),
            dict(secure_boot=None),
            dict(cpu="generic"),
            dict(cpu="amd"),
        ]
        for changes in cases:
            with self.subTest(changes=changes), patch.object(installer, "run") as run:
                with self.assertRaises(ValueError):
                    installer.check_hardware(self.settings(), self.hardware() | changes)
                run.assert_not_called()

    def test_intel_and_amd_profiles(self):
        for cpu, vendor in [("intel", 0x8086), ("amd", 0x1002)]:
            hardware = self.hardware() | {"cpu": cpu}
            hardware["gpus"][0]["vendor"] = vendor
            with patch.object(installer, "storage_modules", return_value={"nvme"}):
                self.assertEqual(
                    installer.check_hardware(self.settings(cpu=cpu), hardware), ["nvme"]
                )

    def test_storage_walk_and_unsupported_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = root / "devices/pci/controller/nvme0"
            device.mkdir(parents=True)
            block = root / "class/block/testdisk"
            block.mkdir(parents=True)
            (block / "device").symlink_to(device)
            driver = device / "driver"
            driver.mkdir()
            (driver / "module").symlink_to(root / "module/nvme")
            self.assertEqual(installer.storage_modules("/dev/testdisk", root), {"nvme"})
            (driver / "module").unlink()
            (driver / "module").symlink_to(root / "module/megaraid_sas")
            with self.assertRaisesRegex(ValueError, "megaraid_sas"):
                installer.storage_modules("/dev/testdisk", root)

    def test_missing_initrd_driver_blocks_install(self):
        with patch.object(installer, "run", return_value='["nvme"]'):
            with self.assertRaisesRegex(ValueError, "missing detected storage"):
                installer.verify_storage_configuration(["nvme", "uas"])

    def test_nvme_behind_pcie_bridges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = root / "devices/pci0000:00/0000:00:02.4"
            second_bridge = bridge / "0000:01:00.0"
            controller = second_bridge / "0000:05:00.0"
            device = controller / "nvme/nvme0"
            device.mkdir(parents=True)
            block = root / "class/block/testdisk"
            block.mkdir(parents=True)
            (block / "device").symlink_to(device)
            for node, name, module, pci_class in [
                (bridge, "pcieport", "pcieportdrv", "0x060400"),
                (second_bridge, "pcieport", "pcieportdrv", "0x060400"),
                (controller, "nvme", "nvme", "0x010802"),
            ]:
                driver = root / "bus/pci/drivers" / name
                driver.mkdir(parents=True, exist_ok=True)
                if not (driver / "module").is_symlink():
                    (driver / "module").symlink_to(root / "module" / module)
                (node / "driver").symlink_to(driver)
                (node / "class").write_text(pci_class)
            modules = installer.storage_modules("/dev/testdisk", root)
            self.assertEqual(modules, {"nvme"})
            with patch.object(installer, "run", return_value='["nvme"]'):
                installer.verify_storage_configuration(modules)

            # The exemption is not a blanket allowance for ancestor drivers.
            for name in ("vmd", "megaraid_sas"):
                driver = root / "bus/pci/drivers" / name
                driver.mkdir()
                (driver / "module").symlink_to(root / "module" / name)
                (bridge / "driver").unlink()
                (bridge / "driver").symlink_to(driver)
                with self.subTest(driver=name), self.assertRaisesRegex(ValueError, name):
                    installer.storage_modules("/dev/testdisk", root)

    def test_pcie_port_service_alone_is_not_a_storage_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = root / "devices/pci0000:00/0000:00:02.4"
            bridge.mkdir(parents=True)
            block = root / "class/block/testdisk"
            block.mkdir(parents=True)
            (block / "device").symlink_to(bridge)
            driver = root / "bus/pci/drivers/pcieport"
            driver.mkdir(parents=True)
            (driver / "module").symlink_to(root / "module/pcieportdrv")
            (bridge / "driver").symlink_to(driver)
            (bridge / "class").write_text("0x060400")
            with self.assertRaisesRegex(ValueError, "unknown"):
                installer.storage_modules("/dev/testdisk", root)
            (bridge / "class").write_text("0x010802")
            with self.assertRaisesRegex(ValueError, "pcieportdrv"):
                installer.storage_modules("/dev/testdisk", root)

    def test_only_text_virtual_console_can_change_keymap(self):
        for tty, mode in [("/dev/pts/1", 0), ("/dev/tty2", 1)]:
            with (
                patch.dict(installer.os.environ, {}, clear=True),
                patch.object(installer.os, "ttyname", return_value=tty),
                patch.object(
                    installer.fcntl, "ioctl", return_value=mode.to_bytes(4, sys.byteorder)
                ),
            ):
                with self.assertRaisesRegex(ValueError, "local text console"):
                    installer.require_local_console()
        with (
            patch.object(installer.os, "ttyname", return_value="/dev/tty2"),
            patch.object(installer.fcntl, "ioctl", return_value=bytes(4)),
        ):
            installer.require_local_console()

    def test_sudo_pty_uses_verified_original_console(self):
        with (
            patch.dict(
                installer.os.environ, {"SUDO_UID": "1000", "SUDO_TTY": "/dev/tty2"}, clear=True
            ),
            patch.object(installer.os, "ttyname", return_value="/dev/pts/0"),
            patch.object(installer.os, "open", return_value=99),
            patch.object(installer.os, "close") as close,
            patch.object(installer.fcntl, "ioctl", return_value=bytes(4)) as ioctl,
        ):
            self.assertEqual(installer.require_local_console(), "/dev/tty2")
            self.assertEqual(ioctl.call_args.args[0], 99)
            close.assert_called_once_with(99)

    def test_keymap_applied_before_typing_test(self):
        events = []

        def run(*args, **kwargs):
            events.append(args[0])
            if args[0] in ("loadkeys", "kbd_mode"):
                return
            if args[-1] == ".#lib.installationKeyboard":
                return json.dumps(
                    {"useXkbConfig": True, "layout": "se,us", "options": "grp:alt_shift_toggle"}
                )
            return "/nix/store/test-keymap"

        def sample(_prompt):
            self.assertEqual(events[-1], "loadkeys")
            return "yY zZ @ : / - _ + ="

        with (
            patch.object(installer, "require_local_console"),
            patch.object(installer, "run", side_effect=run),
            patch.object(Path, "is_file", return_value=True),
            patch("builtins.input", side_effect=sample),
        ):
            installer.configure_keyboard({"keyboardLayout": "se"})

    def test_keymap_mismatch_never_loads_or_prompts(self):
        with (
            patch.object(installer, "require_local_console"),
            patch.object(
                installer, "run", return_value='{"useXkbConfig":true,"layout":"us","options":""}'
            ) as run,
            patch("builtins.input") as prompt,
        ):
            with self.assertRaisesRegex(ValueError, "disagree"):
                installer.configure_keyboard({"keyboardLayout": "se"})
            self.assertFalse(any(call.args[0] == "loadkeys" for call in run.call_args_list))
            prompt.assert_not_called()

    def test_non_latin_keyboard_requires_a_switchable_us_fallback(self):
        with (
            patch.object(installer, "require_local_console"),
            patch.object(
                installer, "run", return_value='{"useXkbConfig":true,"layout":"ru,us","options":""}'
            ) as run,
            patch("builtins.input") as prompt,
        ):
            with self.assertRaisesRegex(ValueError, "group switching"):
                installer.configure_keyboard({"keyboardLayout": "ru"})
            self.assertFalse(any(call.args[0] == "loadkeys" for call in run.call_args_list))
            prompt.assert_not_called()

    def test_keyboard_only_mode_never_inspects_or_formats_a_disk(self):
        with (
            patch.object(installer.sys, "argv", ["install.py", "--keyboard-test"]),
            patch.object(installer, "require_live"),
            patch.object(installer, "run", return_value='{"keyboardLayout":"us"}'),
            patch.object(installer, "configure_keyboard") as keyboard,
            patch.object(installer, "detect_hardware") as hardware,
            patch.object(installer, "choose_disk") as disk,
            patch.object(installer, "finish") as finish,
        ):
            installer.main()
            keyboard.assert_called_once_with({"keyboardLayout": "us"})
            hardware.assert_not_called()
            disk.assert_not_called()
            finish.assert_not_called()

    def test_built_gpu_driver_must_match_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result-system/kernel-modules/lib/modules/test-version").mkdir(parents=True)
            hardware = self.hardware()
            hardware["gpus"][0]["modalias"] = "pci:fixture"
            with (
                patch.object(installer, "REPO", root),
                patch.object(installer, "run", return_value="i915") as run,
            ):
                installer.verify_built_graphics(
                    hardware,
                    {"graphics": {"devices": [hardware["gpus"][0] | {"driver": "intel"}]}},
                    root / "result-system",
                )
                self.assertEqual(run.call_args.args[-1], "pci:fixture")
            with (
                patch.object(installer, "REPO", root),
                patch.object(installer, "run", return_value=""),
            ):
                with self.assertRaisesRegex(ValueError, "no matching GPU driver"):
                    installer.verify_built_graphics(
                        hardware,
                        {"graphics": {"devices": [hardware["gpus"][0] | {"driver": "intel"}]}},
                        root / "result-system",
                    )

    def test_passphrase_verification_does_not_close_or_reformat(self):
        with (
            patch.object(installer, "verify_mounted_install"),
            patch.object(
                installer,
                "run",
                side_effect=[
                    "/dev/mapper/cryptroot crypt\n/dev/testdisk2 part\n/dev/testdisk disk",
                    None,
                ],
            ) as run,
        ):
            installer.verify_disk_passphrase({})
            self.assertEqual(
                run.call_args.args,
                (
                    "cryptsetup",
                    "open",
                    "--type",
                    "luks",
                    "--test-passphrase",
                    "--tries",
                    "3",
                    "/dev/testdisk2",
                ),
            )
        with (
            patch.object(installer, "verify_mounted_install"),
            patch.object(installer, "run", return_value="/dev/testdisk disk") as run,
        ):
            with self.assertRaisesRegex(ValueError, "unique encrypted partition"):
                installer.verify_disk_passphrase({})
            self.assertEqual(run.call_count, 1)


unittest.main()
