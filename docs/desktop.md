# Desktop guide

## Terminal desktop

Niri includes a browser, graphical apps, Waybar, notifications, screen locking,
audio and screen-sharing support.

The desktop starts a maximized Foot window on the **Code** workspace.
**Super+Return** opens a new Foot terminal; **Super+Shift+Return** does the same.
Each window has its own shell, and Niri handles tiling and workspace navigation.
**Super+N** opens the `nmtui` network menu, **Super+E** opens Yazi,
and **Super+B** opens Firefox for normal web browsing. The network indicator
on Waybar also opens `nmtui` when clicked.

Battery capacity is visible on the bar; `!` and `!!` mark warning and critical
levels. **Super+Shift+B** opens a readable battery status window. **Super+M**
restores the latest expired notification, **Super+Shift+M** dismisses one, and
**Super+Ctrl+M** opens its action menu. Ordinary notifications last 15 seconds;
set `notificationTimeout` to `0` in `installation.json` to keep them until dismissed.
Non-US keyboard layouts have a US fallback; **Alt+Shift** switches groups in
Niri, the text console and initrd unlock prompt. Boot starts in the selected group.

Run `nvim` for editing and `yazi` for files. There is no bundled Codex CLI,
terminal multiplexer or detach/reattach layer.
Closing a terminal ends its shell and may terminate commands running in it;
shell sessions are not restored after reboot. Save your work before closing
windows or logging out. Files in persistent directories and shell history
continue to survive reboots.

The terminal-first shell uses [Carapace](https://carapace-sh.github.io/carapace-bin/)
and [zsh-autocomplete](https://github.com/marlonrichert/zsh-autocomplete) for a
live completion menu. Suggestions include command flags, paths and contextual
arguments such as Git branches, even with empty history. Available candidates
depend on the command's completer. Pause briefly while typing to see suggestions;
**Tab** inserts the first candidate and **Down** opens menu selection. In the
menu, use arrows or Tab to move and Enter to accept the selection. **Ctrl+R**
searches history. Completion inserts text; it does not automatically run it.
This is command-aware completion, without an AI account or model dependency.

The installer has no desktop selector. Older `desktop` values in
`installation.json` or `settings.nix` are ignored; all installations use this
setup after rebuilding and booting. The startup window appears at the next
Niri session start. Old Codex data under `/persist` is left on disk, but its
home-directory mount is no longer configured.

The desktop uses Niri's [startup applications](https://niri-wm.github.io/niri/Configuration:-Miscellaneous.html)
and [window rules](https://niri-wm.github.io/niri/Configuration:-Window-Rules.html).
It remains a Wayland desktop with full GUI support.

## Terminal workflow

Type `workstation-help` for the offline quick-start guide, or open **Quick Start**
from Fuzzel. **Super+F1** shows desktop shortcuts; **Super+Shift+F1** opens the guide.

- `cproj` searches folders directly inside `~/Projects`; `cproj name` starts with
  a search. Enter selects a folder, and Esc cancels without changing directory.
- `v` opens Neovim. **Ctrl+P** finds files, **Space then /** searches project text,
  and **Space then b** switches open buffers. Searches start in the editor's current
  directory and respect ignore rules. **F1** opens the guide beside your work;
  `:Tutor` starts the beginner tutorial.
- Neovim uses built-in language-server completion: **Ctrl+Space** requests it,
  **Ctrl+N/P** selects, **Ctrl+Y** accepts and **Ctrl+E** dismisses. Nix is ready
  out of the box; other language servers come from the project's development shell.
  `gd` jumps to a definition, **Space then rn** renames, and **Space then ca**
  offers code actions.
- `y` opens Yazi and returns your shell to the browsed directory when you quit.
  `z name` jumps to a previously visited folder.
- **Ctrl+Shift+N** in Foot opens a new terminal in the current shell directory.
  **Ctrl+Shift+R** searches terminal output. **Ctrl+X then Ctrl+E** edits a shell
  command in Neovim before you review and run it.
- Foot uses **Ctrl+Shift+C/V** for clipboard copy/paste. In Neovim, use
  **Space then y/p** for the system clipboard; normal yank/delete registers
  keep their usual behavior.

The workflow reuses fzf, fd and ripgrep; the editor adds the pinned fzf.vim
integration. There is no project index, session manager or clipboard-history
service. The guide is generated from `modules/home/terminal-help.txt`.

## Shortcuts and appearance

Super+Return opens Foot. Super+D opens Fuzzel; Super+E opens Yazi.
Super+arrows or Super+H/J/K/L moves focus, Shift moves windows/columns, and Super+1…5 selects
Code/Web/Review/Communicate/Lab. Super+Escape locks. Print takes a screenshot.
Super+Shift+E shows the logout confirmation. Niri, Waybar, Mako, the Polkit agent
and idle handling are bound to the graphical session.

The brightness keys and Waybar's **Light** control use the standard Linux
backlight device when one is available. Waybar selects the device automatically.
External monitors without a Linux backlight device use their own brightness
controls.

The desktop uses a charcoal palette, square windows with 2-pixel blue-gray focus
borders, subtle shadows, and 10-pixel gaps. A compact Waybar panel pairs tinted,
underlined workspaces with quiet status text and a date/time display.
Keyboard focus stays in the selected window when the pointer moves. Set
`focusFollowsMouse` to `true` in `installation.json` to enable pointer focus.
ANSI black text uses readable gray by default (`accessibleTerminalColors = true`).
Because ANSI shares foreground and background entries, explicit black backgrounds
also become gray. Set `accessibleTerminalColors` to `false` for conventional dark
ANSI black; terminal apps using black foreground then need their own palette.
Foot, Fuzzel, Mako and Swaylock share the same colors. Tune window spacing and
decorations in `modules/home/niri.kdl`, and panel/application styling in
`modules/home/desktop.nix`. Apply with `just switch` after the
[login-session fix](reliability.md#keep-login-sessions-through-activation)
has been installed; use `just boot` and a planned reboot for its first activation.
New terminal windows pick
up the updated Foot theme. Foot uses DejaVu Sans Mono with a Symbols Nerd Font
Mono fallback for Yazi's icons and separators; Yazi's status colors match the
terminal palette.

The [color review](color-review.md) explains the palette's emotional intent,
contrast measurements, shared selection colors and remaining accessibility limits.
Open [the palette preview](color-preview.html) in a browser to compare the
original and revised colors on representative controls.

Neovim uses its bundled Habamax theme with matching charcoal surfaces, muted
syntax colors, bordered popups and a small built-in status line. Yazi uses
matching selection colors. GTK applications use Adwaita Dark with the
standard Adwaita icons/cursor; there is no separate theme downloader. Editor and
shell styling live in `modules/home/editor.nix` and `modules/home/shell.nix`.

Projects live under `~/Projects`, backed by `/projects/USER`. `~/Scratch` is
discarded after reboot. Documents, Downloads, Pictures, browser profile, keyring,
SSH/GPG state, editor recovery and shell history persist. Caches survive reboots
under `/local` but are not backed up. Containers are disabled by default; when
enabled, their image/volume storage also lives under `/local` without backups.

After installation, the repository is at `~/Projects/workstation`.

```sh
just update  # update inputs and regenerate the coupled graphics metadata
just check
just build
just diff
just boot   # schedule the tested configuration for next boot
```

Review both `flake.lock` and the graphics catalogue/manifest diff after updating.
Validation and build commands refuse implicit lockfile changes. GitHub Actions
pins are maintained separately by Dependabot.

Use `just switch` for ordinary configuration changes after review. If the running
generation still binds greetd to Home Manager with `Requires=`, first install the
[login-session fix](reliability.md#keep-login-sessions-through-activation)
with `just boot`, save work and reboot. Keep the
stateVersion settings unchanged when updating packages. System rollback does
not roll back mutable database schemas or application data.

## Interactive VM preview

Run the terminal-first desktop as a complete NixOS guest on an x86_64 Linux
host with KVM and a Wayland session:

```sh
nix run .#preview-terminal --no-update-lock-file
```

This is a QEMU VM with its own kernel, 3 GiB RAM, two virtual CPUs, an 8 GiB
virtual root disk, and software graphics entirely inside the guest. It starts Niri automatically; the
VM-only username and password are both `preview`. No host folders, credentials,
or GPU devices are shared. Internet access uses QEMU's user networking.
The first build downloads any missing packages; each launch prepares a separate
Nix store image, which needs additional temporary disk space.

The guest disk is retained at
`${XDG_CACHE_HOME:-$HOME/.cache}/workstation/preview-terminal/system.qcow2`.
Shut down from inside the guest with `sudo poweroff` (password `preview`).
QEMU's **View → Grab On Hover** option can help deliver keyboard shortcuts to
the guest; Ctrl+Alt+G releases the keyboard/mouse grab. Use **Alt** instead of
Super for desktop actions in this preview: Alt+Enter for Foot, Alt+E for Yazi,
Alt+B for Firefox, and Alt+Space for the overview.

Niri's TTY backend rejects software EGL, so this VM runs it fullscreen inside
Cage's software-rendered display. Both compositors run inside the guest;
QEMU's host display has OpenGL disabled. The installed desktop uses Niri directly.

To build without starting it:

```sh
nix build .#preview-terminal --no-update-lock-file
./result/bin/workstation-preview-terminal
```

This preview uses the real desktop and application modules with a simple VM
disk. It does not test the installer's encrypted Btrfs layout, impermanence,
physical GPU drivers, or suspend. It never activates the host configuration.
