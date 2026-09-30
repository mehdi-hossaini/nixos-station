"""Prepare, validate and refresh the release's graphics data; never inspect disks."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

FILES = ("graphics-support.json", "supported-gpus.json")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CATALOGUE_BYTES = 4 * 1024 * 1024


def file_limit(path):
    return MAX_MANIFEST_BYTES if path.name == "manifest.json" else MAX_CATALOGUE_BYTES


def open_regular(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Graphics metadata is not a regular file: {path.name}.")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def bounded_bytes(path):
    limit = file_limit(path)
    try:
        with open_regular(path) as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise ValueError(
            f"Cannot read graphics metadata: {path.name}. Use a complete release checkout."
        ) from error
    if len(data) > limit:
        raise ValueError(f"Graphics metadata exceeds the supported size: {path.name}.")
    return data


def parse_json(path, data):
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as error:
        raise ValueError(
            f"Cannot read graphics metadata: {path.name}. Use a complete release checkout."
        ) from error


def read_json(path):
    return parse_json(path, bounded_bytes(path))


def read_verified_json(path, expected_sha256):
    data = bounded_bytes(path)
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"Graphics metadata integrity check failed: {path.name}.")
    return parse_json(path, data)


def digest(path):
    hasher = hashlib.sha256()
    limit = file_limit(path)
    size = 0
    with open_regular(path) as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError(f"Graphics metadata exceeds the supported size: {path.name}.")
            hasher.update(chunk)
    return hasher.hexdigest()


def load_metadata(directory, expected):
    """Fail before any installation changes if data is stale, incomplete or altered."""
    try:
        manifest = read_json(directory / "manifest.json")
        if manifest["provenance"] != expected or expected["schema"] != 1:
            raise ValueError(
                "Graphics metadata does not match the pinned stack or catalogue generator. "
                "Use a matching release; maintainers must run just graphics-update and review the changes."
            )
        if set(manifest["sha256"]) != set(FILES):
            raise ValueError("Graphics metadata manifest has an unexpected file list.")
        support = read_verified_json(directory / FILES[0], manifest["sha256"][FILES[0]])
        nvidia = read_verified_json(directory / FILES[1], manifest["sha256"][FILES[1]])
        if support["stack"] != expected["stack"]:
            raise ValueError("Graphics catalogue stack differs from its manifest.")
        if (
            not support["devices"]
            or not isinstance(support["unsupported"], dict)
            or not nvidia["chips"]
        ):
            raise ValueError("Graphics metadata contains empty or invalid device tables.")
        return support, nvidia
    except (KeyError, TypeError, OSError) as error:
        raise ValueError(
            "Graphics metadata is incomplete or malformed. Use a complete release checkout."
        ) from error


def prepare(directory, provenance):
    manifest = {
        "provenance": provenance,
        "sha256": {name: digest(directory / name) for name in FILES},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    load_metadata(directory, provenance)


def changes(previous, current):
    """Include exclusions and classification changes, not just accepted ID counts."""
    old = {key: ("accepted", value) for key, value in previous.get("devices", {}).items()}
    old.update({key: ("excluded", value) for key, value in previous.get("unsupported", {}).items()})
    new = {key: ("accepted", value) for key, value in current["devices"].items()}
    new.update({key: ("excluded", value) for key, value in current["unsupported"].items()})
    return {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(key for key in old.keys() & new.keys() if old[key] != new[key]),
    }


def atomic_copy(source, destination):
    """Stage a release file in the destination directory before replacing it."""
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as original:
            shutil.copyfileobj(original, target, 1024 * 1024)
            os.fchmod(target.fileno(), mode)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def update(repo):
    result = subprocess.run(
        [
            "nix",
            "build",
            "--no-update-lock-file",
            "--max-jobs",
            "2",
            "--cores",
            "4",
            "--no-link",
            "--print-out-paths",
            ".#graphics-metadata-generated",
        ],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    output = Path(result.stdout.strip())
    provenance = read_json(output / "manifest.json")["provenance"]
    current, _ = load_metadata(output, provenance)
    destination = repo / "hardware/graphics"
    previous = read_json(destination / FILES[0]) if (destination / FILES[0]).exists() else {}
    print(json.dumps(changes(previous, current), indent=2))
    destination.mkdir(parents=True, exist_ok=True)
    # Publish the manifest last. Interrupted updates fail validation, never fall back.
    for name in (*FILES, "manifest.json"):
        atomic_copy(output / name, destination / name)
    directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(
        "Updated release metadata. Review git diff (including NVIDIA changes), then run just check."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "update"))
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("provenance", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "update":
        update(Path(__file__).resolve().parent.parent)
    else:
        if args.directory is None or args.provenance is None:
            parser.error("prepare/check require a directory and provenance JSON file")
        expected = read_json(args.provenance)
        if args.command == "prepare":
            prepare(args.directory, expected)
        else:
            load_metadata(args.directory, expected)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
