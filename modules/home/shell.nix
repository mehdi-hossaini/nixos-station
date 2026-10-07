{
  config,
  pkgs,
  lib,
  ...
}:
let
  # fzf-tab captures Carapace's pre-quoted matches with an extra escape level.
  # Normalize before both capture paths (upstream #503), and decode file
  # candidates in their original quote context when generating the picker.
  fzfTab = pkgs.zsh-fzf-tab.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [
      (pkgs.writeText "fzf-tab-carapace-quoting.patch" ''
        --- a/fzf-tab.zsh
        +++ b/fzf-tab.zsh
        @@ -39,2 +39,3 @@
           local ret=$?
        +  (( ''${funcstack[(I)_carapace_completer]} && ''${_opts[(I)-Q]} )) && __hits=("''${(@)__hits//\\\\/\\}")
           if (( $#__hits == 0 )); then
        @@ -103,2 +104,3 @@
           if [[ -n $isfile ]]; then
        +    __tmp_value+=$'\0quote\0'$compstate[quote]
             # NOTE: need a extra ''${} here or ~ expansion won't work
        @@ -173,2 +175,3 @@
                 && [[ "$compstate[unambiguous]" != "$compstate[quote]$IPREFIX$PREFIX$compstate[quote]" ]] \
        +        && [[ "$compstate[unambiguous]" != "$compstate[quote]$IPREFIX$PREFIX" ]] \
                 && [[ $compstate[list] != *"force"* ]]; then
        --- a/lib/-ftb-generate-complist
        +++ b/lib/-ftb-generate-complist
        @@ -43,3 +43,3 @@
             if (( $+v[realdir] )); then
        -      filepath=$v[realdir]''${(Q)v[word]}
        +      filepath=$v[realdir]''${(Q)''${:-$v[quote]$v[word]$v[quote]}}
               if [[ -d $filepath ]]; then
        --- a/modules/Src/fzftab.c
        +++ b/modules/Src/fzftab.c
        @@ -417,2 +417,2 @@
        -        char *word = "", *group = NULL, *realdir = NULL;
        +        char *word = "", *group = NULL, *realdir = NULL, *quote = "";
                 strcpy(dpre, "");
        @@ -428,8 +428,6 @@
                         word = info[j + 1];
        -                // unquote word
        -                parse_subst_string(word);
        -                remnulargs(word);
        -                untokenize(word);
                     } else if (!strcmp(info[j], "group")) {
                         group = info[j + 1];
        +            } else if (!strcmp(info[j], "quote")) {
        +                quote = info[j + 1];
                     } else if (!strcmp(info[j], "realdir")) {
        @@ -449,3 +447,10 @@
                 // add character and color to describe the type of the files
                 if (realdir) {
        -            filepath = ftb_strcat(filepath, 2, realdir, word);
        +            // Completion words are escaped for the active quote context.
        +            // Non-file words may already contain a closing quote (Carapace).
        +            char *quoted_word = ftb_strcat(NULL, 3, quote, word, quote);
        +            parse_subst_string(quoted_word);
        +            remnulargs(quoted_word);
        +            untokenize(quoted_word);
        +            filepath = ftb_strcat(filepath, 2, realdir, quoted_word);
        +            zsfree(quoted_word);
      '')
    ];
  });
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
    enableCompletion = true;
    autosuggestion = {
      enable = true;
      strategy = [ "history" ];
    };
    initContent = lib.mkMerge [
      # After compinit (570), before autosuggestions (700) and highlighting.
      (lib.mkOrder 580 ''
        zstyle ':completion:*' menu no
        zstyle ':completion:*:descriptions' format '[%d]'
        zstyle ':fzf-tab:*' fzf-flags --height=10
        source ${fzfTab}/share/fzf-tab/fzf-tab.plugin.zsh
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
