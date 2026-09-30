#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  cat <<'HELP'
Guided workstation installation — run from a NixOS UEFI live USB.

  sudo bash scripts/install.sh            Choose settings and install
  sudo bash scripts/install.sh --dry-run  Preview choices without writing
  sudo bash scripts/install.sh --resume   Continue an already-mounted install
  sudo bash scripts/install.sh --save-settings  Save choices without installing
  Add --export-settings /path/on/other-drive/installation.json for a recovery copy.
  sudo bash scripts/install.sh --keyboard-test  Verify the configured console map
  bash scripts/install.sh --demo          Try the TUI with a fictional disk
  Add --plain for numbered prompts, or --verbose for live Nix build output.

Use arrows and Enter to select, type to search, and Space to toggle optional apps.
The normal flow builds first, then asks you to type ERASE after showing the
selected disk. --resume never formats. Neither mode reboots automatically.
Normal/resume mode requires a local text console (Ctrl+Alt+F2). Hardware checks
require x86_64, Secure Boot disabled, and supported automatic graphics.
Preview does not change settings, keyboard state or disks. Installer helpers and
flake inputs may download; graphics device metadata is bundled with the release.
HELP
  exit 0
fi
demo=0
for argument in "$@"; do
  if [[ $argument == --demo ]]; then demo=1; fi
done
if ((!demo)) && { [[ $EUID != 0 ]] || ! mountpoint -q /iso || [[ ! -d /sys/firmware/efi ]]; }; then
  echo 'Boot a NixOS live USB in UEFI mode, then run this command with sudo.' >&2
  exit 1
fi
if [[ $(uname -m) != x86_64 ]]; then
  echo 'This workstation supports x86_64 machines only.' >&2
  exit 1
fi
cd "$repo"
export NIX_CONFIG="${NIX_CONFIG:-}
experimental-features = nix-command flakes"
echo 'Preparing installer helpers (may download/build packages in the live Nix store).'
exec nix develop --no-update-lock-file --max-jobs 2 --cores 4 .#installer -c python3 scripts/install.py "$@"
