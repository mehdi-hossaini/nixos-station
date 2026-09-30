# Review fixes and regression coverage

These notes describe safety and usability decisions preserved in the current
initial snapshot. Earlier dated review reports and test-run claims belong to
the external recovery backup. The coverage below describes the purpose of the
checks; rerun them as described in the [validation guide](validation.md) to verify
a particular commit.

| Finding | Change and coverage |
| --- | --- |
| Login passwords lose surrounding whitespace | Both hidden reads preserve whitespace. The real bootstrap VM authenticates a synthetic password with surrounding spaces and rejects its trimmed form. |
| Manual installation omits keyboard verification | `install.sh --keyboard-test` applies and verifies the configured map without selecting or formatting a disk. The manual runs it before credentials and tests the encrypted-volume passphrase before proceeding. |
| Post-install container instructions use an overridden default | Documentation directs installed users to `installation.json`; the Nix defaults alternative is qualified as applying before saved choices exist. |
| Concurrent build budgets do not compose | Foreground commands share a 20% memory slice per user; daemon builders and maintenance share a 45% slice. Configuration checks verify the limits, and the session VM checks concurrent commands' cgroups. These are limits, not a measured guarantee of desktop responsiveness. |
| Root pruning traverses files and has unbounded nested work | A Btrfs metadata helper validates filesystem/subvolume identities and descendant paths. Each run deletes at most 16 subvolumes or empty archives; helper traversal is capped at 256 visits and depth 64. Unit tests cover failure cases; the boot VM covers real nested-subvolume deletion and resumption. |
| Battery urgency depends on color and hover | The bar always displays capacity and adds `!`/`!!` for warning/critical states. `Super+Shift+B` opens a keyboard-accessible text readout. Generated desktop checks verify the formats and shortcut. |
| Expired notifications lack keyboard recovery | Restore, dismiss and action-menu shortcuts are documented. Ordinary notifications default to 15 seconds; `notificationTimeout = 0` disables expiry. Critical notifications remain until dismissed. |
| Palette values are duplicated | Named roles in `lib/palette.json` feed the desktop, editor and rendered Niri configuration. A generator supplies preview variables; the fast gate rejects stale preview data. |
| Storage module policy is duplicated | `scripts/storage-policy.json` supplies the installer and NixOS initrd module lists. Controller classification remains explicit in the same data file. |
| CI repeats fast builds on another runner | Fast and full validation run sequentially in one job, sharing the Nix store and preserving the early failure gate. |
| Rust artifacts churn project snapshots | The Rust template gives each canonical project path a separate Cargo target directory in the persistent local cache. Existing projects must opt into this convention; cache artifacts are regenerable and excluded from project recovery. |
| Login-manager lifecycle lacks a regression guard | Generated-unit assertions and a new VM exercise production dependency/guard settings through activation restart, failure and recovery. |
| Boot fixture bypasses real credential bootstrap | The disposable Disko fixture executes the production preparation script, checking hashing, key usability, private permissions, atomic failure handling and rerun preservation. |
| Non-Latin layouts cannot enter the required Latin sample | Non-US configurations include a switchable US group. The installer verifies group-switch options; compiled-map checks and physical VM keystrokes cover Russian and US input. |

## Source snapshot guarantees

Build and check recipes share `scripts/with-local-flake.sh`. It includes tracked
files and recognized non-ignored new source files, plus the explicit local
`installation.json` exception. Other ignored data stays out, and the wrapper
leaves the Git index unchanged. Regression checks cover tracked edits,
unusual filenames, ignored credentials, settings permissions, failure-code
preservation, temporary cleanup and rejection of a settings symlink.

## Installer, desktop and backup guarantees

| Finding | Change and regression coverage |
| --- | --- |
| Credential variants can enter local build snapshots | Common credential extensions and environment variants are ignored and explicitly filtered even when tracked. Untracked inputs are limited to project source paths/types. Synthetic secrets are absent from snapshot tests. |
| Unstaged deletions and renames break maintenance commands | Missing index entries are skipped; NUL-delimited names and dangling symlinks remain supported. Snapshot tests exercise deletion and a rename containing a newline. |
| A full disk skips snapshot retention | Excess snapshots are pruned and deletions synchronized before creation. Creation failure is reported after both tiers have been processed. The evaluated-script regression injects a failure, verifies both tiers and checks recovery. |
| Resume leaves stale installed source | Preparation publishes the current filtered checkout and settings, preserving a differing previous checkout in a dated sibling backup. Regression checks verify freshness, unchanged reruns and preservation of custom files. |
| Recovery choices can vanish with the live session | Settings-only and independent export modes save private copies without formatting; recovery documents read-only unlocking and retrieving the target's copy. Export tests reject existing files and symlinks. |
| ANSI black foreground is unreadable | Accessible terminal colors default to readable gray. Conventional dark ANSI black remains opt-in; shared foreground/background tradeoffs are documented and both profiles validate. |
| Pointer movement changes keyboard focus | Stable keyboard focus is the default; `focusFollowsMouse` explicitly enables pointer focus. Both generated Niri configurations validate. |
| Installer geometry is fixed | Input/menu dimensions follow terminal size; small terminals fall back to numbered prompts. Regression checks verify bounded geometry and valid fallback selections. |
| Repeated installer copies and keyboard evaluations | Preview snapshots are reused until saved choices change, then one source is frozen before installation validation and both builds; one JSON evaluation supplies all keyboard fields. Regression tests cover reuse, freezing and the existing keyboard safety checks. |
| Live edits change formatter or bootstrap inputs | The frozen source must match the reviewed choices and define only the selected disk. Exact build output paths and the validated username are passed to formatting and bootstrap; the installed checkout copies the frozen source. Regressions change settings between builds and during confirmation. |
| Local checks omit newly added source files | Local validation and builds share the filtered snapshot wrapper. Tests verify whole-flake checks include untracked source without requiring an installation disk or changing the Git index. |
| Selection presentation is split across installer modules | Search and pagination live in `installer_ui.py`; timezone and keyboard policy call that interface. Existing choice tests continue to exercise search, paging, validation and keeping the current value. |
| Real desktop login/locking lack coverage | A software-rendered desktop-session VM exercises greetd, Niri, the startup terminal, Home Manager restart and rejected/correct lock passwords. |
| Successful backup/restore lacks coverage | A disposable backup-restore VM boots with encrypted test credentials, tests host-key rejection, runs the production unit, restores both tiers and checks exclusions/integrity. |
| SFTP argument splitting prevents backups | The runtime test exposed SSH options being split into separate Restic arguments. Shell quoting preserves the whole `sftp.args` value for initialization, backup, checks and the restore wrapper. |

These changes do not activate the development host. Physical desktop,
assistive-technology, suspend and independent backup acceptance remain required.
