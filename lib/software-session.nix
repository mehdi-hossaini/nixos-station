{ pkgs }:
# Niri's TTY backend rejects software EGL. Run the real session fullscreen
# in Cage's pixman display for previews and automated desktop smoke tests.
pkgs.writeShellScript "workstation-software-session" ''
  export WLR_RENDERER=pixman LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=wayland
  exec ${pkgs.cage}/bin/cage -s -- ${pkgs.niri}/bin/niri-session
''
