# Validation boundaries

This guide describes the checks in the current initial snapshot. Earlier
construction reports described different working trees and removed prototypes;
they are retained in the external history recovery backup rather than used as
validation of this snapshot. Upstream dependency revisions in `flake.lock` and
hardware documentation remain valid pins, independent of this repository's
history.

The shared checks use isolated fixture settings, not local identity, hardware
choices, credentials or backup settings. Destructive storage tests use disposable
VM disk images. Building and testing do not activate the development host or
format a physical disk.

## Reproduce validation

Enter the pinned development environment with `nix develop`, then run:

| Command | Coverage |
| --- | --- |
| `just check-fast` | Formatting, lint, documentation and focused regression checks |
| `just check-python` | Python lint and installer/graphics regressions |
| `just check` | All flake checks, including graphics regeneration and disposable VMs |
| `just build` | Locally selected workstation build, without activation |

For the shared host fixture, run:

```sh
nix build .#nixosConfigurations.workstation-test.config.system.build.toplevel --no-link --no-update-lock-file --max-jobs 2 --cores 4 -L
```

Full VM validation needs a Nix builder with KVM. CI runs the fast gate, verifies
KVM, runs all checks, then builds the host fixture on the same runner. Consult
the GitHub Actions run for the exact commit being reviewed; a successful run for
an earlier commit does not validate a later snapshot. Record commands, results
and environment limitations with each change.

Local recipes include recognized non-ignored new source files without staging
them. Installer regressions cover edits during builds, mismatched formatter
targets, frozen bootstrap inputs, and copying the reviewed source. The
[review coverage notes](review-fixes.md) explain the related safety guarantees.

## Automated coverage

`just check-fast` runs Nix/shell/Python formatting and lint, GitHub Actions workflow
validation, Niri validation, installer orchestration,
pure graphics policy and metadata-integrity tests, archived-root pruning unit
tests, compiled Russian/US console-map validation and preview/palette consistency.
Source-snapshot tests exercise the real host wrapper with an isolated Git
checkout, including new untracked files and exclusion of ignored credentials.
These checks use the prepared
release JSON and do not depend on source archives, full profile closures or VMs.
Metadata tests cover missing/corrupt files, stale pins/source identities/generator,
catalogue/manifest disagreement, driver-independent reads without builds, and
independent Intel/kernel/libdrm parser failures. Support labels do not imply
physical verification; unknown devices still stop automatic installation.

`just check` discovers and builds individual flake checks with separate
evaluators, covering aggregate suites through their declared members, using one
captured source and stopping at the first failure. CI uses the same
runner against its Git checkout. `nix flake check -L` also evaluates and runs
these checks, but retains all their evaluations in one process.

The checks cover:

- Nix/Python/shell formatting, statix, deadnix, shellcheck, Ruff, actionlint and
  Git hook checks. `just check-python` provides a focused Python lint/regression
  subset using the same pinned dependencies.
- Relative Markdown file links and heading anchors, including moved desktop
  documentation. The guard runs offline and does not probe external websites.
- Full-check discovery, failure propagation and snapshot consistency through the
  real shell runner with a stubbed Nix command. Tests change live files during
  checks and verify that every output uses the original captured source.
- Installer tests with synthetic disk inventories and mocked commands: mounted,
  swap-active and mapped disks are rejected; changed identity and incorrect
  confirmation prevent formatting; hardware is rechecked after the build and
  erase confirmation; installer builds use a fixed local budget and the mounted
  target is rechecked after credential setup; builds precede formatting; preview has no
  mutations; resume never formats. Hardware fixtures cover CPU/GPU detection,
  Secure Boot state, NVIDIA support/legacy metadata, storage drivers and built
  GPU aliases. Keyboard tests cover text-console gating, keymap mismatch and
  failure ordering before formatting.
- Niri's own configuration validator against the rendered keyboard workflow,
  including a non-Latin layout with a switchable US group.
- The terminal desktop, including PRIME graphics and legacy desktop settings,
  is evaluated with fixture settings. Generated Niri configs are validated with
  a non-US keyboard layout. Assertions check startup/terminal shortcuts, PRIME
  render-device preservation, smart completion and availability of GUI apps,
  portals and locking. Tmux, Herdr and Codex packages, launchers and persistence
  mounts are absent. Installer tests check the single desktop plan, absence of
  a desktop selector and compatibility with older saved desktop values.
- Terminal workflow checks exercise real fzf project selection and cancellation,
  including directory names containing whitespace, quotes, Unicode and newlines.
  They validate Foot's generated config, encoded shell directory reporting,
  editor search commands, a real Nix language-server completion request, and
  opening the offline guide without losing unsaved editor content.
- Optional-tool checks exercise the minimal default, rootless containers,
  rich file previews, graphical networking and Obtain independently and together.
  They check container ID ranges/storage, excluded default packages, disabled
  editor providers, the applet service and bar action, Obtain's CLI/PATH/state
  mounts, and the actual Yazi closure with and without media helpers. The boot
  test also checks Obtain's CLI and retained state across a power cycle.
- Regeneration of the prepared metadata from pinned Mesa/Linux/libdrm and NVIDIA
  sources, requiring an exact match with the checked-in release files and manifest.
- Graphics policy tests against pinned device tables: single Intel/AMD and
  NVIDIA, Intel/AMD + NVIDIA PRIME, multiple Intel/AMD GPUs, virtual graphics,
  absent live drivers, legacy/unknown/compute devices, hexadecimal PCI conversion
  including domains, legacy settings migration, saved-plan mismatch rejection,
  manual override rejection and failures before any settings/keyboard/disk change.
- A separate graphics-integration check verifies the resolver against the five
  built profiles; fast policy tests do not depend on those closures.
- Five full NixOS graphics closures (Mesa, single NVIDIA, Intel PRIME, AMD PRIME,
  virtual), with assertions on the generated options and Niri validation of each
  generated configuration. Actual built-kernel aliases were also checked for
  representative Intel, AMD, NVIDIA and Virtio IDs in each matching profile.
- A disposable Virtio graphics VM that blacklists the graphics module, detects
  the real guest PCI GPU without it, resolves/saves a plan, validates resume
  identity, and resolves the built module alias without loading the driver.
  This tests detection/configuration, **not accelerated rendering**. VMware and
  VirtualBox coverage is fixture/configuration coverage only.
- A LUKS/Btrfs reset test: required persistent tiers survive; ephemeral state is
  archived and removed from the new root; interrupted reset states recover;
  missing bootstrap material or an incorrect layout marker prevents reset.
- A session-lifecycle VM derives its simulated login unit's dependencies and
  activation guard from the real greetd unit. Home-activation success/failure
  restarts preserve the running login PID; failed activation blocks new login
  startup, and recovery permits it. The VM also checks physical Russian/US
  console group switching and concurrent evaluations sharing a finite slice.
- A desktop-session VM uses the real greetd, Home Manager and Niri modules with
  Cage/pixman software rendering. It logs in through tuigreet, verifies the
  startup terminal, preserves Niri through home activation, and exercises a
  rejected lock password followed by successful unlock. It does not certify
  physical graphics acceleration or suspend.
- A backup-restore VM generates disposable encrypted SOPS credentials, decrypts
  them at boot, verifies strict SFTP host-key rejection and recovery, runs the
  production backup/prune/check unit, and restores project and state sentinels.
  It verifies excluded dependencies and a full repository data check. Actual
  remote credentials and independent disaster recovery still need acceptance.
- A Disko/UEFI integration test: install the actual disk layout, boot the host
  modules, run reset exactly once per boot, activate Home Manager, then power
  down and boot the same disk again. Machine identity, Projects and Documents
  must survive; Scratch contents must disappear. Snapshot and old-root pruning
  services must retain 24 snapshots per tier and three archived roots after
  an overfull fixture. Real credential preparation verifies a whitespace-bearing
  password, valid age identity, private permissions, rerun preservation and
  recovery after generator failures. A further archived-root fixture contains
  33 nested subvolumes and 1,000 ordinary directories: each pruning run deletes
  at most 16 subvolumes, resumes partial cleanup, and preserves the live root.

The UEFI harness uses a public test-only passphrase with German-layout Y/Z
characters. It checks physical key input on the live console and at the initrd
unlock prompt on both boots, without an embedded unlock key. It disables greetd,
shares the builder's store through a writable overlay, and registers its closure in the
guest. These accommodations belong only to the test configuration. The normal
host has no embedded initrd key and uses its persistent local Nix store.
The complete wizard prompts and graphical login are not exercised by the UEFI
test. Credential preparation runs the production age-key generator. The wizard's
orchestration is tested separately with
mocked commands;
a complete interactive installation from live media still needs an end-to-end
trial on a disposable target.

Build the complete host separately with `just build`. Building does not activate
it. The package closure includes the graphical stack, even though the storage
VM does not exercise a graphical login.

## Still requires target hardware and credentials

Review username, disk by-id, CPU/GPU and keyboard in local `installation.json`
or `settings.nix`. Test disk
passphrase entry, graphical login, lock/unlock, portals/screen sharing, audio,
X11 compatibility, networking, and suspend/resume on the actual workstation.
See [supported hardware](supported-hardware.md) for the exact automatic policy.
No physical NVIDIA/PRIME or Intel/AMD graphical boot was performed; MUX routing,
external ports, acceleration, GPU power management and suspend remain unverified.

Backups stay disabled until a repository and encrypted credentials are supplied.
The disposable backup VM does not verify a real remote destination or an
independent restore. Successful evaluation is not a substitute for a restore drill. Local Btrfs snapshots do not
protect against disk failure.

Use the [acceptance procedure and report template](hardware-testing.md) to record
physical evidence by machine and revision. There are no reviewed physical reports
in the repository yet; VM detection is not accelerated desktop certification.
