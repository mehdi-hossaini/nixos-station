{ pkgs, settings, ... }:
let
  palette = builtins.fromJSON (builtins.readFile ../../lib/palette.json);
in
{
  programs.neovim = {
    enable = true;
    defaultEditor = true;
    viAlias = true;
    vimAlias = true;
    plugins = with pkgs.vimPlugins; [
      nvim-lspconfig
      fzf-vim
    ];
    extraPackages = with pkgs; [
      fd
      ripgrep
      fzf
      wl-clipboard
      # Config editing works without installing language tooling into the shell.
      nixd
      nixfmt
    ];
    initLua = ''
      vim.g.mapleader = " "
      vim.opt.number = true
      vim.opt.relativenumber = true
      vim.opt.expandtab = true
      vim.opt.shiftwidth = 2
      vim.opt.tabstop = 2
      vim.opt.undofile = true
      vim.opt.completeopt = { "menuone", "noselect", "popup" }
      vim.opt.signcolumn = "yes"
      vim.opt.termguicolors = true
      vim.opt.background = "dark"
      vim.opt.cursorline = true
      vim.opt.laststatus = 3
      vim.opt.winborder = "single"
      vim.opt.fillchars:append({ eob = " " })
      vim.opt.statusline = " %<%f %m%r%=%y  %l:%c  %p%% "
      -- Keep upstream syntax coverage; only adapt the built-in theme's palette.
      vim.cmd.colorscheme("habamax")
      for group, style in pairs({
        Normal = { fg = "${palette.body}", bg = "${palette.base}" },
        NormalFloat = { fg = "${palette.body}", bg = "${palette.raised}" },
        FloatBorder = { fg = "${palette.border}", bg = "${palette.raised}" },
        CursorLine = { bg = "${palette.raised}" },
        CursorLineNr = { fg = "${palette.focus}", bold = true },
        LineNr = { fg = "${palette.muted}" },
        SignColumn = { bg = "${palette.base}" },
        WinSeparator = { fg = "${palette.border}" },
        StatusLine = { fg = "${palette.focus}", bg = "${palette.raised}" },
        StatusLineNC = { fg = "${palette.muted}", bg = "${palette.base}" },
        TabLine = { link = "StatusLineNC" },
        TabLineFill = { link = "StatusLineNC" },
        TabLineSel = { fg = "${palette.base}", bg = "${palette.focus}", bold = true },
        Pmenu = { fg = "${palette.body}", bg = "${palette.raised}" },
        PmenuSel = { fg = "${palette.bright}", bg = "${palette.selection}" },
        -- A lighter selection needs an explicit foreground over syntax colors.
        Visual = { fg = "${palette.bright}", bg = "${palette.selection}" },
        MatchParen = { fg = "${palette.bright}", bg = "${palette.selection}", bold = true },
        Comment = { fg = "${palette.muted}" },
        String = { fg = "${palette.success}" },
        Constant = { fg = "${palette.warning}" },
        Statement = { fg = "${palette.mauve}" },
        Identifier = { fg = "${palette.teal}" },
        Type = { fg = "${palette.focus}" },
        Special = { fg = "${palette.teal}" },
        DiagnosticError = { fg = "${palette.error}" },
        DiagnosticWarn = { fg = "${palette.warning}" },
        DiagnosticInfo = { fg = "${palette.focus}" },
        DiagnosticHint = { fg = "${palette.teal}" },
      }) do
        vim.api.nvim_set_hl(0, group, style)
      end
      vim.env.FZF_DEFAULT_COMMAND = "fd --type f --hidden --exclude .git"
      vim.g.fzf_layout = { down = "40%" }
      vim.keymap.set("n", "<C-p>", "<cmd>Files<cr>", { desc = "Find a file" })
      vim.keymap.set("n", "<leader>/", "<cmd>RG<cr>", { desc = "Search project text" })
      vim.keymap.set("n", "<leader>b", "<cmd>Buffers<cr>", { desc = "Open buffers" })
      vim.keymap.set("n", "<leader>w", "<cmd>write<cr>", { desc = "Save" })
      vim.keymap.set({ "n", "x" }, "<leader>y", '"+y', { desc = "Copy to clipboard" })
      vim.keymap.set({ "n", "x" }, "<leader>p", '"+p', { desc = "Paste from clipboard" })
      vim.keymap.set("n", "<F1>", function()
        vim.cmd("sview " .. vim.fn.fnameescape("${./terminal-help.txt}"))
      end, { desc = "Workstation quick start" })
      vim.keymap.set("n", "<leader>e", vim.diagnostic.open_float, { desc = "Explain diagnostic" })
      vim.keymap.set("n", "<leader>f", function() vim.lsp.buf.format({ async = true }) end,
        { desc = "Format file" })
      vim.api.nvim_create_autocmd("LspAttach", {
        callback = function(event)
          local client = vim.lsp.get_client_by_id(event.data.client_id)
          if client and client:supports_method("textDocument/completion") then
            vim.lsp.completion.enable(true, client.id, event.buf, { autotrigger = true })
            vim.keymap.set("i", "<C-Space>", vim.lsp.completion.get,
              { buffer = event.buf, desc = "Complete at cursor" })
          end
          vim.keymap.set("n", "gd", vim.lsp.buf.definition,
            { buffer = event.buf, desc = "Go to definition" })
          vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename,
            { buffer = event.buf, desc = "Rename symbol" })
          vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action,
            { buffer = event.buf, desc = "Code actions" })
        end,
      })
      vim.lsp.config("nixd", {
        settings = { nixd = {
          formatting = { command = { "nixfmt" } },
          options = {
            nixos = { expr = '(builtins.getFlake "/projects/${settings.userName}/workstation").nixosConfigurations.workstation.options' },
            home_manager = { expr = '(builtins.getFlake "/projects/${settings.userName}/workstation").nixosConfigurations.workstation.options.home-manager.users.type.getSubOptions []' },
          },
        } },
      })
      vim.lsp.enable("nixd")
      -- Language servers come from each project's shell, not global SDKs.
      local servers = {
        rust_analyzer = "rust-analyzer", pyright = "pyright-langserver",
        ts_ls = "typescript-language-server", gopls = "gopls", clangd = "clangd",
      }
      for server, executable in pairs(servers) do
        if vim.fn.executable(executable) == 1 then vim.lsp.enable(server) end
      end
    '';
  };
}
