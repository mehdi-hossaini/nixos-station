#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
  echo 'Expected a command to run under the workstation resource budget.' >&2
  exit 2
fi

# Foreground evaluation runs outside nix-daemon.service. Keep it in its own
# shared cgroup so concurrent evaluations cannot each claim a full allowance.
if command -v systemd-run >/dev/null && command -v systemctl >/dev/null &&
  systemctl --user show-environment >/dev/null 2>&1; then
  # systemd synthesizes missing slice units. Runtime properties also protect
  # this command before the declarative slice has been installed by reboot.
  systemctl --user start workstation-evaluation.slice
  systemctl --user set-property --runtime workstation-evaluation.slice \
    CPUWeight=25 IOWeight=25 MemoryHigh=15% MemoryMax=20% MemorySwapMax=5%
  exec systemd-run --user --scope --slice=workstation-evaluation.slice --collect --quiet \
    --expand-environment=no \
    -- "$@"
fi

# CI and installer environments may have no user manager.
exec "$@"
