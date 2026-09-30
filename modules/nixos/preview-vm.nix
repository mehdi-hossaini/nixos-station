{
  lib,
  pkgs,
  modulesPath,
  ...
}:
let
  session = import ../../lib/software-session.nix { inherit pkgs; };
in
{
  imports = [ (modulesPath + "/virtualisation/qemu-vm.nix") ];
  # Use the workstation desktop and applications with QEMU's virtual disk.
  # The installed host's encrypted layout and persistence services do not apply.
  disabledModules = [
    ../../hosts/workstation/disks.nix
    ./impermanence.nix
    ./backups.nix
  ];

  virtualisation = {
    memorySize = 3072;
    cores = 2;
    diskSize = 8192;
    graphics = true;
    useNixStoreImage = true;
    mountHostNixStore = false;
    writableStore = true;
    writableStoreUseTmpfs = false;
    useHostCerts = false;
    sharedDirectories = lib.mkForce { };
    qemu.options = [
      "-vga none"
      "-device virtio-vga,xres=1280,yres=800"
      "-display gtk,gl=off"
    ];
  };
  # Niri 26.04 clears the parent display for --session except in its WSL
  # compatibility path. Scope that switch to the compositor, and remove it
  # from applications so the guest is never presented to them as WSL.
  systemd.user.services.niri.environment.WSL_DISTRO_NAME = "workstation-preview";
  home-manager.users.preview.xdg.configFile."niri/config.kdl".text = lib.mkAfter ''
    environment {
        WSL_DISTRO_NAME null
    }
  '';
  services.btrfs.autoScrub.enable = lib.mkForce false;
  programs.nh.clean.enable = lib.mkForce false;

  # Public preview-only credentials; never part of the installation output.
  users.users.preview = {
    hashedPasswordFile = lib.mkForce null;
    password = "preview";
  };
  services.greetd.settings.initial_session = {
    command = "${session}";
    user = "preview";
  };
  services.greetd.settings.default_session.command =
    lib.mkForce "${pkgs.tuigreet}/bin/tuigreet --time --cmd ${session}";
  systemd.tmpfiles.rules = [
    "d /home/preview/Projects 0700 preview users -"
    "d /home/preview/Scratch 0700 preview users -"
  ];
}
