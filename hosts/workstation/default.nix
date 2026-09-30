{ settings, ... }:
{
  imports = [
    ./hardware.nix
    ./disks.nix
    ../../modules/nixos/base.nix
    ../../modules/nixos/impermanence.nix
    ../../modules/nixos/users.nix
    ../../modules/nixos/secrets.nix
    ../../modules/nixos/desktop.nix
    ../../modules/nixos/containers.nix
    ../../modules/nixos/backups.nix
  ];
  networking.hostName = settings.hostName;
  system.stateVersion = "26.05";
}
