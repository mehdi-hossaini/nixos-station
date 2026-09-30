#!/usr/bin/env bash
set -euo pipefail

# Receive one captured flake's checks attribute, then release each evaluator
# before starting the next check. Nix still reuses completed store outputs.
checks=${1:?Pass a flake checks attribute, e.g. .#checks.x86_64-linux}
shift
nix build "$checks.fast" --no-link --no-update-lock-file "$@"
# Aggregate aliases use the same declared members as the flake's link farms.
# Their individual checks are discovered below, avoiding matrix-wide evaluation.
groups=$(nix eval --raw --no-update-lock-file "${checks%#*}#lib.checkGroups" \
  --apply 'groups: builtins.concatStringsSep "\n" (builtins.attrNames groups ++ groups.fast)')
names=$(nix eval --raw --no-update-lock-file "$checks" \
  --apply 'checks: builtins.concatStringsSep "\n" (builtins.attrNames checks)')
while IFS= read -r name; do
  if [[ $'\n'$groups$'\n' == *$'\n'"$name"$'\n'* ]]; then continue; fi
  echo "Checking $name"
  nix build "$checks.$name" --no-link --no-update-lock-file "$@"
done <<<"$names"
