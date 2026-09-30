{
  pkgs,
  lib,
  settings,
  ...
}:
let
  palette = builtins.fromJSON (builtins.readFile ../../lib/palette.json);
  # Rich formats use the file information preview when thumbnail helpers are off.
  mediaInfo = [
    {
      mime = "{image,video,audio,font}/*";
      run = "file";
    }
    {
      mime = "application/{pdf,ms-opentype}";
      run = "file";
    }
  ];
in
{
  home.packages = with pkgs; [
    file
    tree
    zip
    unzip
  ];
  programs.yazi = {
    enable = true;
    enableZshIntegration = true;
    shellWrapperName = "y";
    package =
      if settings.richFilePreviews then
        pkgs.yazi
      else
        pkgs.yazi.override {
          # File browsing/search, JSON and archives. Media converters are opt-in.
          optionalDeps = with pkgs; [
            jq
            _7zz
            fd
            ripgrep
            fzf
            zoxide
          ];
        };
    settings.plugin = lib.mkIf (!settings.richFilePreviews) {
      preloaders = [ ];
      prepend_previewers = mediaInfo;
      prepend_spotters = mediaInfo;
    };
    theme = {
      mode = {
        # Explicit colors keep status labels readable with Foot's muted ANSI palette.
        normal_main = {
          fg = palette.base;
          bg = palette.focus;
          bold = true;
        };
        normal_alt = {
          fg = palette.focus;
          bg = palette.inactive;
        };
        select_main = {
          fg = palette.base;
          bg = palette.success;
          bold = true;
        };
        select_alt = {
          fg = palette.success;
          bg = palette.inactive;
        };
        unset_main = {
          fg = palette.base;
          bg = palette.warning;
          bold = true;
        };
        unset_alt = {
          fg = palette.warning;
          bg = palette.inactive;
        };
      };
      mgr = {
        cwd.fg = palette.focus;
        border_style.fg = palette.border;
        count_copied = {
          fg = palette.base;
          bg = palette.success;
        };
        count_cut = {
          fg = palette.base;
          bg = palette.error;
        };
      };
      indicator = {
        current = {
          fg = palette.bright;
          bg = palette.selection;
          reversed = false;
        };
        parent = {
          fg = palette.body;
          bg = palette.raised;
          reversed = false;
        };
      };
      tabs = {
        active = {
          fg = palette.base;
          bg = palette.focus;
          bold = true;
        };
        inactive = {
          fg = palette.muted;
          bg = palette.raised;
        };
      };
      status.overall = {
        fg = palette.body;
        bg = palette.raised;
      };
    };
  };
}
