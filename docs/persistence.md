# State contract

The live root is replaced each boot. A read-only empty `@root-blank` template
and `.workstation-layout-v1` marker are created by the installer preparation
script. The reset service runs after LUKS unlock and before `sysroot.mount`.
It validates all required subvolumes and bootstrap files, prepares `@root-next`,
archives the old root, then renames the new root into place. A failed reset stops
normal boot. Both intermediate interruption states are covered by VM tests.

| Tier | Contents | Backup |
| --- | --- | --- |
| `/persist` | Identity, login hash, age key, network profiles, selected home state | Yes |
| `/projects` | All work, including uncommitted and untracked files | Yes |
| `/nix` | Store AND Nix database, profiles and roots | Rebuildable |
| `/local` | Caches, journals, user Nix state and container layers | No |
| `/.snapshots` | 24 hourly read-only snapshots per durable tier | Local recovery only |

The previous three root archives are retained. Pruning begins 15 minutes after
boot, outside initrd. This is recovery from accidental omission, not secure
erasure. The rest of `/home` belongs to the ephemeral root. Only Projects and
the application paths listed in `modules/nixos/impermanence.nix` persist.

Each prune run removes at most 16 empty archives or individual subvolumes and
visits at most 256 subvolumes per archive, with a nesting limit of 64.
It queries Btrfs metadata instead of traversing ordinary disposable files.
Partly pruned archives remain valid and resume on the next run.

Directories owned by Home Manager must not also be persisted wholesale.
For a new application, identify its mutable data, add only that path with the
right ownership, and verify it across two reboots. Do not persist all of
`.config`, `.local`, `/var`, or `/var/lib`.

`/local` survives reboot but may be discarded during recovery. Valuable container
data must use an explicit bind mount under Projects or another declared backed-up
path. Named container volumes in default local storage are NOT backed up.
The container storage mount is configured only with `containers = true;`.
Disabling it leaves existing backing files under `/local` untouched, and
reenabling it makes them available again.
With `obtain = true;`, `.config/obtain`, `.local/share/obtain` and
`.local/share/applications` are retained under `/persist`. These hold release
records, locks, profiles, command links and desktop launchers. Obtain's cache
uses the existing `.cache` mount. Disabling the option leaves the backing data
untouched. Applications installed through Obtain may store data elsewhere;
declare those paths explicitly before relying on them across reboots.
CARGO_HOME is a cache directory: use runtime secrets for private registry
credentials rather than relying on cached credential files for recovery.

Snapshots are independent for `/projects` and `/persist`; Btrfs does not recurse
into nested subvolumes. Do not create nested subvolumes inside these tiers without
adding explicit snapshot/backup handling. Running database files and browser
profiles may require application-aware exports for a consistent recovery point.

Monitor space with `btrfs filesystem usage /` and `df -h /`. The tiers share a
storage pool; the subvolume split is not a quota. Keep headroom for new builds and
snapshots. Journals are limited to 1 GiB/14 days. NH is the only automated garbage
collector and excludes direnv roots. Retention cannot preserve generations that
you manually delete or whose paths are independently garbage-collected.
Hourly retention prunes to 23 snapshots and synchronizes deletion before creating
the next snapshot. A creation failure is reported after both tiers have been
processed, normally leaving 23 existing recovery points for the failed tier. Cleanup
is bounded to 128 deletions per tier per run; larger backlogs need multiple runs.
If the pool stays full after normal
retention, inspect usage and remove regenerable data or explicitly selected old
snapshots; there is no automatic policy that deletes additional recovery points.
