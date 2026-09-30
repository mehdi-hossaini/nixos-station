"""Build a conservative device catalogue from the pinned Mesa/Linux/libdrm sources.

This is deliberately not a PCI vendor allowlist. New families require policy review.
See docs/supported-hardware.md for scope and source references.
"""

import json
import re
import sys
import tarfile
from pathlib import Path

KERNEL_TABLE = "/drivers/gpu/drm/amd/amdgpu/amdgpu_drv.c"
KERNEL_MEMBERS_MAX = 250_000
KERNEL_TABLE_BYTES_MAX = 4 * 1024 * 1024
INTEL_PLATFORMS = {
    "bdw",
    "skl",
    "bxt",
    "kbl",
    "glk",
    "cfl",
    "ehl",
    "icl",
    "tgl",
    "rkl",
    "adl",
    "rpl",
    "dg1",
    "dg2",
    "mtl",
    "arl",
    "lnl",
    "bmg",
}
# SI/CIK may default to radeon; Topaz and compute accelerators lack a reviewed
# desktop display path with this pinned stack.
AMD_EXCLUDED = {
    "TAHITI",
    "PITCAIRN",
    "VERDE",
    "OLAND",
    "HAINAN",
    "BONAIRE",
    "HAWAII",
    "KAVERI",
    "KABINI",
    "MULLINS",
    "TOPAZ",
    "ARCTURUS",
    "ALDEBARAN",
}
# IP-discovery APUs no longer carry AMD_IS_APU in the kernel PCI table.
AMD_DISCOVERY_APUS = {
    0x1114,
    0x1506,
    0x150E,
    0x1586,
    0x15BF,
    0x15C8,
    0x15E7,
    0x164E,
    0x1900,
    0x1901,
    0x1902,
}


def kernel_gpu_table(kernel):
    """Read one bounded source member without indexing the entire archive."""
    with tarfile.open(kernel, mode="r|*") as archive:
        for index, member in enumerate(archive):
            if index >= KERNEL_MEMBERS_MAX:
                raise ValueError("Kernel archive exceeds the reviewed member limit.")
            if not member.name.endswith(KERNEL_TABLE):
                continue
            if not member.isfile() or member.size > KERNEL_TABLE_BYTES_MAX:
                raise ValueError("Kernel GPU table is not a bounded regular file.")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Kernel GPU table could not be read.")
            with source:
                data = source.read(KERNEL_TABLE_BYTES_MAX + 1)
            if len(data) != member.size:
                raise ValueError("Kernel GPU table is incomplete or too large.")
            return data.decode()
    raise ValueError("Kernel GPU table is missing from the pinned source archive.")


def intel_catalogue(mesa):
    devices, unsupported = {}, {}
    # Iris supplies the Gen8+ userspace driver. Exclude experimental and server
    # families, and families not reviewed against this kernel's default probes.
    text = (mesa / "include/pci_ids/iris_pci_ids.h").read_text()
    for line in text.splitlines():
        match = re.fullmatch(
            r'CHIPSET\((0x[0-9a-fA-F]+),\s*(\w+),\s*"[^"]*",\s*"([^"]*)".*\)', line
        )
        if not match:
            continue
        devid, platform, name = match.groups()
        family = platform.split("_")[0]
        key = f"8086:{int(devid, 16):04x}"
        if family not in INTEL_PLATFORMS or "FORCE_PROBE" in line:
            unsupported[key] = (
                f"Intel {platform} is experimental, server-only, or outside the reviewed automatic policy"
            )
            continue
        devices[key] = {
            "name": name,
            "driver": "intel",
            "integrated": family not in {"dg1", "dg2", "bmg"},
        }
    return devices, unsupported


def kernel_amd_flags(kernel):
    return {
        int(device, 16): (chip, extra)
        for device, chip, extra in re.findall(
            r"\{0x1002,\s*(0x[0-9a-fA-F]+),\s*PCI_ANY_ID,\s*PCI_ANY_ID,\s*0,\s*0,\s*CHIP_(\w+)([^}]*)\}",
            kernel_gpu_table(kernel),
        )
    }


def libdrm_amd_names(amd_ids):
    names = {}
    for line in amd_ids.read_text().splitlines():
        match = re.match(r"^([0-9a-fA-F]{4}),\s*[0-9a-fA-F]+,\s*(.+)", line)
        if not match:
            continue
        device, name = match.groups()
        names.setdefault(int(device, 16), []).append(name)
    return names


def amd_catalogue(kernel, amd_ids):
    flags = kernel_amd_flags(kernel)
    names = libdrm_amd_names(amd_ids)
    devices, unsupported = {}, {}
    for device, (chip, extra) in flags.items():
        key = f"1002:{device:04x}"
        if chip in AMD_EXCLUDED:
            unsupported[key] = (
                f"AMD {chip}: older driver-selection requirements or no desktop display engine; needs manual review"
            )
        else:
            devices[key] = {
                "name": f"AMD Radeon ({chip.lower().replace('_', ' ')})",
                "driver": "amdgpu",
                "integrated": "AMD_IS_APU" in extra,
            }
    # Require a named libdrm GPU; kernel PCI aliases include compute devices.
    for device, marketing_names in names.items():
        key = f"1002:{device:04x}"
        chip, extra = flags.get(device, ("IP_DISCOVERY", ""))
        if chip in AMD_EXCLUDED or not any("Radeon" in name for name in marketing_names):
            unsupported[key] = (
                f"AMD {chip}: older driver-selection requirements or a non-desktop accelerator; needs manual review"
            )
            continue
        # A PCI ID may have several revision-specific marketing names; do not
        # falsely report one of those as the exact detected board model.
        devices[key] = {
            "name": f"AMD Radeon ({chip.lower().replace('_', ' ')})",
            "driver": "amdgpu",
            "integrated": "AMD_IS_APU" in extra or device in AMD_DISCOVERY_APUS,
        }
    for key in unsupported:
        devices.pop(key, None)
    return devices, unsupported, len(flags), len(names)


def catalogue(mesa, kernel, amd_ids):
    intel_devices, intel_unsupported = intel_catalogue(mesa)
    amd_devices, amd_unsupported, kernel_count, libdrm_count = amd_catalogue(kernel, amd_ids)
    intel_count = len(intel_devices)
    amd_count = len(amd_devices)
    # A healthy AMD table must not hide an empty Intel parse (or vice versa).
    if intel_count < 100 or amd_count < 100 or kernel_count < 100 or libdrm_count < 100:
        raise ValueError(
            "Pinned graphics table format changed; review each vendor parser. "
            f"Intel={intel_count}, AMD={amd_count}, kernel={kernel_count}, libdrm={libdrm_count}"
        )
    return {
        "devices": intel_devices | amd_devices,
        "unsupported": intel_unsupported | amd_unsupported,
    }


if __name__ == "__main__":
    result = catalogue(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    result["stack"] = json.loads(Path(sys.argv[4]).read_text())
    print(json.dumps(result, sort_keys=True))
