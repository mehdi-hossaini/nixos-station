#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=$1
destination=$2
source=${3:-}
if ! test -d "$repo/.git" || test -L "$repo/.git"; then
  echo 'Installation requires a standalone Git checkout.' >&2
  exit 1
fi
if test -L "$destination" || { test -e "$destination" && ! test -d "$destination"; }; then
  echo 'Refusing an invalid destination checkout.' >&2
  exit 1
fi
staging=$(mktemp -d "${destination%/*}/.workstation-checkout.XXXXXXXX")
cleanup() { rm -rf -- "$staging"; }
trap cleanup EXIT
if test -n "$source"; then
  if ! test -d "$source" || test -L "$source" || test -e "$source/.git" || test -L "$source/.git"; then
    echo 'Expected a filtered installation source snapshot without Git metadata.' >&2
    exit 1
  fi
  cp -a -- "$source" "$staging/workstation"
else
  bash "$repo/scripts/with-local-flake.sh" --snapshot-only "$staging/workstation"
fi
# Retain the live checkout's index/history so normal Git maintenance works.
cp -a -- "$repo/.git" "$staging/workstation/.git"
if test -e "$destination"; then
  difference=0
  diff -qr -- "$staging/workstation" "$destination" >/dev/null || difference=$?
  if ((difference == 0)); then exit 0; fi
  if ((difference != 1)); then exit "$difference"; fi
  backup="$destination.before-resume.$(date -u +%Y%m%dT%H%M%S%N)"
  mv -T -- "$destination" "$backup"
  # If publishing fails, put the previous checkout back immediately.
  if ! mv -T -- "$staging/workstation" "$destination"; then
    mv -T -- "$backup" "$destination"
    exit 1
  fi
  echo "Updated workstation checkout; previous files preserved at $backup"
else
  mv -T -- "$staging/workstation" "$destination"
fi
