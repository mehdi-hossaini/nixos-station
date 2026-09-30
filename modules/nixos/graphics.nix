{
  config,
  lib,
  settings,
  ...
}:
let
  graphics = settings.graphics or null;
  # Preserve old manual configurations until the installer resolves/migrates
  # them. The installer never treats this fallback as a hardware assessment.
  profile =
    if graphics == null then
      (if settings.nvidia or false then "nvidia" else "mesa")
    else
      (if builtins.isAttrs graphics then graphics.profile or null else null);
  nvidia = builtins.elem profile [
    "nvidia"
    "prime"
  ];
  prime = if builtins.isAttrs graphics then graphics.prime or null else null;
  pciBusId =
    value: builtins.isString value && builtins.match "PCI:[0-9]+@[0-9]+:[0-9]+:[0-9]+" value != null;
  renderDevice =
    value:
    builtins.isString value
    && builtins.match "/dev/dri/by-path/pci-[0-9a-fA-F:.]+-render" value != null;
  validPrime =
    builtins.isAttrs prime
    && builtins.elem (prime.integratedVendor or null) [
      "intel"
      "amd"
    ]
    && pciBusId (prime.integratedBusId or null)
    && pciBusId (prime.nvidiaBusId or null)
    && renderDevice (prime.renderDevice or null);
  usablePrime = if validPrime then prime else null;
in
{
  nixpkgs.config.allowUnfreePredicate =
    pkg:
    nvidia
    && builtins.elem (lib.getName pkg) [
      "nvidia-x11"
      "nvidia-settings"
      "nvidia-persistenced"
    ];
  assertions = [
    {
      assertion =
        graphics == null
        || (
          builtins.isAttrs graphics
          && (graphics.schema or null) == 1
          && (graphics.mode or null) == "automatic"
          && builtins.elem profile [
            "mesa"
            "nvidia"
            "prime"
            "virtual"
          ]
        );
      message = "Unsupported installation.json graphics schema or profile.";
    }
    {
      assertion = (profile == "prime") == (prime != null);
      message = "PRIME graphics must include detected PCI bus IDs.";
    }
    {
      assertion = prime == null || validPrime;
      message = "PRIME needs Intel or AMD, valid PCI bus IDs, and a render-device by-path.";
    }
  ];
  hardware.graphics.enable = true;
  services.xserver.videoDrivers = if nvidia then [ "nvidia" ] else [ "modesetting" ];
  hardware.nvidia = lib.mkIf nvidia {
    modesetting.enable = true;
    open = true;
    package = config.boot.kernelPackages.nvidiaPackages.stable;
    prime = lib.mkIf (usablePrime != null) {
      offload = {
        enable = true;
        enableOffloadCmd = true;
      };
      inherit (usablePrime) nvidiaBusId;
      intelBusId = if usablePrime.integratedVendor == "intel" then usablePrime.integratedBusId else "";
      amdgpuBusId = if usablePrime.integratedVendor == "amd" then usablePrime.integratedBusId else "";
    };
  };
  # Niri's upstream per-process fix for NVIDIA's excessive free-buffer pool.
  environment.etc."nvidia/nvidia-application-profiles-rc.d/50-niri.json" = lib.mkIf nvidia {
    text = builtins.toJSON {
      rules = [
        {
          pattern = {
            feature = "procname";
            matches = "niri";
          };
          profile = "niri";
        }
      ];
      profiles = [
        {
          name = "niri";
          settings = [
            {
              key = "GLVidHeapReuseRatio";
              value = 0;
            }
          ];
        }
      ];
    };
  };
}
