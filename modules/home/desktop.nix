{
  pkgs,
  lib,
  settings,
  ...
}:
let
  palette = builtins.fromJSON (builtins.readFile ../../lib/palette.json);
  keyboard = import ../../lib/keyboard.nix settings.keyboardLayout;
  hex = lib.removePrefix "#";
  graphics = settings.graphics or null;
  prime =
    if builtins.isAttrs graphics && (graphics.profile or null) == "prime" then
      graphics.prime or null
    else
      null;
  renderDevice =
    if
      builtins.isAttrs prime
      && builtins.isString (prime.renderDevice or null)
      && builtins.match "/dev/dri/by-path/pci-[0-9a-fA-F:.]+-render" prime.renderDevice != null
    then
      prime.renderDevice
    else
      null;
in
{
  home.packages = lib.optional settings.graphicalNetworking pkgs.networkmanagerapplet ++ [
    (pkgs.writeShellApplication {
      name = "workstation-battery";
      runtimeInputs = [ pkgs.coreutils ];
      text = ''
        found=0
        for battery in /sys/class/power_supply/*; do
          if test -f "$battery/type" && test "$(cat "$battery/type")" = Battery; then
            printf '%s: %s%%, %s\n' "''${battery##*/}" \
              "$(cat "$battery/capacity")" "$(cat "$battery/status")"
            found=1
          fi
        done
        if ((found == 0)); then echo 'No battery reported by the kernel.'; fi
      '';
    })
  ];
  services.network-manager-applet.enable = settings.graphicalNetworking;
  # Waybar's tray uses StatusNotifierItem rather than the legacy X11 tray.
  xsession.preferStatusNotifierItems = settings.graphicalNetworking;
  xdg.configFile."niri/config.kdl".text =
    builtins.replaceStrings
      (
        [
          "@keyboardLayout@"
          "@keyboardOptions@"
          "@focusFollowsMouse@"
        ]
        ++ map (name: "@palette.${name}@") (builtins.attrNames palette)
      )
      (
        [
          keyboard.layout
          keyboard.options
          (lib.optionalString settings.focusFollowsMouse ''focus-follows-mouse max-scroll-amount="0%"'')
        ]
        ++ builtins.attrValues palette
      )
      (builtins.readFile ./niri.kdl)
    + (
      if renderDevice != null then
        ''
          debug { render-drm-device "${renderDevice}"; }
        ''
      else
        ""
    );
  programs.foot = {
    enable = true;
    settings = {
      main = {
        font = "DejaVu Sans Mono:size=11,Symbols Nerd Font Mono:size=11";
        pad = "14x14";
      };
      key-bindings = {
        # Leave Ctrl+N and Ctrl+F available to shells and terminal editors.
        spawn-terminal = "Control+Shift+n";
        search-start = "Control+Shift+r";
      };
      colors-dark = {
        background = hex palette.base;
        foreground = hex palette.body;
        selection-background = hex palette.selection;
        selection-foreground = hex palette.bright;
        # ANSI shares foreground/background palette entries. The accessible
        # default favors readable black text; conventional black is opt-in.
        regular0 = hex (if settings.accessibleTerminalColors then palette.muted else palette.raised);
        regular1 = hex palette.error;
        regular2 = hex palette.success;
        regular3 = hex palette.warning;
        regular4 = hex palette.focus;
        regular5 = hex palette.mauve;
        regular6 = hex palette.teal;
        regular7 = hex palette.body;
        bright0 = hex palette.muted;
        bright1 = hex palette.brightError;
        bright2 = hex palette.brightSuccess;
        bright3 = hex palette.brightWarning;
        bright4 = hex palette.brightFocus;
        bright5 = hex palette.brightMauve;
        bright6 = hex palette.brightTeal;
        bright7 = hex palette.bright;
      };
    };
  };
  programs.fuzzel = {
    enable = true;
    settings = {
      main = {
        font = "DejaVu Sans:size=11";
        terminal = "${pkgs.foot}/bin/foot -e";
        # Fuzzel trims trailing spaces unless the prompt itself is quoted.
        prompt = "\">  \"";
        placeholder = "Search applications…";
        icons-enabled = false;
        width = 46;
        lines = 7;
        line-height = 30;
        horizontal-pad = 24;
        vertical-pad = 16;
        inner-pad = 12;
      };
      colors = {
        background = "${hex palette.base}ff";
        text = "${hex palette.body}ff";
        prompt = "${hex palette.focus}ff";
        placeholder = "${hex palette.muted}ff";
        input = "${hex palette.bright}ff";
        match = "${hex palette.teal}ff";
        selection = "${hex palette.selection}ff";
        selection-text = "${hex palette.bright}ff";
        selection-match = "${hex palette.selectedMatch}ff";
        border = "${hex palette.border}ff";
      };
      border = {
        width = 1;
        radius = 0;
      };
    };
  };
  programs.swaylock = {
    enable = true;
    settings = {
      color = hex palette.base;
      show-failed-attempts = true;
      font = "DejaVu Sans";
      indicator-radius = 64;
      indicator-thickness = 2;
      inside-color = hex palette.base;
      ring-color = hex palette.border;
      key-hl-color = hex palette.teal;
      bs-hl-color = hex palette.warning;
      text-color = hex palette.body;
      line-uses-inside = true;
      separator-color = "00000000";
      inside-ver-color = hex palette.raised;
      ring-ver-color = hex palette.teal;
      text-ver-color = hex palette.body;
      inside-wrong-color = hex palette.raised;
      ring-wrong-color = hex palette.error;
      text-wrong-color = hex palette.error;
    };
  };
  programs.waybar = {
    enable = true;
    systemd = {
      enable = true;
      targets = [ "niri.service" ];
    };
    settings.mainBar = {
      layer = "top";
      position = "left";
      width = 30;
      spacing = 0;
      modules-left = [ "niri/workspaces" ];
      modules-right = [
        "pulseaudio"
        "backlight"
        "network"
        "battery"
        "tray"
        "clock"
      ];
      "niri/workspaces" = {
        all-outputs = false;
        format = "{index}";
      };
      clock.format = "{:%H\n%M}";
      clock.justify = "center";
      clock.tooltip-format = "<big>{:%B %Y}</big>\n<tt><small>{calendar}</small></tt>";
      network.format = "󰈀";
      network.format-wifi = "";
      network.tooltip-format-wifi = "{essid} · {signalStrength}%";
      network.format-ethernet = "󰈀";
      network.format-linked = "󰈀";
      network.format-disconnected = "󰖪";
      network.format-disabled = "󰖪";
      network.tooltip-format-ethernet = "{ifname} · {ipaddr}";
      network.tooltip-format-disconnected = "Network disconnected";
      network.tooltip-format-disabled = "Wi-Fi disabled";
      network.on-click =
        if settings.graphicalNetworking then
          "${pkgs.networkmanagerapplet}/bin/nm-connection-editor"
        else
          "${pkgs.foot}/bin/foot -e ${pkgs.networkmanager}/bin/nmtui";
      pulseaudio.format = "{icon}";
      pulseaudio.format-muted = "󰖁";
      pulseaudio.format-icons = [
        ""
        ""
        ""
      ];
      pulseaudio.tooltip-format = "{desc} · {volume}%";
      pulseaudio.on-click = "${pkgs.pavucontrol}/bin/pavucontrol";
      backlight = {
        format = "󰃟";
        tooltip-format = "Brightness {percent}%";
        interval = 2;
        # Native scrolling controls the same device selected for the display.
        scroll-step = 5.0;
      };
      battery = {
        format = "{icon}\n{capacity}%";
        format-warning = "!\n{capacity}%";
        format-critical = "!!\n{capacity}%";
        format-charging = "\n{capacity}%";
        justify = "center";
        format-icons = [
          ""
          ""
          ""
          ""
          ""
        ];
        tooltip-format = "Battery {capacity}% · {timeTo}";
        states = {
          warning = 25;
          critical = 10;
        };
      };
      tray = {
        icon-size = 14;
        spacing = 6;
      };
    };
    style = ''
      * {
        font-family: DejaVu Sans, Symbols Nerd Font Mono;
        font-size: 12px;
        min-height: 0;
        min-width: 0;
        border-radius: 0;
      }
      window#waybar {
        background: ${palette.base};
        color: ${palette.barText};
        border-right: 1px solid ${palette.inactive};
      }
      tooltip {
        background: ${palette.raised};
        border: 1px solid ${palette.border};
      }
      tooltip label { color: ${palette.body}; padding: 6px; }
      #workspaces { margin: 4px 0 0; }
      #workspaces button {
        color: ${palette.workspaceText};
        padding: 6px 0;
        margin: 0;
        border: none;
        border-left: 2px solid transparent;
        background: transparent;
        box-shadow: none;
        text-shadow: none;
        transition: background-color 150ms ease, color 150ms ease;
      }
      #workspaces button.empty { color: ${palette.muted}; }
      #workspaces button:hover { background: ${palette.raised}; color: ${palette.bright}; }
      #workspaces button.active {
        color: ${palette.activeText};
        background: ${palette.activeSurface};
        border-left-color: ${palette.focus};
      }
      #workspaces button.urgent { color: ${palette.error}; border-left-color: ${palette.error}; }
      .modules-right { margin-bottom: 4px; }
      #network, #pulseaudio, #backlight, #battery, #tray { padding: 7px 0; }
      #pulseaudio:hover, #backlight:hover, #network:hover, #battery:hover, #clock:hover { background: ${palette.raised}; }
      #clock {
        color: ${palette.activeText};
        font-family: DejaVu Sans Mono;
        font-weight: 600;
        padding: 8px 0 4px;
        margin: 2px 0 0;
        border-top: 1px solid ${palette.inactive};
      }
      #battery.warning { color: ${palette.warning}; }
      #battery.critical { color: ${palette.error}; }
      #battery.charging { color: ${palette.success}; }
      #network.disconnected, #pulseaudio.muted { color: ${palette.muted}; }
    '';
  };
  services.mako = {
    enable = true;
    settings = {
      default-timeout = settings.notificationTimeout;
      max-history = 50;
      font = "DejaVu Sans 11";
      background-color = palette.raised;
      text-color = palette.body;
      border-color = palette.border;
      border-size = 1;
      border-radius = 0;
      padding = "16,18";
      margin = "10";
      width = 360;
      progress-color = "over ${palette.focus}33";
      "urgency=critical" = {
        border-color = palette.error;
        default-timeout = 0;
      };
    };
  };
  services.swayidle = {
    enable = true;
    systemdTargets = [ "niri.service" ];
    timeouts = [
      {
        timeout = 600;
        command = "${pkgs.swaylock}/bin/swaylock -f";
      }
      {
        timeout = 660;
        command = "${pkgs.niri}/bin/niri msg action power-off-monitors";
        resumeCommand = "${pkgs.niri}/bin/niri msg action power-on-monitors";
      }
    ];
    events = {
      before-sleep = "${pkgs.swaylock}/bin/swaylock -f";
      lock = "${pkgs.swaylock}/bin/swaylock -f";
    };
  };
  systemd.user.services.polkit-agent = {
    Unit = {
      Description = "Polkit authentication agent";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${pkgs.polkit_gnome}/libexec/polkit-gnome-authentication-agent-1";
      Restart = "on-failure";
    };
    Install.WantedBy = [ "niri.service" ];
  };
  gtk = {
    enable = true;
    font = {
      name = "DejaVu Sans";
      size = 11;
    };
    colorScheme = "dark";
    theme = {
      name = "Adwaita-dark";
      package = pkgs.gnome-themes-extra;
    };
    iconTheme = {
      name = "Adwaita";
      package = pkgs.adwaita-icon-theme;
    };
  };
  home.pointerCursor = {
    name = "Adwaita";
    package = pkgs.adwaita-icon-theme;
    size = 24;
    gtk.enable = true;
    x11.enable = true;
  };
  dconf.settings."org/gnome/desktop/interface".color-scheme = "prefer-dark";
}
