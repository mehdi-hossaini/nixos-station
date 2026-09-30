"""Pure graphics policy. No running driver, shell command or mutable host state."""

import re

SCHEMA = 1
IDENTITY = ("address", "vendor", "device", "subvendor", "subdevice")
VIRTUAL = {
    (0x1AF4, 0x1050): ("Virtio GPU (VirGL)", "virtio_gpu"),
    (0x15AD, 0x0405): ("VMware SVGA / VirtualBox VMSVGA", "vmwgfx"),
    (0x15AD, 0x0406): ("VMware SVGA 3", "vmwgfx"),
}


def pci_bus_id(address):
    match = re.fullmatch(r"([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", address)
    if not match:
        raise ValueError(f"Invalid PCI address: {address}")
    domain, bus, slot, function = (int(part, 16) for part in match.groups())
    if slot > 31:
        raise ValueError(f"Invalid PCI slot: {address}")
    return f"PCI:{bus}@{domain}:{slot}:{function}"


def nvidia_chip(gpu, metadata):
    matches = [
        chip
        for chip in metadata["chips"]
        if int(chip["devid"], 16) == gpu["device"]
        and all(
            key not in chip or int(chip[key], 16) == gpu[field]
            for key, field in [("subdevid", "subdevice"), ("subvendorid", "subvendor")]
        )
    ]
    # Subsystem-specific entries take precedence over generic device entries.
    return max(matches, key=lambda c: ("subdevid" in c) + ("subvendorid" in c), default=None)


def resolve_device(gpu, support, nvidia):
    pci_bus_id(gpu["address"])
    identity = {key: gpu[key] for key in IDENTITY}
    vendor, device = gpu["vendor"], gpu["device"]
    key = f"{vendor:04x}:{device:04x}"
    if vendor == 0x10DE:
        chip = nvidia_chip(gpu, nvidia)
        if not chip or chip.get("legacybranch") or "kernelopen" not in chip.get("features", []):
            branch = chip.get("legacybranch") if chip else None
            reason = (
                f"requires legacy NVIDIA {branch}"
                if branch
                else "is absent from the pinned open-driver support list"
            )
            raise ValueError(
                f"NVIDIA {key} {chip['name'] if chip else ''} {reason}. "
                f"Pinned driver: {support['stack']['nvidia']}. "
                "Niri needs GBM and DRM modesetting; NVIDIA 470 and older lack GBM. "
                "Pre-Turing GPUs cannot use NVIDIA open kernel modules. "
                "Use a supported GPU, or disable the discrete GPU in firmware and rerun with a supported integrated GPU. "
                "A different driver/desktop stack requires separate manual validation; it is not an automatic fallback."
            )
        if not any(
            label in chip.get("name", "") for label in ("GeForce", "Quadro", "TITAN", "RTX")
        ):
            raise ValueError(
                f"{chip.get('name', key)} is not a reviewed NVIDIA desktop/display GPU. "
                "Driver support also includes compute-only devices; use a supported display GPU."
            )
        return identity | {
            "name": chip.get("name", "NVIDIA GPU"),
            "driver": "nvidia",
            "integrated": False,
        }
    if (vendor, device) in VIRTUAL:
        name, driver = VIRTUAL[vendor, device]
        return identity | {"name": name, "driver": driver, "integrated": False}
    if key in support["devices"]:
        return identity | support["devices"][key]
    limitation = support.get("unsupported", {}).get(key)
    limitation = (
        ("Outside automatic policy: " + limitation)
        if limitation
        else "Unrecognized device: no compatibility evidence in this release; this is not proof of incompatibility"
    )
    raise ValueError(
        f"GPU {key} at {gpu['address']}: {limitation}. "
        "A vendor/module match does not establish Niri compatibility. "
        "Use a supported GPU or a separately validated manual profile. "
        "For a VM, select Virtio with VirGL or VMware/VMSVGA with 3D acceleration."
    )


def graphics_profile(devices):
    nv = [g for g in devices if g["driver"] == "nvidia"]
    vm = [g for g in devices if g["driver"] in ("virtio_gpu", "vmwgfx")]
    prime = None
    if vm:
        if len(devices) != 1:
            raise ValueError(
                "Mixed virtual/physical or multiple virtual GPUs need a reviewed host profile."
            )
        profile = "virtual"
    elif nv:
        if len(nv) != 1:
            raise ValueError(
                "Multiple NVIDIA GPUs need a reviewed host profile; none will be ignored."
            )
        if len(devices) == 1:
            profile = "nvidia"
        else:
            integrated = [g for g in devices if g["integrated"]]
            if len(devices) != 2 or len(integrated) != 1:
                raise ValueError(
                    "Automatic PRIME requires exactly one supported Intel/AMD integrated GPU and one NVIDIA GPU."
                )
            igpu = integrated[0]
            profile = "prime"
            prime = {
                "integratedVendor": "intel" if igpu["vendor"] == 0x8086 else "amd",
                "integratedBusId": pci_bus_id(igpu["address"]),
                "nvidiaBusId": pci_bus_id(nv[0]["address"]),
                "renderDevice": f"/dev/dri/by-path/pci-{igpu['address']}-render",
            }
    else:
        profile = "mesa"
    return profile, prime


def resolve_graphics(gpus, support, nvidia=None):
    """Resolve only reviewed families, not a vendor or a broad kernel alias."""
    if not gpus:
        raise ValueError(
            "No PCI display GPU detected. Headless/non-PCI graphics need a reviewed host profile."
        )
    if len({g["address"] for g in gpus}) != len(gpus):
        raise ValueError("Duplicate GPU PCI addresses.")
    metadata = nvidia if nvidia is not None else {"chips": []}
    devices = [
        resolve_device(gpu, support, metadata) for gpu in sorted(gpus, key=lambda g: g["address"])
    ]
    profile, prime = graphics_profile(devices)
    return {
        "schema": SCHEMA,
        "mode": "automatic",
        "profile": profile,
        "devices": devices,
        "prime": prime,
        "stack": support["stack"],
    }


def validate_saved(settings, resolved):
    """Never silently reselect on resume, including after a pin or topology change."""
    saved = settings.get("graphics")
    if saved is not None:
        if saved != resolved:
            raise ValueError(
                "Saved graphics configuration differs from this hardware, policy or pinned stack. "
                "Resume stopped. Review the differences with --dry-run; do not restart an erase operation."
            )
        return settings
    legacy = settings.get("nvidia", False)
    if type(legacy) is not bool:
        raise ValueError("Legacy nvidia setting must be a boolean.")
    if (legacy and resolved["profile"] != "nvidia") or (
        not legacy and resolved["profile"] not in ("mesa", "virtual")
    ):
        raise ValueError(
            "Legacy nvidia setting does not describe the detected graphics arrangement. "
            "Resume needs a reviewed graphics migration; no disk will be formatted."
        )
    # Legacy settings have no device inventory. Preserve their driver intent.
    return settings | {"graphics": resolved}


def describe(config):
    lines = ["Graphics: Automatic"]
    for gpu in config["devices"]:
        lines.append(
            f"  {gpu['name']} — {gpu['vendor']:04x}:{gpu['device']:04x} at {gpu['address']}"
        )
    descriptions = {
        "mesa": "Intel/AMD graphics using the built-in kernel drivers and Mesa; all detected GPUs remain available.",
        "nvidia": "NVIDIA open kernel driver with GBM and DRM modesetting for Niri.",
        "prime": "Intel/AMD renders the desktop; NVIDIA is available with nvidia-offload <application>.",
        "virtual": "Virtual graphics using Mesa. Enable 3D acceleration in the VM settings (VirGL for Virtio).",
    }
    lines.append("  " + descriptions[config["profile"]])
    experimental = any(g["driver"] == "vmwgfx" for g in config["devices"])
    level = (
        "Experimental (configuration fixtures only)"
        if experimental
        else "Configuration supported by project policy"
    )
    lines.append("  Support level: " + level + ".")
    lines.append("  Hardware verification: not established by detection or a successful build.")
    lines.append("  See docs/hardware-testing.md for model-specific acceptance and reports.")
    if config["prime"]:
        prime = config["prime"]
        lines.append(
            f"  PRIME render offload: integrated {prime['integratedBusId']}, NVIDIA {prime['nvidiaBusId']}."
        )
        lines.append(
            "  External ports may be wired to NVIDIA; display routing, performance and suspend need hardware testing."
        )
    lines.append(
        "  Device-table checks cannot certify acceleration or display wiring; first-boot testing is required."
    )
    return "\n".join(lines)
