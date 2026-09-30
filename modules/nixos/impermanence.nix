{
  lib,
  pkgs,
  settings,
  ...
}:
let
  user = settings.userName;
  reset = import ../../lib/root-reset.nix { inherit pkgs; };
in
{
  boot.initrd.systemd.storePaths = [
    reset
    "${pkgs.util-linux}/bin/mountpoint"
    "${pkgs.util-linux}/bin/mount"
    "${pkgs.util-linux}/bin/umount"
    "${pkgs.btrfs-progs}/bin/btrfs"
    "${pkgs.coreutils}/bin/mkdir"
    "${pkgs.coreutils}/bin/cat"
    "${pkgs.findutils}/bin/find"
    "${pkgs.coreutils}/bin/mktemp"
    "${pkgs.coreutils}/bin/mv"
    "${pkgs.coreutils}/bin/sync"
  ];
  boot.initrd.systemd.services.workstation-reset-root = {
    description = "Prepare a fresh Btrfs root, retaining the previous root";
    requiredBy = [ "sysroot.mount" ];
    before = [ "sysroot.mount" ];
    after = [ "systemd-cryptsetup@cryptroot.service" ];
    requires = [ "systemd-cryptsetup@cryptroot.service" ];
    unitConfig = {
      DefaultDependencies = false;
      IgnoreOnIsolate = true;
      ConditionKernelCommandLine = "!workstation.keep-root";
      OnFailure = "emergency.target";
    };
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = "${reset}/bin/workstation-reset-root /dev/mapper/cryptroot /run/root-reset";
    };
  };

  environment.persistence."/persist" = {
    hideMounts = true;
    directories = [
      "/var/lib/nixos"
      "/var/lib/NetworkManager"
      {
        directory = "/etc/NetworkManager/system-connections";
        mode = "0700";
      }
    ]
    ++ lib.optional settings.bluetooth "/var/lib/bluetooth";
    files = [
      "/etc/machine-id"
      "/var/lib/systemd/random-seed"
    ];
    users.${user} = {
      directories = [
        "Documents"
        "Downloads"
        "Pictures"
        {
          directory = ".ssh";
          mode = "0700";
        }
        {
          directory = ".gnupg";
          mode = "0700";
        }
        {
          directory = ".local/share/keyrings";
          mode = "0700";
        }
        ".local/share/direnv"
        ".local/state/nvim"
        ".local/state/zsh"
        ".local/share/zoxide"
        ".mozilla/firefox"
      ]
      ++ lib.optionals settings.obtain [
        ".config/obtain"
        ".local/share/obtain"
        ".local/share/applications"
      ];
    };
  };
  environment.persistence."/local" = {
    hideMounts = true;
    directories = [
      {
        directory = "/var/log/journal";
        mode = "2755";
        group = "systemd-journal";
      }
      {
        directory = "/var/cache";
        mode = "0755";
      }
    ];
    users.${user}.directories = [
      ".cache"
      ".local/share/nix"
    ]
    ++ lib.optional settings.containers ".local/share/containers";
  };
  fileSystems."/home/${user}/Projects" = {
    device = "/projects/${user}";
    fsType = "none";
    options = [
      "bind"
      "x-gvfs-hide"
    ];
    neededForBoot = true;
    depends = [ "/projects" ];
  };
  # The installer creates the source directory before the first boot.
  systemd.tmpfiles.rules = [
    "d /projects/${user} 0700 ${user} users -"
    "d /home/${user}/Scratch 0700 ${user} users -"
    "d /persist/bootstrap 0700 root root -"
    "d /persist/keys/sops 0700 root root -"
    "d /.snapshots/projects 0700 root root -"
    "d /.snapshots/persist 0700 root root -"
  ];
  # Login must never proceed on top of missing durable storage.
  systemd.services."home-manager-${user}" = {
    requires = [
      "persist.mount"
      "projects.mount"
      "local.mount"
    ];
    after = [
      "persist.mount"
      "projects.mount"
      "local.mount"
    ];
  };
  systemd.services.workstation-snapshots = {
    description = "Retain 24 hourly project and state snapshots";
    requires = [
      "projects.mount"
      "persist.mount"
      "\\x2esnapshots.mount"
    ];
    after = [
      "projects.mount"
      "persist.mount"
      "\\x2esnapshots.mount"
    ];
    serviceConfig = {
      Type = "oneshot";
      CPUWeight = 25;
      IOWeight = 25;
      Slice = "workstation-build.slice";
    };
    path = with pkgs; [
      btrfs-progs
      coreutils
      findutils
    ];
    script = ''
      set -euo pipefail
      listing=$(mktemp /run/workstation-snapshots.XXXXXXXX)
      trap 'rm -f "$listing"' EXIT
      failed=0
      for source in projects persist; do
        destination="/.snapshots/$source"
        mkdir -p "$destination"
        # A regular pipeline propagates discovery errors before any deletion.
        # Make room for the next snapshot before creation. A full disk must
        # not prevent retention cleanup, or cleanup of the other tier.
        find "$destination" -mindepth 1 -maxdepth 1 -type d -printf '%f\0' \
          | sort -zr | tail -zn +24 > "$listing"
        removed=0
        while IFS= read -r -d $'\0' name; do
          btrfs subvolume delete "$destination/$name"
          removed=$((removed + 1))
          if ((removed >= 128)); then break; fi
        done < "$listing"
        if ((removed > 0)); then btrfs subvolume sync "$destination"; fi
        if ! btrfs subvolume snapshot -r "/$source" "$destination/$(date -u +%Y%m%dT%H%M%S%N)"; then
          echo "Snapshot creation failed for $source; retention cleanup completed." >&2
          failed=1
        fi
      done
      exit "$failed"
    '';
  };
  systemd.timers.workstation-snapshots = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "hourly";
      Persistent = true;
      RandomizedDelaySec = "5m";
    };
  };
  # Pruning is deliberately outside initrd and starts only after a successful boot.
  systemd.services.workstation-prune-roots = {
    description = "Keep the three most recent archived roots";
    after = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      CPUWeight = 25;
      IOWeight = 25;
      Slice = "workstation-build.slice";
    };
    path = with pkgs; [
      btrfs-progs
      coreutils
      findutils
      util-linux
    ];
    script = ''
      set -euo pipefail
      workdir=$(mktemp -d /run/root-prune.XXXXXXXX)
      staging="$workdir/mount"
      mkdir "$staging"
      cleanup() {
        if mountpoint -q "$staging"; then
          umount "$staging" || return 1
        fi
        rm -f "$workdir/archives" "$workdir/complete" "$workdir/stale"
        rmdir "$staging" "$workdir"
      }
      trap cleanup EXIT
      mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot "$staging"
      test "$(cat "$staging/.workstation-layout-v1")" = "niri-workstation-v1"
      test -d "$staging/@old-roots" || exit 0
      # An interrupted reset can leave an empty archive directory before it
      # moves @root into place. Budget 16 empty archives/subvolume deletions
      # per run, and count only real root subvolumes for retention.
      # Keep names NUL-delimited and fail if discovery or sorting fails.
      find "$staging/@old-roots" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %f\0' \
        > "$workdir/archives"
      : > "$workdir/complete"
      removed=0
      while IFS= read -r -d $'\0' entry; do
        name="''${entry#* }"
        archive="$staging/@old-roots/$name"
        root="$archive/root"
        if ! test -e "$root" && ! test -L "$root"; then
          if ((removed < 16)); then
            # Refuse unexpected contents instead of deleting an unknown tree.
            rmdir "$archive"
            removed=$((removed + 1))
          fi
          continue
        fi
        test ! -L "$root"
        btrfs subvolume show "$root" > /dev/null
        printf '%s\0' "$entry" >> "$workdir/complete"
      done < "$workdir/archives"
      sort -zrn "$workdir/complete" | tail -zn +4 | cut -z -d ' ' -f 2- > "$workdir/stale"
      while IFS= read -r -d $'\0' name; do
        if ((removed >= 16)); then break; fi
        root="$staging/@old-roots/$name/root"
        # Metadata lookup avoids visiting ordinary files. Partial archives
        # remain valid roots and are resumed by the next maintenance run.
        pruned=$(${pkgs.python3}/bin/python3 ${../../scripts/prune-root.py} \
          "$staging" "$root" "$((16 - removed))")
        removed=$((removed + pruned))
        if ! test -e "$root"; then rmdir "$staging/@old-roots/$name"; fi
      done < "$workdir/stale"
    '';
  };
  systemd.timers.workstation-prune-roots = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "15m";
      OnUnitActiveSec = "1d";
    };
  };
}
