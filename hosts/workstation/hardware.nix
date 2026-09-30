{
  lib,
  settings,
  ...
}:
{
  imports = [ ../../modules/nixos/graphics.nix ];
  # Generic starting point, deliberately not copied from an existing machine.
  nixpkgs.hostPlatform = "x86_64-linux";
  boot.initrd.availableKernelModules =
    (builtins.fromJSON (builtins.readFile ../../scripts/storage-policy.json)).modules;
  boot.kernelModules =
    lib.optional (settings.cpu == "intel") "kvm-intel"
    ++ lib.optional (settings.cpu == "amd") "kvm-amd";
  hardware.cpu.intel.updateMicrocode = settings.cpu == "intel";
  hardware.cpu.amd.updateMicrocode = settings.cpu == "amd";
  hardware.enableRedistributableFirmware = true;
  hardware.bluetooth.enable = settings.bluetooth;
  services.blueman.enable = settings.bluetooth;
}
