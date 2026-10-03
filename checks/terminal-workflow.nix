{
  pkgs,
  host,
  settings,
}:
let
  home = host.config.home-manager.users.${settings.userName};
in
pkgs.runCommand "terminal-workflow"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.zsh
      pkgs.fd
      pkgs.fzf
      pkgs.git
      home.programs.carapace.package
      home.programs.neovim.finalPackage
    ];
  }
  ''
    export HOME="$TMPDIR/home" XDG_CONFIG_HOME="$TMPDIR/home/.config"
    export XDG_DATA_HOME="$TMPDIR/home/.local/share" XDG_STATE_HOME="$TMPDIR/home/.local/state"
    export XDG_CACHE_HOME="$TMPDIR/home/.cache"
    mkdir -p "$XDG_CONFIG_HOME/nvim" "$XDG_DATA_HOME/nvim/site/pack"
    ln -s ${home.xdg.configFile."nvim/init.lua".source} "$XDG_CONFIG_HOME/nvim/init.lua"
    ln -s ${home.xdg.dataFile."nvim/site/pack/hm".source} "$XDG_DATA_HOME/nvim/site/pack/hm"
    zsh -n ${../modules/home/terminal-workflow.zsh}
    zsh -n ${home.home.file.".config/zsh/.zshrc".source}
    python3 ${./shell-completion.py} ${
      home.home.file.".config/zsh/.zshrc".source
    } ${home.home.homeDirectory} compiled
    python3 ${./shell-completion.py} ${
      home.home.file.".config/zsh/.zshrc".source
    } ${home.home.homeDirectory} shell
    python3 ${./terminal-workflow.py} ${../modules/home/terminal-workflow.zsh}
    ${pkgs.foot}/bin/foot --check-config --config ${home.xdg.configFile."foot/foot.ini".source}
    printf 'let\n  workflowValue = 42;\nin\n  work\n' > fixture.nix
    nvim --headless "+luafile ${./terminal-editor.lua}"
    touch "$out"
  ''
