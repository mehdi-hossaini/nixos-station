# Install the workstation

You need an x86-64 machine, a NixOS 26.05 live USB booted in **UEFI mode**
with Secure Boot disabled, internet access, this repository in a writable folder,
and a target disk of at least 32 GiB. The live
environment needs enough free Nix-store space for the full workstation build;
on a RAM-backed live USB, that can require substantial RAM. A failed build stops
before the target disk is erased.

## Before reinstalling

If this workstation repository already manages your installed system, these
terminal improvements can be applied with the normal build and boot workflow;
a fresh installation is optional. See [daily use](desktop.md).

For a fresh installation, copy important data and recovery material to a separate
device or remote backup and verify that you can read it back. The installer
reformats the target disk, including its existing persistent directories and
snapshots. Boot the preview VM to learn the shortcuts before erasing the target.

## One command

Switch to a local text console with **Ctrl+Alt+F2**, log in, then run from this
repository. The normal and resume flows require a text console so the installer
can control the keyboard layout used for passwords. Graphical terminals and SSH
can run previews and settings-only mode.

```sh
sudo bash scripts/install.sh
```

1. Choose your target disk with **arrow keys and Enter**. Model, size, device and
   serial identify it; the full stable disk ID also appears before erasure.
   Mounted disks, active swap and storage mappers are excluded.
2. Review preferences on one screen. **Press Enter to keep the defaults**, or
   select a field to edit. Type to search timezone and keyboard choices by name.
   The **Optional apps** checklist uses **Space to toggle** and Enter to save.
   Ctrl+C cancels the installer.
   **Containers (Podman)** runs isolated application and
   development environments. **Rich file previews** adds media/PDF thumbnails
   in Yazi. **Graphical network controls** adds a tray menu for Wi-Fi connections
   and opens a graphical connection editor when clicking the bar's network label.
   Super+N still opens the terminal network controls. **Obtain** installs apps
   from public GitHub releases using a CLI; it does not add apps automatically.
   All four extras default to disabled on a fresh install; saved choices are kept
   when rerunning the installer. Only custom usernames
   and computer names need free-text entry. CPU selection is automatic;
   Bluetooth defaults come from live hardware. **Graphics: Automatic** selects
   the appropriate drivers, including PRIME render offload on supported hybrids.
   No knowledge of driver names or installed drivers is required.
   The desktop is always **Niri — terminal-first**, with a maximized Foot
   terminal at login and graphical apps, including Firefox through Super+B.
   Accepting this screen does not erase anything; the separate disk confirmation
   still follows the successful build and keyboard test.
3. The installer checks architecture, CPU, GPU, firmware and storage support.
   It applies the chosen keyboard layout and asks you to type a visible sample.
   **Use the sample text, never a password, in that typing test.**
   Non-US layouts include a US fallback; **Alt+Shift** switches groups on the
   live console, at disk unlock/login, and in Niri. If Latin letters are unavailable,
   switch to US for the sample and passwords. Each boot starts in the selected
   layout, so use the same group again before entering those passwords.
4. Wait for the system build and GPU driver check. Progress indicators identify
   the work in progress; failures display their output. Review the selected disk
   and type **ERASE** to confirm. You never need to type its long NVMe ID.
5. Choose a disk encryption passphrase, verify it again under the selected layout,
   and choose a separate login password when prompted.

The installer formats the disk, sets up persistence and recovery keys, copies
your configuration, and installs the system and bootloader. It finishes with
instructions for saving the recovery key and rebooting. It does not reboot for you.

To try the TUI without root or a live USB, run `bash scripts/install.sh --demo`.
It uses a fictional disk and never reads real disk inventories, saves settings,
changes the keyboard, builds a workstation, or formats anything. Preparing its
installer dependencies may download packages. Use `--plain` for numbered text
prompts or `--verbose` to see live Nix output instead of progress indicators.
The TUI uses Gum only in the installer environment; it is not installed on the
workstation. Actual download and compilation time still depends on the connection,
cache availability and machine.
Input widths and menu heights adapt to terminal size; terminals smaller than
40 columns or 18 rows use numbered text prompts automatically.

**The chosen disk is completely erased.** The wizard rechecks its identity and
whether it is in use immediately before running the formatter.

Your answers are saved in the local, Git-ignored `installation.json`; no passwords
are stored there. A new clone starts without this file, and the installer creates
it after you choose the target. Keep it with the live checkout to resume an
interrupted installation.
Before building, the installer captures one source snapshot, checks that its
settings match the reviewed choices, and verifies that its formatter targets
only the selected disk. Both builds, bootstrap and the installed checkout use
that snapshot. Edits to the live checkout during installation apply on the next
run; bootstrap uses the validated username rather than rereading settings.
Live-USB storage can disappear on reboot. Before erasing, save a copy on a
different device by adding `--export-settings /path/on/other-drive/installation.json`.
The destination must not already exist. To save choices without installation, run
`sudo bash scripts/install.sh --save-settings --export-settings /path/on/other-drive/installation.json`.
This mode performs hardware-policy checks but does not change the keyboard,
build the workstation, format or install anything.
Exports also work on FAT/exFAT recovery drives. Those filesystems use mount-wide
permissions; use an encrypted recovery device if you need private file access.
Older `desktop` values are ignored, including during resume; every installation
uses the terminal-first setup.
This file overrides the defaults in `settings.nix`. After installation, the
checkout lives at `~/Projects/workstation`.

## Preview or continue

Preview the questions and plan without saving settings, building the workstation
or formatting. The installer environment and flake inputs may download packages.
Graphics checks read integrity-checked metadata bundled with the release; they do
not build or download Mesa, Linux or NVIDIA source archives. A stale/missing bundle
stops installation: use a matching release, or have the maintainer regenerate and
validate its metadata. Preview does not load drivers or change the keyboard.
The final built-kernel check requires a full installation build:

```sh
sudo bash scripts/install.sh --dry-run
```

If a later step fails **after formatting completed**, keep the live session and
target mounts open, fix the reported problem, then run:

```sh
sudo bash scripts/install.sh --resume
```

Resume verifies the target disk, each encrypted Btrfs mount's filesystem UUID and
subvolume, and the EFI mount before rebuilding and continuing installation.
It never formats. If you rebooted the live USB, first unlock and remount the
existing layout using the [recovery instructions](recovery.md); do not
start a new erase operation to recover an interrupted install.
Preparation synchronizes the installed checkout with the source and choices
captured at the start of this installation attempt. A differing existing checkout
is preserved beside it as
`workstation.before-resume.TIMESTAMP`, including any custom files. Reconcile
those custom changes before making later rebuilds; bootstrap credentials remain
preserved on resume.

The wizard supports Intel/AMD graphics, supported single NVIDIA GPUs, Intel +
NVIDIA and AMD + NVIDIA hybrids, multiple Intel/AMD GPUs, and common accelerated
virtual GPUs within the [supported-hardware policy](supported-hardware.md).
It uses PCI identities directly, including when live-media graphics drivers are
missing. It checks reviewed device tables as well as the final built drivers;
a vendor match or an AMD catch-all module alias alone is never sufficient.
Older/unknown GPUs stop with a reason and supported alternatives before erasure.
There is no force-through option. VM installations require 3D acceleration;
the wizard asks you to confirm the hypervisor setting because PCI IDs cannot
prove that it is enabled.

The plan labels configuration support separately from hardware verification.
VMware/VirtualBox graphics is experimental. No level bypasses compatibility or disk
checks; a successful build does not establish physical desktop behavior. See
[hardware acceptance](hardware-testing.md) for the matrix and report template.

The resolved `graphics` object in `installation.json` records the profile,
GPU/subsystem identities, PCI addresses, PRIME choices, and pinned stack versions.
The legacy `nvidia` boolean is removed when saving the resolved configuration;
other saved overrides are preserved. Existing manually built boolean-based
configurations still evaluate as before. Resume re-detects the physical GPUs and
validates the saved object, refusing changed devices, bus IDs, policy, or pins.
For legacy resume, `nvidia=true` can migrate only to supported single NVIDIA,
and `false` to Intel/AMD or virtual graphics. It will not silently convert an old
single-GPU choice into PRIME. Review mismatches with `--dry-run` and the manual
runbook; never restart an erase operation to fix a resume mismatch.

Generic storage covers NVMe, AHCI/ATA, USB mass storage/UAS and virtio; detected
drivers must be present in the configured initrd. Secure Boot must be disabled
and its firmware state readable. Use the [manual runbook](installation-manual.md)
for separately reviewed hardware outside this scope. These checks cannot certify
acceleration, display wiring, external displays, or suspend on every model.
The live console retains the selected keyboard layout after normal/resume exit;
rerun with a different layout if the typing sample does not behave as expected.

## First-boot acceptance

- Unlock the disk, log in, and open a terminal with Super+Return.
- Confirm the Foot terminal opens automatically on
  **Code**, maximized. Open another with Super+Return and confirm it has an
  independent shell. Check that Niri tiles the windows and that closing one
  leaves the other usable. Test Super+Shift+Return and Super+B for Firefox.
- Save files in `~/Projects`, `~/Documents` and `~/Scratch`, then reboot.
  Projects and Documents must survive; Scratch contents should disappear.
- Open `workstation-help` and test Super+F1. Put a test folder in `~/Projects`,
  use `cproj` to enter it, and use Ctrl+Shift+N to open another terminal there.
  Test `y`, Neovim's Ctrl+P file picker and clipboard copy/paste with Firefox.
- Test Wi-Fi, audio, screen sharing, lock/unlock and suspend/resume.
- Back up the recovery key and disk passphrase independently. Configure remote
  backups using [the backup guide](secrets.md), and test a restore.

The VM tests cover boot and persistence. Physical hardware and the complete
interactive live-USB flow still require a target-machine acceptance test.
