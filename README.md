# Niri developer workstation

A NixOS 26.05 workstation with Niri, Foot, Home Manager, encrypted Btrfs,
an ephemeral root, and explicit persistence. Project SDKs stay in development
shells. Containers, rich file previews, graphical networking and Obtain are
independent opt-ins, disabled by default.

The design favors [small tools with clear responsibilities](docs/philosophy.md).

## Install

Use an x86_64 machine, a NixOS 26.05 live USB booted in UEFI mode, Secure Boot
disabled, internet access and a target disk of at least 32 GiB. Review the
[supported graphics policy](docs/supported-hardware.md) and save independent
backups before proceeding. The live Nix store needs space for a complete build.

From a local text console (Ctrl+Alt+F2) on the live USB:

```sh
git clone https://github.com/mehdi-hossaini/nixos-station.git workstation
cd workstation
sudo bash scripts/install.sh
```

**Installation erases the selected disk, including its persistent data and
snapshots.** The installer validates hardware and keyboard input, freezes the
reviewed configuration, builds first, and asks you to type `ERASE` before
formatting. It prepares credentials and persistence, installs the system, and
leaves rebooting to you.

Read the [installation guide](docs/installation.md) for prerequisites, recovery
material, settings export and resume. Saved choices live in the ignored local
`installation.json`; passwords do not. Review [persistence](docs/persistence.md)
before adding applications and keep [recovery](docs/recovery.md) independently.
Do not activate this disk layout on an existing installation.

## Try safely

Try the installer with a fictional disk, without root:

```sh
bash scripts/install.sh --demo
```

On an x86_64 Linux host with KVM and a Wayland session, preview the desktop:

```sh
nix run .#preview-terminal --no-update-lock-file
```

The VM uses its own disk and software graphics; its username and password are
`preview`. See the [desktop guide](docs/desktop.md#interactive-vm-preview) for
storage, shortcuts and shutdown. The preview does not test the encrypted
installation layout or physical hardware.

## Validate changes

Enter the pinned development environment:

```sh
nix develop
just check-fast
```

| Command | Purpose |
| --- | --- |
| `just fmt` | Format Nix, Python and shell sources |
| `just check-python` | Python lint and installer/graphics regressions |
| `just check-fast` | Formatting, lint, documentation links and focused checks |
| `just check` | Every flake check, including metadata regeneration and disposable VMs |
| `just build` | Build the locally selected workstation without activation |

Full checks require a Nix builder with KVM. Checks use isolated fixture settings;
local recipes include recognized new source files without staging. Full checks
build individual outputs separately, covering aggregate suites through their
declared members, to reduce evaluation memory. CI reuses the same
runner's Nix store for fast checks, full checks and the fixture system build.

A fresh clone can build the CI fixture without choosing a physical disk:

```sh
nix build .#nixosConfigurations.workstation-test.config.system.build.toplevel --no-link --no-update-lock-file
```

`just build` requires a local disk choice. Builds and checks do not activate the
host or format physical disks. Physical login, GPU acceleration, suspend and
independent restores need [hardware acceptance](docs/hardware-testing.md).

## Guides

- [Desktop and daily maintenance](docs/desktop.md)
- [Project environments and repository development](docs/development.md)
- [Validation coverage and boundaries](docs/validation.md)
- [Manual installation](docs/installation-manual.md)
- [Encrypted secrets and backups](docs/secrets.md)
- [Engineering rules](docs/engineering.md)
- [Security reporting](SECURITY.md)

Backups remain disabled until their destination, encrypted credentials and SSH
host key are configured. Local snapshots do not protect against disk failure.
Hibernation is disabled. Hardware outside the automatic policy requires a
reviewed manual configuration.

## Licensing

Project author: [mehdi-hossaini](https://github.com/mehdi-hossaini).
No project license file is currently declared in this checkout.
