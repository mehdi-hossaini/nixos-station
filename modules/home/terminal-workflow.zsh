# Choose a folder directly inside Projects without changing the current command.
cproj() {
  emulate -L zsh
  local project
  if [[ ! -d "$HOME/Projects" ]]; then
    print -u2 -- 'Create ~/Projects and put your project folders inside it first.'
    return 1
  fi
  IFS= read -r -d '' project < <(
    command fd --type d --max-depth 1 --hidden --no-ignore --exclude .git \
      --absolute-path --print0 . "$HOME/Projects" |
      command fzf --read0 --print0 --height=60% --layout=reverse --border \
        --prompt='Project > ' --query="${1-}"
  ) || return 0
  builtin cd -- "$project"
}

# Foot uses OSC 7 to open Ctrl+Shift+N in the current directory. Encode every
# non-URI byte, including whitespace/control characters and UTF-8 sequences.
_workstation_report_cwd() {
  emulate -L zsh
  local LC_ALL=C
  local directory=$PWD encoded='' character byte
  local -i index
  for ((index = 1; index <= ${#directory}; index++)); do
    character=$directory[index]
    case "$character" in
      [a-zA-Z0-9/._~-]) encoded+=$character ;;
      *)
        printf -v byte '%%%02X' "'$character"
        encoded+=$byte
        ;;
    esac
  done
  printf '\e]7;file://%s%s\e\\' "$HOST" "$encoded"
}

if [[ -o interactive ]]; then
  autoload -Uz edit-command-line
  zle -N edit-command-line
  bindkey '^X^E' edit-command-line
  if [[ $TERM == foot* && -z ${SSH_CONNECTION-} ]]; then
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd _workstation_report_cwd
  fi
fi
