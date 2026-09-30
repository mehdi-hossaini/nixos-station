{ pkgs, src }:
{
  documentation =
    pkgs.runCommand "workstation-documentation-links" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python3 ${./documentation.py} --self-test
        python3 ${./documentation.py} ${src}
        touch "$out"
      '';
  lint =
    pkgs.runCommand "workstation-nix-lint"
      {
        nativeBuildInputs = [
          pkgs.statix
          pkgs.deadnix
        ];
      }
      ''
        cd ${src}
        statix check .
        deadnix --fail .
        touch "$out"
      '';
  shell =
    pkgs.runCommand "workstation-shellcheck"
      {
        nativeBuildInputs = [ pkgs.shellcheck ];
      }
      ''
        shellcheck ${src}/scripts/*.sh
        shellcheck ${src}/checks/*.sh
        touch "$out"
      '';
  python =
    pkgs.runCommand "workstation-python-lint"
      {
        nativeBuildInputs = [ pkgs.ruff ];
      }
      ''
        cd ${src}
        ruff check --no-cache scripts checks
        ruff format --check --no-cache scripts checks
        touch "$out"
      '';
  workflow =
    pkgs.runCommand "workstation-workflow-lint"
      {
        nativeBuildInputs = [
          pkgs.actionlint
          pkgs.shellcheck
        ];
      }
      ''
        actionlint ${src}/.github/workflows/*.yml
        touch "$out"
      '';
}
