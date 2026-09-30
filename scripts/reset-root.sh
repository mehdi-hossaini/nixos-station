#!/usr/bin/env bash
set -euo pipefail

# Runs in initrd. The exact same implementation is exercised by the VM test.
device=${1:?encrypted Btrfs device required}
staging=${2:?temporary mountpoint required}
for tool in mountpoint mount umount btrfs mkdir cat find mktemp mv sync; do
  command -v "$tool" >/dev/null || {
    echo "Missing reset dependency: $tool" >&2
    exit 1
  }
done
mkdir -p "$staging"
if mountpoint -q "$staging"; then
  echo "Refusing to use an already-mounted staging directory" >&2
  exit 1
fi
mount -t btrfs -o subvolid=5 "$device" "$staging"
trap 'umount "$staging"' EXIT

test "$(cat "$staging/.workstation-layout-v1")" = "niri-workstation-v1"
for volume in @root-blank @nix @persist @projects @local @snapshots; do
  btrfs subvolume show "$staging/$volume" >/dev/null
done
test "$(btrfs property get -ts "$staging/@root-blank" ro)" = "ro=true"
blank_entry=$(find "$staging/@root-blank" -mindepth 1 -print -quit)
if test -n "$blank_entry"; then
  echo "Refusing a nonempty root template: $blank_entry" >&2
  exit 1
fi
test -s "$staging/@persist/bootstrap/login-password.hash"
test -s "$staging/@persist/keys/sops/age.key"

# An interrupted earlier reset can leave @root-next or no @root at all.
# This subvolume is always an unused snapshot of the empty template.
if test -e "$staging/@root-next"; then
  btrfs subvolume show "$staging/@root-next" >/dev/null
  btrfs subvolume delete "$staging/@root-next"
fi
btrfs subvolume snapshot "$staging/@root-blank" "$staging/@root-next"

mkdir -p "$staging/@old-roots"
if test -e "$staging/@root"; then
  btrfs subvolume show "$staging/@root" >/dev/null
  archive=$(mktemp -d "$staging/@old-roots/boot-XXXXXXXXXX")
  mv "$staging/@root" "$archive/root"
fi
mv "$staging/@root-next" "$staging/@root"
sync
