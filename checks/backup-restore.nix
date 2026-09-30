{
  pkgs,
  inputs,
  host,
  settings,
}:
let
  # Disposable credentials generated solely for these guests. No workstation
  # secrets, host keys or installation.json enter this test.
  credentials =
    pkgs.runCommand "workstation-backup-test-credentials"
      {
        nativeBuildInputs = [
          pkgs.age
          pkgs.sops
          pkgs.openssh
        ];
      }
      ''
        mkdir "$out"
        age-keygen -o "$out/age.key"
        ssh-keygen -q -t ed25519 -N "" -f "$out/client-key"
        ssh-keygen -q -t ed25519 -N "" -f "$out/server-key"
        {
          printf 'restic-password: fixture-only-password\nrestic-ssh-key: |\n'
          sed 's/^/  /' "$out/client-key"
        } > secrets.yaml
        sops --encrypt --age "$(age-keygen -y "$out/age.key")" secrets.yaml > "$out/secrets.yaml"
      '';
in
pkgs.testers.runNixOSTest {
  name = "workstation-backup-restore";
  globalTimeout = 180;
  nodes = {
    backup = { lib, ... }: {
      imports = [
        inputs.sops-nix.nixosModules.sops
        ../modules/nixos/secrets.nix
        ../modules/nixos/backups.nix
      ];
      _module.args.settings = settings // {
        secretsFile = "${credentials}/secrets.yaml";
        backupRepository = "sftp:fixture@sftp:/srv/backups";
      };
      # The encrypted file is generated at build time; runtime decryption is
      # exercised instead of causing import-from-derivation during evaluation.
      sops.validateSopsFiles = false;
      sops.useSystemdActivation = true;
      sops.age.keyFile = lib.mkForce "/run/backup-test-age.key";
      systemd.services.sops-install-secrets.preStart = ''
        install -m 0600 ${credentials}/age.key /run/backup-test-age.key
      '';
      virtualisation.fileSystems = {
        "/persist" = {
          device = "tmpfs";
          fsType = "tmpfs";
        };
        "/projects" = {
          device = "tmpfs";
          fsType = "tmpfs";
        };
      };
      systemd.slices.workstation-build.sliceConfig =
        host.config.systemd.slices.workstation-build.sliceConfig;
      systemd.timers.restic-backups-workstation.wantedBy = lib.mkForce [ ];
      programs.ssh.knownHosts.sftp = {
        hostNames = [ "sftp" ];
        publicKeyFile = "${credentials}/server-key.pub";
      };
    };
    sftp = _: {
      services.openssh.enable = true;
      users.users.fixture = {
        isNormalUser = true;
        openssh.authorizedKeys.keyFiles = [ "${credentials}/client-key.pub" ];
      };
      system.activationScripts.backup-test-host-key.text = ''
        mkdir -p /etc/ssh
        install -m 0600 ${credentials}/server-key /etc/ssh/ssh_host_ed25519_key
        install -m 0644 ${credentials}/server-key.pub /etc/ssh/ssh_host_ed25519_key.pub
      '';
    };
  };
  testScript = ''
    start_all()
    sftp.wait_for_unit("sshd.service")
    backup.wait_for_unit("sops-install-secrets.service")
    backup.wait_for_unit("projects.mount")
    backup.wait_for_unit("persist.mount")
    backup.wait_for_open_port(22, addr="sftp", timeout=30)
    sftp.succeed("mkdir -p /srv/backups; chown fixture:users /srv/backups")
    backup.succeed("mkdir -p /projects/demo/node_modules /persist/state; echo project-data > /projects/demo/sentinel; echo identity-data > /persist/state/sentinel; echo excluded > /projects/demo/node_modules/excluded")
    backup.succeed("test $(stat -c %a /run/secrets/restic-password) = 400; test $(stat -c %a /run/secrets/restic-ssh-key) = 400")
    # The production unit must reject an untrusted host, then recover after
    # the declarative known-hosts entry is restored.
    backup.succeed("mv /etc/ssh/ssh_known_hosts /etc/ssh/ssh_known_hosts.saved")
    backup.fail("systemctl start restic-backups-workstation.service", timeout=30)
    backup.succeed("mv /etc/ssh/ssh_known_hosts.saved /etc/ssh/ssh_known_hosts; systemctl reset-failed restic-backups-workstation.service")
    backup.succeed("systemctl start restic-backups-workstation.service", timeout=120)
    backup.succeed("restic-workstation snapshots --json | grep '/projects'")
    # Give restore/check an independent session and file-backed output; the
    # VM control shell must retain ownership of its command terminal.
    backup.succeed("rm /projects/demo/sentinel /persist/state/sentinel; systemd-run --wait --collect -p StandardInput=null -p StandardOutput=append:/tmp/restore.log -p StandardError=append:/tmp/restore.log /run/current-system/sw/bin/restic-workstation restore latest --target /tmp/restored", timeout=120)
    backup.succeed("grep project-data /tmp/restored/projects/demo/sentinel; grep identity-data /tmp/restored/persist/state/sentinel")
    backup.fail("test -e /tmp/restored/projects/demo/node_modules/excluded")
    backup.succeed("systemd-run --wait --collect -p StandardInput=null -p StandardOutput=append:/tmp/check.log -p StandardError=append:/tmp/check.log /run/current-system/sw/bin/restic-workstation check --read-data", timeout=120)
    backup.succeed("test $(systemctl show -P Slice restic-backups-workstation) = workstation-build.slice")
  '';
}
