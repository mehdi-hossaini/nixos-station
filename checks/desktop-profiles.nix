{
  pkgs,
  host,
  settings,
}:
let
  check =
    name: overrides: graphics:
    let
      c =
        (host.extendModules {
          specialArgs.settings =
            settings
            // overrides
            // {
              inherit graphics;
              keyboardLayout = "de";
            };
        }).config;
      home = c.home-manager.users.${settings.userName};
      persisted = map (
        d: d.directory
      ) c.environment.persistence."/persist".users.${settings.userName}.directories;
      kdl = home.xdg.configFile."niri/config.kdl".text;
      activation = "home-manager-${settings.userName}.service";
      greetd = c.systemd.services.greetd;
      codexLauncher = pkgs.lib.findFirst (
        p: pkgs.lib.getName p == "workstation-codex"
      ) null home.home.packages;
    in
    assert builtins.all (a: a.assertion) c.assertions;
    assert builtins.elem activation greetd.wants;
    assert builtins.elem activation greetd.after;
    assert !(builtins.elem activation greetd.requires);
    assert
      greetd.serviceConfig.ExecStartPre
      == "${pkgs.systemd}/bin/systemctl is-active --quiet ${activation}";
    assert c.programs.niri.enable && home.programs.foot.enable;
    assert !home.programs.tmux.enable;
    assert home.programs.carapace.enable;
    assert !home.programs.zsh.enableCompletion;
    assert !home.programs.zsh.autosuggestion.enable;
    assert !c.programs.zsh.enableGlobalCompInit;
    assert !(builtins.any (p: pkgs.lib.getName p == "herdr") home.home.packages);
    assert home.programs.firefox.enable;
    assert !(builtins.any (p: pkgs.lib.getName p == "codex") home.home.packages);
    assert codexLauncher == null;
    assert !(builtins.hasAttr "codex-cli" home.xdg.desktopEntries);
    assert !(builtins.elem ".codex" persisted);
    assert !(pkgs.lib.hasInfix "workstation-codex" kdl);
    assert home.programs.waybar.enable && home.programs.fuzzel.enable;
    assert home.programs.swaylock.enable && home.services.swayidle.enable && c.xdg.portal.enable;
    assert home.services.mako.settings.default-timeout == settings.notificationTimeout;
    assert home.programs.waybar.settings.mainBar.battery.format-critical == "!!\n{capacity}%";
    assert pkgs.lib.hasInfix "workstation-battery" kdl;
    assert pkgs.lib.hasInfix "\"makoctl\" \"restore\"" kdl;
    assert !(pkgs.lib.hasInfix "@palette." kdl);
    assert !(pkgs.lib.hasInfix "@focusFollowsMouse@" kdl);
    assert
      pkgs.lib.hasInfix "focus-follows-mouse" kdl
      == (overrides.focusFollowsMouse or settings.focusFollowsMouse);
    assert
      home.programs.foot.settings.colors-dark.regular0 == (
        if overrides.accessibleTerminalColors or settings.accessibleTerminalColors then
          "8c8c8c"
        else
          "222222"
      );
    assert !(builtins.elem ".config/herdr" persisted);
    assert !(builtins.elem ".local/state/herdr" persisted);
    assert pkgs.lib.hasInfix "layout \"de,us\"" kdl;
    assert pkgs.lib.hasInfix "grp:alt_shift_toggle" kdl;
    assert (pkgs.lib.hasInfix "spawn-at-startup \"foot\" \"--app-id=workstation-terminal\"" kdl);
    assert pkgs.lib.hasInfix "Mod+Return { spawn \"foot\"; }" kdl;
    assert (pkgs.lib.hasInfix "Mod+Shift+Return { spawn \"foot\"; }" kdl);
    assert
      graphics == null || pkgs.lib.hasInfix "render-drm-device \"${graphics.prime.renderDevice}\"" kdl;
    pkgs.runCommand "desktop-${name}" { nativeBuildInputs = [ pkgs.niri ]; } ''
      niri validate --config ${pkgs.writeText "niri-${name}.kdl" kdl}
      mkdir "$out"
    '';
in
pkgs.linkFarm "desktop-profiles" [
  {
    name = "legacy-niri";
    path = check "terminal" { desktop = "niri"; } null;
  }
  {
    name = "terminal";
    path = check "terminal" { } null;
  }
  {
    name = "legacy-terminal";
    path = check "terminal" { desktop = "niri-terminal"; } null;
  }
  {
    name = "pointer-focus";
    path = check "pointer-focus" {
      focusFollowsMouse = true;
      accessibleTerminalColors = false;
    } null;
  }
  {
    name = "terminal-prime";
    path = check "terminal-prime" { } {
      schema = 1;
      mode = "automatic";
      profile = "prime";
      prime = {
        integratedVendor = "intel";
        integratedBusId = "PCI:0@0:2:0";
        nvidiaBusId = "PCI:1@0:0:0";
        renderDevice = "/dev/dri/by-path/pci-0000:00:02.0-render";
      };
    };
  }
]
