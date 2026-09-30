# Supported graphics and hardware boundaries

Automatic graphics uses physical PCI display devices from sysfs, including VGA,
3D and other display subclasses. It does not consult `nvidia-smi`, the current
driver binding, loaded modules, `/dev/dri`, or an existing OS configuration.
CPU, unsigned UEFI boot, storage and disk-identity checks remain separate.

**Configuration supported**, **hardware verified**, and **experimental** are
different claims. The installer displays the profile's support level and does not
infer physical verification from detection or a successful build. See the bounded
[support matrix and acceptance reports](hardware-testing.md). VMware/VirtualBox
graphics is experimental; its existing compatibility checks remain mandatory.

## Pinned compatibility baseline

The researched baseline is nixpkgs `f5c082a40f7571c266e74e80ae2e68aadd8a9fc7`
(NixOS 26.05), Linux **6.18.53**, NVIDIA **595.71.05**, Niri **26.04**.
The metadata builder records the actual kernel, Mesa, NVIDIA, Niri and nixpkgs
versions. Release JSON is committed in `hardware/graphics` with source identities
and integrity hashes. Updating pins requires `just graphics-update`, reviewing
added/removed/reclassified devices and the NVIDIA manifest, then `just check`.
The installer validates the bundled data against the evaluated stack and generator
before using it. Stale or incomplete data stops installation without source builds.
Saved installations are not silently re-resolved on resume after such an update.

| Arrangement | Automatic choice and limits |
| --- | --- |
| Intel integrated or discrete | Mesa Iris, using i915/xe from the built kernel. Reviewed Broadwell through Lunar Lake/Arrow Lake families and DG1, DG2, Battlemage; exact IDs must occur in pinned Iris tables. Experimental/force-probe, server and unreviewed newer families are excluded. |
| AMD integrated or discrete | Mesa with amdgpu. Exact supported desktop IDs come from the pinned kernel's named chip table and libdrm's Radeon table for IP-discovery devices. SI/CIK and compute/displayless families are excluded. |
| Multiple Intel/AMD GPUs | Keep all supported devices available; Niri chooses its render/output devices. No arbitrary GPU is discarded. |
| Single NVIDIA | Exact device/subsystem entry must support open modules in the pinned driver's manifest, have no legacy branch, and be a reviewed GeForce/Quadro/TITAN/RTX display product. Enable open modules, GBM userspace and DRM modesetting. |
| Intel + NVIDIA / AMD + NVIDIA | Exactly one recognized integrated GPU plus one supported NVIDIA device. PRIME render offload with decimal PCI bus/domain/slot/function IDs. Niri explicitly renders on the integrated GPU's stable `/dev/dri/by-path` render node; `nvidia-offload` selects NVIDIA for applications. |
| Virtio GPU (`1af4:1050`) | Mesa/VirGL and virtio_gpu; **enable 3D/VirGL in the hypervisor**. The PCI transport is not confused with the virtio child graphics module. |
| VMware SVGA 2/3 (`15ad:0405`, `15ad:0406`), including VirtualBox VMSVGA | Mesa and vmwgfx; **enable 3D acceleration**, subject to the hypervisor's implementation. This is conditional configuration support, not a certified graphical boot. |

AMD IP-discovery devices can omit integrated/discrete flags from the kernel's
PCI table. A small explicit APU-ID list supplements that table for PRIME. An AMD
device with unclassified integration status can use the single/Mesa profile,
but does not become the integrated PRIME device by guessing from its vendor.

The installer asks VM users to confirm their 3D setting; it cannot establish
hypervisor acceleration from a PCI ID. Preflight does not exercise a graphical
session or change driver bindings. It validates every selected driver against
the built kernel before formatting, and checks the evaluated Nix configuration
against the saved plan, including modesetting, PRIME and the Niri render device.

## Unsupported cases and useful alternatives

- **Pre-Turing NVIDIA:** open kernel modules cannot drive these GPUs. Driver
  595's proprietary flavor does not restore support for Maxwell/Pascal either.
  The pinned manifest reports the required legacy branch when known. NVIDIA
  470 and earlier also lack the GBM path Niri needs. Maxwell/Pascal's 580 branch
  is a different stack requiring independent review; it is not automatically
  selected. Nouveau/NVK is not an automatic fallback in this installer.
- **Older Intel (before Broadwell) and AMD SI/CIK or radeon-era devices:** outside
  the reviewed policy. Some can run Niri with separately validated drivers; this
  is a policy boundary, not a claim that all older devices are incompatible.
  A kernel alias alone cannot prove rendering support or select the correct
  radeon/amdgpu policy.
- **Unknown/new devices, headless systems, compute-only GPUs, multiple NVIDIA,
  mixed physical/virtual GPUs, or ambiguous multi-GPU PRIME:** stop for review.
  Use a supported display GPU, or use firmware to disable an unsupported
  discrete device and rerun with a supported integrated GPU. Firmware changes
  can disable ports wired to that device.
- **QXL, Bochs/standard VGA, VBoxVGA and other unreviewed virtual displays:**
  not automatically accepted for this accelerated Niri desktop. Switch the VM
  to Virtio + VirGL or supported VMware/VMSVGA + 3D, or use a separately validated
  desktop profile. No software-rendering override is silently applied.

A manual module cannot make an incompatible driver compatible. Use the manual
runbook only with an independently validated stack; there is no wizard bypass.

## Why these checks are separate

`scripts/install.py` reads hardware and runs preflight/build checks.
`scripts/graphics-support.py` derives the release catalogue from immutable pinned
sources. Each vendor's parser is checked independently. `scripts/graphics_metadata.py`
prepares and verifies the release bundle; installation consumes that bundle without
fetching driver or kernel source archives. `scripts/graphics.py` is a pure resolver
and saved-settings validator.
`modules/nixos/graphics.nix` generates NixOS driver/PRIME options; Home Manager
adds the selected Niri render node. This split allows tests without host drivers.

Linux amdgpu includes catch-all display-device PCI aliases for IP discovery.
Consequently, matching amdgpu is especially **not** evidence that an arbitrary
AMD PCI ID is usable. Conversely, absent live drivers are not evidence that a
physical GPU is unsupported. Niri requires a functioning GBM/EGL rendering path
and modesetting; the pinned Niri source includes legacy KMS handling, so the
policy does not falsely require atomic KMS for every device.

Hybrid external outputs may require copies between GPUs, causing lag or extra
power use. PRIME offload does not determine laptop MUX wiring. Fine-grained
NVIDIA power management is not forced: NVIDIA documents RTD3 limitations for
the open modules. The upstream per-process Niri NVIDIA buffer-pool workaround
is installed; global NVIDIA rendering environment variables are not used.

## Sources reviewed

- [Niri getting started](https://niri-wm.github.io/niri/Getting-Started.html): GBM,
  modesetting, matching Mesa on NixOS, and VM 3D requirements. Also checked in the
  pinned 26.04 source, `docs/wiki/Getting-Started.md` and `src/backend/tty.rs`.
- [Niri NVIDIA guidance](https://niri-wm.github.io/niri/Nvidia.html): per-process
  `GLVidHeapReuseRatio`; checked against the pinned source.
- [Niri hybrid-output FAQ](https://niri-wm.github.io/niri/FAQ.html#how-to-fix-lag-on-external-monitors-connected-to-a-hybrid-gpu-laptop): render-device routing and power/performance tradeoffs.
- [NVIDIA 595 open-module documentation](https://download.nvidia.com/XFree86/Linux-x86_64/595.71.05/README/kernel_open.html): architecture support and RTD3 limits.
- [NVIDIA 495 GBM documentation](https://download.nvidia.com/XFree86/Linux-x86_64/495.44/README/gbm.html): GBM userspace requirements and DRM modesetting.
- [NVIDIA 595 supported chips](https://download.nvidia.com/XFree86/Linux-x86_64/595.71.05/README/supportedchips.html): the installer uses the machine-readable manifest from that exact driver's Nix-hashed archive, including subsystem restrictions and legacy markers.
- [Pinned NixOS NVIDIA module](https://github.com/NixOS/nixpkgs/blob/f5c082a40f7571c266e74e80ae2e68aadd8a9fc7/nixos/modules/hardware/video/nvidia.nix): PRIME options, decimal domain-aware bus IDs and offload wrapper.
- [Mesa driver documentation](https://docs.mesa3d.org/systems.html), pinned
  Mesa `include/pci_ids/iris_pci_ids.h`, libdrm `amdgpu.ids`, and Linux 6.18.53
  `drivers/gpu/drm/amd/amdgpu/amdgpu_drv.c`: exact device classifications and the
  AMD catch-all alias. Sources are fetched by their existing Nix hashes.

## Validation still needed on physical machines

No install or activation is performed on the development host. Software builds,
fixtures and disposable VMs cannot verify physical display wiring, firmware/MUX
behavior, GPU acceleration, suspend/resume, power draw, hotplug, external ports,
lock/unlock or screen sharing. Run the installation guide's first-boot checks on
each target. A supported configuration is not a guarantee that every laptop or
monitor combination is free of driver bugs.
