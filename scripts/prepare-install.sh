#!/usr/bin/env bash
set -euo pipefail
umask 077

# Run ONLY from the installer after reviewing settings and running disko.
test "$(id -u)" -eq 0 || {
  echo 'Run as root from the installer.' >&2
  exit 1
}
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
user=${1:?Pass the validated installation username}
checkout=${2:-$repo}
[[ $user =~ ^[a-z_][a-z0-9_-]*$ ]]
[[ $user != root && $user != nobody && $user != greeter ]]
for path in /mnt /mnt/nix /mnt/persist /mnt/projects /mnt/local; do
  mountpoint -q "$path" || {
    echo "Missing target mount: $path" >&2
    exit 1
  }
done
test "$(findmnt -n -o FSTYPE /mnt)" = btrfs
test "$(findmnt -n -o FSROOT /mnt)" = /@root
test "$(findmnt -n -o FSROOT /mnt/persist)" = /@persist
expected_uuid=$(blkid -s UUID -o value /dev/mapper/cryptroot)
for path in /mnt /mnt/nix /mnt/persist /mnt/projects /mnt/local; do
  test "$(findmnt -n -o UUID "$path")" = "$expected_uuid"
done
test "$(findmnt -n -o FSROOT /mnt/nix)" = /@nix
test "$(findmnt -n -o FSROOT /mnt/projects)" = /@projects
test "$(findmnt -n -o FSROOT /mnt/local)" = /@local

staging=$(mktemp -d /run/workstation-install.XXXXXXXX)
staging_mounted=0
bootstrap_temp=
cleanup_staging() {
  if test -n "$bootstrap_temp"; then
    rm -f -- "$bootstrap_temp"
  fi
  if ((staging_mounted)); then
    umount "$staging"
  fi
  rmdir "$staging"
}
publish_bootstrap_file() {
  local destination=$1
  test -s "$bootstrap_temp"
  sync -f "$bootstrap_temp"
  mv -T -- "$bootstrap_temp" "$destination"
  bootstrap_temp=
  sync -f "${destination%/*}"
}
trap cleanup_staging EXIT
mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot "$staging"
staging_mounted=1
layout_marker=$staging/.workstation-layout-v1
if test -e "$layout_marker" || test -L "$layout_marker"; then
  if ! test -f "$layout_marker" || test -L "$layout_marker" ||
    test "$(cat "$layout_marker")" != niri-workstation-v1; then
    echo 'Refusing an invalid workstation layout marker.' >&2
    exit 1
  fi
fi
if ! test -e "$staging/@root-blank" && ! test -L "$staging/@root-blank"; then
  btrfs subvolume create "$staging/@root-blank"
fi
if test -L "$staging/@root-blank" || ! btrfs subvolume show "$staging/@root-blank" >/dev/null; then
  echo 'Refusing an invalid root template.' >&2
  exit 1
fi
blank_entry=$(find "$staging/@root-blank" -mindepth 1 -print -quit)
if test -n "$blank_entry"; then
  echo "Refusing a nonempty root template: $blank_entry" >&2
  exit 1
fi
case $(btrfs property get -ts "$staging/@root-blank" ro) in
ro=false)
  # Complete a prior attempt interrupted between creation and making it read-only.
  # The private bootstrap umask must not restrict traversal of the system root.
  chmod 0755 "$staging/@root-blank"
  btrfs property set -ts "$staging/@root-blank" ro true
  ;;
ro=true) ;;
*)
  echo 'Refusing an invalid root template read-only property.' >&2
  exit 1
  ;;
esac
test "$(stat -c %a "$staging/@root-blank")" = 755
test "$(btrfs property get -ts "$staging/@root-blank" ro)" = ro=true
bootstrap_temp=$(mktemp "$staging/.workstation-layout-v1.XXXXXXXX")
printf '%s\n' niri-workstation-v1 >"$bootstrap_temp"
publish_bootstrap_file "$layout_marker"

install -d -m 0700 /mnt/persist/bootstrap /mnt/persist/keys/sops
password_path=/mnt/persist/bootstrap/login-password.hash
age_path=/mnt/persist/keys/sops/age.key
for path in "$password_path" "$age_path"; do
  if test -e "$path" || test -L "$path"; then
    if ! test -f "$path" || test -L "$path" || ! test -s "$path"; then
      echo "Refusing an invalid bootstrap file: $path" >&2
      exit 1
    fi
  fi
done
if ! test -e "$password_path"; then
  while true; do
    IFS= read -r -s -p "Password for $user: " first
    printf '\n'
    IFS= read -r -s -p 'Repeat password: ' second
    printf '\n'
    if test -n "$first" && test "$first" = "$second"; then
      break
    fi
    echo 'Passwords do not match or are empty. Try again.' >&2
  done
  bootstrap_temp=$(mktemp /mnt/persist/bootstrap/.login-password.hash.XXXXXXXX)
  printf '%s\n' "$first" | mkpasswd --method=yescrypt --stdin >"$bootstrap_temp"
  unset first second
  publish_bootstrap_file "$password_path"
fi
if ! test -e "$age_path"; then
  bootstrap_temp=$(mktemp /mnt/persist/keys/sops/.age.key.XXXXXXXX)
  age-keygen >"$bootstrap_temp"
  publish_bootstrap_file "$age_path"
fi
chmod 0600 "$password_path" "$age_path"
install -d -m 0700 -o 1000 -g 100 "/mnt/projects/$user" "/mnt/persist/home/$user" "/mnt/local/home/$user"
if [[ $checkout == "$repo" ]]; then
  bash "$repo/scripts/sync-checkout.sh" "$checkout" "/mnt/projects/$user/workstation"
else
  # The installer runs this helper from its frozen source and supplies the live
  # checkout only for Git history. Do not reread its settings or source files.
  bash "$repo/scripts/sync-checkout.sh" "$checkout" "/mnt/projects/$user/workstation" "$repo"
fi
chown -R 1000:100 "/mnt/projects/$user/workstation"
echo 'Bootstrap complete. Back up the age identity and recovery material before rebooting.'
