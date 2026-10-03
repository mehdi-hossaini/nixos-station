{
  description = "Developer workstation: Niri, encrypted Btrfs and impermanence";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    obtain = {
      url = "github:mehdi-hossaini/obtain/codex/release-only";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    impermanence = {
      url = "github:nix-community/impermanence";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      flake-parts,
      ...
    }:
    let
      settings = import ./settings.nix;
      system = "x86_64-linux";
      graphicsProfileNames = [
        "mesa"
        "virtual"
        "nvidia"
        "intel-prime"
        "amd-prime"
      ];
      checkGroups = {
        fast = [
          "pre-commit"
          "treefmt"
          "lint"
          "shell"
          "python"
          "workflow"
          "documentation"
          "niri"
          "installer"
          "settings"
          "service-scripts"
          "desktop-profiles"
          "terminal-workflow"
          "optional-tools"
          "palette"
          "keyboard"
          "local-flake"
        ];
        graphics-profiles = map (name: "graphics-profile-${name}") graphicsProfileNames;
        graphics-integration = map (name: "graphics-integration-${name}") graphicsProfileNames;
      };
      mkWorkstation =
        settings:
        nixpkgs.lib.nixosSystem {
          inherit system;
          specialArgs = { inherit inputs settings; };
          modules = [
            inputs.disko.nixosModules.disko
            inputs.impermanence.nixosModules.impermanence
            inputs.sops-nix.nixosModules.sops
            inputs.home-manager.nixosModules.home-manager
            ./hosts/workstation
          ];
        };
      # Shared checks must not inherit local hardware trials, credentials or identity.
      testSettings = (import ./lib/default-settings.nix) // {
        disk = "/dev/disk/by-id/test-fixture";
        hostName = "workstation-test";
        userName = "tester";
        timeZone = "UTC";
      };
      testHost = mkWorkstation testSettings;
      previewHost =
        (mkWorkstation (
          testSettings
          // {
            hostName = "workstation-preview";
            userName = "preview";
          }
        )).extendModules
          {
            modules = [ ./modules/nixos/preview-vm.nix ];
          };
    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ system ];
      imports = [
        inputs.treefmt-nix.flakeModule
        inputs.git-hooks.flakeModule
      ];
      flake = {
        lib.checkGroups =
          assert builtins.all (name: builtins.hasAttr name self.checks.${system}) (
            nixpkgs.lib.concatLists (builtins.attrValues checkGroups)
          );
          checkGroups;
        lib.installationKeyboard = {
          inherit (self.nixosConfigurations.workstation.config.console) useXkbConfig;
          inherit (self.nixosConfigurations.workstation.config.services.xserver.xkb) layout options;
        };
        lib.installationGraphics = import ./lib/graphics-plan.nix self.nixosConfigurations.workstation.config;
        lib.graphicsMetadata = import ./lib/graphics-metadata.nix {
          inherit (self.nixosConfigurations.workstation) pkgs;
          host = self.nixosConfigurations.workstation.config;
          nixpkgsRev = inputs.nixpkgs.rev;
        };
        nixosConfigurations = {
          # A fresh clone has no disk choice yet. Keep flake checks evaluable
          # with the fixture until a local installer or manual choice exists.
          workstation =
            if !builtins.pathExists ./installation.json && settings.disk == "/dev/disk/by-id/CHANGE-ME" then
              testHost
            else
              mkWorkstation settings;
          workstation-test = testHost;
          preview-terminal = previewHost;
        };
        templates = {
          default = self.templates.minimal;
          minimal = {
            path = ./templates/minimal;
            description = "Small flake devShell";
          };
          rust = {
            path = ./templates/rust;
            description = "Rust development and Crane packaging";
          };
          python = {
            path = ./templates/python;
            description = "Python and uv development";
          };
          web = {
            path = ./templates/web;
            description = "Node and pnpm development";
          };
        };
      };
      perSystem =
        { pkgs, config, ... }:
        let
          provenance = pkgs.writeText "graphics-provenance.json" (builtins.toJSON self.lib.graphicsMetadata);
          graphicsProfiles = import ./checks/graphics-profiles.nix {
            inherit pkgs;
            settings = testSettings;
            host = testHost;
          };
          group =
            name: members:
            pkgs.linkFarm name (
              map (member: {
                name = pkgs.lib.removePrefix "graphics-profile-" member;
                path = self.checks.${system}.${member};
              }) members
            );
        in
        {
          pre-commit.settings.hooks = {
            nixfmt.enable = true;
            statix.enable = true;
            deadnix.enable = true;
            shellcheck = {
              enable = true;
              # ShellCheck does not support Zsh; terminal-workflow uses zsh -n
              # and runtime checks for the sourced shell integration instead.
              excludes = [ "\\.zsh$" ];
            };
            ruff.enable = true;
            ruff-format.enable = true;
            actionlint.enable = true;
          };
          treefmt = {
            projectRootFile = "flake.nix";
            programs.nixfmt.enable = true;
            programs.shfmt.enable = true;
            programs.ruff-format.enable = true;
            settings.formatter.shfmt.options = [
              "-i"
              "2"
            ];
          };
          devShells.default = pkgs.mkShell {
            shellHook = config.pre-commit.installationScript;
            packages = with pkgs; [
              git
              nixd
              nixfmt
              nix-tree
              nix-diff
              statix
              deadnix
              shellcheck
              shfmt
              ruff
              actionlint
              sops
              age
              just
              btrfs-progs
              cryptsetup
              mkpasswd
              util-linux
              python3
            ];
          };
          devShells.installer = pkgs.mkShell {
            packages = with pkgs; [
              gum
              kbd
              kmod
              python3
              git
              gnutar
              btrfs-progs
              cryptsetup
              mkpasswd
              age
              util-linux
            ];
            WORKSTATION_ZONEINFO = "${pkgs.tzdata}/share/zoneinfo";
            WORKSTATION_XKB = "${pkgs.xkeyboard_config}/share/X11/xkb";
            WORKSTATION_BLKID_LIBRARY = "${pkgs.util-linux.lib}/lib/libblkid.so.1";
          };
          apps.preview-terminal = {
            type = "app";
            program = "${self.packages.${system}.preview-terminal}/bin/workstation-preview-terminal";
            meta.description = "Boot the terminal-first workstation preview VM";
          };
          packages = {
            preview-terminal = pkgs.writeShellApplication {
              name = "workstation-preview-terminal";
              runtimeInputs = [ pkgs.coreutils ];
              text = ''
                state_dir="''${XDG_CACHE_HOME:-$HOME/.cache}/workstation/preview-terminal"
                mkdir -p "$state_dir"
                export NIX_DISK_IMAGE="''${NIX_DISK_IMAGE:-$state_dir/system.qcow2}"
                preview_tmp=$(mktemp -d -t workstation-preview.XXXXXXXX)
                trap 'rm -rf "$preview_tmp"' EXIT
                export TMPDIR="$preview_tmp" USE_TMPDIR=1
                export LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=wayland
                echo "Starting Niri terminal-first VM (login: preview / preview)."
                echo "Virtual disk: $NIX_DISK_IMAGE"
                ${previewHost.config.system.build.vm}/bin/run-workstation-preview-vm "$@"
              '';
            };
            graphics-support = pkgs.runCommand "graphics-support" { nativeBuildInputs = [ pkgs.python3 ]; } ''
              python3 ${./scripts/graphics_metadata.py} check ${./hardware/graphics} ${provenance}
              cp -r ${./hardware/graphics} "$out"
            '';
            nvidia-support = self.packages.${system}.graphics-support;
            # Maintainer/release build only. Installers consume the bundled data above.
            graphics-metadata-generated =
              let
                host = self.nixosConfigurations.workstation.config;
                driver = host.hardware.nvidia.package;
                stack = pkgs.writeText "graphics-stack.json" (builtins.toJSON self.lib.graphicsMetadata.stack);
              in
              pkgs.runCommand "graphics-metadata-generated"
                {
                  nativeBuildInputs = [
                    pkgs.python3
                    pkgs.libarchive
                  ];
                }
                ''
                  mkdir "$out"
                  python3 ${./scripts/graphics-support.py} ${pkgs.mesa.src} \
                    ${host.boot.kernelPackages.kernel.src} ${pkgs.libdrm}/share/libdrm/amdgpu.ids \
                    ${stack} | python3 -m json.tool --sort-keys > "$out/graphics-support.json"
                  skip=$(sed -n 's/^skip=//p' ${driver.src})
                  test -n "$skip"
                  mkdir unpacked
                  cd unpacked
                  tail -n +"$skip" ${driver.src} | bsdtar xf - supported-gpus/supported-gpus.json
                  python3 -m json.tool --sort-keys supported-gpus/supported-gpus.json > "$out/supported-gpus.json"
                  python3 ${./scripts/graphics_metadata.py} prepare "$out" ${provenance}
                '';
            root-reset = import ./lib/root-reset.nix { inherit pkgs; };
          };
          checks =
            (import ./checks/quality.nix {
              inherit pkgs;
              src = self;
            })
            // pkgs.lib.mapAttrs' (name: profile: {
              name = "graphics-profile-${name}";
              value = profile;
            }) graphicsProfiles
            // pkgs.lib.mapAttrs' (name: profile: {
              name = "graphics-integration-${name}";
              value = pkgs.runCommand "graphics-integration-${name}" { nativeBuildInputs = [ pkgs.python3 ]; } ''
                python3 ${./checks/graphics.py} ${./scripts} ${self.packages.${system}.graphics-support} \
                  ${profile} --profile ${name} GraphicsTests.test_actual_nix_projections_match_resolved_choices
                touch "$out"
              '';
            }) graphicsProfiles
            // {
              fast = group "workstation-fast-checks" checkGroups.fast;
              graphics-metadata-source = pkgs.runCommand "graphics-metadata-source-check" { } ''
                for file in graphics-support.json supported-gpus.json manifest.json; do
                  cmp ${self.packages.${system}.graphics-support}/"$file" \
                    ${self.packages.${system}.graphics-metadata-generated}/"$file"
                done
                touch "$out"
              '';
              palette = pkgs.runCommand "workstation-palette-preview" { nativeBuildInputs = [ pkgs.python3 ]; } ''
                python3 ${./scripts/palette-preview.py} --check ${self}
                touch "$out"
              '';
              local-flake =
                pkgs.runCommand "workstation-local-flake-snapshot"
                  {
                    nativeBuildInputs = [
                      pkgs.python3
                      pkgs.git
                      pkgs.gnutar
                      pkgs.diffutils
                      pkgs.just
                      pkgs.nh
                    ];
                  }
                  ''
                    python3 ${./checks/local-flake.py} ${./scripts/with-local-flake.sh} ${./.gitignore} ${./scripts/sync-checkout.sh} ${./scripts/check-all.sh} ${./justfile} ${./scripts/run-bounded.sh}
                    touch "$out"
                  '';
              graphics-profiles = group "graphics-profiles" checkGroups.graphics-profiles;
              desktop-profiles = import ./checks/desktop-profiles.nix {
                inherit pkgs;
                settings = testSettings;
                host = testHost;
              };
              terminal-workflow = import ./checks/terminal-workflow.nix {
                inherit pkgs;
                settings = testSettings;
                host = testHost;
              };
              optional-tools = import ./checks/optional-tools.nix {
                inherit pkgs;
                settings = testSettings;
                host = testHost;
              };
              graphics-vm = import ./checks/graphics-vm.nix {
                inherit pkgs;
                support = self.packages.${system}.graphics-support;
              };
              installer =
                pkgs.runCommand "workstation-installer-tests"
                  {
                    WORKSTATION_BLKID_LIBRARY = "${pkgs.util-linux.lib}/lib/libblkid.so.1";
                    nativeBuildInputs = [
                      pkgs.python3
                      pkgs.gum
                    ];
                  }
                  ''
                    python3 ${./checks/installer.py} ${./scripts}/install.py
                    python3 ${./checks/prune-root.py} ${./scripts}/prune-root.py
                    python3 ${./checks/graphics.py} ${./scripts} ${self.packages.${system}.graphics-support}
                    python3 ${./checks/graphics-metadata.py} ${./scripts} ${
                      self.packages.${system}.graphics-support
                    } ${provenance}
                    touch $out
                  '';
              settings = import ./checks/settings.nix {
                inherit pkgs;
                host = testHost;
                settings = testSettings;
              };
              keyboard = import ./checks/keyboard.nix {
                inherit pkgs;
                host = testHost;
                settings = testSettings;
              };
              service-scripts = import ./checks/service-scripts.nix {
                inherit pkgs;
                host = testHost;
              };
              graphics-integration = group "graphics-integration-tests" checkGroups.graphics-integration;
              boot = import ./checks/boot.nix {
                inherit pkgs inputs;
                settings = testSettings;
                host = testHost.extendModules {
                  specialArgs.settings = testSettings // {
                    secretsFile = null;
                    backupRepository = null;
                    nvidia = false;
                    graphics = null;
                    cpu = "generic";
                    keyboardLayout = "de";
                    obtain = true;
                  };
                };
              };
              root-reset = import ./checks/root-reset.nix { inherit pkgs; };
              session-lifecycle = import ./checks/session-lifecycle.nix {
                inherit pkgs;
                host = testHost;
                settings = testSettings;
              };
              desktop-session = import ./checks/desktop-session.nix {
                inherit pkgs inputs;
                settings = testSettings;
              };
              backup-restore = import ./checks/backup-restore.nix {
                inherit pkgs inputs;
                host = testHost;
                settings = testSettings;
              };
              niri = pkgs.runCommand "niri-config-check" { nativeBuildInputs = [ pkgs.niri ]; } ''
                niri validate --config ${
                  testHost.config.home-manager.users.${testSettings.userName}.xdg.configFile."niri/config.kdl".source
                }
                touch $out
              '';
            };
        };
    };
}
