# Workstation color review

The strongest direction for this workstation is **charcoal surfaces, restrained
blue-gray focus, and clearly legible states**. The original palette already fits
the repository's small-tools philosophy. The revision improves text, boundaries,
and selection rather than replacing its identity with a brighter theme.

Scope: the explicit settings in `modules/home/desktop.nix`,
`modules/home/editor.nix`, and `modules/home/niri.kdl`. This is a configuration
audit, not an observation of a running desktop. Open
[the comparison preview](color-preview.html) for representative before/after
controls; its browser rendering is illustrative rather than a native screenshot.

## What color psychology can tell us

Color is a useful communication cue, but emotional association, personal
preference, and an actual change in mood are different outcomes. A
[2025 systematic review](https://link.springer.com/article/10.3758/s13423-024-02615-z)
covered 132 studies and 42,266 participants. It found recurring, many-to-many
color/emotion associations, while emphasizing that most evidence concerns
abstract associations rather than emotional effects in specific settings.
Blue/green commonly aligned with lower arousal; red with both positive and
negative high-arousal emotions; yellow/orange with positive high-arousal emotions.
Gray also had negative, low-arousal associations. Therefore a dark gray UI is
not automatically calming, and a blue border cannot promise trust or productivity.

Hue alone is an incomplete design variable. In an
[experiment varying hue, saturation, and brightness](https://doi.org/10.1007/s00426-017-0880-8),
62 participants rated more saturated and brighter stimuli as more arousing.
These dimensions also interacted: findings about a vivid blue do not necessarily
apply to a muted blue-gray. My design inference is to keep large surfaces neutral
and place brighter colors in small, purposeful areas, such as the focused window
or selected row. This balances a restrained appearance with discoverable controls;
it is not a demonstrated productivity intervention.

Meaning is learned and contextual. An error, a copied-file count, and a syntax
string can carry different meanings even when they use related hues. The
[ecological valence account of preference](https://pubmed.ncbi.nlm.nih.gov/20421475/)
links liking for colors to liking for associated objects. This supports treating
user experience with a palette as relevant to preference, rather than choosing
a hue from a universal branding dictionary. Repeated roles within this desktop
can make it feel coherent and familiar; that last point is a design rationale.

Culture matters alongside common patterns. A
[study across 30 nations](https://pubmed.ncbi.nlm.nih.gov/32900287/)
found broad similarity with differences related to language and geography. It
tested associations with color terms, not this workstation's exact hex codes.
Likewise, the
[Elliot and Maier review](https://www.annualreviews.org/content/journals/10.1146/annurev-psych-010213-115035/)
warns that real-world application depends on context and boundary conditions.
These findings justify testing the design with its users, not assuming a
particular emotional response from a particular nationality or demographic.

For this design, the practical interpretation is:

| Family | Intended role and impression | Design tradeoff |
| --- | --- | --- |
| Charcoal and off-white | A restrained, work-oriented canvas | Too little lightness separation makes structure disappear; restraint can feel dull to some users. |
| Blue-gray | Focus, navigation, information; continuity with the existing identity | Using it everywhere would dilute the focus cue. Keep the brightest blue-gray for small markers. |
| Muted green and teal | Positive status, verification, syntax, matching text | Green and red can be hard to distinguish; status still needs words or symbols. |
| Sand/amber | Warning and numerical constants | A warning should be contextual, not inferred from every amber token in code. |
| Muted rose | Error and urgency | Reserve structural rose borders for urgent states, so ordinary chrome does not appear alarmed. |
| Mauve | Statements and syntax differentiation | Its purpose here is code organization, not a claim that purple creates creativity or luxury. |

These are intended impressions and UI conventions, not measured reactions to
this theme. There is no formal brand guide in the repository, so brand fit is
inferred from the README's explicit charcoal styling and the tool philosophy.

## Evaluation of the original configuration

| Dimension | Finding | Consequence |
| --- | --- | --- |
| Emotional impact | Neutral surfaces dominate; restrained green, sand, teal and mauve add variety. | Appropriate for a quiet workstation identity, though individual users may find it austere. Retain the palette's character. |
| Readability | `#D4D4D4` on `#171717` is 12.09:1. Comments/placeholder text `#8C8C8C` on `#222222` is 4.73:1. Line numbers and ANSI bright black `#737373` are only 3.78:1 on `#171717`. | Body text is already strong. Raise the weaker muted text rather than whitening every label. |
| Accessibility | `#606A73` borders are 3.25:1 on the base but 2.88:1 on raised `#222222`. Foot's selected fill is 1.59:1 against the base; Fuzzel's is 1.38:1. The translucent Niri insertion hint depends on the content underneath. | Some meaningful boundaries and selected regions are difficult to discern even though the text inside them is legible. |
| Visual hierarchy | Focus markers `#B8C4CE` already contrast strongly. Surfaces and decorative rules are close in brightness; selections vary across tools. | Preserve the focus hue, distinguish functional outlines from decoration, and standardize selection. |
| Brand consistency | Most apps share the same colors, but selected fills use `#333C43`, `#2A3239`, and the Waybar active tint `#242A2F`. GTK uses upstream Adwaita Dark. | Unify text-selection/list-selection roles; retain the quieter Waybar tint because its active border already identifies the state. Adwaita remains an adjacent native style. |

## Specific changes applied

| Role | Original → revised hex | Reason and measured result |
| --- | --- | --- |
| Muted text | `#737373` → `#8C8C8C` | Neovim line numbers and Foot bright black now match the existing comment/placeholder color. Contrast on the base rises from 3.78:1 to 5.33:1, while remaining below body text in emphasis. |
| Functional boundaries | `#606A73` → `#7B8793` | Fuzzel, Mako, Waybar tooltips, Swaylock's resting ring and Neovim float borders become clearer. On raised surfaces, contrast rises from 2.88:1 to 4.34:1. |
| Pane separators | `#303030` → `#7B8793` in Neovim/Yazi | Pane structure should remain visible independently of syntax or file contents. Decorative Waybar dividers and Niri inactive borders remain `#303030`. |
| Selection fill | `#333C43` / `#2A3239` → `#5B7182` | A consistent muted steel blue makes selected text/rows recognizable. Fill contrast is 3.53:1 on the base and 3.13:1 on raised surfaces. |
| Selected foreground | Explicit `#F5F5F5` on `#5B7182` | Selected text measures 4.66:1. Neovim Visual and MatchParen now explicitly set it; the other selected roles already used it. Normal syntax colors would not all remain readable over the lighter fill. |
| Selected search match | `#A1BBB9` → `#FFF2CF` in Fuzzel's selected row only | The former teal would fall to 2.50:1 on the new selection. Pale sand measures 4.57:1; it is limited to matched characters. Unselected matches retain teal. |
| Insertion target | `#B8C4CE24` → opaque `#5B7182` | Eliminates content-dependent alpha blending over the configured empty desktop and uses the same visual language as selection. It must still be inspected if the compositor overlays it on other backgrounds. |
| Window border width | 1 → 2 pixels, same `#B8C4CE` | A larger visible focus marker makes the already strong contrast easier to locate at high pixel densities. This is a visibility improvement, not a WCAG conformance claim. |

The main tradeoff is a more visible selected region. Neovim selected text becomes
uniform off-white, temporarily reducing syntax differentiation in exchange for
consistent reading contrast. Selected search matches use a very light warm tint;
the selected row itself is communicated by its luminance, not that subtle hue.

## Colors worth retaining

All measurements below use the raised `#222222` surface, the weaker of the two
standard surfaces for light text. They are foreground/background contrasts,
not contrasts between status colors.

| Role | Hex | Contrast | Rationale |
| --- | --- | --- | --- |
| Base / raised surface | `#171717` / `#222222` | — | Keeps the established charcoal identity; structure comes from layout and functional borders. |
| Body text | `#D4D4D4` | 10.73:1 | Strong reading contrast without promoting all text to the brightest white. |
| Focus / information | `#B8C4CE` | 8.96:1 | A strong, familiar navigation accent; use it for active markers and important headings. |
| Success / strings | `#A8B89A` | 7.57:1 | Readable restrained green, with role supplied by the surrounding UI. |
| Warning / constants | `#C9B18B` | 7.69:1 | Adds warmth without the visual intensity of a saturated yellow. |
| Error / urgency | `#D48383` | 5.59:1 | Already readable; brighter red would add emphasis without fixing a measured deficiency. |
| Teal / identifiers | `#A1BBB9` | 7.82:1 | Preserves syntax variety and a consistent secondary accent. |
| Mauve / statements | `#B6A7BD` | 7.01:1 | Already readable and compatible with the muted syntax family. |

## Accessibility interpretation and remaining limits

The audit uses WCAG 2.2 as a contrast benchmark for native desktop settings.
[Normal text requires 4.5:1; large text 3:1](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
[Essential non-text cues require 3:1 against adjacent colors](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
The latter does not apply to every decorative separator. The selection-fill
target is a conservative choice for making the selected region visible; it is
not a claim that every OS text-selection rendering is subject to the same rule.
[Color must not be the only way to communicate meaning](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).
Passing a few contrast pairs does not establish complete accessibility.

Ratios use opaque sRGB values and the WCAG relative-luminance formula:
linearize each channel using the 0.04045 threshold, compute
`L = 0.2126 R + 0.7152 G + 0.0722 B`, then calculate
`(L_lighter + 0.05) / (L_darker + 0.05)`. Displayed ratios are rounded to two
decimals; threshold comparisons use unrounded values.

Remaining considerations:

- Foot ANSI regular black defaults to `#8C8C8C`, giving 5.33:1 on `#171717`.
  ANSI foreground and background use the same slot, so applications requesting
  a black background also get gray. `accessibleTerminalColors = false` restores
  conventional `#222222` black (1.13:1 as text on the base); those applications
  then need readable foreground settings of their own. Arbitrary ANSI pairings
  still require inspection.
- Changing the selection fill requires off-white selected text. Custom terminal
  apps, editor highlight priorities, search overlays, and plugins may override
  configured colors. Inspect actual selected syntax and popup content.
- Battery warning/critical states now show `!` / `!!` and the capacity, with
  Super+Shift+B opening a readable status window. Mako should
  receive meaningful urgency text from applications. Diagnostic messages should
  identify severity in words/signs. Hue differences alone are insufficient.
- The shared rose, green, amber and teal colors need not be distinguishable by
  hue for everyone. Check grayscale and red/green color-vision simulations,
  while also ensuring that labels, icons and position convey meaning. Simulation
  is a diagnostic tool, not a substitute for testing with users.
- Active Waybar workspaces retain their blue-gray edge marker. Their tinted
  background is supplemental. Hover fills and decorative inactive-window
  borders stay subtle; do not rely on those fills to convey a required state.
- Adwaita applications, inherited Habamax highlight groups, application-owned
  colors, and arbitrary client window backgrounds are outside this explicit
  palette audit. Contrast over a bright client surface can differ substantially.

The next native review should cover a selected terminal paragraph, selected
syntax, the launcher with a search match, split panes, a critical notification,
and focused/unfocused windows at the user's usual scale. Ask users to locate
focus, read muted text, and identify a warning without relying on color. Compare
errors and task completion as well as subjective comfort. This can assess the
specific design; generic color-emotion evidence cannot establish those outcomes.

## Validation and activation

The patch changes configuration only. Use `just check-fast` for repository
validation. If the running generation still has greetd's Home Manager
`Requires=` dependency, use `just boot`, save work, and reboot to install the
[login-session fix](reliability.md#keep-login-sessions-through-activation)
and colors together. After that fix is running, use `just switch` for ordinary
activation. Newly opened Foot
windows pick up the revised theme; restart relevant applications or the desktop
session if they retain earlier colors. Activation changes the running system
and is separate from reviewing the patch.
