{
  pkgs,
  host,
  settings,
}:
let
  russian =
    (host.extendModules {
      specialArgs.settings = settings // {
        keyboardLayout = "ru";
      };
    }).config;
  kdl = russian.home-manager.users.${settings.userName}.xdg.configFile."niri/config.kdl".text;
in
assert russian.services.xserver.xkb.layout == "ru,us";
assert russian.services.xserver.xkb.options == "grp:alt_shift_toggle";
assert pkgs.lib.hasInfix "layout \"ru,us\"" kdl;
pkgs.runCommand "workstation-keyboard-fallback"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.niri
    ];
  }
  ''
    python3 - ${russian.console.keyMap} <<'PY'
    import sys
    from pathlib import Path
    text = Path(sys.argv[1]).read_text()
    # Check the compiled console map, not just the source XKB symbols.
    assert "U+043" in text, "Russian group missing"
    assert "U+0079" in text or "+y " in text, "Latin y missing"
    assert "U+007a" in text or "+z " in text, "Latin z missing"
    rows = {}
    for line in text.splitlines():
        if line.startswith("keycode "):
            key, values = line.split("=", 1)
            rows[int(key.split()[1])] = values.split()
    assert rows[21][0] == "+U+043d", "Selected Russian group is not first"
    assert rows[21][32] == "+U+0079", "US fallback y unavailable"
    assert rows[44][32] == "+U+007a", "US fallback z unavailable"
    assert rows[56][1] == "ShiftL_Lock", "Alt+Shift cannot enter US group"
    PY
    niri validate --config ${pkgs.writeText "niri-russian.kdl" kdl}
    touch "$out"
  ''
