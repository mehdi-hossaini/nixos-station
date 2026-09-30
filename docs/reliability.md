# Keeping the workstation responsive

The build limits in `modules/nixos/base.nix` apply to the workstation and its preview VM.
Nix starts at most two local derivations with four suggested build cores each.
Nix treats the job and core settings independently, so their product bounds
requested build parallelism; see the [Nix manual](https://nix.dev/manual/nix/2.31/advanced-topics/cores-vs-jobs.html).
The daemon and its builders run in `workstation-build.slice`, where CPU and I/O
weights favor the interactive session. The slice throttles at 35% of physical
memory and has a 45% hard limit and a 20% swap limit. These percentages scale
with the machine instead of assuming a particular RAM size. systemd-oomd
monitors user slices so a sustained user workload can be stopped before the
whole desktop becomes unresponsive.
The [systemd resource controls](https://github.com/systemd/systemd/blob/main/man/systemd.resource-control.xml)
apply throttling at `MemoryHigh` and a local OOM limit at `MemoryMax`.

Nix evaluates flakes in the calling process, outside the daemon. The `just`
recipes for checks, builds, formatting, updates, and system activation run that
foreground command in a transient user scope under `workstation-evaluation.slice`.
All of these scopes share a 15% throttle, 20% hard memory limit and 5% swap
limit; concurrent invocations do not get independent allowances. Builders and
foreground evaluations together are capped at 65% of physical memory for the
workstation user. The wrapper installs the slice's runtime properties even
before the new declarative configuration has been activated. On
CI or an installer without a user systemd manager, `scripts/run-bounded.sh`
runs the command directly. A command that exceeds the hard limit can fail; use a
remote builder or review the limits for workloads that genuinely need more memory.
The live installer also passes two jobs and four cores to its Nix builds; it
cannot rely on the installed system's daemon settings. Repository recipes,
metadata updates and CI builds pass the same limits explicitly. Snapshot and
old-root pruning services have low CPU and I/O weights so scheduled maintenance
yields to interactive work.
Snapshot/root pruning and optional Restic backup, prune and check share the
builders' aggregate slice, so they cannot add separate full-size memory budgets.
NixOS already schedules
the monthly Btrfs scrub with idle I/O priority.

## Historical observations behind the limits

The following observations were recorded during development before the history
reset. Their raw host logs are not shipped with this snapshot; they explain the
chosen limits and do not verify current responsiveness.

On 2026-09-29, a Nix builder's `mkdwarfs` process reached about 11 GiB resident
on a 14 GiB workstation. The kernel's global OOM killer stopped it at 12:08.
The previous evening, Niri reported input-event delays of 6–13 seconds while
Nix activity was logged. Before a forced restart at 17:02 on 2026-09-29, Niri
again reported delayed input, and an hourly Btrfs snapshot took 27.9 seconds
instead of its usual under 0.1 seconds. That last incident has no recorded OOM
kill or kernel panic, so the precise cause of that freeze remains unproven.
The Btrfs device error counters were zero after reboot.

## Keep login sessions through activation

The login manager must wait for Home Manager to finish at startup, but its
lifetime must not be bound to home activation. The previous configuration used
`Requires=home-manager-USER.service` together with `After=`. Restarting that
activation service during `just switch` can also stop greetd. The user-managed
Niri compositor can outlive the login wrapper; a subsequent login then fails
with `A niri session is already running.` rather than reconnecting to it.

The fix uses `Wants=` and `After=` to start home activation and wait for it.
An `ExecStartPre` check requires that activation to be active before greetd
starts. Home Manager's service is a oneshot with `RemainAfterExit=yes`, so
successful activation stays active. Failed activation still prevents login
startup. Later Home Manager restarts do not propagate a stop to greetd. The
upstream NixOS modules already disable automatic restarts on definition changes
for both greetd and Niri; that does not cancel a `Requires=` stop dependency.
See [systemd's dependency semantics](https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml)
and [Niri's session startup check](https://github.com/niri-wm/niri/blob/v26.04/resources/niri-session).

An older installed generation may still have the previous dependency until
the current configuration is installed.
For the first activation, use `just boot` to prepare the next generation without
switching the running system, save work, and perform a normal reboot. Use
`just switch` for ordinary changes once the corrected generation is running.
Other changes to login, graphics, or session services can still interrupt a
desktop; schedule those for a reboot too.

If returned to the greeter unexpectedly, first try `Ctrl+Alt+F2` to return to
Niri's existing VT (normally VT2). If it is elsewhere, log in on an unused TTY
such as `Ctrl+Alt+F3` and inspect it:

```sh
loginctl list-sessions
loginctl show-session SESSION_ID -p Name -p Type -p State -p VTNr
```

Use the ID for your existing graphical login, matching your user and VT. Switch to its VT with
`Ctrl+Alt+F` followed by that VT number, or `loginctl activate SESSION_ID`.
This attempts to return to the existing session, preserving its applications.
If it cannot be recovered, stop it deliberately from your own TTY:

```sh
systemctl --user start --job-mode=replace-irreversibly niri-shutdown.target
```

This closes Niri and its graphical applications; unsaved work can be lost.
Return to the greeter on `Ctrl+Alt+F1` and log in again. Do not restart greetd
as a way to recover an existing desktop session. Keep the greeter and Niri logs
before rebooting where possible:

```sh
journalctl -b -u greetd --no-pager
journalctl --user -b -u niri --no-pager
```

This dependency provides a concrete explanation for the reported symptoms,
but the incident's previous-boot logs were unavailable when investigating it;
the exact historical sequence is not confirmed.

## Verify after activation

```sh
nix config show | rg '^(max-jobs|cores) = '
systemctl show nix-daemon.service -p Slice -p ControlGroup
systemctl show workstation-build.slice -p CPUWeight -p IOWeight -p MemoryHigh -p MemoryMax -p MemorySwapMax
systemctl --user show workstation-evaluation.slice -p CPUWeight -p IOWeight -p MemoryHigh -p MemoryMax -p MemorySwapMax
systemctl show user.slice -p ManagedOOMMemoryPressure
```

For a future stall, compare the last minutes of the previous boot with
`journalctl -b -1 -k`, `journalctl -b -1 -u nix-daemon`, and
`journalctl -b -1 -u workstation-snapshots`. A kernel OOM kill and a delayed
compositor are separate observations; retain their timestamps before assigning
one cause.
