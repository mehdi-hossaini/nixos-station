{ settings, pkgs, ... }:
{
  imports = [
    ./desktop.nix
    ./shell.nix
    ./editor.nix
    ./files.nix
  ];
  home = {
    username = settings.userName;
    homeDirectory = "/home/${settings.userName}";
    stateVersion = "26.05";
    sessionVariables = {
      EDITOR = "nvim";
      VISUAL = "nvim";
      TERMINAL = "foot";
      # These are regenerable caches and live in the persistent local tier.
      CARGO_HOME = "$HOME/.cache/cargo";
      UV_CACHE_DIR = "$HOME/.cache/uv";
    };
    packages = with pkgs; [
      ripgrep
      fd
      jq
      fzf
      just
      wl-clipboard
      xwayland-satellite
      pavucontrol
    ];
  };
  xdg.enable = true;
  programs = {
    obtain.enable = settings.obtain;
    home-manager.enable = true;
    firefox.enable = true;
    zoxide = {
      enable = true;
      enableZshIntegration = true;
    };
    git = {
      enable = true;
      settings.init.defaultBranch = "main";
    };
    direnv = {
      enable = true;
      nix-direnv.enable = true;
      enableZshIntegration = true;
    };
  };
}
