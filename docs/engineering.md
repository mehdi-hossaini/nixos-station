# Engineering rules

This repository applies [TigerStyle](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md)
in this order: safety, performance, then developer experience. The code here is
Nix, Python, and shell, so rules tied to Zig's memory model are translated into
bounded work and explicit resource ownership rather than copied literally.

Follow [the small-tools policy](philosophy.md) when choosing applications and
adding features: compose focused programs, keep optional workloads opt-in,
and put development dependencies in the relevant project shell.

## Safety

- Treat the installer as a destructive state machine. Validate hardware,
  configuration, mounted storage, and built artifacts before formatting. Recheck
  the selected disk and hardware after the user's erase confirmation. On resume
  and after credential setup, match every target Btrfs mount to cryptroot's UUID
  and its expected subvolume; verify the EFI mount before `nixos-install`.
- Distinguish invalid input from broken program invariants. Reject malformed
  hardware and release metadata with an actionable error. Use assertions for
  internal facts that cannot legitimately fail during operation.
- Bound work over externally supplied data. Disk topology walks have a fixed
  node limit; release catalogues have fixed byte limits and must be regular
  files. Unsupported arrangements stop installation instead of guessing.
- Save resumable state through a unique same-directory temporary file, flush it,
  and replace atomically. Never use a predictable temporary path for root writes.
- Publish refreshed release data through unique temporary files with the
  integrity manifest last. An interrupted update must fail validation before
  installation can continue. Hash and parse each catalogue from the same
  bounded read so bytes cannot change between integrity check and use.
- Check both sides of critical transitions: release metadata against the pinned
  manifest, selected disks before and after confirmation, and saved graphics
  configuration against detected hardware on resume. Validate a saved PRIME
  render path before placing it in generated compositor configuration.
- Require the read-only root template to be empty both when installation prepares
  it and before initrd replaces the current root. A failed check leaves the
  current root in place.
- Keep tests for the negative space: changed identities, malformed topology,
  wrong mount sources or subvolumes, missing files, unsupported GPUs, build
  failures, and wrong confirmations must stop before formatting.
- Budget background builders and foreground evaluation against physical memory.
  Prefer a failed oversized build to a machine-wide stall that loses work.

## Performance

- Sketch the cost before changing a hot path. Installation time is dominated by
  downloads, builds, and disk I/O; hardware detection should avoid redundant
  catalogue scans and unbounded in-memory work.
- Stream the pinned kernel archive to the one needed GPU table, with explicit
  member and file-size limits. Keep periodic snapshot and root pruning within a
  deletion budget so one delayed timer run cannot monopolize the machine.
- Keep hardware policy pure and deterministic. Resolve each GPU once, then
  classify the complete arrangement. Do not probe or load drivers during policy
  selection.
- Measure before claiming a speedup. Keep any benchmark inputs and command with
  a performance change; do not weaken compatibility checks to save time.

Historical development measurements, whose raw timing logs are not included
in this snapshot, used the pinned Linux 6.18.53 archive. In that run, two
separate-process lookup timings on the development host were 6.88 and 6.79
seconds with `tarfile.getmembers()`, versus
1.64 and 1.75 seconds with the streaming lookup. This measures extraction of
`amdgpu_drv.c`, not an installation or full catalogue build.

## Change workflow

1. Identify the invariant and the failure path before editing. For disk or boot
   changes, state which operation can be destructive.
2. Make the smallest change that enforces the invariant. Keep control flow
   visible and names specific to the domain.
3. Run focused regression tests, then `just check-fast`. Run `just check` and
   `just build` for changes to NixOS configuration or release inputs. Full VM
   checks require a builder with KVM.
4. Record any validation that could not run. A Nix build proves evaluation and
   derivation success, not first-boot hardware behavior; follow
   [hardware testing](hardware-testing.md) for that evidence.

The existing [validation guide](validation.md) lists the exact check commands
and their scope.
