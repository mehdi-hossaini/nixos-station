{
  description = "Rust development and packaged builds";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    crane.url = "github:ipetkov/crane";
  };
  outputs =
    { nixpkgs, crane, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      project =
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          craneLib = crane.mkLib pkgs;
          args = {
            src = craneLib.cleanCargoSource ./.;
            strictDeps = true;
          };
          cargoArtifacts = craneLib.buildDepsOnly args;
        in
        {
          devShells.default = pkgs.mkShell {
            packages = with pkgs; [
              cargo
              rustc
              rust-analyzer
              rustfmt
              clippy
              pkg-config
            ];
            RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
            # Keep regenerable output outside hourly project snapshots. Hash
            # the canonical project path so separate projects never share it.
            shellHook = ''
              project_cache_key=$(printf '%s' "$(pwd -P)" | ${pkgs.coreutils}/bin/sha256sum)
              export CARGO_TARGET_DIR="''${XDG_CACHE_HOME:-$HOME/.cache}/cargo-targets/''${project_cache_key%% *}"
            '';
          };
          # Initialize Cargo and commit Cargo.lock before building these outputs.
          packages.default = craneLib.buildPackage (args // { inherit cargoArtifacts; });
          checks.clippy = craneLib.cargoClippy (args // { inherit cargoArtifacts; });
          checks.fmt = craneLib.cargoFmt args;
          checks.test = craneLib.cargoTest (args // { inherit cargoArtifacts; });
        };
    in
    {
      devShells = eachSystem (system: (project system).devShells);
      packages = eachSystem (system: (project system).packages);
      checks = eachSystem (system: (project system).checks);
    };
}
