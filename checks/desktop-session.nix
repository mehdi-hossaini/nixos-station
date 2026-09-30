{
  pkgs,
  inputs,
  settings,
}:
let
  session = import ../lib/software-session.nix { inherit pkgs; };
  user = settings.userName;
  command = pkgs.writeShellScript "workstation-desktop-test-command" ''
    export XDG_RUNTIME_DIR=/run/user/1000
    export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
    export NIRI_SOCKET
    NIRI_SOCKET=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'niri.*.sock' -print -quit)
    exec "$@"
  '';
in
pkgs.testers.runNixOSTest {
  name = "workstation-desktop-session";
  enableOCR = true;
  nodes.machine = { lib, ... }: {
    imports = [
      inputs.home-manager.nixosModules.home-manager
      ../modules/nixos/desktop.nix
    ];
    _module.args = { inherit settings; };
    users.users.${user} = {
      isNormalUser = true;
      uid = 1000;
      password = "fixture";
    };
    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
      extraSpecialArgs = { inherit settings; };
      users.${user} = {
        imports = [
          inputs.obtain.homeManagerModules.default
          ../modules/home
        ];
        xdg.configFile."niri/config.kdl".text = lib.mkAfter ''
          environment { WSL_DISTRO_NAME null; }
        '';
      };
    };
    programs.zsh.enable = true;
    services.greetd.settings.default_session.command =
      lib.mkForce "${pkgs.tuigreet}/bin/tuigreet --time --cmd ${session}";
    systemd.user.services.niri.environment.WSL_DISTRO_NAME = "workstation-test";
    virtualisation = {
      memorySize = 3072;
      cores = 2;
      graphics = true;
      qemu.options = [
        "-vga none"
        "-device virtio-vga,xres=1280,yres=800"
      ];
    };
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("home-manager-${user}.service")
    machine.wait_for_unit("greetd.service")
    machine.wait_for_text("Username", timeout=120)
    machine.send_chars("${user}\n")
    machine.wait_for_text("Password")
    machine.send_chars("fixture\n")
    machine.wait_until_succeeds("pgrep -u ${user} -x niri", timeout=120)
    user_command = "runuser -u ${user} -- ${command}"
    machine.wait_until_succeeds(f"{user_command} ${pkgs.niri}/bin/niri msg --json windows | grep workstation-terminal", timeout=120)
    pid = machine.succeed("pgrep -u ${user} -x niri").strip()
    machine.succeed("systemctl restart home-manager-${user}.service")
    assert machine.succeed("pgrep -u ${user} -x niri").strip() == pid
    machine.succeed(f"{user_command} ${pkgs.niri}/bin/niri msg action spawn -- swaylock -f")
    locker = "pgrep -u ${user} -f '(^|/)[.]?swaylock(-wrapped)?([ ]|$)'"
    machine.wait_until_succeeds(locker, timeout=30)
    machine.wait_until_succeeds("journalctl -b -o cat | grep 'locking session'", timeout=30)
    machine.send_chars("incorrect\n")
    machine.wait_until_succeeds("journalctl -b -o cat | grep -F 'pam_unix(swaylock:auth): authentication failure'", timeout=30)
    machine.sleep(3)
    machine.succeed(locker)
    machine.send_chars("fixture\n")
    machine.wait_until_succeeds("journalctl -b -o cat | grep 'unlocking session'", timeout=30)
    machine.succeed(f"{user_command} ${pkgs.niri}/bin/niri msg --json windows | grep workstation-terminal")
    machine.screenshot("desktop-unlocked")
  '';
}
