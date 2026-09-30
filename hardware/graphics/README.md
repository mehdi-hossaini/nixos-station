# Prepared graphics metadata

These JSON files are generated release inputs, committed alongside `flake.lock`.
Do not edit them by hand. Run `just graphics-update` after changing the pinned
graphics stack or catalogue generator, review the diff, and run `just check`.

`manifest.json` records the stack, immutable Nix source identities, catalogue
generator hash, and SHA-256 hashes of both data files. The installer checks these
against the evaluated configuration before using the tables. Missing, altered or
stale data stops installation; it never triggers source downloads or a fallback.
The installer environment and flake inputs can still need downloads.

`just check-fast` verifies the bundled data and resolver without regenerating the
catalogue or building the five profile closures. `just check` also rebuilds
the data from Nix-hashed sources and requires an exact match, then exercises the
full profile/VM checks. Checksums detect mismatched or corrupted release files;
the trusted project checkout remains the trust boundary, not the manifest alone.

These tables establish configuration policy. They contain no physical test claims.
See [hardware acceptance](../../docs/hardware-testing.md).
