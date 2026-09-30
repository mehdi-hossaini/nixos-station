default:
    @just --list

fmt:
    bash scripts/run-bounded.sh nix fmt --max-jobs 2 --cores 4

check:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh bash scripts/check-all.sh .#checks.x86_64-linux --max-jobs 2 --cores 4 -L

check-fast:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh nix build .#checks.x86_64-linux.fast --no-link --no-update-lock-file --max-jobs 2 --cores 4 -L

# Python lint and regression tests without profile builds or virtual machines.
check-python:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh nix build .#checks.x86_64-linux.python .#checks.x86_64-linux.installer --no-link --no-update-lock-file --max-jobs 2 --cores 4 -L

# Update the workstation inputs and regenerate their coupled graphics metadata.
update:
    bash scripts/run-bounded.sh nix flake update --max-jobs 2 --cores 4
    just graphics-update

graphics-update:
    bash scripts/run-bounded.sh nix develop --no-update-lock-file --max-jobs 2 --cores 4 --command python3 scripts/graphics_metadata.py update

palette-update:
    bash scripts/run-bounded.sh nix develop --no-update-lock-file --max-jobs 2 --cores 4 --command python3 scripts/palette-preview.py

install:
    sudo bash scripts/install.sh

build:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh nix build .#nixosConfigurations.workstation.config.system.build.toplevel --no-update-lock-file --max-jobs 2 --cores 4 -L

test:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh nix build .#checks.x86_64-linux.root-reset .#checks.x86_64-linux.boot .#checks.x86_64-linux.session-lifecycle .#checks.x86_64-linux.desktop-session .#checks.x86_64-linux.backup-restore --no-link --no-update-lock-file --max-jobs 2 --cores 4 -L

diff:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh nh os build @local-flake@ --hostname workstation --max-jobs 2 --cores 4

switch:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh sudo nixos-rebuild switch --flake .#workstation --max-jobs 2 --cores 4

boot:
    bash scripts/run-bounded.sh bash scripts/with-local-flake.sh sudo nixos-rebuild boot --flake .#workstation --max-jobs 2 --cores 4
