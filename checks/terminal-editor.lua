local function check()
  assert(vim.fn.exists(":Files") == 2, "File finder unavailable")
  assert(vim.fn.exists(":RG") == 2, "Text search unavailable")
  assert(vim.fn.exists(":Buffers") == 2, "Buffer picker unavailable")
  assert(vim.fn.executable("wl-copy") == 1, "Clipboard provider unavailable")
  assert(vim.fn.executable("fd") == 1 and vim.fn.executable("rg") == 1)

  vim.cmd("edit fixture.nix")
  assert(vim.wait(15000, function()
    local clients = vim.lsp.get_clients({ bufnr = 0, name = "nixd" })
    return clients[1] ~= nil and clients[1].initialized
  end, 50), "Nix language server did not attach")
  assert(vim.fn.maparg("<C-Space>", "i") ~= "", "Completion shortcut unavailable")
  local client = vim.lsp.get_clients({ bufnr = 0, name = "nixd" })[1]
  local reply = client:request_sync("textDocument/completion", {
    textDocument = { uri = vim.uri_from_bufnr(0) },
    position = { line = 3, character = 6 },
  }, 10000, 0)
  assert(reply and reply.result and not reply.err, "Completion request failed")
  local found = false
  for _, item in ipairs(reply.result.items or reply.result) do
    if item.label == "workflowValue" then found = true end
  end
  assert(found, "Nix completion did not find the local variable")

  vim.api.nvim_buf_set_lines(0, 0, -1, false, { "unsaved work" })
  local original = vim.api.nvim_get_current_buf()
  local guide = vim.fn.maparg("<F1>", "n", false, true)
  guide.callback()
  assert(vim.bo.readonly, "Guide should open read-only")
  vim.cmd("quit")
  assert(vim.api.nvim_get_current_buf() == original)
  assert(vim.bo.modified, "Opening help lost unsaved work")
  print("Editor search, real Nix completion and help with unsaved work passed.")
end

local ok, error = pcall(check)
if not ok then
  io.stderr:write(tostring(error) .. "\n")
  vim.cmd("cquit 1")
else
  vim.cmd("qa!")
end
