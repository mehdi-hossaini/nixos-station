"""Exercise the evaluated retention script with a failing Btrfs command."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

script = Path(sys.argv[1]).read_text()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    snapshots = root / "snapshots"
    for source in ("projects", "persist"):
        for index in range(26):
            (snapshots / source / f"20200101T{index:09d}").mkdir(parents=True)
    commands = root / "commands"
    commands.mkdir()
    btrfs = commands / "btrfs"
    btrfs.write_text(
        f"#!{shutil.which('bash')}\nset -euo pipefail\n"
        'printf "%s\\n" "$*" >> "$SNAPSHOT_TEST_LOG"\n'
        'case "$2" in\n'
        'delete) rmdir -- "$3";;\n'
        "sync) :;;\n"
        'snapshot) if [[ $4 == /projects && -e $SNAPSHOT_TEST_FAIL ]]; then exit 1; fi; mkdir -- "$5";;\n'
        "*) exit 2;;\nesac\n"
    )
    btrfs.chmod(0o755)
    evaluated = root / "retention.sh"
    evaluated.write_text(
        script.replace("/.snapshots/", str(snapshots) + "/").replace(
            "/run/workstation-snapshots.", str(root / "listing.")
        )
    )
    failure = root / "fail"
    failure.touch()
    log = root / "log"
    env = os.environ | {
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "SNAPSHOT_TEST_LOG": str(log),
        "SNAPSHOT_TEST_FAIL": str(failure),
    }
    result = subprocess.run(["bash", str(evaluated)], env=env, capture_output=True, text=True)
    assert result.returncode == 1, result
    assert len(list((snapshots / "projects").iterdir())) == 23
    assert len(list((snapshots / "persist").iterdir())) == 24
    lines = log.read_text().splitlines()
    creation = next(index for index, line in enumerate(lines) if "snapshot -r /projects" in line)
    assert any("delete" in line for line in lines[:creation])
    assert any("sync" in line for line in lines[:creation])
    assert any("snapshot -r /persist" in line for line in lines)
    failure.unlink()
    subprocess.run(["bash", str(evaluated)], env=env, check=True, capture_output=True)
    for source in ("projects", "persist"):
        assert len(list((snapshots / source).iterdir())) == 24
    print("Retention survives snapshot failure, continues both tiers and recovers.")
