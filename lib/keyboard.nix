layout: {
  # Keep the selected layout first, with a Latin group available for console
  # passwords, shell commands and desktop shortcuts on non-Latin keyboards.
  layout = if layout == "us" then "us" else "${layout},us";
  options = if layout == "us" then "" else "grp:alt_shift_toggle";
}
