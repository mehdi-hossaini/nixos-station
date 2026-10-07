"""Graphics policy and pinned-table regressions. Never load drivers or touch disks."""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
scripts = Path(sys.argv.pop(1))
support = json.loads((Path(sys.argv.pop(1)) / "graphics-support.json").read_text())
profiles = Path(sys.argv.pop(1)) if len(sys.argv) > 1 else None
single_profile = None
if len(sys.argv) > 1 and sys.argv[1] == "--profile":
    sys.argv.pop(1)
    single_profile = sys.argv.pop(1)
sys.path.insert(0, str(scripts))
import graphics

spec = importlib.util.spec_from_file_location("installer", scripts / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def gpu(vendor, device, address="0000:00:02.0"):
    return dict(
        vendor=vendor,
        device=device,
        address=address,
        subvendor=vendor,
        subdevice=0,
        modalias=f"pci:v{vendor:08X}d{device:08X}sv{vendor:08X}sd00000000bc03sc00i00",
    )


INTEL = gpu(0x8086, 0x5916)
AMD = gpu(0x1002, 0x1636)
RADEON = gpu(0x1002, 0x73BF, "0000:03:00.0")
NVIDIA = gpu(0x10DE, 0x1E04, "0000:01:00.0")
MANIFEST = {
    "chips": [dict(devid="0x1E04", name="NVIDIA GeForce RTX 2080 Ti", features=["kernelopen"])]
}


class GraphicsTests(unittest.TestCase):
    def resolve(self, devices):
        return graphics.resolve_graphics(devices, support, MANIFEST)

    def test_supported_arrangements(self):
        for devices, profile in [
            ([INTEL], "mesa"),
            ([AMD], "mesa"),
            ([RADEON], "mesa"),
            ([gpu(0x8086, 0x56A0)], "mesa"),
            ([NVIDIA], "nvidia"),
            ([INTEL, NVIDIA], "prime"),
            ([AMD, NVIDIA], "prime"),
            ([INTEL, RADEON], "mesa"),
            ([AMD, RADEON], "mesa"),
            ([INTEL, gpu(0x8086, 0x56A0, "0000:03:00.0")], "mesa"),
        ]:
            with self.subTest(devices=devices):
                config = self.resolve(devices)
                self.assertEqual(config["profile"], profile)
                self.assertEqual(len(config["devices"]), len(devices))
                self.assertEqual(config, self.resolve(list(reversed(devices))))
                if profile == "prime":
                    self.assertEqual(config["prime"]["nvidiaBusId"], "PCI:1@0:0:0")
                    self.assertEqual(config["prime"]["integratedBusId"], "PCI:0@0:2:0")
                    self.assertIn(devices[0]["address"], config["prime"]["renderDevice"])

    def test_vm_devices_and_explicit_3d_requirement(self):
        for vendor, device in graphics.VIRTUAL:
            config = self.resolve([gpu(vendor, device)])
            self.assertEqual(config["profile"], "virtual")
            self.assertIn("3D acceleration", graphics.describe(config))
        for vendor, device in [(0x1234, 0x1111), (0x1B36, 0x0100), (0x80EE, 0xBEEF)]:
            with self.assertRaisesRegex(ValueError, "For a VM"):
                self.resolve([gpu(vendor, device)])
        config = self.resolve([gpu(0x1AF4, 0x1050)])
        with patch("builtins.input", return_value="no"):
            with self.assertRaisesRegex(ValueError, "Enable VM 3D"):
                installer.confirm_graphics_requirements({"graphics": config})

    def test_modern_and_revision_named_amd_apus(self):
        for device in [0x15DD, 0x15D8, 0x15BF, 0x150E, 0x1114, 0x1586, 0x164E, 0x1900]:
            with self.subTest(device=device):
                config = self.resolve([gpu(0x1002, device), NVIDIA])
                self.assertEqual(config["profile"], "prime")
                self.assertEqual(config["prime"]["integratedVendor"], "amd")

    def test_no_existing_drivers_or_drm_nodes_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cpu = root / "cpuinfo"
            cpu.write_text("vendor_id : GenuineIntel\n")
            for fixture in [INTEL, NVIDIA]:
                device = root / "bus/pci/devices" / fixture["address"]
                device.mkdir(parents=True)
                for name, value in {
                    "class": "0x030000",
                    "vendor": hex(fixture["vendor"]),
                    "device": hex(fixture["device"]),
                    "subsystem_vendor": hex(fixture["subvendor"]),
                    "subsystem_device": "0",
                    "modalias": fixture["modalias"],
                }.items():
                    (device / name).write_text(value)
            with patch.object(
                installer, "run", side_effect=AssertionError("no driver command permitted")
            ):
                detected = installer.detect_hardware(root, cpu)
                self.assertEqual(self.resolve(detected["gpus"])["profile"], "prime")

    def test_unknown_and_legacy_devices_are_not_vendor_matches(self):
        for device in [
            gpu(0x8086, 0xFFFF),
            gpu(0x1002, 0xFFFF),
            gpu(0xFFFF, 0x1234),
            gpu(0x8086, 0x2A42),
            gpu(0x1002, 0x6798),
            gpu(0x8086, 0xD740),
        ]:
            with (
                self.subTest(device=device),
                self.assertRaisesRegex(ValueError, "Niri compatibility"),
            ):
                self.resolve([device])

    def test_nvidia_legacy_and_wrong_subsystem(self):
        for branch in ["470.xx", "390.xx", "580.xx"]:
            metadata = {"chips": [MANIFEST["chips"][0] | {"legacybranch": branch}]}
            with self.assertRaisesRegex(ValueError, branch):
                graphics.resolve_graphics([NVIDIA], support, metadata)
        for metadata in [
            {"chips": []},
            {"chips": [MANIFEST["chips"][0] | {"devid": "0x0000"}]},
            {"chips": [MANIFEST["chips"][0] | {"features": []}]},
            {"chips": [MANIFEST["chips"][0] | {"subvendorid": "0x1028"}]},
            {"chips": [MANIFEST["chips"][0] | {"subdevid": "0x5678"}]},
        ]:
            with self.assertRaisesRegex(ValueError, "GBM"):
                graphics.resolve_graphics([NVIDIA], support, metadata)
        metadata = {
            "chips": [
                MANIFEST["chips"][0],
                MANIFEST["chips"][0]
                | {"subvendorid": "0x10de", "subdevid": "0", "legacybranch": "470.xx"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "470.xx"):
            graphics.resolve_graphics([NVIDIA], support, metadata)
        with self.assertRaisesRegex(ValueError, "compute-only"):
            graphics.resolve_graphics(
                [NVIDIA], support, {"chips": [MANIFEST["chips"][0] | {"name": "NVIDIA H100"}]}
            )

    def test_nvidia_catalogue_is_scanned_once_per_device(self):
        with patch.object(graphics, "nvidia_chip", wraps=graphics.nvidia_chip) as lookup:
            self.assertEqual(self.resolve([NVIDIA])["profile"], "nvidia")
        lookup.assert_called_once()

    def test_support_level_is_separate_from_hardware_verification(self):
        for devices in [[INTEL], [AMD], [NVIDIA], [INTEL, NVIDIA], [gpu(0x1AF4, 0x1050)]]:
            description = graphics.describe(self.resolve(devices))
            self.assertIn("Support level: Configuration supported", description)
            self.assertIn("Hardware verification: not established", description)
        description = graphics.describe(self.resolve([gpu(0x15AD, 0x0405)]))
        self.assertIn("Support level: Experimental", description)
        self.assertIn("Hardware verification: not established", description)

    def test_unknown_is_distinct_from_outside_policy_without_bypassing_either(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized device"):
            self.resolve([gpu(0x1002, 0xFFFF)])
        with self.assertRaisesRegex(ValueError, "Outside automatic policy"):
            self.resolve([gpu(0x1002, 0x6798)])

    def test_ambiguous_arrangements(self):
        for devices in [
            [],
            [INTEL, INTEL],
            [NVIDIA, NVIDIA | {"address": "0000:03:00.0"}],
            [INTEL, RADEON, NVIDIA],
            [RADEON, NVIDIA],
            [INTEL, gpu(0x1AF4, 0x1050, "0000:04:00.0")],
        ]:
            with self.subTest(devices=devices), self.assertRaises(ValueError):
                self.resolve(devices)

    def test_pci_bus_ids_are_decimal_and_preserve_domain(self):
        for address, expected in [
            ("0000:00:02.0", "PCI:0@0:2:0"),
            ("0001:0a:1f.7", "PCI:10@1:31:7"),
            ("10000:ff:00.1", "PCI:255@65536:0:1"),
        ]:
            self.assertEqual(graphics.pci_bus_id(address), expected)
        for address in ["01:00.0", "0000:00:20.0", "0000:01:00.8", "PCI:1:0:0", "0000:00:00.0\n"]:
            with self.assertRaises(ValueError):
                graphics.pci_bus_id(address)

    def test_settings_migration_preserves_driver_intent(self):
        for old, devices in [(False, [INTEL]), (True, [NVIDIA])]:
            resolved = self.resolve(devices)
            settings = graphics.validate_saved(
                {"nvidia": old, "backupRepository": "fixture"}, resolved
            )
            self.assertEqual(settings["graphics"], resolved)
            self.assertEqual(settings["backupRepository"], "fixture")
        for old, devices in [(False, [NVIDIA]), (True, [INTEL]), (True, [INTEL, NVIDIA])]:
            with self.assertRaisesRegex(ValueError, "Legacy"):
                graphics.validate_saved({"nvidia": old}, self.resolve(devices))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "installation.json"
            path.write_text('{"nvidia":true,"userName":"dev","backupRepository":"fixture"}')
            with patch.object(installer, "REPO", Path(tmp)):
                installer.save_settings({"graphics": self.resolve([NVIDIA])})
            saved = json.loads(path.read_text())
            self.assertNotIn("nvidia", saved)
            self.assertEqual(saved["backupRepository"], "fixture")

    def test_resume_rejects_hardware_pin_schema_and_bus_id_changes(self):
        config = self.resolve([INTEL, NVIDIA])
        self.assertEqual(graphics.validate_saved({"graphics": config}, config)["graphics"], config)
        for mutation in [
            lambda c: c.update(schema=99),
            lambda c: c["stack"].update(kernel="changed"),
            lambda c: c["devices"][0].update(subdevice=123),
            lambda c: c["prime"].update(nvidiaBusId="PCI:9@0:0:0"),
            lambda c: c.update(profile="nvidia"),
        ]:
            changed = copy.deepcopy(config)
            mutation(changed)
            with self.assertRaisesRegex(ValueError, "Resume stopped"):
                graphics.validate_saved({"graphics": changed}, config)

    def evaluated(self, config):
        prime = config["prime"]
        nv = config["profile"] in ("prime", "nvidia")
        return dict(
            enabled=True,
            drivers=["nvidia"] if nv else ["modesetting"],
            open=nv,
            modesetting=nv,
            nvidia=config["stack"]["nvidia"],
            kernel=config["stack"]["kernel"],
            offload=bool(prime),
            command=bool(prime),
            sync=False,
            reverse=False,
            intel=prime["integratedBusId"]
            if prime and prime["integratedVendor"] == "intel"
            else "",
            amd=prime["integratedBusId"] if prime and prime["integratedVendor"] == "amd" else "",
            nvbus=prime["nvidiaBusId"] if prime else "",
            params=[],
            blacklist=[],
            niriConfigs={
                "dev": f'debug {{ render-drm-device "{prime["renderDevice"]}"; }}' if prime else ""
            },
        )

    def test_evaluated_overrides_cannot_bypass_saved_plan(self):
        for devices in [[INTEL], [NVIDIA], [INTEL, NVIDIA], [AMD, NVIDIA]]:
            config = self.resolve(devices)
            actual = self.evaluated(config)
            with patch.object(installer, "run", return_value=json.dumps(actual)):
                installer.verify_graphics_configuration({"graphics": config, "userName": "dev"})
            changes = [
                {"drivers": ["nouveau"]},
                {"params": ["nomodeset"]},
                {"kernel": "other"},
                {"params": ["i915.force_probe=*"]},
                {"enabled": False},
            ]
            if config["prime"]:
                changes += [{"offload": False}, {"nvbus": "PCI:2@0:0:0"}, {"niriConfigs": {}}]
            for change in changes:
                with (
                    self.subTest(change=change),
                    patch.object(installer, "run", return_value=json.dumps(actual | change)),
                ):
                    with self.assertRaises(ValueError):
                        installer.verify_graphics_configuration(
                            {"graphics": config, "userName": "dev"}
                        )

    def test_selected_driver_blacklists_are_checked_in_kernel_parameters(self):
        for devices, driver in (([RADEON], "amdgpu"), ([INTEL], "i915"), ([NVIDIA], "nvidia")):
            config = self.resolve(devices)
            actual = self.evaluated(config)
            for parameter in (
                f"module_blacklist={driver}",
                f"module-blacklist=unrelated,{driver}",
                f'module_blacklist="{driver},unrelated"',
                f"modprobe.blacklist=unrelated,{driver}",
            ):
                with (
                    self.subTest(parameter=parameter),
                    patch.object(
                        installer, "run", return_value=json.dumps(actual | {"params": [parameter]})
                    ),
                    self.assertRaisesRegex(ValueError, "graphics driver is blacklisted"),
                ):
                    installer.verify_graphics_configuration({"graphics": config, "userName": "dev"})
            with patch.object(
                installer,
                "run",
                return_value=json.dumps(actual | {"params": ["module_blacklist=unrelated"]}),
            ):
                installer.verify_graphics_configuration({"graphics": config, "userName": "dev"})

    def test_nvidia_required_display_modules_cannot_be_blacklisted(self):
        for devices in ([NVIDIA], [INTEL, NVIDIA]):
            config = self.resolve(devices)
            actual = self.evaluated(config)
            for module in ("nvidia_drm", "nvidia_modeset"):
                for change in (
                    {"blacklist": [module]},
                    {"blacklist": [module.replace("_", "-")]},
                    {"params": [f"module_blacklist={module}"]},
                    {"params": [f"modprobe.blacklist={module}"]},
                    {"params": [f'modprobe.blacklist="unrelated,{module.replace("_", "-")}"']},
                ):
                    with (
                        self.subTest(devices=devices, module=module, change=change),
                        patch.object(installer, "run", return_value=json.dumps(actual | change)),
                        self.assertRaisesRegex(ValueError, "graphics driver is blacklisted"),
                    ):
                        installer.verify_graphics_configuration(
                            {"graphics": config, "userName": "dev"}
                        )
                # The kernel blacklist compares names literally. These hyphen
                # spellings do not match the modules' actual underscore names.
                with patch.object(
                    installer,
                    "run",
                    return_value=json.dumps(
                        actual | {"params": [f"module_blacklist={module.replace('_', '-')}"]}
                    ),
                ):
                    installer.verify_graphics_configuration({"graphics": config, "userName": "dev"})

    @unittest.skipIf(
        profiles is None, "provide built graphics-profiles for Nix projection integration"
    )
    def test_actual_nix_projections_match_resolved_choices(self):
        arrangements = {
            "mesa": [INTEL, RADEON],
            "nvidia": [NVIDIA],
            "intel-prime": [INTEL, NVIDIA],
            "amd-prime": [AMD, NVIDIA],
            "virtual": [gpu(0x1AF4, 0x1050)],
        }
        if single_profile is not None:
            arrangements = {single_profile: arrangements[single_profile]}
        for name, devices in arrangements.items():
            if name.endswith("prime"):
                devices = [
                    devices[0] | {"address": "0001:0a:02.0"},
                    devices[1] | {"address": "0001:0b:00.0"},
                ]
            directory = profiles if single_profile is not None else profiles / name
            actual = (directory / "plan.json").read_text()
            # Exercise the installer validator with fully evaluated Nix data,
            # not just a handwritten mock of the expected module options.
            user = next(iter(json.loads(actual)["niriConfigs"]))
            with self.subTest(profile=name), patch.object(installer, "run", return_value=actual):
                installer.verify_graphics_configuration(
                    {"graphics": self.resolve(devices), "userName": user}
                )

    def test_incompatible_hardware_stops_real_resolution_before_mutations(self):
        from contextlib import ExitStack

        for args in [[], ["--dry-run"], ["--resume"]]:
            with ExitStack() as stack:
                stack.enter_context(patch.object(sys, "argv", ["install.py", *args]))
                stack.enter_context(patch.object(installer, "run", return_value="{}"))
                stack.enter_context(patch.object(installer, "require_live"))
                stack.enter_context(patch.object(installer, "require_local_console"))
                stack.enter_context(patch.object(installer, "check_hardware"))
                stack.enter_context(patch.object(installer, "choose_disk", return_value={}))
                stack.enter_context(patch.object(installer, "hardware_defaults", return_value={}))
                stack.enter_context(patch.object(installer, "collect_settings", return_value={}))
                stack.enter_context(
                    patch.object(
                        installer, "detect_hardware", return_value={"gpus": [gpu(0x1002, 0xFFFF)]}
                    )
                )
                stack.enter_context(
                    patch.object(
                        installer,
                        "resolve_hardware_graphics",
                        side_effect=lambda h: self.resolve(h["gpus"]),
                    )
                )
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
                with self.assertRaisesRegex(ValueError, "Niri compatibility"):
                    installer.main()
                for mutation in mutations:
                    mutation.assert_not_called()

    def test_built_driver_checks_every_gpu_and_virtio_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "result-system/kernel-modules/lib/modules/fixture").mkdir(parents=True)
            config = self.resolve([INTEL, RADEON])
            with (
                patch.object(installer, "REPO", Path(tmp)),
                patch.object(installer, "run", side_effect=["i915", "radeon"]) as run,
            ):
                with self.assertRaisesRegex(ValueError, RADEON["address"]):
                    installer.verify_built_graphics(
                        {"gpus": [INTEL, RADEON]}, {"graphics": config}, Path(tmp) / "result-system"
                    )
                self.assertEqual(run.call_count, 2)
            virtual = gpu(0x1AF4, 0x1050)
            with (
                patch.object(installer, "REPO", Path(tmp)),
                patch.object(installer, "run", return_value="virtio_gpu") as run,
            ):
                installer.verify_built_graphics(
                    {"gpus": [virtual]},
                    {"graphics": self.resolve([virtual])},
                    Path(tmp) / "result-system",
                )
                self.assertEqual(run.call_args.args[-1], "virtio:d00000010v00001AF4")


unittest.main()
