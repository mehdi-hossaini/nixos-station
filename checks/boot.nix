{
  pkgs,
  inputs,
  host,
  settings,
}:
let
  inherit (pkgs) lib;
  diskoLib = import "${inputs.disko}/lib" {
    inherit lib;
    makeTest = import "${inputs.nixpkgs}/nixos/tests/make-test-python.nix";
    eval-config = import "${inputs.nixpkgs}/nixos/lib/eval-config.nix";
    qemu-common = import "${inputs.nixpkgs}/nixos/lib/qemu-common.nix";
  };
  diskConfig = lib.recursiveUpdate (import ../hosts/workstation/disks.nix { inherit settings; }) {
    disko.devices.disk.system = {
      imageSize = "8G";
      content.partitions.encrypted.content = {
        # Public test-only credential. Never used by the real host configuration.
        passwordFile = "/tmp/secret.key";
      };
    };
  };
  bootstrapRepo =
    pkgs.runCommand "workstation-bootstrap-fixture" { nativeBuildInputs = [ pkgs.git ]; }
      ''
        mkdir -p "$out/scripts"
        cp ${../scripts/prepare-install.sh} "$out/scripts/prepare-install.sh"
        cp ${../scripts/sync-checkout.sh} "$out/scripts/sync-checkout.sh"
        cp ${../scripts/with-local-flake.sh} "$out/scripts/with-local-flake.sh"
        cp ${../.gitignore} "$out/.gitignore"
        git -C "$out" init --quiet
        git -C "$out" add .
      '';
in
diskoLib.testLib.makeDiskoTest {
  inherit pkgs;
  name = "workstation-uefi-boot";
  disko-config = diskConfig;
  inherit (host) extendModules;
  testMode = "module";
  efi = true;
  enableOCR = true;
  extraInstallerConfig.nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  extraInstallerConfig.environment.systemPackages = [
    pkgs.cryptsetup
    pkgs.kbd
    pkgs.mkpasswd
    pkgs.age
    pkgs.git
    pkgs.gnutar
    pkgs.diffutils
  ];
  extraSystemConfig = {
    # The VM harness supplies its own root credential via hashedPasswordFile.
    # Clear the host's locked-password value only in the disposable guest.
    users.users.root.hashedPassword = lib.mkForce null;
    # Exercise real keyboard input in the initrd; override the harness keyfile.
    boot.initrd.secrets = lib.mkForce { };
    boot.kernelParams = lib.mkAfter [ "console=tty0" ];
    # This test validates storage/activation, without requiring a GPU in QEMU.
    systemd.services.greetd.enable = lib.mkForce false;
    # Disko's fast test install shares store files but does not populate the
    # installed guest's Nix database. Home Manager queries that database.
    systemd.services.test-register-closure = {
      requiredBy = [ "home-manager-${settings.userName}.service" ];
      before = [ "home-manager-${settings.userName}.service" ];
      serviceConfig.Type = "oneshot";
      script = ''
        ${pkgs.nix}/bin/nix-store --load-db < ${
          pkgs.closureInfo { rootPaths = [ host.config.system.build.toplevel ]; }
        }/registration
      '';
    };
    # Disko shares the builder store over 9p. Give the guest a writable overlay
    # so nix-daemon/Home Manager can operate without chown on the shared store.
    fileSystems = {
      "/nix/.ro-store" = {
        device = "nix-store";
        fsType = "9p";
        neededForBoot = true;
        options = [
          "trans=virtio"
          "version=9p2000.L"
          "cache=loose"
          "ro"
        ];
      };
      "/nix/store" = lib.mkOverride 0 {
        neededForBoot = true;
        overlay = {
          lowerdir = [ "/nix/.ro-store" ];
          upperdir = "/nix/.rw-store/upper";
          workdir = "/nix/.rw-store/work";
        };
      };
    };
  };
  postDisko = ''
    # Public fixture with Y/Z differences on the German layout. Replace the
    # harness credential so an embedded/default test key cannot unlock it.
    machine.succeed("printf yYzZ > /tmp/keyboard-test.key")
    machine.succeed("cryptsetup luksChangeKey --key-file /tmp/secret.key /dev/disk/by-partlabel/disk-system-encrypted /tmp/keyboard-test.key")
    machine.succeed("loadkeys --unicode ${host.config.console.keyMap}")
    machine.succeed("openvt -c 2 -s -- sh -c 'cryptsetup open --test-passphrase --tries 1 /dev/disk/by-partlabel/disk-system-encrypted && touch /tmp/keyboard-verified' &")
    machine.wait_until_tty_matches("2", "passphrase", timeout=30)
    for key in ["z", "shift-z", "y", "shift-y", "ret"]:
        machine.send_key(key)
    machine.wait_for_file("/tmp/keyboard-verified", timeout=30)
    machine.succeed("bash ${./bootstrap.sh} ${bootstrapRepo} ${settings.userName}")
  '';
  bootCommands = ''
    machine.wait_for_text("passphrase", timeout=120)
    for key in ["z", "shift-z", "y", "shift-y", "ret"]:
        machine.send_key(key)
  '';
  extraTestScript = ''
    machine.wait_for_unit("multi-user.target", timeout=180)
    print(machine.succeed("journalctl -b -u home-manager-${settings.userName}.service --no-pager"))
    machine.wait_for_unit("home-manager-${settings.userName}.service")
    machine.succeed("test $(journalctl -b -u workstation-reset-root -o cat | grep -c 'Create snapshot') -eq 1")
    machine.succeed("nix config show | grep -x 'max-jobs = 2'")
    machine.succeed("nix config show | grep -x 'cores = 4'")
    machine.succeed("test $(systemctl show -P Slice nix-daemon.service) = workstation-build.slice")
    machine.succeed("test $(systemctl show -P MemoryMax workstation-build.slice) != infinity")
    machine.succeed("test $(systemctl show -P ManagedOOMMemoryPressure user.slice) = kill")
    machine.succeed("test -L /home/${settings.userName}/.config/niri/config.kdl")
    machine.succeed("echo durable > /home/${settings.userName}/Projects/sentinel")
    machine.succeed("echo durable > /home/${settings.userName}/Documents/sentinel")
    machine.succeed("echo ephemeral > /home/${settings.userName}/Scratch/sentinel")
    machine.succeed("su - ${settings.userName} -c 'obtain list'")
    for directory in [".config/obtain", ".local/share/obtain", ".local/share/applications"]:
        machine.succeed(f"su - ${settings.userName} -c 'echo durable > /home/${settings.userName}/{directory}/sentinel'")
    identity = machine.succeed("cat /etc/machine-id").strip()
    # Disko starts QEMU with reboot disabled; power-cycle the same disk image.
    machine.shutdown()
    machine.start()
    machine.wait_for_text("passphrase", timeout=120)
    for key in ["z", "shift-z", "y", "shift-y", "ret"]:
        machine.send_key(key)
    machine.wait_for_unit("multi-user.target", timeout=180)
    machine.wait_for_unit("home-manager-${settings.userName}.service")
    machine.succeed("test $(journalctl -b -u workstation-reset-root -o cat | grep -c 'Create snapshot') -eq 1")
    assert machine.succeed("cat /etc/machine-id").strip() == identity
    machine.succeed("grep durable /home/${settings.userName}/Projects/sentinel")
    machine.succeed("grep durable /home/${settings.userName}/Documents/sentinel")
    machine.fail("test -e /home/${settings.userName}/Scratch/sentinel")
    machine.succeed("su - ${settings.userName} -c 'obtain list'")
    for directory in [".config/obtain", ".local/share/obtain", ".local/share/applications"]:
        machine.succeed(f"grep durable /home/${settings.userName}/{directory}/sentinel")
    # Exercise retention against real Btrfs subvolumes, not just service startup.
    for source in ["projects", "persist"]:
        for index in range(26):
            machine.succeed(f"btrfs subvolume snapshot -r /{source} /.snapshots/{source}/20200101T000000{index:09d}")
    machine.succeed("systemctl start workstation-snapshots.service")
    for source in ["projects", "persist"]:
        machine.succeed(f"test $(find /.snapshots/{source} -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 24")

    machine.succeed("mkdir -p /top; mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top")
    for index in range(5):
        machine.succeed(f"mkdir /top/@old-roots/fixture-{index}")
        machine.succeed(f"btrfs subvolume snapshot /top/@root-blank /top/@old-roots/fixture-{index}/root")
    # Reset can be interrupted after mktemp but before @root is moved. These
    # empty archives must not displace real roots from the retention count.
    for index in range(18):
        machine.succeed(f"mkdir /top/@old-roots/boot-interrupted-{index}")
    machine.succeed("umount /top")
    machine.succeed("systemctl start workstation-prune-roots.service")
    machine.succeed("mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top")
    machine.succeed("test $(find /top/@old-roots -mindepth 1 -maxdepth 1 -type d -name 'boot-interrupted-*' | wc -l) -eq 2")
    machine.succeed("umount /top")
    machine.succeed("systemctl start workstation-prune-roots.service")
    machine.succeed("mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top")
    machine.succeed("test $(find /top/@old-roots -mindepth 1 -maxdepth 1 -type d -name 'boot-interrupted-*' | wc -l) -eq 0")
    machine.succeed("test $(find /top/@old-roots -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 3")
    # One old archive with many nested subvolumes must be partially pruned,
    # then resumed. Ordinary Scratch directories must not affect discovery.
    machine.succeed("mkdir /top/@old-roots/budget-fixture; btrfs subvolume snapshot /top/@root-blank /top/@old-roots/budget-fixture/root")
    machine.succeed("touch -d 2000-01-01 /top/@old-roots/budget-fixture")
    for index in range(33):
        machine.succeed(f"btrfs subvolume create /top/@old-roots/budget-fixture/root/nested-{index}")
    machine.succeed("mkdir -p /top/@old-roots/budget-fixture/root/Scratch; seq 1 1000 | xargs -I{} mkdir /top/@old-roots/budget-fixture/root/Scratch/{}")
    machine.succeed("echo protected > /top/@root/prune-protected; umount /top")
    for remaining in [17, 1]:
        machine.succeed("systemctl start workstation-prune-roots.service")
        machine.succeed("mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top")
        machine.succeed(f"test $(find /top/@old-roots/budget-fixture/root -mindepth 1 -maxdepth 1 -name 'nested-*' | wc -l) -eq {remaining}")
        machine.succeed("grep protected /top/@root/prune-protected; umount /top")
    machine.succeed("systemctl start workstation-prune-roots.service")
    machine.succeed("mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top")
    machine.fail("test -e /top/@old-roots/budget-fixture")
    machine.succeed("grep protected /top/@root/prune-protected")
    machine.succeed("umount /top")
  '';
}
