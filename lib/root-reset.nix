{ pkgs }:
pkgs.writeShellApplication {
  name = "workstation-reset-root";
  runtimeInputs = with pkgs; [
    btrfs-progs
    coreutils
    findutils
    util-linux
  ];
  text = builtins.readFile ../scripts/reset-root.sh;
}
