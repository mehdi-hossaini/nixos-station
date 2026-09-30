{
  pkgs,
  host,
  settings,
}:
let
  login = host.config.systemd.services.greetd;
  rename =
    builtins.replaceStrings
      [ "home-manager-${settings.userName}.service" ]
      [ "fixture-home.service" ];
in
pkgs.testers.runNixOSTest {
  name = "workstation-session-lifecycle";
  nodes.machine = _: {
    console.keyMap =
      (host.extendModules {
        specialArgs.settings = settings // {
          keyboardLayout = "ru";
        };
      }).config.console.keyMap;
    systemd.user.slices.workstation-evaluation.sliceConfig =
      host.config.systemd.user.slices.workstation-evaluation.sliceConfig;
    systemd.services.fixture-home = {
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = "test ! -e /run/fixture-home-fails";
    };
    # Exercise the production dependencies and startup guard without a GPU,
    # real login session or a second copy of the dependency policy.
    systemd.services.fixture-login = {
      wants = map rename login.wants;
      after = map rename login.after;
      requires = map rename login.requires;
      serviceConfig = {
        ExecStartPre = rename login.serviceConfig.ExecStartPre;
        ExecStart = "${pkgs.coreutils}/bin/sleep infinity";
      };
    };
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("systemctl start fixture-login")
    pid = machine.succeed("systemctl show -P MainPID fixture-login").strip()
    assert pid != "0"
    machine.succeed("systemctl restart fixture-home")
    assert machine.succeed("systemctl show -P MainPID fixture-login").strip() == pid
    machine.succeed("touch /run/fixture-home-fails")
    machine.fail("systemctl restart fixture-home")
    machine.succeed("systemctl is-active --quiet fixture-login")
    machine.succeed("openvt -c 2 -s -- sh -c 'head -n 2 > /run/keyboard-input' &")
    machine.send_key("y")
    machine.send_key("ret")
    machine.send_key("alt-shift")
    machine.send_key("y")
    machine.send_key("ret")
    machine.wait_until_succeeds("test $(wc -l < /run/keyboard-input) -eq 2")
    assert machine.succeed("cat /run/keyboard-input").splitlines() == ["н", "y"]
    # Concurrent foreground commands must be descendants of one finite
    # aggregate slice.
    machine.succeed("loginctl enable-linger root; systemctl start user@0.service")
    user_env = "XDG_RUNTIME_DIR=/run/user/0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus"
    for name in ["one", "two"]:
        machine.succeed(f"env {user_env} bash ${../scripts/run-bounded.sh} sh -c 'echo $$ > /run/evaluation-{name}; sleep 120' >/run/evaluation-{name}.log 2>&1 &")
        machine.wait_for_file(f"/run/evaluation-{name}")
        machine.succeed(f"grep workstation-evaluation.slice /proc/$(cat /run/evaluation-{name})/cgroup")
    machine.succeed(f"env {user_env} systemctl --user show workstation-evaluation.slice -P MemoryMax | grep -v infinity")
    machine.succeed(f"env {user_env} systemctl --user stop workstation-evaluation.slice")
    assert machine.succeed("systemctl show -P MainPID fixture-login").strip() == pid
    machine.succeed("systemctl stop fixture-login")
    machine.fail("systemctl start fixture-login")
    machine.succeed("rm /run/fixture-home-fails; systemctl reset-failed fixture-home fixture-login")
    machine.succeed("systemctl start fixture-home fixture-login")
    machine.succeed("systemctl is-active --quiet fixture-login")
  '';
}
