# Hardware acceptance and support commitments

## Support levels

- **Configuration supported:** an arrangement covered by the resolver and Nix
  profile checks. The installer still builds and verifies the target configuration
  before erasing a disk. This level does not certify a whole computer.
- **Hardware verified:** a named machine and project revision with a reviewed
  acceptance report covering the features claimed below. A passing build, a PCI
  ID, or another machine with the same GPU does not confer this status.
- **Experimental:** an arrangement with limited configuration fixtures and no
  repeatable desktop acceptance environment. VMware/VirtualBox graphics currently
  has this level. Existing device, driver, VM acceleration and disk checks apply.

Unknown devices and excluded arrangements stop automatic installation. An unknown
device has insufficient evidence; it is not necessarily incompatible. Neither
experimental status nor a hardware report bypasses a failed preflight check.

No reviewed physical acceptance reports are recorded in this repository yet.
The installer therefore never prints a hardware-verified claim. Reports apply to
their recorded revision; upgrading does not silently renew that evidence.
Separate disposable tests now cover software-rendered greetd/Niri login and
locking, plus encrypted test-credential SFTP backup and restoration. They do not
establish hardware acceleration, physical input accessibility or recovery from
an actual independent backup.

## Bounded matrix

The baseline is x86-64 Intel/AMD, unsigned UEFI (Secure Boot disabled), the declared
single-disk LUKS/Btrfs layout, supported NVMe/AHCI/USB/virtio storage, and the Niri
desktop. Other boot/storage layouts, legacy NVIDIA branches, headless systems,
multiple NVIDIA GPUs and ambiguous PRIME arrangements are outside automatic scope.

| Arrangement | Commitment and evidence still required |
| --- | --- |
| Intel/AMD Mesa | Configuration supported for IDs admitted by the release catalogue. Maintain Intel and AMD reference machines before claiming physical coverage. |
| Single NVIDIA | Configuration supported for the release's selected driver and open-module policy. A real graphical boot is required for physical verification. |
| Intel/AMD + NVIDIA PRIME | Configuration supported for one recognized integrated GPU and one supported NVIDIA GPU. Verify each laptop's display routing, offload and suspend. |
| Multiple Intel/AMD | Configuration supported. External ports and compositor render selection require results for the actual arrangement. |
| QEMU Virtio + VirGL | Configuration supported. Current VM test proves driver-independent detection only; acceleration and desktop acceptance remain unverified. |
| VMware/VirtualBox VMSVGA | Experimental until a documented hypervisor configuration and repeatable desktop test are maintained. |

## Acceptance procedure

Run on a disposable target or with independent, verified backups. Installing still
erases the selected disk. Keep the exact tested checkout and lockfile available.

1. Run `just check` and `just build` for the candidate revision.
2. Exercise the complete live-USB installer, including preview, keyboard/password
   entry and an interrupted-install resume. Record the installation path tested.
3. Verify cold and warm boot, unlock, graphical login, accelerated rendering
   (record the renderer and ensure it is not software rendering), and X11 apps.
4. Verify lock/unlock, suspend/resume where applicable, networking, audio and
   screen sharing. Test the actual internal/external displays and hotplug paths.
5. For PRIME, verify ordinary applications and `nvidia-offload`, display routing,
   and suspend with the relevant displays connected. Record firmware/MUX mode.
6. Verify documented persistent/disposable paths after two reboots and restore a
   file from an independent backup. Record failures and untested features plainly.

Use this report template in a contribution or issue. Do not include disk serials,
passwords, credentials, or an unreviewed full hardware dump.

```text
Model / hardware revision:
CPU and GPU PCI/subsystem IDs:
Firmware version / MUX mode (if applicable):
Hypervisor version and 3D settings (if applicable):
Project Git revision / flake.lock revision:
Kernel, Mesa, NVIDIA (if used), Niri versions:
Test date and person able to reproduce failures:
Installation: fresh / resumed (include both results when tested)
Boot, login, accelerated renderer, X11:
Lock/unlock, suspend/resume:
Networking, audio, screen sharing:
Displays, ports, hotplug, PRIME offload:
Persistence and independent restore:
Untested / not applicable / failed features:
Relevant sanitized logs and reproduction steps:
```

## Release policy

Fast checks run on every change; full source/profile/VM checks remain required in
CI and before a release. Keep disk-safety regressions in the fast suite. GPU, kernel,
firmware or desktop changes require acceptance on the affected reference machines
to renew their verification. Until that is done, retain the dated report and label
the new release as physically unverified for those machines.

New arrangements need configuration tests, a documented scope, and a maintainer
or contributor able to repeat the relevant acceptance tests. One passing machine
does not certify an entire GPU family. Keep unsupported features explicit instead
of adding untested fallbacks or silently expanding the support promise.
