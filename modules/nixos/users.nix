{
  settings,
  pkgs,
  inputs,
  ...
}:
{
  users.mutableUsers = false;
  users.users.root.hashedPassword = "!";
  users.users.${settings.userName} = {
    isNormalUser = true;
    uid = 1000;
    group = "users";
    extraGroups = [
      "wheel"
      "networkmanager"
    ];
    shell = pkgs.zsh;
    hashedPasswordFile = "/persist/bootstrap/login-password.hash";
    # The optional container module owns the fixed rootless ID mappings.
    autoSubUidGidRange = false;
  };
  programs.zsh = {
    enable = true;
    # Home Manager initializes completion once, before loading fzf-tab.
    enableGlobalCompInit = false;
  };
  home-manager = {
    useGlobalPkgs = true;
    useUserPackages = true;
    extraSpecialArgs = { inherit settings; };
    sharedModules = [ inputs.obtain.homeManagerModules.default ];
    users.${settings.userName} = import ../home;
  };
}
