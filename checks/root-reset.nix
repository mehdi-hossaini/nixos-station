{ pkgs }:
let
  reset = import ../lib/root-reset.nix { inherit pkgs; };
in
pkgs.testers.runNixOSTest {
  name = "workstation-root-reset";
  nodes.machine = _: {
    virtualisation.emptyDiskImages = [ 2048 ];
    environment.systemPackages = [
      reset
      pkgs.btrfs-progs
      pkgs.cryptsetup
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
    machine.succeed("umount /top")
  '';
}
