#!/usr/bin/env python3
"""Interactive live installer. Commands are argument arrays, never shell text."""

import argparse
import fcntl
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import installer_ui as ui
from graphics import describe, resolve_graphics, validate_saved
from graphics_metadata import load_metadata

REPO = Path(__file__).resolve().parent.parent
MIN_DISK_SIZE = 32 * 1024**3
MAX_BLOCK_NODES = 256
SNAPSHOTS = None


class FlakeSnapshots:
    """Refresh previews, then freeze one source for the installation transaction."""

    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workstation-installer-")
        self.path = None
        self.signature = None
        self.generation = 0
        self.frozen = False

    def command(self, args):
        settings = REPO / "installation.json"
        signature = (
            self.signature
            if self.frozen
            else (settings.read_bytes() if settings.exists() else None)
        )
        if self.path is None or signature != self.signature:
            path = Path(self.temporary.name) / str(self.generation)
            self.generation += 1
            subprocess.run(
                ["bash", str(REPO / "scripts/with-local-flake.sh"), "--snapshot-only", str(path)],
                check=True,
                cwd=REPO,
            )
            self.path, self.signature = path, signature
        return tuple(f"path:{self.path}#{arg[2:]}" if arg.startswith(".#") else arg for arg in args)

    def freeze(self):
        if self.frozen:
            raise ValueError("The installation source is already frozen.")
        # Capture current source even if the settings bytes have not changed.
        self.path = None
        self.command(())
        self.frozen = True
        return self.path

    def close(self):
        self.temporary.cleanup()


def run(*args, capture=False):
    nix_work = args[0] == "nix" and args[1] in ("eval", "build")
    if args[0] == "nix" and any(".#" in arg for arg in args):
        # Installation must not implicitly move the researched compatibility pin.
        args = (*args[:2], "--no-update-lock-file", *args[2:])
        # The generated installation.json is ignored by Git flakes. Supply a
        # filtered local snapshot so every evaluation sees the saved choices.
        args = (
            SNAPSHOTS.command(args)
            if SNAPSHOTS is not None
            else ("bash", str(REPO / "scripts/with-local-flake.sh"), *args)
        )
    if nix_work:
        args = ui.progress_command(args, capture=capture)
    result = subprocess.run(
        args,
        cwd=REPO,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        env=ui.environment() if ui.enabled() else None,
    )
    return result.stdout.strip() if capture else None


def require_live():
    if os.geteuid() != 0 or not os.path.ismount("/iso"):
        raise ValueError("Run from a NixOS live USB with sudo.")
    if not Path("/sys/firmware/efi").is_dir():
        raise ValueError("Reboot the live USB in UEFI mode.")
    for tool in (
        "nix",
        "git",
        "tar",
        "nixos-install",
        "lsblk",
        "findmnt",
        "blkid",
        "age-keygen",
        "mkpasswd",
        "loadkeys",
        "cryptsetup",
        "modprobe",
        "kbd_mode",
    ):
        if shutil.which(tool) is None:
            raise ValueError(f"Missing installer tool: {tool}")


def require_local_console():
    """Account for sudo's PTY without accepting a graphical or SSH terminal."""
    opened = None
    try:
        descriptor = sys.stdin.fileno()
        tty = os.ttyname(descriptor)
        if not re.fullmatch(r"/dev/tty[1-9][0-9]*", tty):
            # Recent sudo versions allocate a PTY even when invoked from a VT.
            tty = os.environ.get("SUDO_TTY", "") if "SUDO_UID" in os.environ else ""
            if not re.fullmatch(r"/dev/tty[1-9][0-9]*", tty) or os.environ.get("SSH_CONNECTION"):
                raise ValueError("not a local virtual console")
            opened = os.open(tty, os.O_RDONLY | os.O_NOCTTY)
            descriptor = opened
        mode = fcntl.ioctl(descriptor, 0x4B3B, bytes(4))  # KDGETMODE
        if int.from_bytes(mode, sys.byteorder) != 0:  # KD_TEXT
            raise ValueError("console is in graphics mode")
        return tty
    except (OSError, ValueError) as error:
        raise ValueError(
            "Password entry requires a local text console. Switch with "
            "Ctrl+Alt+F2, log in, and rerun the installer there. "
            "Graphical terminals and SSH are supported only for --dry-run."
        ) from error
    finally:
        if opened is not None:
            os.close(opened)


def configure_keyboard(settings):
    console = require_local_console()
    # Use the very same compiled keymap that NixOS embeds in the initrd.
    keyboard = json.loads(
        run(
            "nix",
            "eval",
            "--json",
            ".#lib.installationKeyboard",
            capture=True,
        )
    )
    selected = settings["keyboardLayout"]
    expected = "us" if selected == "us" else f"{selected},us"
    if keyboard["useXkbConfig"] is not True or keyboard["layout"] != expected:
        raise ValueError(
            "Installed console/desktop keyboard settings disagree with the installation plan."
        )
    options = keyboard["options"]
    if selected != "us" and "grp:alt_shift_toggle" not in options.split(","):
        raise ValueError("Installed console/desktop keyboard group switching is missing.")
    keymap = run(
        "nix",
        "build",
        "--max-jobs",
        "2",
        "--cores",
        "4",
        "--no-link",
        "--print-out-paths",
        ".#nixosConfigurations.workstation.config.console.keyMap",
        capture=True,
    )
    if not keymap.startswith("/nix/store/") or "\n" in keymap or not Path(keymap).is_file():
        raise ValueError("Could not build the installed console keymap.")
    run("kbd_mode", "--unicode", "--console", console)
    run("loadkeys", "--unicode", "--console", console, keymap)
    print(f"\nKeyboard layout applied: {settings['keyboardLayout']}.")
    print("Typing test — use the displayed sample, NEVER your password.")
    if selected != "us":
        print(
            "Alt+Shift switches between your selected layout and the US fallback. "
            "If Latin letters are unavailable, switch to US for this sample and passwords. "
            "Use the same group at disk unlock and login; each boot starts in the selected layout."
        )
    sample = "yY zZ @ : / - _ + ="
    while ui.text(f"Type exactly: {sample}") != sample:
        print("The sample did not match. Try again, or press Ctrl+C to change the layout.")


def secure_boot_state(directory=Path("/sys/firmware/efi/efivars")):
    path = directory / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
    try:
        value = path.read_bytes()
    except OSError:
        return None
    return bool(value[4]) if len(value) == 5 and value[4] in (0, 1) else None


def detect_hardware(sysfs=Path("/sys"), cpuinfo=Path("/proc/cpuinfo")):
    vendors = set(re.findall(r"^vendor_id\s*:\s*(\S+)", cpuinfo.read_text(), re.M))
    cpu = (
        {"GenuineIntel": "intel", "AuthenticAMD": "amd"}.get(next(iter(vendors)), "generic")
        if len(vendors) == 1
        else "generic"
    )
    gpus = []
    for device in sorted((sysfs / "bus/pci/devices").iterdir()):
        if int((device / "class").read_text(), 16) >> 16 != 3:
            continue
        gpus.append(
            {
                "address": device.name,
                "vendor": int((device / "vendor").read_text(), 16),
                "device": int((device / "device").read_text(), 16),
                "subvendor": int((device / "subsystem_vendor").read_text(), 16),
                "subdevice": int((device / "subsystem_device").read_text(), 16),
                "modalias": (device / "modalias").read_text().strip(),
            }
        )
    return {
        "architecture": platform.machine(),
        "cpu": cpu,
        "gpus": gpus,
        "bluetooth": any((sysfs / "class/bluetooth").glob("hci*")),
        "secure_boot": secure_boot_state(sysfs / "firmware/efi/efivars"),
    }


def hardware_defaults(defaults, hardware):
    return defaults | {"cpu": hardware["cpu"], "bluetooth": hardware["bluetooth"]}


def storage_modules(disk, sysfs=Path("/sys")):
    device = sysfs / "class/block" / Path(disk).resolve().name / "device"
    if not device.exists():
        raise ValueError(
            "Cannot identify the target storage controller; use a reviewed hardware module."
        )
    modules = set()
    for parent in (device.resolve(), *device.resolve().parents):
        driver = parent / "driver"
        module = driver / "module"
        if module.is_symlink():
            # PCIe port services appear in sysfs as pcieportdrv even though
            # they are built into the kernel, not an initrd storage module.
            # Exempt only an identified PCI bridge; retain unknown controllers
            # and intermediaries (such as VMD/RAID) for the checks below.
            pci_class = parent / "class"
            if (
                module.resolve().name == "pcieportdrv"
                and driver.resolve().name == "pcieport"
                and pci_class.is_file()
                and int(pci_class.read_text(), 16) >> 8 == 0x0604
            ):
                continue
            modules.add(module.resolve().name)
    # Controller/bus modules supported by the generic installation profile.
    policy = json.loads(Path(__file__).with_name("storage-policy.json").read_text())
    supported, controllers = set(policy["modules"]), set(policy["controllers"])
    if not modules.intersection(controllers) or modules - supported:
        raise ValueError(
            "Storage needs a reviewed hardware module: " + ", ".join(sorted(modules or {"unknown"}))
        )
    return modules


def resolve_hardware_graphics(hardware):
    print("  Checking graphics compatibility…")
    expected = json.loads(run("nix", "eval", "--json", ".#lib.graphicsMetadata", capture=True))
    support, metadata = load_metadata(REPO / "hardware/graphics", expected)
    return resolve_graphics(hardware["gpus"], support, metadata)


def check_hardware(settings, hardware):
    print("\nHardware compatibility checks")
    if not ui.enabled() or ui.verbose:
        print(f"  Architecture: {hardware['architecture']}; CPU: {hardware['cpu']}")
        for gpu in hardware["gpus"]:
            print(f"  GPU: {gpu['address']} {gpu['vendor']:04x}:{gpu['device']:04x}")
    if hardware["architecture"] != "x86_64":
        raise ValueError("This workstation supports x86_64 only.")
    if hardware["secure_boot"] is not False:
        raise ValueError(
            "Secure Boot is enabled or its state could not be read. "
            "This boot configuration is unsigned. Disable Secure Boot if enabled; "
            "otherwise check that EFI variables are mounted and readable, then retry."
        )
    if hardware["cpu"] == "generic" or settings["cpu"] != hardware["cpu"]:
        raise ValueError(
            "CPU vendor is unknown or differs from the selected microcode profile. Review the hardware configuration."
        )
    modules = storage_modules(settings["disk"])
    if not ui.enabled() or ui.verbose:
        print("  Storage drivers: " + ", ".join(sorted(modules)))
    print("  Platform/storage checks passed. Graphics are checked separately.")
    return sorted(modules)


def verify_storage_configuration(modules):
    available = json.loads(
        run(
            "nix",
            "eval",
            "--json",
            ".#nixosConfigurations.workstation.config.boot.initrd.availableKernelModules",
            capture=True,
        )
    )
    if set(modules) - set(available):
        raise ValueError(
            "The installed initrd is missing detected storage drivers. Review hosts/workstation/hardware.nix."
        )


def verify_graphics_configuration(settings):
    """Check evaluated Nix options, including manual overrides, before erasure."""
    actual = json.loads(run("nix", "eval", "--json", ".#lib.installationGraphics", capture=True))
    graphics = settings["graphics"]
    nv = graphics["profile"] in ("nvidia", "prime")
    prime = graphics["prime"]
    expected = {
        "enabled": True,
        "drivers": ["nvidia"] if nv else ["modesetting"],
        "offload": prime is not None,
        "command": prime is not None,
        "sync": False,
        "reverse": False,
        "intel": "",
        "amd": "",
        "nvbus": "",
        "kernel": graphics["stack"]["kernel"],
        "nvidia": graphics["stack"]["nvidia"],
    }
    if nv:
        expected.update(open=True, modesetting=True)
    if prime:
        expected.update(nvbus=prime["nvidiaBusId"])
        expected[prime["integratedVendor"]] = prime["integratedBusId"]
    if any(actual.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Evaluated graphics configuration differs from the saved installation plan."
        )
    params = actual["params"]
    drivers = {g["driver"] for g in graphics["devices"]}
    forbidden = {
        "nomodeset",
        "nvidia-drm.modeset=0",
        "nvidia_drm.modeset=0",
        "i915.modeset=0",
        "xe.modeset=0",
        "amdgpu.modeset=0",
    }
    if forbidden.intersection(params) or any("force_probe=" in p for p in params):
        raise ValueError(
            "Kernel graphics overrides disable modesetting or force unsupported hardware."
        )
    modules = (drivers - {"intel"}) | ({"i915", "xe"} if "intel" in drivers else set())
    if modules.intersection(actual["blacklist"]):
        raise ValueError(
            "A selected graphics driver is blacklisted in the installed configuration."
        )
    if prime and f'render-drm-device "{prime["renderDevice"]}"' not in actual["niriConfigs"].get(
        settings["userName"], ""
    ):
        raise ValueError("Niri render device differs from the saved PRIME configuration.")


def verify_built_graphics(hardware, settings, system):
    directory = system / "kernel-modules"
    versions = list((directory / "lib/modules").glob("*"))
    if len(versions) != 1:
        raise ValueError("Cannot identify the built kernel modules for GPU compatibility checking.")
    expected = {
        "intel": {"i915", "xe"},
        "amdgpu": {"amdgpu"},
        "nvidia": {"nvidia"},
        "virtio_gpu": {"virtio_gpu"},
        "vmwgfx": {"vmwgfx"},
    }
    choices = {g["address"]: g for g in settings["graphics"]["devices"]}
    for gpu in hardware["gpus"]:
        driver = choices[gpu["address"]]["driver"]
        # Virtio PCI transport aliases resolve to virtio_pci, not the child GPU
        # driver. Check the latter's virtio device alias in the built kernel.
        alias = "virtio:d00000010v00001AF4" if driver == "virtio_gpu" else gpu["modalias"]
        try:
            drivers = set(
                run(
                    "modprobe",
                    "--dirname",
                    str(directory),
                    "--set-version",
                    versions[0].name,
                    "--resolve-alias",
                    alias,
                    capture=True,
                ).splitlines()
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(
                f"Could not resolve GPU {gpu['address']} against the built kernel."
            ) from error
        if not drivers.intersection(expected[driver]):
            raise ValueError(
                f"The built kernel has no matching GPU driver for {gpu['address']}. Nothing was formatted."
            )


def verify_disk_passphrase(settings):
    verify_mounted_install(settings)
    ancestors = run(
        "lsblk",
        "--inverse",
        "--noheadings",
        "--raw",
        "--paths",
        "--output",
        "NAME,TYPE",
        "/dev/mapper/cryptroot",
        capture=True,
    ).splitlines()
    partitions = [
        line.split()[0]
        for line in ancestors
        if len(line.split()) == 2 and line.split()[1] == "part"
    ]
    if len(partitions) != 1:
        raise ValueError(
            "Cannot identify a unique encrypted partition for passphrase verification."
        )
    print(
        "\nVerify your disk passphrase using the selected keyboard layout. The disk remains mounted."
    )
    run("cryptsetup", "open", "--type", "luks", "--test-passphrase", "--tries", "3", partitions[0])


def disk_inventory():
    return json.loads(
        run(
            "lsblk",
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,SIZE,TYPE,MODEL,SERIAL,RO,MOUNTPOINTS,MAJ:MIN,PARTLABEL",
            capture=True,
        )
    )["blockdevices"]


def block_tree(root):
    """Walk one lsblk tree with a fixed work limit, including malformed fixtures."""
    pending = [root]
    seen = set()
    for _ in range(MAX_BLOCK_NODES):
        if not pending:
            return
        node = pending.pop()
        if not isinstance(node, dict) or id(node) in seen:
            raise ValueError("Disk topology is malformed. Nothing was formatted.")
        seen.add(id(node))
        children = node.get("children") or []
        if not isinstance(children, list):
            raise ValueError("Disk topology is malformed. Nothing was formatted.")
        if len(seen) + len(pending) + len(children) > MAX_BLOCK_NODES:
            raise ValueError("Disk topology exceeds the supported limit. Nothing was formatted.")
        pending.extend(reversed(children))
        yield node
    if pending:
        raise ValueError("Disk topology exceeds the supported limit. Nothing was formatted.")


def blocked_reason(disk):
    if disk["type"] != "disk":
        return "not a whole disk"
    if disk.get("ro"):
        return "read-only"
    if int(disk["size"]) < MIN_DISK_SIZE:
        return "smaller than 32 GiB"

    for node in block_tree(disk):
        if any(node.get("mountpoints") or []):
            return "mounted, swap-active, or used by a storage mapper"
        # Reject active device-mapper/RAID consumers, even if unmounted.
        if node.get("type") not in ("disk", "part"):
            return "mounted, swap-active, or used by a storage mapper"

    return None


def by_id_paths():
    aliases = {}
    for path in sorted(Path("/dev/disk/by-id").glob("*")):
        if path.is_symlink() and not re.search(r"-part\d+$", path.name):
            aliases.setdefault(str(path.resolve()), []).append(str(path))
    return aliases


def choose_disk(inventory=None, aliases=None):
    aliases = by_id_paths() if aliases is None else aliases
    choices = []
    ui.screen("1 / 5  Choose a disk", "Select the disk for the new system. Nothing is erased yet.")
    print("The live USB and other busy disks cannot be selected.")
    for disk in disk_inventory() if inventory is None else inventory:
        if disk["type"] != "disk":
            continue
        label = disk_label(disk)
        reason = blocked_reason(disk)
        ids = aliases.get(disk["name"], [])
        if reason or not ids:
            print(f"  unavailable: {label} ({reason or 'no stable by-id name'})")
            continue
        # WWN/EUI identities are preferred to transport-specific aliases.
        disk["by_id"] = min(
            ids, key=lambda p: (not Path(p).name.startswith(("wwn-", "nvme-eui.")), p)
        )
        choices.append(disk)
        if not ui.enabled():
            print(f"  {len(choices)}. {label}\n     {disk['by_id']}")
    if not choices:
        raise ValueError("No eligible target disk. Unmount the target and disable its swap first.")
    if ui.enabled():
        index = ui.select(
            "Target disk — arrows to move; Enter to select; Ctrl+C to cancel",
            [(index, disk_label(disk)) for index, disk in enumerate(choices)],
        )
        return choices[index]
    while True:
        value = input("Disk number (or q to cancel): ").strip()
        if value.lower() == "q":
            raise KeyboardInterrupt
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        print("Choose one of the listed numbers.")


def disk_label(disk):
    return ui.clean(
        f"{disk.get('model') or 'Disk'} · {int(disk['size']) / 1024**3:.1f} GiB · "
        f"{Path(disk['name']).name} · serial {disk.get('serial') or '?'}"
    )


def ask(label, default, validate):
    while True:
        value = ui.text(label, default).strip() or str(default)
        if validate(value):
            return value
        print("Invalid value; please try again.")


def keyboard_choices(xkb):
    choices = {}
    section = None
    for line in (xkb / "rules/base.lst").read_text().splitlines():
        if line.startswith("!"):
            section = line.strip()
        elif section == "! layout" and line.strip():
            code, title = line.split(None, 1)
            if (xkb / "symbols" / code).is_file():
                choices[code] = title.strip()
    return dict(sorted(choices.items(), key=lambda item: item[1].casefold()))


def choose_timezone(zones, current):
    names = {
        line.split()[2]
        for line in (zones / "zone.tab").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    names.add("Etc/UTC")
    if valid_timezone(zones, current):
        names.add(current)
    names = sorted(name for name in names if valid_timezone(zones, name))
    regions = sorted({name.split("/")[0] for name in names})
    region = ui.choose_value("Timezone region", {r: r for r in regions}, current.split("/")[0])
    return ui.choose_value(
        "Timezone city",
        {
            name: name.partition("/")[2].replace("_", " ") or name
            for name in names
            if name.split("/")[0] == region
        },
        current,
    )


def valid_timezone(zones, value):
    return (
        bool(re.fullmatch(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*", value))
        and (zones / value).is_file()
    )


def collect_settings(defaults, disk):
    zones = Path(os.environ["WORKSTATION_ZONEINFO"])
    xkb = Path(os.environ["WORKSTATION_XKB"])
    fields = [
        ("userName", "Username"),
        ("hostName", "Computer name"),
        ("timeZone", "Timezone"),
        ("keyboardLayout", "Keyboard layout"),
        ("bluetooth", "Bluetooth"),
        ("containers", "Containers (Podman)"),
        ("richFilePreviews", "Rich file previews (media/PDF thumbnails)"),
        ("graphicalNetworking", "Graphical network controls (tray applet)"),
        ("obtain", "Obtain (install apps from GitHub releases)"),
    ]
    toggles = {"bluetooth", "containers", "richFilePreviews", "graphicalNetworking", "obtain"}
    validate = {
        "userName": lambda v: (
            bool(re.fullmatch(r"[a-z_][a-z0-9_-]*", v)) and v not in ("root", "nobody", "greeter")
        ),
        "hostName": lambda v: bool(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", v)
        ),
        "timeZone": lambda v: valid_timezone(zones, v),
        "keyboardLayout": lambda v: (
            bool(re.fullmatch(r"[a-z0-9_]+", v)) and (xkb / "symbols" / v).is_file()
        ),
        **dict.fromkeys(toggles, lambda v: type(v) is bool),
    }
    result = {key: defaults[key] for key, _ in fields} | {
        "disk": disk["by_id"],
        "cpu": defaults["cpu"],
    }
    cursor, notice = "continue", ""
    while True:
        invalid = [key for key, _ in fields if not validate[key](result[key])]
        if ui.enabled():
            ui.screen(
                "2 / 5  Preferences",
                disk_label(disk)
                + "\n"
                + (notice or "Choose a setting to edit, or continue with the defaults."),
            )
            optional = fields[5:]
            rows = [("continue", "Continue — review and build")]
            rows += [
                (key, f"{label}: " + ("on" if result[key] else "off"))
                if key in toggles
                else (key, f"{label}: {result[key]}")
                for key, label in fields[:5]
            ]
            extras = ", ".join(
                label.split(" (")[0] for key, label in optional if result[key] is True
            )
            rows.append(("extras", f"Optional apps: {extras or 'none — minimal setup'}"))
            cursor = ui.select("Arrows to move · Enter to edit · Ctrl+C to cancel", rows, cursor)
            if cursor == "continue":
                if not invalid:
                    return result
                notice = "Correct these settings: " + ", ".join(invalid)
                continue
            if cursor == "extras":
                chosen = ui.checklist(
                    "Optional apps — Space toggles; Enter saves; none are required",
                    optional,
                    {key for key, _ in optional if result[key] is True},
                )
                result.update({key: key in chosen for key, _ in optional})
                notice = "Optional apps saved. You can change them again before continuing."
                continue
            key, label = next((key, label) for key, label in fields if key == cursor)
            notice = ""
            if key in toggles:
                result[key] = not result[key]
            elif key == "timeZone":
                result[key] = choose_timezone(zones, result[key])
            elif key == "keyboardLayout":
                result[key] = ui.choose_value(label, keyboard_choices(xkb), result[key])
            else:
                result[key] = ask(label, result[key], validate[key])
            continue
        print("\nReview settings — Enter accepts all; choose a number to change one.")
        print("Containers, rich previews, graphical network controls and Obtain are optional.")
        print("Leave these extras disabled for a minimal setup.")
        for index, (key, label) in enumerate(fields, 1):
            value = ("enabled" if result[key] else "disabled") if key in toggles else result[key]
            print(
                f"  {index}. {label}: {value}" + (" — needs correction" if key in invalid else "")
            )
        print(f"  CPU: {result['cpu']} (detected); Graphics: Automatic")
        answer = input(
            f"Enter to continue (does not erase), 1–{len(fields)} to edit, q to cancel: "
        ).strip()
        if answer.lower() == "q":
            raise KeyboardInterrupt
        if not answer:
            if not invalid:
                return result
            print("Correct the marked settings before continuing.")
            continue
        if not answer.isdigit() or not 1 <= int(answer) <= len(fields):
            print("Choose one of the displayed numbers, or press Enter.")
            continue
        key, label = fields[int(answer) - 1]
        if key in toggles:
            result[key] = not result[key]
        elif key == "timeZone":
            result[key] = choose_timezone(zones, result[key])
        elif key == "keyboardLayout":
            result[key] = ui.choose_value(label, keyboard_choices(xkb), result[key])
        else:
            result[key] = ask(label, result[key], validate[key])


def show_plan(settings):
    ui.screen(
        "3 / 5  Review and prepare", "The system is built before the final erase confirmation."
    )
    labels = {
        "disk": "Erase disk",
        "userName": "Username",
        "hostName": "Computer",
        "timeZone": "Timezone",
        "keyboardLayout": "Keyboard",
        "cpu": "CPU",
        "bluetooth": "Bluetooth",
        "containers": "Containers (Podman)",
        "richFilePreviews": "Rich file previews (media/PDF thumbnails)",
        "graphicalNetworking": "Graphical network controls (tray applet)",
        "obtain": "Obtain (install apps from GitHub releases)",
    }
    for key, label in labels.items():
        value = settings[key]
        if isinstance(value, bool):
            value = "yes" if value else "no"
        print(f"  {label}: {value}")
    if ui.enabled() and not ui.verbose:
        names = [ui.clean(gpu["name"]) for gpu in settings["graphics"]["devices"]]
        print("  Graphics: automatic" + (" — " + ", ".join(names) if names else ""))
    else:
        print(describe(settings["graphics"]))
    print("  Desktop: Niri — terminal-first (Foot; graphical apps available)")
    print("  Encrypted Btrfs, ephemeral root, persistent Projects")


def confirm_graphics_requirements(settings):
    if settings["graphics"]["profile"] == "virtual":
        if ui.enabled():
            if not ui.select(
                "Does this VM have 3D acceleration enabled?",
                [(False, "No — cancel"), (True, "Yes — continue")],
            ):
                raise ValueError("Enable VM 3D acceleration before installing Niri.")
            return
        if (
            input(
                "VM requires 3D acceleration (VirGL for Virtio). Is it enabled? Type yes: "
            ).strip()
            != "yes"
        ):
            raise ValueError("Enable VM 3D acceleration before installing Niri.")


def save_settings(settings):
    destination = REPO / "installation.json"
    # Retain extra overrides made by hand, including secrets/backup choices.
    if destination.is_symlink():
        raise ValueError("Refusing a symlinked installation.json.")
    existing = json.loads(destination.read_text()) if destination.exists() else {}
    if not isinstance(existing, dict):
        raise ValueError("installation.json must contain a JSON object.")
    existing.update(settings)
    if "graphics" in settings:
        existing.pop("nvidia", None)
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o600
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(json.dumps(existing, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def export_settings(destination):
    """Save recovery choices outside the live checkout without overwriting files."""
    destination = Path(destination)
    data = (REPO / "installation.json").read_bytes()
    # Exclusive creation also works on FAT/exFAT recovery drives, where hard
    # links and atomic link publication are unavailable.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(f"Recovery settings saved to {destination}. Keep this copy independently available.")


def freeze_installation(settings):
    """Bind validated choices and all subsequent work to one captured source."""
    if SNAPSHOTS is None:
        raise ValueError("Installation requires a source snapshot.")
    source = SNAPSHOTS.freeze()
    actual = json.loads(
        run("nix", "eval", "--json", "--file", str(source / "settings.nix"), capture=True)
    )
    if not isinstance(actual, dict) or any(
        actual.get(key) != value for key, value in settings.items()
    ):
        raise ValueError("Settings changed before the installation source was frozen. Start again.")
    disks = json.loads(
        run(
            "nix",
            "eval",
            "--json",
            ".#nixosConfigurations.workstation.config.disko.devices.disk",
            "--apply",
            "disks: builtins.mapAttrs (_: disk: disk.device) disks",
            capture=True,
        )
    )
    if disks != {"system": settings["disk"]}:
        raise ValueError("The formatter's disk configuration differs from the selected target.")
    return source


def build():
    if SNAPSHOTS is None or not SNAPSHOTS.frozen:
        raise ValueError("Builds require a frozen installation source.")
    print("\nBuilding the system and disk formatter. No disk changes yet; this may take a while.")
    outputs = []
    for attribute, link, directory in (
        ("toplevel", "result-system", True),
        ("diskoScript", "result-disko", False),
    ):
        output = run(
            "nix",
            "build",
            "--max-jobs",
            "2",
            "--cores",
            "4",
            f".#nixosConfigurations.workstation.config.system.build.{attribute}",
            "-o",
            link,
            "--print-out-paths",
            "-L",
            capture=True,
        )
        path = Path(output)
        if (
            path.parent != Path("/nix/store")
            or "\n" in output
            or not (path.is_dir() if directory else path.is_file())
        ):
            raise ValueError(f"Could not identify the built {attribute} store path.")
        outputs.append(path)
    return tuple(outputs)


def verify_target(selected):
    real = str(Path(selected["by_id"]).resolve())
    inventory = disk_inventory()
    candidates = [d for d in inventory if d["name"] == real]
    if len(candidates) != 1:
        raise ValueError("The selected disk disappeared. Start again.")
    current = candidates[0]
    for field in ("name", "maj:min", "size", "serial", "model"):
        if current.get(field) != selected.get(field):
            raise ValueError("Disk identity changed. Start again.")
    if blocked_reason(current):
        raise ValueError("The selected disk is now busy or unavailable. Nothing was formatted.")

    # Disko addresses generated partitions by label. Duplicates on a second
    # disk would make those links ambiguous even when the target ID is stable.
    def has_layout_label(disk):
        return any(
            node.get("partlabel") in ("disk-system-ESP", "disk-system-encrypted")
            for node in block_tree(disk)
        )

    if any(d["name"] != real and has_layout_label(d) for d in inventory):
        raise ValueError(
            "Another disk has workstation partition labels. Disconnect it before installing."
        )
    if Path("/dev/mapper/cryptroot").exists() or os.path.ismount("/mnt"):
        raise ValueError(
            "An installation or cryptroot mapping already exists; use --resume for that installation."
        )


def verify_hardware_unchanged(original, settings, modules):
    if detect_hardware() != original:
        raise ValueError("Hardware changed after compatibility checks. Restart the installer.")
    if sorted(storage_modules(settings["disk"])) != modules:
        raise ValueError(
            "Storage drivers changed after compatibility checks. Restart the installer."
        )


def confirm_erase(selected):
    ui.screen(
        "4 / 5  Erase selected disk",
        "This deletes ALL files, partitions and snapshots on this disk.",
    )
    print(f"\n  {disk_label(selected)}\n  {ui.clean(selected['by_id'])}\n")
    if (
        ui.text("Type ERASE to erase this disk; Ctrl+C cancels", placeholder="ERASE")
        .strip()
        .casefold()
        != "erase"
    ):
        raise ValueError("Confirmation did not match. Nothing was formatted.")


def confirm_and_format(selected, hardware, settings, modules, formatter):
    if selected["by_id"] != settings["disk"]:
        raise ValueError("The confirmed disk differs from the frozen installation plan.")
    verify_target(selected)
    confirm_erase(selected)
    verify_target(selected)
    verify_hardware_unchanged(hardware, settings, modules)
    print("\nChoose the disk encryption passphrase at the next prompt. Keep it for every boot.")
    run(str(formatter))


def verify_mounted_install(settings):
    # Resume must never install into an unrelated disk's /mnt tree.
    real = str(Path(settings["disk"]).resolve())
    disks = [d for d in disk_inventory() if d["name"] == real and d["type"] == "disk"]
    if len(disks) != 1:
        raise ValueError("Configured target disk is not present.")
    ancestors = run(
        "lsblk",
        "--inverse",
        "--noheadings",
        "--raw",
        "--paths",
        "--output",
        "NAME",
        "/dev/mapper/cryptroot",
        capture=True,
    ).splitlines()
    if real not in ancestors:
        raise ValueError("Mounted cryptroot belongs to a different target disk.")
    subvolumes = {
        "/mnt": "/@root",
        "/mnt/nix": "/@nix",
        "/mnt/persist": "/@persist",
        "/mnt/projects": "/@projects",
        "/mnt/local": "/@local",
    }
    for path in (*subvolumes, "/mnt/boot"):
        if not os.path.ismount(path):
            raise ValueError(
                f"Missing {path}. Resume requires the formatted target to remain mounted."
            )
    uuid = run("blkid", "-s", "UUID", "-o", "value", "/dev/mapper/cryptroot", capture=True)
    if not uuid:
        raise ValueError("Cannot identify the mounted cryptroot filesystem.")
    for path, subvolume in subvolumes.items():
        mounted = run(
            "findmnt",
            "--noheadings",
            "--raw",
            "--output",
            "FSTYPE,UUID,FSROOT",
            "--mountpoint",
            path,
            capture=True,
        ).split()
        if mounted != ["btrfs", uuid, subvolume]:
            raise ValueError(f"{path} is not the expected target Btrfs subvolume.")
    esp = run("findmnt", "-n", "-o", "SOURCE", "--mountpoint", "/mnt/boot", capture=True)
    esp_type = run("findmnt", "-n", "-o", "FSTYPE", "--mountpoint", "/mnt/boot", capture=True)
    if esp_type != "vfat":
        raise ValueError("Mounted EFI partition is not a FAT filesystem.")
    ancestors = run(
        "lsblk",
        "--inverse",
        "--noheadings",
        "--raw",
        "--paths",
        "--output",
        "NAME",
        esp,
        capture=True,
    ).splitlines()
    if real not in ancestors:
        raise ValueError("Mounted EFI partition belongs to a different target disk.")


def finish(settings, system, source):
    ui.screen("5 / 5  Install", "Set up your passwords and install the prepared system.")
    verify_mounted_install(settings)
    verify_disk_passphrase(settings)
    print("\nSet the login password (separate from the disk encryption passphrase).")
    run("bash", str(source / "scripts/prepare-install.sh"), settings["userName"], str(REPO))
    verify_mounted_install(settings)
    print("\nInstalling the built system and bootloader…")
    run("nixos-install", "--no-root-passwd", "--system", str(system))
    print(f"\nInstallation complete. Your login is {settings['userName']}.")
    print("Recovery key: /mnt/persist/keys/sops/age.key — copy it to independent secure storage.")
    print("Keep the disk passphrase and this repository independently available too.")
    print("When ready, run: reboot\nRemove the live USB, unlock the disk, and log in.")


def demo():
    ui.demo = True
    disk = {
        "name": "/dev/demo-nvme",
        "size": 512 * 1024**3,
        "type": "disk",
        "model": "DEMO SSD",
        "serial": "NOT-A-REAL-DISK",
        "ro": False,
        "mountpoints": [],
        "children": [],
    }
    selected = choose_disk([disk], {disk["name"]: ["/dev/disk/by-id/DEMO-ONLY"]})
    defaults = {
        "userName": "dev",
        "hostName": "workstation",
        "timeZone": "UTC",
        "keyboardLayout": "us",
        "cpu": "generic",
        "bluetooth": False,
        "containers": False,
        "richFilePreviews": False,
        "graphicalNetworking": False,
        "obtain": False,
    }
    settings = collect_settings(defaults, selected)
    settings["graphics"] = {"profile": "mesa", "devices": [], "prime": None}
    show_plan(settings)
    if ui.enabled():
        ui.select("Demo only", [(True, "Preview the erase confirmation")])
    confirm_erase(selected)
    print("\nDemo complete. No hardware accessed, settings saved, or installation performed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--keyboard-test",
        action="store_true",
        help="apply the target console keymap and test typing; do not format or install",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview only; no settings or target changes (helpers may build)",
    )
    mode.add_argument(
        "--resume", action="store_true", help="continue with mounted target; never format"
    )
    mode.add_argument(
        "--save-settings",
        action="store_true",
        help="collect and save choices; never format or install",
    )
    mode.add_argument(
        "--demo",
        action="store_true",
        help="try the interface with a fictional disk; no root required",
    )
    parser.add_argument(
        "--plain", action="store_true", help="use numbered text prompts instead of the TUI"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show live Nix output instead of progress spinners"
    )
    parser.add_argument(
        "--export-settings",
        type=Path,
        help="also save choices to a new file on independent storage",
    )
    args = parser.parse_args()
    if args.export_settings and (args.demo or args.dry_run or args.keyboard_test):
        parser.error("--export-settings requires installation, --resume or --save-settings")
    ui.plain, ui.verbose = args.plain, args.verbose
    if args.demo:
        demo()
        return
    require_live()
    settings = json.loads(
        run("nix", "eval", "--json", "--file", str(REPO / "settings.nix"), capture=True)
    )
    if args.keyboard_test:
        configure_keyboard(settings)
        return
    hardware = detect_hardware()
    if not args.dry_run and not args.save_settings:
        require_local_console()
    if args.resume:
        modules = check_hardware(settings, hardware)
        resolved = resolve_hardware_graphics(hardware)
        migrated = settings.get("graphics") is None
        settings = validate_saved(settings, resolved)
        show_plan(settings)
        confirm_graphics_requirements(settings)
        verify_mounted_install(settings)
        if migrated:
            print("Migrating legacy graphics settings; original driver intent is preserved.")
            settings.pop("nvidia", None)
            save_settings(settings)
        if args.export_settings:
            export_settings(args.export_settings)
        source = freeze_installation(settings)
        verify_graphics_configuration(settings)
        verify_storage_configuration(modules)
        configure_keyboard(settings)
        verify_mounted_install(settings)
        if ui.enabled():
            proceed = ui.select(
                "Resume this mounted installation?",
                [(False, "Cancel"), (True, "Continue installation — do not format")],
            )
        else:
            proceed = (
                input("Continue installing into this mounted target? Type continue: ").strip()
                == "continue"
            )
        if not proceed:
            raise ValueError("Cancelled.")
        system, formatter = build()
        verify_hardware_unchanged(hardware, settings, modules)
        verify_built_graphics(hardware, settings, system)
    else:
        selected = choose_disk()
        settings = collect_settings(hardware_defaults(settings, hardware), selected)
        modules = check_hardware(settings, hardware)
        settings["graphics"] = resolve_hardware_graphics(hardware)
        show_plan(settings)
        if args.dry_run:
            print(
                "\nPreview complete. No settings saved, keyboard changed, workstation build started, or target disk changed. Full GPU driver validation runs after the workstation build."
            )
            return
        confirm_graphics_requirements(settings)
        save_settings(settings)
        if args.export_settings:
            export_settings(args.export_settings)
        else:
            print(
                "Recovery choices saved in installation.json. Copy it to independent storage before erasing."
            )
        if args.save_settings:
            print("Settings saved. No keyboard, target filesystem or installation changes made.")
            return
        source = freeze_installation(settings)
        verify_graphics_configuration(settings)
        verify_storage_configuration(modules)
        configure_keyboard(settings)
        system, formatter = build()
        verify_hardware_unchanged(hardware, settings, modules)
        verify_built_graphics(hardware, settings, system)
        confirm_and_format(selected, hardware, settings, modules, formatter)
    finish(settings, system, source)


if __name__ == "__main__":
    try:
        SNAPSHOTS = FlakeSnapshots()
        main()
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        KeyboardInterrupt,
        EOFError,
    ) as error:
        print(f"\nInstallation stopped: {error or 'cancelled'}", file=sys.stderr)
        if not ui.demo:
            print(
                "If formatting completed and the target is still mounted, retry with:\n  sudo bash scripts/install.sh --resume",
                file=sys.stderr,
            )
        sys.exit(1)
    finally:
        if SNAPSHOTS is not None:
            SNAPSHOTS.close()
