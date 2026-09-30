# Recovery

## Interrupted guided installation

If the formatted target is still mounted in the live session, use
`sudo bash scripts/install.sh --resume`. This does not format it again.

After a live-USB reboot, use the same checkout and local `installation.json`
answers. A new clone does not contain the file. Copy your independently exported
settings into the checkout. If preparation completed, retrieve the target copy
without needing those settings first. Use `lsblk -f` to identify the existing
LUKS partition on the intended disk; substitute its stable partition ID below:

```sh
sudo cryptsetup open --readonly /dev/disk/by-id/YOUR-DISK-part2 workstation-recovery
sudo mkdir -p /run/workstation-recovery
sudo mount -t btrfs -o ro,subvol=@projects /dev/mapper/workstation-recovery /run/workstation-recovery
ls /run/workstation-recovery
sudo install -m 0600 /run/workstation-recovery/YOUR-USER/workstation/installation.json ./installation.json
sudo umount /run/workstation-recovery
sudo cryptsetup close workstation-recovery
```

If preparation had not yet copied the checkout, recreate the same disk, user and
hardware choices with `sudo bash scripts/install.sh --save-settings`. This saves
choices without changing the target, keyboard or installing anything. Add
`--export-settings /path/on/other-drive/installation.json` to keep a recovery copy.
The export destination must be a new file on independent storage. Verify the
resolved graphics and keyboard choices against your original plan.
Review the saved disk ID, then build and run only the mount script:

```sh
bash scripts/with-local-flake.sh nix --extra-experimental-features 'nix-command flakes' build \
  .#nixosConfigurations.workstation.config.system.build.mountScript -o result-mount --no-update-lock-file
sudo ./result-mount
sudo bash scripts/install.sh --resume
```

The mount script asks for the existing disk passphrase. Do not run
`result-disko` when recovering data; that is the format-and-mount script.
If formatting itself did not complete, inspect the layout using the live
installer before deciding whether a fresh erase is appropriate.

## Bad configuration generation

Select a known-good generation in systemd-boot. This restores its software and
declarative configuration, not old database formats or application contents.

## Reset failure or accidentally omitted state

Use the NixOS live installer to unlock the encrypted partition and mount Btrfs
top-level (`subvolid=5`). The old roots are beneath `@old-roots/boot-*/root`.
Copy selected missing files to the correct persistent tier and add the matching
declaration before the next reboot. Do not replace the entire persistent tier
with an old root.

Adding `workstation.keep-root` to the boot entry skips reset for that boot. This
is useful only when `@root` exists and is usable. If power was lost after the old
root was archived, normal boot reconstructs root from the template; skipping
reset at that point would leave no root to mount.

Reset failures intentionally fail closed. The root account is locked, so keep a
live USB and disk passphrase available rather than relying on an emergency login.

## Replacement disk

1. Obtain the repository/lockfile, live installer, independent age recovery key,
   backup credentials and Restic repository password.
2. Review and change the disk by-id setting. Run the installation format step on
   the replacement disk only.
3. With the target subvolumes mounted below `/mnt`, restore `/persist` and
   `/projects` to `/mnt/persist` and `/mnt/projects`. Verify ownership, especially
   UID 1000 for the user. Restore the age identity and login hash.
4. Run the installer preparation script. It preserves existing bootstrap secrets
   and creates the reset template/marker. Do not overwrite a restored checkout
   accidentally: a differing checkout is preserved beside the new one as
   `workstation.before-resume.TIMESTAMP`. Reconcile any restored custom changes
   from that backup before later rebuilds.
5. Build the pinned system, install its bootloader/system, and reboot.
6. Verify state, credentials, development environments and backup execution.

The Nix store can normally be downloaded/rebuilt. If long-term offline recovery
is required, keep a separately exported system closure and its inputs; a lockfile
does not guarantee upstream sources or caches will remain available forever.

## Hardware acceptance

The VM tests exercise LUKS/Btrfs root-reset behavior, UEFI guest boot and
persistence across a guest power cycle. Before using this as your primary workstation, validate UEFI boot,
disk unlock, both cold and warm boot, missing-persistence failure, GPU startup,
suspend, screen locking and an independent backup restore on target hardware.
