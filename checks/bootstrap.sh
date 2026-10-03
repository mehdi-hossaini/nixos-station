#!/usr/bin/env bash
# Run only inside the disposable Disko test VM, against its mounted target.
set -euo pipefail
umask 077
repo=$1
user=${2:?fixture username required}
mkdir -p /tmp/bootstrap-no-nix
printf '#!/usr/bin/env bash\necho "Bootstrap must use the supplied username, not reread Nix settings." >&2\nexit 1\n' >/tmp/bootstrap-no-nix/nix
chmod +x /tmp/bootstrap-no-nix/nix
export PATH="/tmp/bootstrap-no-nix:$PATH"
mountpoint -q /mnt
test ! -e /mnt/persist/bootstrap/login-password.hash
test ! -e /mnt/persist/keys/sops/age.key
hash=/mnt/persist/bootstrap/login-password.hash
key=/mnt/persist/keys/sops/age.key
fixture_password='  fixture password  '
mkdir /top
mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top

# Interrupt the real bootstrap after subvolume creation, before read-only
# publication. A rerun must finish the empty template without recreating it.
mkdir /tmp/bootstrap-template-stubs
cat >/tmp/bootstrap-template-stubs/btrfs <<'STUB'
#!/usr/bin/env bash
if [[ ${1:-} == property && ${2:-} == set && ${3:-} == -ts &&
  ${4:-} == */@root-blank && ${5:-} == ro && ${6:-} == true ]]; then
  echo 'Fixture interruption before the read-only property was set.' >&2
  exit 1
fi
exec "$BOOTSTRAP_REAL_BTRFS" "$@"
STUB
chmod +x /tmp/bootstrap-template-stubs/btrfs
real_btrfs=$(command -v btrfs)
if PATH="/tmp/bootstrap-template-stubs:$PATH" BOOTSTRAP_REAL_BTRFS="$real_btrfs" \
  bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'Interrupted template preparation unexpectedly succeeded.' >&2
  exit 1
fi
btrfs subvolume show /top/@root-blank >/dev/null
test "$(btrfs property get -ts /top/@root-blank ro)" = ro=false
test ! -e /top/.workstation-layout-v1
test ! -e "$hash"
test ! -e "$key"
template_id=$(btrfs subvolume show /top/@root-blank | sed -n 's/^[[:space:]]*Subvolume ID:[[:space:]]*//p')
# Also recover the private creation mode if the interruption preceded chmod.
chmod 0700 /top/@root-blank
printf '%s\n%s\n' "$fixture_password" "$fixture_password" | bash "$repo/scripts/prepare-install.sh" "$user"
test "$(btrfs subvolume show /top/@root-blank | sed -n 's/^[[:space:]]*Subvolume ID:[[:space:]]*//p')" = "$template_id"
test "$(stat -c %a "$hash")" = 600
test "$(stat -c %a "$key")" = 600
test "$(printf '%s\n' "$fixture_password" | mkpasswd --method=yescrypt --salt "$(cat "$hash")" --stdin)" = "$(cat "$hash")"
test "$(printf '%s\n' 'fixture password' | mkpasswd --method=yescrypt --salt "$(cat "$hash")" --stdin)" != "$(cat "$hash")"
recipient=$(age-keygen -y "$key")
printf 'round trip\n' | age -r "$recipient" >/tmp/fixture.age
test "$(age -d -i "$key" /tmp/fixture.age)" = 'round trip'
before=$(sha256sum "$hash" "$key")
bash "$repo/scripts/prepare-install.sh" "$user" </dev/null
test "$(sha256sum "$hash" "$key")" = "$before"

# A failed durability write must preserve the already published layout marker.
marker_before=$(sha256sum /top/.workstation-layout-v1)
cat >/tmp/bootstrap-template-stubs/sync <<'STUB'
#!/usr/bin/env bash
if [[ ${1:-} == -f && ${2:-} == */.workstation-layout-v1.* ]]; then
  echo 'Fixture layout marker write failure.' >&2
  exit 1
fi
exec "$BOOTSTRAP_REAL_SYNC" "$@"
STUB
chmod +x /tmp/bootstrap-template-stubs/sync
rm /tmp/bootstrap-template-stubs/btrfs
real_sync=$(command -v sync)
if PATH="/tmp/bootstrap-template-stubs:$PATH" BOOTSTRAP_REAL_SYNC="$real_sync" \
  bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'Failed layout marker publication unexpectedly succeeded.' >&2
  exit 1
fi
test "$(sha256sum /top/.workstation-layout-v1)" = "$marker_before"
test "$(sha256sum "$hash" "$key")" = "$before"
test -z "$(find /top -maxdepth 1 -name '.workstation-layout-v1.????????' -print -quit)"
bash "$repo/scripts/prepare-install.sh" "$user" </dev/null

# An interrupted writable template is resumable only while it is empty and
# remains a real Btrfs subvolume. Refusals must not publish a layout marker.
btrfs property set -ts /top/@root-blank ro false
printf 'unexpected\n' >/top/@root-blank/unexpected
if bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'A nonempty template unexpectedly passed bootstrap.' >&2
  exit 1
fi
test "$(btrfs property get -ts /top/@root-blank ro)" = ro=false
test "$(sha256sum /top/.workstation-layout-v1)" = "$marker_before"
rm /top/@root-blank/unexpected
btrfs property set -ts /top/@root-blank ro true
mv /top/@root-blank /top/@root-blank.saved
mkdir /top/@root-blank
if bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'An ordinary directory unexpectedly passed as a root template.' >&2
  exit 1
fi
rmdir /top/@root-blank
ln -s @root-blank.saved /top/@root-blank
if bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'A symlink unexpectedly passed as a root template.' >&2
  exit 1
fi
rm /top/@root-blank
mv /top/@root-blank.saved /top/@root-blank
test "$(sha256sum /top/.workstation-layout-v1)" = "$marker_before"
printf 'wrong\n' >/top/.workstation-layout-v1
if bash "$repo/scripts/prepare-install.sh" "$user" </dev/null; then
  echo 'An invalid layout marker unexpectedly passed bootstrap.' >&2
  exit 1
fi
test "$(cat /top/.workstation-layout-v1)" = wrong
printf '%s\n' niri-workstation-v1 >/top/.workstation-layout-v1
test "$(sha256sum "$hash" "$key")" = "$before"

# A failing generator must not publish a partial credential or replace the
# other credential. Test both publication points, then resume successfully.
mkdir /tmp/bootstrap-stubs
for command in age-keygen mkpasswd; do
  printf '#!/usr/bin/env bash\nprintf broken\nexit 1\n' >"/tmp/bootstrap-stubs/$command"
  chmod +x "/tmp/bootstrap-stubs/$command"
  if [[ $command == age-keygen ]]; then
    credential=$key
    other=$hash
  else
    credential=$hash
    other=$key
  fi
  mv "$credential" /tmp/saved-bootstrap-credential
  preserved=$(sha256sum "$other")
  if printf '%s\n%s\n' "$fixture_password" "$fixture_password" |
    PATH="/tmp/bootstrap-stubs:$PATH" bash "$repo/scripts/prepare-install.sh" "$user"; then
    echo 'A failed generator unexpectedly succeeded.' >&2
    exit 1
  fi
  test ! -e "$credential"
  test "$(sha256sum "$other")" = "$preserved"
  test -z "$(find "${credential%/*}" -name '.*.????????' -print -quit)"
  mv /tmp/saved-bootstrap-credential "$credential"
done
bash "$repo/scripts/prepare-install.sh" "$user" </dev/null
test "$(sha256sum "$hash" "$key")" = "$before"
test "$(stat -c %a /top/@root-blank)" = 755
test -z "$(find /top/@root-blank -mindepth 1 -print -quit)"
test "$(btrfs property get -ts /top/@root-blank ro)" = ro=true
umount /top
