{
  config,
  lib,
  settings,
  ...
}:
{
  config = lib.mkMerge [
    {
      assertions = [
        {
          assertion = settings.backupRepository == null || settings.secretsFile != null;
          message = "Backups require an encrypted secretsFile containing restic-password and restic-ssh-key";
        }
      ];
    }
    (lib.mkIf (settings.backupRepository != null) {
      sops.secrets = {
        restic-password = { };
        restic-ssh-key = { };
      };
      services.restic.backups.workstation = {
        repository = settings.backupRepository;
        passwordFile = config.sops.secrets.restic-password.path;
        initialize = true;
        paths = [
          "/persist"
          "/projects"
        ];
        # Exclude cache contents only in Projects. Matching children preserves
        # ordinary files with these names and all durable personal state.
        exclude = [
          "/projects/**/node_modules/*"
          "/projects/**/target/*"
          "/projects/**/.venv/*"
          "/projects/**/.direnv/*"
        ];
        extraOptions = [
          # NixOS inserts extraOptions into shell commands. Preserve the
          # complete SSH argument list as one Restic -o argument.
          (lib.escapeShellArg "sftp.args=-i ${config.sops.secrets.restic-ssh-key.path} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes")
        ];
        timerConfig = {
          OnCalendar = "daily";
          Persistent = true;
          RandomizedDelaySec = "30m";
        };
        pruneOpts = [
          "--keep-daily 7"
          "--keep-weekly 5"
          "--keep-monthly 12"
        ];
        checkOpts = [ "--read-data-subset=5%" ];
      };
      systemd.services.restic-backups-workstation = {
        requires = [
          "persist.mount"
          "projects.mount"
        ];
        after = [
          "persist.mount"
          "projects.mount"
          "network-online.target"
        ];
        # One NixOS unit runs backup, prune and check in sequence.
        serviceConfig = {
          CPUWeight = 25;
          IOWeight = 25;
          # Backups share the aggregate background budget with builders.
          Slice = "workstation-build.slice";
        };
      };
    })
  ];
}
