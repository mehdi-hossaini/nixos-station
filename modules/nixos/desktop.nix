{ pkgs, settings, ... }:
let
  keyboard = import ../../lib/keyboard.nix settings.keyboardLayout;
in
{
  programs.niri = {
    enable = true;
    useNautilus = false;
  };
  programs.dconf.enable = true;
  services.greetd = {
    enable = true;
    settings.default_session = {
      command = "${pkgs.tuigreet}/bin/tuigreet --time --cmd niri-session";
      user = "greeter";
    };
  };
  security.pam.services = {
    swaylock = { };
    greetd.enableGnomeKeyring = true;
  };
  services.gnome.gnome-keyring.enable = true;
  security.polkit.enable = true;
  security.rtkit.enable = true;
  environment.systemPackages = [ pkgs.brightnessctl ];
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    wireplumber.enable = true;
  };
  services.xserver.xkb = { inherit (keyboard) layout options; };
  xdg.portal.extraPortals = [ pkgs.xdg-desktop-portal-gtk ];
  fonts.packages = with pkgs; [
    dejavu_fonts
    nerd-fonts.symbols-only
    noto-fonts
    noto-fonts-color-emoji
  ];
  # Wait for home activation at startup without binding the login manager's
  # lifetime to it: Requires would stop greetd during home-manager restarts.
  # The startup check still refuses login when home activation has failed.
  systemd.services.greetd = {
    wants = [ "home-manager-${settings.userName}.service" ];
    after = [ "home-manager-${settings.userName}.service" ];
    serviceConfig.ExecStartPre = "${pkgs.systemd}/bin/systemctl is-active --quiet home-manager-${settings.userName}.service";
  };
}
