# Small tools, explicit responsibilities

The workstation follows the Unix approach of programs with focused jobs that
cooperate through files, pipes and ordinary commands. The [Bell Labs history of
pipes and the Unix philosophy](https://www.nokia.com/bell-labs/unix-history/philosophy.html)
describes the design behind this choice.

## Everyday tools

| Job | Tool and boundary |
| --- | --- |
| Arrange windows/workspaces | Niri; shells do not also manage window layouts |
| Display a terminal | Foot; no multiplexer, desktop shell or session daemon inside it |
| Run commands | Zsh; small functions compose external tools |
| Complete commands | Carapace supplies candidates; zsh-autocomplete presents them |
| Find paths / search contents / select results | fd / ripgrep / fzf, also reused by the editor |
| Browse files | Yazi; edit and open actions delegate to other programs |
| Edit text/code | Neovim; separate language servers and formatters supply language support |
| Track source changes | Git, available directly from a terminal |
| Open web content | Firefox; desktop controls and project tools remain separate |
| Connect to networks | NetworkManager with nmtui; graphical applet/editor are opt-in |
| Audio routing / device selection | PipeWire and WirePlumber / pavucontrol |
| Show status / notifications | Waybar / Mako |
| Launch apps / lock / handle idle | Fuzzel / Swaylock / swayidle |
| Select a project | `cproj` pipes fd output into fzf, then changes the shell directory |
| Read local help | `workstation-help` opens a plain text file with less |

The editor's two integrations are nvim-lspconfig and fzf.vim. They connect existing
tools; there is no editor distribution, automatic plugin downloader, AI service,
embedded project service manager or second search implementation. Python, Node,
Ruby and Perl editor providers are disabled by the pinned Home Manager defaults
and checked in validation. Nixd and nixfmt are supplied to the editor's PATH;
other language tools come from project development shells.

The shell can still run each underlying tool directly. For example:

```sh
fd --type f --extension nix
rg --line-number 'programs' modules
git status --short
```

## Keep optional work optional

The default file manager previews text, JSON, directories and archives. Media,
PDFs and fonts show file information without invoking thumbnail converters.
Rootless containers are off. The guided installer's settings screen lets you
toggle **Containers (Podman)**, **Rich file previews**, **Graphical network controls**
and **Obtain** independently. All choices appear in the installation plan and
are saved for rebuilds and resume.
To change them manually, merge the relevant field into the existing local
`installation.json`, or set it in `settings.nix` before installation:

```nix
containers = true;
richFilePreviews = true;
graphicalNetworking = true;
obtain = true;
```

These are independent settings; all default to `false`. `containers` enables
Podman, fixed subordinate IDs and its `/local` storage mount. `richFilePreviews`
restores Yazi's packaged media helpers and preview rules. `graphicalNetworking`
starts the NetworkManager applet in the desktop tray and makes the bar's network
label open the connection editor. Super+N still opens nmtui. Both interfaces use
the same NetworkManager connections and existing persistent credential storage.
Rebuild and boot to apply system changes. Disabling containers leaves the backing data on disk;
reenabling it mounts that storage again. Named volumes remain outside backups.

`obtain` enables the [Obtain release application manager](https://github.com/mehdi-hossaini/obtain/tree/codex/release-only),
pinned by this repository's lockfile. It adds the CLI and managed commands to
PATH, with no updater daemon or preinstalled third-party apps. Use `obtain --help`
and `obtain add https://github.com/OWNER/REPO` to install a supported release;
updates are explicit through `obtain update`. Use Nix for native Nix packages.
Its records, profiles and desktop launchers persist; the applications you install
may need their own data paths declared in the persistence configuration.

Repository maintenance tools such as statix, deadnix, ShellCheck, shfmt,
nix-tree and nix-diff live in `nix develop`. Application SDKs live in each
project's devShell. System recovery tools remain available outside those shells.
Curl handles ordinary downloads; a second downloader is not selected by default.

## System responsibilities

Nix and Home Manager generate configuration. Disko provisions storage,
impermanence declares retained paths, Btrfs handles snapshots, and Restic handles
remote backup only after it is configured. NetworkManager, PipeWire, portals,
Polkit and the login keyring each provide a desktop service with a specific role.
The system does not replace these services with custom workstation daemons.

The installer coordinates one installation transaction, with hardware policy in
separate modules and disk preparation/reset in separate scripts. Its validation
and failure ordering are part of that job; reducing lines must not remove them.
The small `just` recipes call Nix and existing scripts rather than implementing
another package manager or updater.

Firefox, NixOS and the graphics stack have substantial dependencies. They remain
because the workstation needs a compatible browser, reproducible system and
working hardware. This policy judges responsibilities and useful composition;
package count alone does not establish whether a design is simple.

## Rules for future additions

- State the program's job and how it communicates with the existing tools.
- Reuse an existing tool when it already performs the job. Avoid duplicate
  launchers, search engines, package managers and background watchers.
- Prefer small command wrappers over persistent services for interactive tasks.
- Put project dependencies in devShells and optional workloads behind explicit
  settings. Keep configuration generated from the repository.
- Declare any new persistent data narrowly. Do not add session restoration or
  history databases merely to support a picker or help screen.
- Verify actual runtime behavior and dependency closures. Keep the terminal,
  editor and file-manager commands useful independently of each other.

The `optional-tools` check validates all four opt-ins independently and together, their defaults,
container storage/ID mappings, and the actual Yazi dependency closure. The
terminal workflow checks exercise the composed project picker and editor.

Sources informing the implementation: [awesome-nix](https://github.com/nix-community/awesome-nix),
[impermanence](https://github.com/nix-community/impermanence),
[disko](https://github.com/nix-community/disko),
[sops-nix](https://github.com/Mic92/sops-nix),
[Niri](https://niri-wm.github.io/niri/), and
[Restic](https://restic.readthedocs.io/en/stable/).
