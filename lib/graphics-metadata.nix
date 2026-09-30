{
  pkgs,
  host,
  nixpkgsRev,
}:
{
  schema = 1;
  stack = {
    nixpkgs = nixpkgsRev;
    kernel = host.boot.kernelPackages.kernel.version;
    nvidia = host.hardware.nvidia.package.version;
    niri = host.programs.niri.package.version;
    mesa = pkgs.mesa.version;
    policy = 1;
  };
  # Record immutable source identities without making consumers build/fetch them.
  sources = builtins.mapAttrs (_: src: builtins.unsafeDiscardStringContext (toString src)) {
    kernel = host.boot.kernelPackages.kernel.src;
    mesa = pkgs.mesa.src;
    libdrm = pkgs.libdrm.src;
    nvidia = host.hardware.nvidia.package.src;
  };
  generator = builtins.hashFile "sha256" ../scripts/graphics-support.py;
}
