{
  pkgs,
  settings,
  ...
}:
{
  assertions = [
    {
      assertion =
        builtins.isString settings.keyboardLayout
        && builtins.match "[a-zA-Z0-9_-]+" settings.keyboardLayout != null;
      message = "keyboardLayout must name one XKB layout; a US fallback is added automatically";
    }
    {
      assertion = builtins.isInt settings.notificationTimeout && settings.notificationTimeout >= 0;
      message = "notificationTimeout must be a nonnegative number of milliseconds (0 disables expiry)";
    }
    {
      assertion =
        builtins.isBool settings.containers
        && builtins.isBool settings.richFilePreviews
        && builtins.isBool settings.graphicalNetworking
        && builtins.isBool settings.obtain
        && builtins.isBool settings.focusFollowsMouse
        && builtins.isBool settings.accessibleTerminalColors;
      message = "Application and accessibility toggles must be booleans";
    }
    {
      assertion = builtins.elem settings.cpu [
        "generic"
        "intel"
        "amd"
      ];
      message = "settings.cpu must be generic, intel or amd";
    }
    {
      assertion =
        builtins.isString settings.userName
        && builtins.match "[a-z_][a-z0-9_-]*" settings.userName != null
        && !(builtins.elem settings.userName [
          "root"
          "nobody"
          "greeter"
        ]);
      message = "Choose a non-reserved conventional lowercase username";
    }
    {
      assertion =
        builtins.isString settings.hostName
        && builtins.stringLength settings.hostName <= 63
        && builtins.match "[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?" settings.hostName != null;
      message = "settings.hostName must be a DNS-compatible computer name";
    }
    {
      assertion =
        builtins.isString settings.disk
        && builtins.match "/dev/disk/by-id/[^/]+" settings.disk != null
        && settings.disk != "/dev/disk/by-id/CHANGE-ME";
      message = "settings.disk must name an explicit /dev/disk/by-id device";
    }
  ];
  nix = {
    settings = {
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      sandbox = true;
      trusted-users = [ "root" ];
      auto-optimise-store = true;
      warn-dirty = true;
      # Two bounded builders avoid starving the interactive session.
      max-jobs = 2;
      cores = 4;
    };
    # NH is the only automatic GC scheduler. Protect direnv roots.
    gc.automatic = false;
  };
  systemd.slices.workstation-build.sliceConfig = {
    CPUWeight = 25;
    IOWeight = 25;
    MemoryHigh = "35%";
    MemoryMax = "45%";
    MemorySwapMax = "20%";
  };
  # All foreground commands share one user slice, rather than each receiving
  # its own allowance. Together with builders the memory caps total 65%.
  systemd.user.slices.workstation-evaluation.sliceConfig = {
    CPUWeight = 25;
    IOWeight = 25;
    MemoryHigh = "15%";
    MemoryMax = "20%";
    MemorySwapMax = "5%";
  };
  systemd.services.nix-daemon.serviceConfig.Slice = "workstation-build.slice";
  systemd.oomd.enableUserSlices = true;
  programs.nh = {
    enable = true;
    flake = "/projects/${settings.userName}/workstation";
    clean = {
      enable = true;
      dates = "weekly";
      extraArgs = "--keep-since 30d --keep 5 --no-direnv";
    };
  };
  boot = {
    loader.systemd-boot = {
      enable = true;
      configurationLimit = 10;
    };
    loader.efi.canTouchEfiVariables = true;
    initrd.systemd.enable = true;
    tmp.useTmpfs = false;
  };
  systemd.sleep.settings.Sleep = {
    AllowHibernation = false;
    AllowHybridSleep = false;
    AllowSuspendThenHibernate = false;
  };
  zramSwap.enable = true;
  time.timeZone = settings.timeZone;
  i18n.defaultLocale = "en_US.UTF-8";
  # Share the selected XKB layout with the login console and initrd unlock prompt.
  console.useXkbConfig = true;
  networking = {
    networkmanager.enable = true;
    firewall.enable = true;
  };
  services = {
    openssh.enable = false;
    btrfs.autoScrub = {
      enable = true;
      fileSystems = [ "/" ];
      interval = "monthly";
    };
    journald.extraConfig = ''
      Storage=persistent
      SystemMaxUse=1G
      MaxRetentionSec=14day
    '';
  };
  security.sudo.wheelNeedsPassword = true;
  environment.systemPackages = with pkgs; [
    git
    curl
    btrfs-progs
    cryptsetup
    sops
    age
    restic
  ];
}
