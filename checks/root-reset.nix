{ pkgs }:
let
  reset = import ../lib/root-reset.nix { inherit pkgs; };
in
pkgs.testers.runNixOSTest {
  name = "workstation-root-reset";
  nodes.machine = _: {
    virtualisation.emptyDiskImages = [
      2048
      32768
      32768
    ];
    environment.systemPackages = [
      reset
      pkgs.btrfs-progs
      pkgs.cryptsetup
      pkgs.lvm2.bin
      pkgs.python3
    ];
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    # A real LUKS container and Btrfs filesystem on the disposable second disk.
    machine.succeed("echo vm-only-passphrase > /run/key")
    machine.succeed("cryptsetup luksFormat --batch-mode --key-file /run/key /dev/vdb")
    machine.succeed("cryptsetup open --key-file /run/key /dev/vdb testroot")
    machine.succeed("mkfs.btrfs /dev/mapper/testroot")
    machine.succeed("mkdir /top; mount /dev/mapper/testroot /top")
    for name in ["root", "root-blank", "nix", "persist", "projects", "local", "snapshots"]:
        machine.succeed(f"btrfs subvolume create /top/@{name}")
    machine.succeed("btrfs property set -ts /top/@root-blank ro true")
    machine.succeed("echo niri-workstation-v1 > /top/.workstation-layout-v1")
    machine.succeed("mkdir -p /top/@persist/bootstrap /top/@persist/keys/sops")
    machine.succeed("echo test-hash > /top/@persist/bootstrap/login-password.hash")
    machine.succeed("echo test-key > /top/@persist/keys/sops/age.key")
    for name in ["nix", "persist", "projects", "local", "snapshots"]:
        machine.succeed(f"echo keep > /top/@{name}/sentinel")
    machine.succeed("echo disposable > /top/@root/ephemeral")
    machine.succeed("umount /top")

    def reset_root():
        machine.succeed("workstation-reset-root /dev/mapper/testroot /run/test-reset")

    reset_root()
    machine.succeed("mount /dev/mapper/testroot /top")
    machine.fail("test -e /top/@root/ephemeral")
    machine.succeed("test $(find /top/@old-roots -name ephemeral | wc -l) -eq 1")
    for name in ["nix", "persist", "projects", "local", "snapshots"]:
        machine.succeed(f"grep keep /top/@{name}/sentinel")
    # Simulate interruption before archiving the old root.
    machine.succeed("btrfs subvolume snapshot /top/@root-blank /top/@root-next")
    machine.succeed("umount /top")
    reset_root()
    machine.succeed("mount /dev/mapper/testroot /top")
    # Simulate interruption after archiving root, before the final rename.
    machine.succeed("mv /top/@root /top/interrupted-root")
    machine.succeed("btrfs subvolume snapshot /top/@root-blank /top/@root-next")
    machine.succeed("umount /top")
    reset_root()
    machine.succeed("mount /dev/mapper/testroot /top; test -d /top/@root")
    # Missing bootstrap material must stop the reset before root is changed.
    machine.succeed("echo protected > /top/@root/do-not-change")
    machine.succeed("mv /top/@persist/keys/sops/age.key /top/saved-key; umount /top")
    machine.fail("workstation-reset-root /dev/mapper/testroot /run/test-reset")
    machine.succeed("mount /dev/mapper/testroot /top; grep protected /top/@root/do-not-change")
    machine.succeed("mv /top/saved-key /top/@persist/keys/sops/age.key")
    # Reject a filesystem with an incorrect identity marker.
    machine.succeed("echo wrong > /top/.workstation-layout-v1; umount /top")
    machine.fail("workstation-reset-root /dev/mapper/testroot /run/test-reset")
    machine.succeed("mount /dev/mapper/testroot /top; grep protected /top/@root/do-not-change")
    # A contaminated template must never replace the current root.
    machine.succeed("echo niri-workstation-v1 > /top/.workstation-layout-v1")
    machine.succeed("btrfs property set -ts /top/@root-blank ro false")
    machine.succeed("echo contaminated > /top/@root-blank/unexpected")
    machine.succeed("btrfs property set -ts /top/@root-blank ro true; umount /top")
    machine.fail("workstation-reset-root /dev/mapper/testroot /run/test-reset")
    machine.succeed("mount /dev/mapper/testroot /top; grep protected /top/@root/do-not-change")
    machine.fail("test -e /top/@root/unexpected")
    # Read-only nested ancestors must not stall budgeted archive cleanup.
    machine.succeed("mkdir /top/@old-roots/readonly-fixture; btrfs subvolume create /top/@old-roots/readonly-fixture/root")
    machine.succeed("btrfs subvolume create /top/@old-roots/readonly-fixture/root/parent; btrfs subvolume create /top/@old-roots/readonly-fixture/root/parent/child")
    for path in ["/top/@old-roots/readonly-fixture/root/parent/child", "/top/@old-roots/readonly-fixture/root/parent", "/top/@old-roots/readonly-fixture/root"]:
        machine.succeed(f"btrfs property set -ts {path} ro true")
    machine.succeed("test $(python3 ${../scripts/prune-root.py} /top /top/@old-roots/readonly-fixture/root 1) -eq 1")
    machine.fail("test -e /top/@old-roots/readonly-fixture/root/parent/child")
    machine.succeed("test -d /top/@old-roots/readonly-fixture/root/parent; grep protected /top/@root/do-not-change")
    machine.succeed("test $(btrfs property get -ts /top/@root-blank ro) = ro=true")
    machine.succeed("test $(python3 ${../scripts/prune-root.py} /top /top/@old-roots/readonly-fixture/root 16) -eq 2")
    machine.fail("test -e /top/@old-roots/readonly-fixture/root")
    machine.succeed("grep protected /top/@root/do-not-change")
    machine.succeed("umount /top")

    # Two additional disposable disks exercise the installer's actual probes.
    storage_check = "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${../scripts} WORKSTATION_BLKID_LIBRARY=${pkgs.util-linux.lib}/lib/libblkid.so.1 python3 ${./storage-guards.py}"
    machine.succeed("mkfs.btrfs -f /dev/vdc /dev/vdd; mkdir /tmp/storage-guard-btrfs; mount /dev/vdc /tmp/storage-guard-btrfs")
    machine.succeed(f"{storage_check} mounted-btrfs")
    machine.succeed("umount /tmp/storage-guard-btrfs")
    machine.succeed(f"{storage_check} unmounted-btrfs")

    machine.succeed("wipefs -a /dev/vdc /dev/vdd; pvcreate /dev/vdc /dev/vdd; vgcreate storage-guard-fixture /dev/vdc /dev/vdd")
    machine.succeed("lvcreate -n selected -L 32M storage-guard-fixture /dev/vdc; lvcreate -n survivor -L 32M storage-guard-fixture /dev/vdd")
    machine.succeed("vgchange -an storage-guard-fixture; udevadm settle")
    machine.succeed(f"{storage_check} inactive-lvm")
  '';
}
