{ pkgs, host }:
let
  services = host.config.systemd.services;
  snapshots = pkgs.writeText "workstation-snapshots.sh" services.workstation-snapshots.script;
  pruneRoots = pkgs.writeText "workstation-prune-roots.sh" services.workstation-prune-roots.script;
in
assert services.workstation-snapshots.serviceConfig.IOWeight == 25;
assert services.workstation-prune-roots.serviceConfig.IOWeight == 25;
pkgs.runCommand "workstation-service-scripts"
  {
    nativeBuildInputs = [
      pkgs.shellcheck
      pkgs.python3
    ];
  }
  ''
    shellcheck -s bash ${snapshots} ${pruneRoots}
    python3 ${./snapshots.py} ${snapshots}
    touch "$out"
  ''
