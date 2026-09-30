{
  pkgs,
  host,
  settings,
}:
let
  validSettings = (import ../lib/default-settings.nix) // {
    disk = "/dev/disk/by-id/test-fixture";
  };
  accepted =
    overrides:
    let
      module = import ../modules/nixos/base.nix {
        inherit pkgs;
        settings = validSettings // overrides;
      };
    in
    builtins.all (item: item.assertion) module.assertions;
  resources = import ../modules/nixos/base.nix {
    inherit pkgs;
    settings = validSettings;
  };
  acceptedGraphics =
    graphics:
    let
      module = import ../modules/nixos/graphics.nix {
        inherit (pkgs) lib;
        config = { };
        settings = validSettings // {
          inherit graphics;
        };
      };
    in
    builtins.all (item: item.assertion) module.assertions;
  prime = {
    integratedVendor = "amd";
    integratedBusId = "PCI:10@1:2:0";
    nvidiaBusId = "PCI:11@1:0:0";
    renderDevice = "/dev/dri/by-path/pci-0001:0a:02.0-render";
  };
  plan = {
    schema = 1;
    mode = "automatic";
    profile = "prime";
    inherit prime;
  };
  unsafePlan = plan // {
    prime = prime // {
      renderDevice = "\"; spawn \"bad";
    };
  };
  unsafeNiri =
    (import ../modules/home/desktop.nix {
      inherit pkgs;
      inherit (pkgs) lib;
      settings = validSettings // {
        graphics = unsafePlan;
      };
    }).xdg.configFile."niri/config.kdl".text;
  incompleteHost = host.extendModules {
    specialArgs.settings = settings // {
      graphics = plan // {
        prime = { };
      };
    };
  };
  backupHost = host.extendModules {
    specialArgs.settings = settings // {
      backupRepository = "sftp:fixture:/backups";
    };
  };
in
assert accepted { };
assert accepted {
  containers = true;
  richFilePreviews = true;
  graphicalNetworking = true;
  obtain = true;
};
assert !accepted { containers = "yes"; };
assert !accepted { richFilePreviews = null; };
assert !accepted { graphicalNetworking = "yes"; };
assert !accepted { obtain = "yes"; };
assert !accepted { userName = "root"; };
assert !accepted { userName = "nobody"; };
assert !accepted { userName = "greeter"; };
assert !accepted { hostName = "bad host"; };
assert !accepted { hostName = "-bad"; };
assert !accepted { disk = "/dev/sda"; };
assert !accepted { disk = "/dev/disk/by-id/CHANGE-ME"; };
assert resources.nix.settings.max-jobs == 2;
assert resources.nix.settings.cores == 4;
assert resources.systemd.services.nix-daemon.serviceConfig.Slice == "workstation-build.slice";
assert resources.systemd.slices.workstation-build.sliceConfig.MemoryHigh == "35%";
assert resources.systemd.slices.workstation-build.sliceConfig.MemoryMax == "45%";
assert resources.systemd.user.slices.workstation-evaluation.sliceConfig.MemoryHigh == "15%";
assert resources.systemd.user.slices.workstation-evaluation.sliceConfig.MemoryMax == "20%";
assert resources.systemd.oomd.enableUserSlices;
assert acceptedGraphics null;
assert acceptedGraphics plan;
assert !acceptedGraphics "damaged";
assert !acceptedGraphics { };
assert !acceptedGraphics (plan // { prime = { }; });
assert
  !acceptedGraphics (
    plan
    // {
      prime = prime // {
        integratedBusId = "wrong";
      };
    }
  );
assert !acceptedGraphics unsafePlan;
assert !(pkgs.lib.hasInfix ''spawn "bad"'' unsafeNiri);
assert builtins.any (
  item:
  !item.assertion
  && item.message == "PRIME needs Intel or AMD, valid PCI bus IDs, and a render-device by-path."
) incompleteHost.config.assertions;
assert backupHost.config.systemd.services.restic-backups-workstation.serviceConfig.IOWeight == 25;
assert
  backupHost.config.systemd.services.restic-backups-workstation.serviceConfig.Slice
  == "workstation-build.slice";
assert builtins.any (
  item:
  !item.assertion
  &&
    item.message
    == "Backups require an encrypted secretsFile containing restic-password and restic-ssh-key"
) backupHost.config.assertions;
pkgs.runCommand "workstation-settings-invariants" { } ''
  touch "$out"
''
