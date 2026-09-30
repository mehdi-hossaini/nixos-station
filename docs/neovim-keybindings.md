# Neovim keybinding cheat sheet

Your workstation shortcuts, followed by useful built-in editing keys. Based on
[the editor configuration](../modules/home/editor.nix) and the installed Neovim
0.12 defaults.

**Leader = Space.** `Space r n` means press those keys in sequence;
`Ctrl+p` means hold Ctrl and press p. Keys are case-sensitive.
Press `Esc` to return to Normal mode before using a Normal-mode shortcut.
Commands beginning with `:` finish with `Enter`.

## Your configured shortcuts

| Keys | Mode | Action |
| --- | --- | --- |
| `Ctrl+p` | Normal | Find a file below the current directory |
| `Space /` | Normal | Search project text with ripgrep |
| `Space b` | Normal | Choose an open buffer |
| `Space w` | Normal | Save the current file |
| `Space y` | Visual | Copy the selection to the system clipboard |
| `Space y` + motion | Normal | Copy the text covered by the motion to the system clipboard |
| `Space y y` | Normal | Copy the current line to the system clipboard |
| `Space p` | Normal | Paste from the system clipboard after the cursor |
| `Space p` | Visual | Replace the selection with the system clipboard |
| `Space e` | Normal | Show diagnostic details at the cursor |
| `Space f` | Normal | Format the file with an attached language server |
| `F1` | Normal | Open the workstation quick-start guide read-only; `:q` closes its window |

File and text searches start in Neovim's current directory and respect ignore
rules. `:pwd` shows that directory; `:cd path` changes it. The file picker includes
hidden files and excludes `.git`.

Inside the file picker: type to filter, use arrow keys to select, and press
`Enter` to open or `Esc` to cancel. `Ctrl+x` opens a horizontal split,
`Ctrl+v` a vertical split, and `Ctrl+t` a new tab.

## Language tools and completion

These actions need an attached language server with support for the requested
feature. Nix support is included. For other languages, launch Neovim inside the
project's development shell; restart it after changing environments.

| Keys | Mode | Action |
| --- | --- | --- |
| `gd` | Normal | Go to definition; `Ctrl+o` returns |
| `K` | Normal | Show documentation for the symbol under the cursor |
| `Space r n` | Normal | Rename a symbol and its references |
| `Space c a` | Normal | Show available code actions |
| `grr` | Normal | Find references using Neovim's built-in LSP mapping |
| `gri` | Normal | Go to implementation using the built-in LSP mapping |
| `Ctrl+Space` | Insert | Request language-server completion |
| `Ctrl+n` / `Ctrl+p` | Insert | Select the next / previous completion candidate |
| `Ctrl+y` / `Ctrl+e` | Insert | Accept / dismiss completion |

Completion also opens after server-defined trigger characters. Without a
language server, `Ctrl+n` / `Ctrl+p` can complete words from buffers.
`Tab` inserts whitespace or advances an active snippet; use `Ctrl+y` to accept a
completion candidate.

`[d` / `]d` move to the previous / next diagnostic. Diagnostics navigation does
not require an LSP if another tool supplies diagnostics. `:checkhealth vim.lsp`
helps inspect language-server setup.

## Type and edit

These keys start in Normal mode unless the table says otherwise.

| Keys | Action |
| --- | --- |
| `i` / `a` | Insert before / after the cursor |
| `I` / `A` | Insert at the first nonblank character / end of the line |
| `o` / `O` | Open a line below / above and start typing |
| `v` / `V` / `Ctrl+v` | Select characters / lines / a block |
| `x` / `dd` | Delete a character / line |
| `yy` / `p` / `P` | Copy a line / paste after / paste before using editor registers |
| `u` / `Ctrl+r` | Undo / redo |
| `.` | Repeat the last text change |
| `>>` / `<<` | Indent / unindent the current line |
| `>` / `<` in Visual mode | Indent / unindent the selection |
| `gcc` | Toggle the current line's comment |
| `gc` in Visual mode | Toggle comments on selected lines |

Comments use the file type's comment syntax. Plain `y`, `d`, and `p` use editor
registers; use your `Space y` / `Space p` mappings for the system clipboard.

## Move and search

| Keys | Action |
| --- | --- |
| `h` / `j` / `k` / `l` | Left / down / up / right |
| `w` / `b` / `e` | Next word start / previous word start / word end |
| `0` / `^` / `$` | Line start / first nonblank character / line end |
| `gg` / `G` / `42G` | First line / last line / line 42 |
| `5j` / `5k` | Move five lines down / up; use your relative line numbers |
| `Ctrl+d` / `Ctrl+u` | Scroll half a screen down / up |
| `zz` | Center the cursor's line on screen |
| `f` + character / `;` | Find the next occurrence on the line / repeat that find |
| `/text` / `?text` | Search forward / backward in the current file |
| `n` / `N` | Next / previous match relative to the search direction |
| `*` | Search forward for the word under the cursor |
| `%` | Jump to the matching bracket |
| `Ctrl+o` / `Ctrl+i` | Older / newer position in the jump list |
| `:noh` | Clear search highlighting |
| `:%s/old/new/gc` | Replace matches throughout the file, confirming each one |

## Combine actions with motions

Use **action + motion or text object**: `d` deletes, `c` changes and starts
Insert mode, and `y` copies. Add a count when useful.

| Example | Meaning |
| --- | --- |
| `dw` | Delete through the next word start |
| `d$` | Delete to the end of the line |
| `ciw` | Replace the word under the cursor |
| `ci"` | Replace the text inside double quotes |
| `di(` | Delete the text inside parentheses |
| `yiw` | Copy the word under the cursor |
| `Space y i w` | Copy that word to the system clipboard |
| `3dd` | Delete three lines |
| `ggVG` | Select the entire file |
| `ggVG` then `Space y` | Copy the entire file to the system clipboard |

## Buffers windows and saving

A buffer holds a file's text; a window displays a buffer; a tab groups windows.
Switching buffers does not save a file.

| Keys or command | Action |
| --- | --- |
| `Space b` / `[b` / `]b` | Pick a buffer / previous buffer / next buffer |
| `:split` / `:vsplit` | Split the window horizontally / vertically |
| `Ctrl+w` then `h` / `j` / `k` / `l` | Focus the window to the left / below / above / right |
| `Ctrl+w` then `=` | Equalize window sizes |
| `:w` / `:wa` | Save the current file / all changed files |
| `:q` / `:wq` | Close the current window / save its file and close |
| `:q!` | Force-close the current window; unsaved edits may be lost |
| `:bd` | Remove the current buffer; refuses if it has unsaved changes |
| `:Tutor` / `:help` | Open the interactive tutorial / built-in reference |

To inspect a shortcut, use `:verbose nmap <Space>w` in Normal mode or
`:verbose imap <C-Space>` for Insert mode. Buffer-specific LSP mappings appear
after the server attaches. For a specific built-in key, try `:help ciw` or
`:help CTRL-W`.
