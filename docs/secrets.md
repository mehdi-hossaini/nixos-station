# Secrets and backups

Initial login deliberately uses `/persist/bootstrap/login-password.hash`,
created interactively by the installer. This makes first boot independent of
remote secrets or a not-yet-encrypted YAML file. `users.mutableUsers = false`
means `passwd` alone is not the persistent source of truth. To change the login
password, replace that root-only hash with `mkpasswd` output and rebuild. Never
put the password or hash in Git or Nix string literals.

The sops-nix age identity is `/persist/keys/sops/age.key`, provisioned before first
boot. Automatic identity generation is disabled. Store another recovery identity
outside the workstation. Encrypt secrets to both public recipients.

Create `.sops.yaml` with public recipients only, then use `sops secrets/workstation.yaml`.
Set `secretsFile = ./secrets/workstation.yaml;` in the override attribute set in
`settings.nix` and stage the encrypted file. There is deliberately no fake encrypted secret committed here.
New secrets should be declared in `modules/nixos/secrets.nix` with service-specific
ownership and restart requirements. Plaintext is delivered under `/run/secrets`.

## Enable SFTP backups

1. Prepare a remote Restic destination and dedicated SSH account/key.
2. Encrypt `restic-password` and `restic-ssh-key` in the SOPS YAML.
3. Set `backupRepository = "sftp:backup@HOST:/absolute/repository";`.
4. Add a verified public host key declaratively in a NixOS module:

   ```nix
   programs.ssh.knownHosts.backup = {
     hostNames = [ "HOST" ];
     publicKey = "ssh-ed25519 YOUR_VERIFIED_PUBLIC_HOST_KEY";
   };
   ```

5. Build and activate, then run `sudo systemctl start restic-backups-workstation`.
   Review `journalctl -u restic-backups-workstation`. Strict host checking is
   enabled; the job must fail until the correct host key has been configured.
6. Test a restore into a separate directory before relying on the job.

Daily backups cover `/persist` and `/projects`, including Git-ignored work except
the contents of project directories named `node_modules`, `target`, `.venv` and
`.direnv`. These exclusions apply only under `/projects`; ordinary files with
those names and all `/persist` personal state are backed up. Review the excluded
directories for your projects. Retention is 7 daily, 5 weekly and 12 monthly
snapshots. These jobs read live files: use database dumps or quiesce services when
application-level consistency is required. `/local` and `/nix` are excluded.

Keep the repository password and SSH access material independently available.
Saving them only inside the backup they unlock prevents disaster recovery.
Each backup includes a repository check that reads a 5% data sample. Schedule
periodic full checks and an actual restoration drill. Local snapshots
and generation rollback do not replace these backups.
