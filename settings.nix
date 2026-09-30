# Shared defaults are also used by isolated validation fixtures.
# Put Nix-only installation overrides (such as an encrypted secrets path) here.
let
  installation = ./installation.json;
in
(import ./lib/default-settings.nix)
// {
  # secretsFile = ./secrets/workstation.yaml;
}
// (
  if builtins.pathExists installation then builtins.fromJSON (builtins.readFile installation) else { }
)
