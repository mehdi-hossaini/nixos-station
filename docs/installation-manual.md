# Manual installation on a new target

Most installations should use the [guided installer](installation.md). This
runbook is the lower-level alternative for custom hardware and recovery. If you
used the wizard previously, its `installation.json` overrides `settings.nix`;
edit that file or reset it to `{}` before changing defaults manually. The wizard
saves a resolved `graphics` object, which takes precedence over the legacy
`nvidia` boolean. See [supported hardware](supported-hardware.md) before changing
driver branches: a module match alone does not establish Niri compatibility.

This runbook is for a NixOS 26.05 UEFI live installer. The formatting step erases
the selected target disk. These steps were not executed on the development host.

1. Clone this repository to the installer. Open a root shell with `sudo -i` and
   change into the checkout. Enable flakes in the installer shell if necessary:
   `export NIX_CONFIG='experimental-features = nix-command flakes'`.
2. Set installation overrides in the attribute set in `settings.nix`, or create
   a local `installation.json` containing a JSON object. The JSON file is ignored
   by Git and is not restored by a new clone. Select an actual
   `/dev/disk/by-id/...` disk, username and CPU.
   `lib/default-settings.nix` holds reusable defaults and does not need editing.
   Niri always starts a Foot terminal; no desktop choice is needed. Older
   `desktop` overrides are ignored. See [daily use](desktop.md#terminal-desktop).
   Review `hosts/workstation/hardware.nix` against target hardware documentation. Add required drivers there. The generic profile
   deliberately does not inspect any pre-existing system configuration.
3. Run `bash scripts/preflight.sh`; it requires a whole-disk by-id target. Verify
   the printed disk identity and size. Verify you booted in UEFI mode and that
   the target is unmounted. Disconnect unrelated removable drives when practical.
4. Run `just check` on a KVM-capable builder. Capture one source snapshot for
   both builds and preparation; keep it until installation is complete:

   ```sh
   installation_checkout=$PWD
   installation_plan=$(mktemp -d /run/workstation-plan.XXXXXXXX)
   bash scripts/with-local-flake.sh --snapshot-only "$installation_plan/source"
   installation_user=$(nix eval --raw --file "$installation_plan/source/settings.nix" userName)
   nix build "path:$installation_plan/source#nixosConfigurations.workstation.config.system.build.toplevel" -o result-system --no-update-lock-file
   nix build "path:$installation_plan/source#nixosConfigurations.workstation.config.system.build.diskoScript" -o result-disko --no-update-lock-file
   bash scripts/install.sh --keyboard-test
   ```

   Run the keyboard test on a local text console (Ctrl+Alt+F2). It applies the
   exact compiled map used by the target login console and initrd. Type the
   visible sample, never a password, and keep that map loaded for the following
   password prompts. The selected layout may differ from the live USB's map.
   Non-US choices include a US fallback; Alt+Shift switches groups on both the
   console and desktop. For a password entered in the US group, switch to that
   group again at disk unlock/login; each boot starts in the selected layout.

5. Only after reviewing the selected disk, execute `./result-disko`. This is the
   destructive format-and-mount step. Enter the disk encryption passphrase when
   prompted. No keyfile is embedded in the boot image.
   Verify the passphrase again with the target map before preparing credentials:

   ```sh
   cryptsetup open --test-passphrase --tries 3 /dev/disk/by-partlabel/disk-system-encrypted
   ```

   If verification fails, resolve the layout/passphrase mismatch before rebooting.
6. Initialize the empty reset template, identity marker, login hash and age key:

   ```sh
   nix develop --no-update-lock-file "path:$installation_plan/source#installer" -c bash "$installation_plan/source/scripts/prepare-install.sh" "$installation_user" "$installation_checkout"
   ```

   The script verifies `/mnt`, `/mnt/nix`, `/mnt/persist`, `/mnt/projects` and
   `/mnt/local` are the expected subvolumes of the encrypted filesystem. It
   prompts twice for the new user's password and stores only its hash. It also
   copies this checkout into the new user's persistent Projects directory.
7. Independently back up the generated age identity, disk recovery material and
   repository. Do not commit plaintext keys or password hashes. The age identity
   is `/mnt/persist/keys/sops/age.key`. Add an independent recovery recipient when
   configuring encrypted application secrets.
8. Install the built system:

   ```sh
   nixos-install --no-root-passwd --system ./result-system
   ```

9. Reboot, unlock the disk, and log in. The root account is locked; the chosen
   user has password-authenticated sudo. Root-reset refusal requires the live
   installer for recovery; see `recovery.md`.

## First-boot acceptance

- Confirm `findmnt / /nix /persist /projects /local` using separate invocations
  if your findmnt version expects only one target.
- Create a file in `~/Projects`, a file in `~/Documents`, and a file in
  `~/Scratch`. Reboot: only the scratch file should disappear from the live root.
- Confirm browser profile, shell history, credentials and machine identity
  survive another reboot. Logs from previous boots should be available.
- Test lock/unlock, suspend/resume, audio, browser screen sharing, portal file
  chooser, Polkit prompts, and at least one X11 application.
- Warm a project environment, disconnect the network, and reopen it.
- Configure backups and complete an independent restore drill.

Use suspend, not hibernation. The root reset path must be redesigned and tested
with resume ordering before enabling any disk-backed hibernation.
