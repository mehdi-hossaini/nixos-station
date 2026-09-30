{
  # The installer or installation overrides must select a stable disk by-id path.
  disk = "/dev/disk/by-id/CHANGE-ME";
  hostName = "workstation";
  userName = "dev";
  timeZone = "UTC";
  keyboardLayout = "us";
  cpu = "generic"; # generic, intel, amd
  nvidia = false; # Legacy fallback; the installer saves a resolved graphics object.
  graphics = null; # Automatic detection is performed by the installer, never by Nix evaluation.
  bluetooth = false;
  containers = false; # Opt in to rootless Podman and its local storage.
  richFilePreviews = false; # Opt in to Yazi's media/PDF/font thumbnail helpers.
  graphicalNetworking = false; # Opt in to the network tray applet and connection editor.
  notificationTimeout = 15000; # Milliseconds; 0 keeps notifications until dismissed.
  focusFollowsMouse = false; # Keep keyboard focus stable unless explicitly enabled.
  accessibleTerminalColors = true; # Readable ANSI black text; ANSI black backgrounds also become gray.
  obtain = false; # Opt in to the GitHub release application manager.
  # Encrypted YAML only. Set after following docs/secrets.md.
  secretsFile = null;
  backupRepository = null; # e.g. sftp:backup@example:/srv/restic/workstation
}
