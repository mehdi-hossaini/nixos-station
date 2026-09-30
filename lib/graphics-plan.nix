c:
let
  enabled = builtins.elem "nvidia" c.services.xserver.videoDrivers;
in
{
  enabled = c.hardware.graphics.enable;
  drivers = c.services.xserver.videoDrivers;
  # NixOS's disabled NVIDIA module has lazy defaults referring to a null
  # driver. Do not force those defaults for a Mesa-only configuration.
  open = if enabled then c.hardware.nvidia.open else null;
  modesetting = if enabled then c.hardware.nvidia.modesetting.enable else false;
  nvidia = c.hardware.nvidia.package.version;
  kernel = c.boot.kernelPackages.kernel.version;
  offload = c.hardware.nvidia.prime.offload.enable;
  command = c.hardware.nvidia.prime.offload.enableOffloadCmd;
  sync = c.hardware.nvidia.prime.sync.enable;
  reverse = c.hardware.nvidia.prime.reverseSync.enable;
  intel = c.hardware.nvidia.prime.intelBusId;
  amd = c.hardware.nvidia.prime.amdgpuBusId;
  nvbus = c.hardware.nvidia.prime.nvidiaBusId;
  params = c.boot.kernelParams;
  blacklist = c.boot.blacklistedKernelModules;
  niriConfigs = builtins.mapAttrs (
    _: u: u.xdg.configFile."niri/config.kdl".text or ""
  ) c.home-manager.users;
}
