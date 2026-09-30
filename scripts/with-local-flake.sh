#!/usr/bin/env bash
set -euo pipefail

# Git flakes omit new, untracked source files and installation.json. Snapshot
# tracked and recognized untracked source files plus that one settings file, keeping
# .git and other ignored data out of the world-readable Nix store.
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $(git -C "$repo" rev-parse --show-toplevel) != "$repo" ]]; then
  echo 'Use a Git checkout of the workstation repository.' >&2
  exit 1
fi
staging=
if [[ ${1:-} == --snapshot-only ]]; then
  [[ $# == 2 ]] || exit 2
  snapshot=$2
  # Never merge with an existing directory or follow a destination symlink.
  mkdir -- "$snapshot"
else
  staging=$(mktemp -d -t workstation-flake.XXXXXXXX)
  snapshot="$staging/workstation"
  mkdir "$snapshot"
fi
cleanup() {
  if test -n "$staging"; then rm -rf -- "$staging"; fi
}
trap cleanup EXIT

source_files() {
  local path
  git -C "$repo" ls-files --cached -z
  # New source files work without staging. Arbitrary untracked files never
  # become public store inputs, even when a user's ignore rules omit them.
  while IFS= read -r -d '' path; do
    case "$path" in
    README.md | SECURITY.md | \
      scripts/*.py | scripts/*.sh | scripts/*.json | \
      checks/*.py | checks/*.sh | checks/*.nix | checks/*.lua | \
      lib/*.nix | lib/*.json | hosts/*.nix | \
      modules/*.nix | modules/*.kdl | modules/*.txt | modules/*.zsh | \
      hardware/graphics/*.json | hardware/graphics/*.md | \
      docs/*.md | docs/*.html | docs/*.js | docs/*.css | \
      templates/*/flake.nix | templates/*/.envrc | templates/*/.gitignore | \
      .github/*.yml | .github/*.yaml)
      printf '%s\0' "$path"
      ;;
    esac
  done < <(git -C "$repo" ls-files --others --exclude-standard -z)
}
source_files | while IFS= read -r -d '' path; do
  # Block credential names even if mistakenly tracked. installation.json is
  # admitted separately, only as a regular file containing public choices.
  case "/$path" in
  */.env | */.env.* | *.key | *.hash | *.pem | *.p12 | *.pfx | *.agekey | /installation.json) continue ;;
  esac
  # Deleted index entries are normal during refactoring. Keep dangling links.
  if test -e "$repo/$path" || test -L "$repo/$path"; then
    printf '%s\0' "$path"
  fi
done |
  tar -C "$repo" --null -T - -cf - |
  tar -C "$snapshot" -xf -
if test -e "$repo/installation.json" || test -L "$repo/installation.json"; then
  if ! test -f "$repo/installation.json" || test -L "$repo/installation.json"; then
    echo 'installation.json must be a regular file.' >&2
    exit 1
  fi
  cp -p -- "$repo/installation.json" "$snapshot/installation.json"
fi
if [[ ${1:-} == --snapshot-only ]]; then exit 0; fi

flake="path:$snapshot"
command=()
replaced=0
needs_host=0
for argument in "$@"; do
  case "$argument" in
  .#*)
    command+=("$flake#${argument#.#}")
    replaced=1
    case "$argument" in
    .#workstation | .#nixosConfigurations.workstation.*) needs_host=1 ;;
    esac
    ;;
  @local-flake@)
    command+=("$flake")
    replaced=1
    # Flake checks use isolated settings and do not need a real disk choice.
    if [[ ${1:-} != nix || ${2:-} != flake || ${3:-} != check ]]; then needs_host=1; fi
    ;;
  *) command+=("$argument") ;;
  esac
done
if ((replaced == 0)); then
  echo 'Expected a .# output or @local-flake@ argument.' >&2
  exit 2
fi
if ((needs_host)) && ! test -e "$repo/installation.json"; then
  disk=$(nix eval --raw --file "$repo/settings.nix" disk)
  if [[ $disk == /dev/disk/by-id/CHANGE-ME ]]; then
    echo 'Choose an installation disk before building the workstation host.' >&2
    exit 1
  fi
fi
"${command[@]}"
