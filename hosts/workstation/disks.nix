{ settings, ... }:
let
  mountOptions = [
    "compress=zstd:3"
    "noatime"
  ];
in
{
  disko.devices.disk.system = {
    type = "disk";
    device = settings.disk;
    content = {
      type = "gpt";
      partitions = {
        ESP = {
          size = "2G";
          type = "EF00";
          content = {
            type = "filesystem";
            format = "vfat";
            mountpoint = "/boot";
            mountOptions = [ "umask=0077" ];
          };
        };
        encrypted = {
          size = "100%";
          content = {
            type = "luks";
            name = "cryptroot";
            settings.allowDiscards = false;
            content = {
              type = "btrfs";
              extraArgs = [
                "-L"
                "workstation"
              ];
              subvolumes = {
                "@root" = {
                  mountpoint = "/";
                  inherit mountOptions;
                };
                "@nix" = {
                  mountpoint = "/nix";
                  inherit mountOptions;
                };
                "@persist" = {
                  mountpoint = "/persist";
                  inherit mountOptions;
                };
                "@projects" = {
                  mountpoint = "/projects";
                  inherit mountOptions;
                };
                "@local" = {
                  mountpoint = "/local";
                  inherit mountOptions;
                };
                "@snapshots" = {
                  mountpoint = "/.snapshots";
                  inherit mountOptions;
                };
              };
            };
          };
        };
      };
    };
  };
  fileSystems = {
    "/nix".neededForBoot = true;
    "/persist".neededForBoot = true;
    "/projects".neededForBoot = true;
    "/local".neededForBoot = true;
  };
}
