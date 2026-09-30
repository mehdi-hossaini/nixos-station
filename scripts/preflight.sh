#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
disk=$(nix eval --raw --file "$repo/settings.nix" disk)
case "$disk" in
/dev/disk/by-id/CHANGE-ME)
  echo 'Set the installation disk in settings.nix first.' >&2
  exit 1
  ;;
/dev/disk/by-id/*) ;;
*)
  echo 'The target must be an explicit /dev/disk/by-id path.' >&2
  exit 1
  ;;
esac
test -b "$disk" || {
  echo 'The selected disk is not present.' >&2
  exit 1
}
if [[ $(lsblk -dn -o TYPE -- "$disk") != disk ]]; then
  echo 'The selected target must be a whole disk, not a partition or other block device.' >&2
  exit 1
fi
echo "Selected installation target: $disk"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$disk"
echo 'This check does not partition, format or install anything.'
