"""Release-data integrity, installer isolation and catalogue parser regressions."""

import copy
import importlib.util
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
scripts = Path(sys.argv.pop(1))
data = Path(sys.argv.pop(1))
expected = json.loads(Path(sys.argv.pop(1)).read_text())
sys.path.insert(0, str(scripts))
import graphics
import graphics_metadata as metadata


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


installer = module("installer", scripts / "install.py")
generator = module("generator", scripts / "graphics-support.py")


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.directory = self.repo / "hardware/graphics"
        shutil.copytree(data, self.directory)
        # Store inputs can be read-only; mutations here are confined to a fixture.
        self.directory.chmod(0o755)
        for path in self.directory.iterdir():
            path.chmod(0o644)

    def test_install_reads_prepared_data_without_building_archives(self):
        hardware = {
            "gpus": [
                dict(
                    address="0000:00:02.0",
                    vendor=0x8086,
                    device=0x5916,
                    subvendor=0x8086,
                    subdevice=0,
                )
            ]
        }
        with (
            patch.object(installer, "REPO", self.repo),
            patch.object(installer, "run", return_value=json.dumps(expected)) as run,
        ):
            self.assertEqual(installer.resolve_hardware_graphics(hardware)["profile"], "mesa")
            run.assert_called_once_with(
                "nix", "eval", "--json", ".#lib.graphicsMetadata", capture=True
            )

    def test_verified_catalogues_are_each_opened_once(self):
        with patch.object(metadata, "open_regular", wraps=metadata.open_regular) as opened:
            metadata.load_metadata(self.directory, expected)
        self.assertEqual(
            [call.args[0].name for call in opened.call_args_list],
            ["manifest.json", *metadata.FILES],
        )

    def test_corrupt_missing_or_partial_release_fails_closed(self):
        for name in (*metadata.FILES, "manifest.json"):
            path = self.directory / name
            original = path.read_bytes()
            for replacement in (None, b"{bad json", b"{}"):
                with self.subTest(name=name, replacement=replacement):
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_bytes(replacement)
                    with self.assertRaises(ValueError):
                        metadata.load_metadata(self.directory, expected)
                    path.write_bytes(original)

    def test_release_files_have_fixed_read_and_hash_limits(self):
        with (
            patch.object(metadata, "MAX_CATALOGUE_BYTES", 1024),
            self.assertRaisesRegex(ValueError, "exceeds the supported size"),
        ):
            metadata.load_metadata(self.directory, expected)
        manifest = self.directory / "manifest.json"
        manifest.write_bytes(b" " * (metadata.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "exceeds the supported size"):
            metadata.read_json(manifest)
        manifest.write_bytes(b"[" * 30000 + b"0" + b"]" * 30000)
        with self.assertRaisesRegex(ValueError, "Cannot read graphics metadata"):
            metadata.read_json(manifest)

    def test_release_loader_rejects_symlinks_and_fifos(self):
        manifest = self.directory / "manifest.json"
        victim = self.repo / "outside.json"
        victim.write_bytes(manifest.read_bytes())
        manifest.unlink()
        manifest.symlink_to(victim)
        with self.assertRaisesRegex(ValueError, "Cannot read graphics metadata"):
            metadata.read_json(manifest)
        manifest.unlink()
        os.mkfifo(manifest)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            metadata.read_json(manifest)

    def test_missing_bundle_stops_every_installer_mode_before_mutations(self):
        from contextlib import ExitStack

        (self.directory / "manifest.json").unlink()
        for args in ([], ["--dry-run"], ["--resume"]):
            with self.subTest(args=args), ExitStack() as stack:
                stack.enter_context(patch.object(sys, "argv", ["install.py", *args]))
                stack.enter_context(patch.object(installer, "REPO", self.repo))
                stack.enter_context(
                    patch.object(installer, "run", return_value=json.dumps(expected))
                )
                stack.enter_context(patch.object(installer, "require_live"))
                stack.enter_context(patch.object(installer, "require_local_console"))
                stack.enter_context(
                    patch.object(installer, "detect_hardware", return_value={"gpus": []})
                )
                stack.enter_context(patch.object(installer, "choose_disk", return_value={}))
                stack.enter_context(patch.object(installer, "collect_settings", return_value={}))
                stack.enter_context(patch.object(installer, "hardware_defaults", return_value={}))
                stack.enter_context(patch.object(installer, "check_hardware"))
                mutations = [
                    stack.enter_context(patch.object(installer, name))
                    for name in (
                        "save_settings",
                        "configure_keyboard",
                        "build",
                        "confirm_and_format",
                        "finish",
                    )
                ]
                with self.assertRaisesRegex(ValueError, "Cannot read graphics metadata"):
                    installer.main()
                for mutation in mutations:
                    mutation.assert_not_called()

    def test_pin_source_policy_and_generator_changes_require_refresh(self):
        for category, key in [
            ("stack", "nixpkgs"),
            ("stack", "kernel"),
            ("stack", "nvidia"),
            ("stack", "mesa"),
            ("stack", "niri"),
            ("stack", "policy"),
            ("sources", "libdrm"),
            ("sources", "kernel"),
        ]:
            changed = copy.deepcopy(expected)
            changed[category][key] = "changed"
            with (
                self.subTest(category=category, key=key),
                self.assertRaisesRegex(ValueError, "does not match"),
            ):
                metadata.load_metadata(self.directory, changed)
        with self.assertRaisesRegex(ValueError, "does not match"):
            metadata.load_metadata(self.directory, expected | {"generator": "changed"})

    def test_manifest_cannot_disagree_with_catalogue_stack(self):
        support = metadata.read_json(self.directory / metadata.FILES[0])
        support["stack"]["kernel"] = "wrong"
        (self.directory / metadata.FILES[0]).write_text(json.dumps(support))
        with self.assertRaisesRegex(ValueError, "stack differs"):
            metadata.prepare(self.directory, expected)

    def test_bundled_nvidia_manifest_retains_exact_driver_support(self):
        support, nvidia = metadata.load_metadata(self.directory, expected)
        gpu = dict(
            address="0000:01:00.0", vendor=0x10DE, device=0x1E04, subvendor=0x10DE, subdevice=0
        )
        self.assertEqual(graphics.resolve_graphics([gpu], support, nvidia)["profile"], "nvidia")
        with self.assertRaisesRegex(ValueError, "absent from the pinned"):
            graphics.resolve_graphics([gpu | {"device": 0xFFFF}], support, nvidia)

    def test_change_report_includes_acceptance_and_classification_changes(self):
        before = {
            "devices": {"8086:0001": {"integrated": True}, "1002:0002": {}},
            "unsupported": {"1002:0003": "legacy"},
        }
        after = {
            "devices": {"8086:0001": {"integrated": False}, "1002:0003": {}, "1002:0004": {}},
            "unsupported": {},
        }
        self.assertEqual(
            metadata.changes(before, after),
            {
                "added": ["1002:0004"],
                "removed": ["1002:0002"],
                "changed": ["1002:0003", "8086:0001"],
            },
        )

    def test_update_ignores_predictable_temporary_symlinks(self):
        generated = self.repo / "generated"
        shutil.copytree(self.directory, generated)
        victim = self.repo / "victim"
        victim.write_text("keep me")
        (self.directory / "graphics-support.json.tmp").symlink_to(victim)
        with patch.object(
            metadata.subprocess, "run", return_value=SimpleNamespace(stdout=str(generated))
        ) as run:
            metadata.update(self.repo)
        self.assertEqual(
            run.call_args.args[0][:7],
            ["nix", "build", "--no-update-lock-file", "--max-jobs", "2", "--cores", "4"],
        )
        self.assertEqual(victim.read_text(), "keep me")
        self.assertEqual(
            metadata.load_metadata(self.directory, expected),
            metadata.load_metadata(generated, expected),
        )
        self.assertEqual(list(self.directory.glob(".graphics-support.json.*")), [])

    def test_interrupted_update_keeps_old_manifest_and_fails_validation(self):
        generated = self.repo / "generated"
        shutil.copytree(self.directory, generated)
        support = metadata.read_json(generated / metadata.FILES[0])
        first = next(iter(support["devices"]))
        support["devices"][first]["name"] = "changed fixture"
        (generated / metadata.FILES[0]).write_text(json.dumps(support))
        metadata.prepare(generated, expected)
        original_manifest = (self.directory / "manifest.json").read_bytes()
        copy = metadata.atomic_copy

        def interrupt(source, destination):
            if destination.name == metadata.FILES[1]:
                raise OSError("interrupted copy")
            copy(source, destination)

        with (
            patch.object(
                metadata.subprocess, "run", return_value=SimpleNamespace(stdout=str(generated))
            ),
            patch.object(metadata, "atomic_copy", side_effect=interrupt),
            self.assertRaisesRegex(OSError, "interrupted copy"),
        ):
            metadata.update(self.repo)
        self.assertEqual((self.directory / "manifest.json").read_bytes(), original_manifest)
        with self.assertRaisesRegex(ValueError, "integrity check"):
            metadata.load_metadata(self.directory, expected)


class ParserTests(unittest.TestCase):
    def test_kernel_source_lookup_streams_and_has_a_member_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel = Path(tmp) / "kernel.tar"
            source = b"reviewed table"
            with tarfile.open(kernel, "w") as archive:
                for name, content in [
                    ("linux/unrelated", b"skip"),
                    ("linux/drivers/gpu/drm/amd/amdgpu/amdgpu_drv.c", source),
                ]:
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
            with patch.object(tarfile.TarFile, "getmembers", side_effect=AssertionError):
                self.assertEqual(generator.kernel_gpu_table(kernel), source.decode())
            with patch.object(generator, "KERNEL_MEMBERS_MAX", 1):
                with self.assertRaisesRegex(ValueError, "member limit"):
                    generator.kernel_gpu_table(kernel)

    def test_missing_kernel_table_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel = Path(tmp) / "kernel.tar"
            with tarfile.open(kernel, "w") as archive:
                member = tarfile.TarInfo("linux/unrelated")
                archive.addfile(member, io.BytesIO())
            with self.assertRaisesRegex(ValueError, "missing"):
                generator.kernel_gpu_table(kernel)

    def test_each_upstream_table_must_parse_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intel = root / "include/pci_ids/iris_pci_ids.h"
            intel.parent.mkdir(parents=True)
            amd = root / "amdgpu.ids"
            kernel = root / "kernel.tar"
            iris = "\n".join(f'CHIPSET(0x{i:04x}, bdw, "GT", "Intel Graphics")' for i in range(105))
            names = "\n".join(f"{i:04x}, 00, AMD Radeon" for i in range(105))
            chips = "\n".join(
                f"{{0x1002, 0x{i:04x}, PCI_ANY_ID, PCI_ANY_ID, 0, 0, CHIP_POLARIS10}},"
                for i in range(105)
            )
            for broken in (None, "intel", "kernel", "libdrm"):
                intel.write_text("CHANGED_FORMAT" if broken == "intel" else iris)
                amd.write_text("CHANGED_FORMAT" if broken == "libdrm" else names)
                content = ("CHANGED_FORMAT" if broken == "kernel" else chips).encode()
                with tarfile.open(kernel, "w") as archive:
                    member = tarfile.TarInfo("linux/drivers/gpu/drm/amd/amdgpu/amdgpu_drv.c")
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
                with self.subTest(broken=broken):
                    if broken:
                        with self.assertRaisesRegex(ValueError, "each vendor parser"):
                            generator.catalogue(root, kernel, amd)
                    else:
                        self.assertEqual(
                            len(generator.catalogue(root, kernel, amd)["devices"]), 210
                        )


unittest.main()
