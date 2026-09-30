{ lib, settings, ... }:
{
  sops = {
    age = {
      keyFile = "/persist/keys/sops/age.key";
      sshKeyPaths = [ ];
      generateKey = false;
    };
    gnupg.sshKeyPaths = [ ];
  }
  // lib.optionalAttrs (settings.secretsFile != null) {
    defaultSopsFile = settings.secretsFile;
  };
}
