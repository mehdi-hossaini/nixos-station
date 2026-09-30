"""Exercise project selection and terminal directory reporting without a desktop."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

workflow = str(Path(sys.argv[1]).resolve())


def shell(script, env):
    return subprocess.run(
        ["zsh", "-f", "-c", 'source "$1"; ' + script, "zsh", workflow],
        env=env,
        check=True,
        capture_output=True,
    ).stdout


with tempfile.TemporaryDirectory() as directory:
    home = Path(directory)
    projects = home / "Projects"
    projects.mkdir()
    unusual = projects / "space ' quote % café\nnext line"
    unusual.mkdir()
    (projects / "another-project").mkdir()
    env = os.environ | {
        "HOME": str(home),
        "__NIXOS_SET_ENVIRONMENT_DONE": "1",
        # Real fzf's noninteractive filter exercises its NUL input/output path.
        "FZF_DEFAULT_OPTS": "--filter=café",
    }
    selected = shell('cproj; printf "%s" "$PWD"', env)
    assert selected.decode() == str(unusual), selected
    cancelled = shell(
        'cd -- "$HOME"; cproj; printf "%s" "$PWD"',
        env | {"FZF_DEFAULT_OPTS": "--filter=missing-project"},
    )
    assert cancelled.decode() == str(home), cancelled
    result = shell("cproj; HOST=fixture; _workstation_report_cwd", env)
    expected = f"\x1b]7;file://fixture{quote(str(unusual), safe='/')}\x1b\\".encode()
    assert result == expected, (result, expected)
    print("Project selection, cancellation and encoded directory reporting passed.")
