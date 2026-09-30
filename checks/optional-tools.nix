{
  pkgs,
  host,
  settings,
}:
let
  check =
    name: containers: richFilePreviews: graphicalNetworking: obtain:
    let
      c =
        (host.extendModules {
          specialArgs.settings = settings // {
            inherit
              containers
              richFilePreviews
              graphicalNetworking
              obtain
              ;
          };
        }).config;
      home = c.home-manager.users.${settings.userName};
      user = c.users.users.${settings.userName};
      localState = map (
        entry: entry.directory
      ) c.environment.persistence."/local".users.${settings.userName}.directories;
      packageNames = map pkgs.lib.getName home.home.packages;
      persistentState = map (
        entry: entry.directory
      ) c.environment.persistence."/persist".users.${settings.userName}.directories;
      previews = pkgs.closureInfo { rootPaths = [ home.programs.yazi.finalPackage ]; };
    in
    assert builtins.all (a: a.assertion) c.assertions;
    assert c.virtualisation.podman.enable == containers;
    assert
      user.subUidRanges == (pkgs.lib.optional containers {
        startUid = 100000;
        count = 65536;
      });
    assert
      user.subGidRanges == (pkgs.lib.optional containers {
        startGid = 100000;
        count = 65536;
      });
    assert !user.autoSubUidGidRange;
    assert builtins.elem ".local/share/containers" localState == containers;
    assert builtins.elem "network-manager-applet" packageNames == graphicalNetworking;
    assert home.services.network-manager-applet.enable == graphicalNetworking;
    assert builtins.hasAttr "network-manager-applet" home.systemd.user.services == graphicalNetworking;
    assert
      !graphicalNetworking
      ||
        home.systemd.user.services.network-manager-applet.Service.ExecStart
        == [ "${pkgs.networkmanagerapplet}/bin/nm-applet --indicator" ];
    assert home.programs.obtain.enable == obtain;
    assert builtins.elem "obtain" packageNames == obtain;
    assert
      builtins.elem "/home/${settings.userName}/.local/share/obtain/bin" home.home.sessionPath == obtain;
    assert builtins.all (path: builtins.elem path persistentState == obtain) [
      ".config/obtain"
      ".local/share/obtain"
      ".local/share/applications"
    ];
    assert
      home.programs.waybar.settings.mainBar.network.on-click == (
        if graphicalNetworking then
          "${pkgs.networkmanagerapplet}/bin/nm-connection-editor"
        else
          "${pkgs.foot}/bin/foot -e ${pkgs.networkmanager}/bin/nmtui"
      );
    assert builtins.all (name: !(builtins.elem name packageNames)) [
      "wget"
      "statix"
      "deadnix"
      "shellcheck"
      "shfmt"
      "nix-tree"
      "nix-diff"
    ];
    assert home.programs.yazi.enable && home.programs.neovim.enable;
    assert
      !home.programs.neovim.withPython3
      && !home.programs.neovim.withNodeJs
      && !home.programs.neovim.withRuby
      && !home.programs.neovim.withPerl;
    assert richFilePreviews || home.programs.yazi.settings.plugin.preloaders == [ ];
    pkgs.runCommand "optional-tools-${name}" { } ''
      # Verify the actual file-manager closure, not only the package expression.
      test "$(grep -Fxc '${pkgs.ffmpeg-headless}' ${previews}/store-paths)" -eq ${
        if richFilePreviews then "1" else "0"
      }
      test "$(grep -Fxc '${pkgs.imagemagick}' ${previews}/store-paths)" -eq ${
        if richFilePreviews then "1" else "0"
      }
      test "$(grep -Fxc '${pkgs.poppler-utils}' ${previews}/store-paths)" -eq ${
        if richFilePreviews then "1" else "0"
      }
      mkdir "$out"
      ln -s ${home.programs.yazi.finalPackage} "$out/yazi"
      ${pkgs.lib.optionalString containers ''ln -s ${c.virtualisation.podman.package} "$out/podman"''}
      ${pkgs.lib.optionalString graphicalNetworking ''
        test -x ${pkgs.networkmanagerapplet}/bin/nm-applet
        test -x ${pkgs.networkmanagerapplet}/bin/nm-connection-editor
        ln -s ${pkgs.networkmanagerapplet} "$out/network-applet"
      ''}
      ${pkgs.lib.optionalString obtain ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        ${home.programs.obtain.package}/bin/obtain --help > help.txt
        grep -q 'add' help.txt
        ${home.programs.obtain.package}/bin/obtain list
        ln -s ${home.programs.obtain.package} "$out/obtain"
      ''}
    '';
in
pkgs.linkFarm "optional-tools" [
  {
    name = "minimal";
    path = check "minimal" false false false false;
  }
  {
    name = "containers";
    path = check "containers" true false false false;
  }
  {
    name = "rich-previews";
    path = check "rich-previews" false true false false;
  }
  {
    name = "graphical-networking";
    path = check "graphical-networking" false false true false;
  }
  {
    name = "obtain";
    path = check "obtain" false false false true;
  }
  {
    name = "all";
    path = check "all" true true true true;
  }
]
