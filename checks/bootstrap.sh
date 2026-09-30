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
printf '%s\n%s\n' "$fixture_password" "$fixture_password" | bash "$repo/scripts/prepare-install.sh" "$user"
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
mkdir /top
mount -t btrfs -o subvolid=5 /dev/mapper/cryptroot /top
test "$(stat -c %a /top/@root-blank)" = 755
test -z "$(find /top/@root-blank -mindepth 1 -print -quit)"
test "$(btrfs property get -ts /top/@root-blank ro)" = ro=true
umount /top
