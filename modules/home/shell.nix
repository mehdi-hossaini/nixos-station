{
  config,
  pkgs,
  lib,
  ...
}:
let
  quickStart = pkgs.writeShellApplication {
    name = "workstation-help";
    runtimeInputs = [ pkgs.less ];
    text = ''
      export LESSHISTFILE=-
      exec less -R ${./terminal-help.txt}
    '';
  };
in
{
  home.packages = [ quickStart ];
  xdg.desktopEntries.workstation-help = {
    name = "Quick Start";
    comment = "Terminal, editing and desktop shortcuts";
    exec = "${pkgs.foot}/bin/foot -e ${quickStart}/bin/workstation-help";
    terminal = false;
    categories = [ "Utility" ];
  };
  programs.zsh = {
    enable = true;
    defaultKeymap = "emacs";
    # zsh-autocomplete initializes completion itself, before Carapace registers.
    enableCompletion = false;
    autosuggestion.enable = false;
    initContent = lib.mkMerge [
      (lib.mkOrder 550 ''
        # The pinned plugin evaluates functions containing inline comments.
        setopt interactivecomments
        zstyle ':autocomplete:*' delay 0.15
        zstyle ':autocomplete:*' min-input 1
        zstyle ':autocomplete:*:*' list-lines 8
        zstyle ':autocomplete:*' add-semicolon no
        zstyle ':chpwd:*' recent-dirs-file "${config.xdg.stateHome}/zsh/recent-dirs"
        source ${pkgs.zsh-autocomplete}/share/zsh-autocomplete/zsh-autocomplete.plugin.zsh
      '')
      (lib.mkAfter (builtins.readFile ./terminal-workflow.zsh))
    ];
    syntaxHighlighting.enable = true;
    history = {
      path = "${config.xdg.stateHome}/zsh/history";
      size = 50000;
      save = 50000;
      ignoreSpace = true;
    };
    shellAliases = {
      v = "nvim";
      ll = "ls -lah";
    };
  };
  programs.carapace = {
    enable = true;
    enableZshIntegration = true;
  };
  programs.starship = {
    enable = true;
    # Keep the branch label readable with the desktop's DejaVu Sans Mono font.
    settings.git_branch.symbol = "git ";
  };
}
