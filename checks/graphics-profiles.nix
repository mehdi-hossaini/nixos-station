{
  pkgs,
  host,
  settings,
}:
let
  mkProfile =
    profile: prime:
    host.extendModules {
      specialArgs.settings = settings // {
        graphics = {
          schema = 1;
          mode = "automatic";
          inherit profile prime;
        };
      };
    };
  prime = vendor: {
    integratedVendor = vendor;
    integratedBusId = "PCI:10@1:2:0";
    nvidiaBusId = "PCI:11@1:0:0";
    renderDevice = "/dev/dri/by-path/pci-0001:0a:02.0-render";
  };
  profiles = {
    mesa = mkProfile "mesa" null;
    virtual = mkProfile "virtual" null;
    nvidia = mkProfile "nvidia" null;
    intel-prime = mkProfile "prime" (prime "intel");
    amd-prime = mkProfile "prime" (prime "amd");
  };
  check =
    name: system:
    let
      c = system.config;
      nv = builtins.elem name [
        "nvidia"
        "intel-prime"
        "amd-prime"
      ];
      hybrid = builtins.elem name [
        "intel-prime"
        "amd-prime"
      ];
    in
    assert c.hardware.graphics.enable;
    assert c.services.xserver.videoDrivers == (if nv then [ "nvidia" ] else [ "modesetting" ]);
    assert !nv || (c.hardware.nvidia.open && c.hardware.nvidia.modesetting.enable);
    assert c.hardware.nvidia.prime.offload.enable == hybrid;
    assert c.hardware.nvidia.prime.offload.enableOffloadCmd == hybrid;
    assert !c.hardware.nvidia.prime.sync.enable && !c.hardware.nvidia.prime.reverseSync.enable;
    assert c.hardware.nvidia.prime.intelBusId == (if name == "intel-prime" then "PCI:10@1:2:0" else "");
    assert c.hardware.nvidia.prime.amdgpuBusId == (if name == "amd-prime" then "PCI:10@1:2:0" else "");
    assert c.hardware.nvidia.prime.nvidiaBusId == (if hybrid then "PCI:11@1:0:0" else "");
    pkgs.runCommand "graphics-profile-${name}" { nativeBuildInputs = [ pkgs.niri ]; } ''
      niri validate --config ${
        pkgs.writeText "niri-${name}.kdl"
          c.home-manager.users.${settings.userName}.xdg.configFile."niri/config.kdl".text
      }
      mkdir "$out"
      ln -s ${c.system.build.toplevel} "$out/system"
      ln -s ${pkgs.writeText "graphics-plan-${name}.json" (builtins.toJSON (import ../lib/graphics-plan.nix c))} "$out/plan.json"
    '';
in
pkgs.lib.mapAttrs check profiles
