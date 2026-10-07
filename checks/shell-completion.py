"""Exercise completion and history suggestions in a real, isolated terminal."""

import fcntl
import os
import pty
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

source = Path(sys.argv[1]).read_text()
original_home = sys.argv[2]
capture_mode = sys.argv[3]
assert capture_mode in {"compiled", "shell"}
assert "zsh-autocomplete.plugin.zsh" not in source
assert source.index("autoload -U compinit") < source.index("fzf-tab.plugin.zsh")
assert source.index("fzf-tab.plugin.zsh") < source.index("zsh-autosuggestions.zsh")

with tempfile.TemporaryDirectory() as directory:
    home = Path(directory)
    (home / ".local/state/zsh").mkdir(parents=True)
    quoted_files = [
        "completion space ' \" quote.txt",
        "completion back\\slash.txt",
        "completion ($HOME); [λ].txt",
    ]
    for name in ["completion-alpha.txt", "completion-target.txt", *quoted_files]:
        (home / name).touch()
    (home / "bin").mkdir()
    fzf = shutil.which("fzf")
    assert fzf
    wrapper = home / "bin/fzf"
    wrapper.write_text(
        f'#!{shutil.which("sh")}\nprintf "invoked\\n" >> "$HOME/fzf-invocations"\nexec {shlex.quote(fzf)} "$@"\n'
    )
    wrapper.chmod(0o755)
    (home / "starship.toml").write_text('format = "TEST> "\n')
    (home / ".local/state/zsh/history").write_text("echo COMPLETION_HISTORY_FIXTURE\n")
    (home / ".zshrc").write_text(
        source.replace(original_home, str(home))
        + ("\nzmodload -u aloxaf/fzftab\n" if capture_mode == "shell" else "")
        + """
fc -R "$HISTFILE"
ZSH_AUTOSUGGEST_IGNORE_WIDGETS+=(_completion_probe)
_completion_probe() {
  printf '%s\\0%s\\0%s\\0' "$BUFFER" "$POSTDISPLAY" "$CURSOR" > "$HOME/probe"
}
zle -N _completion_probe
bindkey '^X^T' _completion_probe
preexec() { print -r -- "$1" >> "$HOME/executed"; }
print -r -- ready > "$HOME/ready"
print -r -- ${+builtins[fzf-tab-candidates-generate]} > "$HOME/compiled"
"""
    )

    pid, terminal = pty.fork()
    if pid == 0:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_SETMASK, [])
        os.chdir(home)
        env = os.environ | {
            "HOME": str(home),
            "ZDOTDIR": str(home),
            "PATH": str(home / "bin") + os.pathsep + os.environ["PATH"],
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "STARSHIP_CONFIG": str(home / "starship.toml"),
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "__NIXOS_SET_ENVIRONMENT_DONE": "1",
        }
        os.execvpe("zsh", ["zsh", "-d", "-i"], env)

    fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    output = bytearray()

    def drain(duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            ready, _, _ = select.select([terminal], [], [], max(0, deadline - time.monotonic()))
            if ready:
                try:
                    data = os.read(terminal, 65536)
                except OSError:
                    raise AssertionError(output.decode(errors="replace")) from None
                if not data:
                    raise AssertionError(output.decode(errors="replace"))
                requests = output.count(b"\x1b[6n")
                output.extend(data)
                # fzf asks for the cursor position; emulate a terminal reply.
                for _ in range(output.count(b"\x1b[6n") - requests):
                    os.write(terminal, b"\x1b[3;1R")

    def send(data):
        os.write(terminal, data)
        drain(0.6)

    def probe():
        path = home / "probe"
        path.unlink(missing_ok=True)
        send(b"\x18\x14")
        assert path.exists(), output.decode(errors="replace")
        fields = path.read_bytes().split(b"\0")
        assert len(fields) == 4, fields
        return tuple(field.decode() for field in fields[:3])

    def completed_arguments(buffer):
        # Evaluate only fixture commands, checking actual argument expansion.
        result = subprocess.run(
            [
                "zsh",
                "-f",
                "-c",
                'cat() { printf "%s\\0" "$@"; }; '
                'unregistered-completion-fixture() { cat "$@"; }; ' + buffer,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.split("\0")[:-1]

    try:
        drain(2)
        assert (home / "ready").exists(), output.decode(errors="replace")
        assert (home / "compiled").read_text().strip() == (
            "1" if capture_mode == "compiled" else "0"
        ), "Unexpected fzf-tab capture mode."
        send(b"echo COMPLETION_HISTORY_")
        assert probe()[:2] == ("echo COMPLETION_HISTORY_", "FIXTURE"), probe()
        assert not (home / "fzf-invocations").exists(), "Typing opened the picker."
        send(b"\x1b[C")
        assert probe()[:2] == ("echo COMPLETION_HISTORY_FIXTURE", ""), probe()
        assert not (home / "executed").exists(), "Accepting a suggestion executed it."

        send(b"\x15")
        send(b"cat completion-")
        assert not (home / "fzf-invocations").exists(), "Typing opened the picker."
        send(b"\t")
        assert (home / "fzf-invocations").exists(), "Tab did not open the picker."
        send(b"target")
        send(b"\r")
        assert probe()[0].strip() == "cat completion-target.txt", probe()
        assert not (home / "executed").exists(), "Selecting a completion executed it."

        send(b"\x15")
        send(b"cat completion-")
        before = probe()[0]
        send(b"\t")
        send(b"\x1b")
        assert probe()[0] == before, "Cancelling changed the command line."

        for quote in [b'"', b"'"]:
            send(b"\x15")
            send(b"cat " + quote + b"completion-")
            (home / "fzf-invocations").unlink()
            send(b"\t")
            assert (home / "fzf-invocations").exists(), "Quoted Tab did not open the picker."
            send(b"target")
            send(b"\r")
            buffer = probe()[0]
            assert completed_arguments(buffer) == ["completion-target.txt"], buffer
            assert not (home / "executed").exists(), "Quoted completion executed a command."

        # cat uses Carapace; an unregistered command uses native Zsh file completion.
        for command in [b"cat", b"unregistered-completion-fixture"]:
            for quote in [b"", b'"', b"'"]:
                for filename, query in zip(quoted_files, [b"space", b"back", b"HOME"], strict=True):
                    send(b"\x15")
                    send(command + b" " + quote + b"completion")
                    (home / "fzf-invocations").unlink()
                    send(b"\t")
                    assert (home / "fzf-invocations").exists(), "Path Tab did not open the picker."
                    send(query)
                    send(b"\r")
                    buffer = probe()[0]
                    # Native Zsh may leave a quote open to extend the argument.
                    if quote and not buffer.rstrip().endswith(quote.decode()):
                        send(quote)
                        buffer = probe()[0]
                    assert completed_arguments(buffer) == [filename], (buffer, filename)

        send(b"\x15")
        send(b"git --vers")
        send(b"\t")
        assert probe()[0].strip() == "git --version", probe()
        assert not (home / "executed").exists(), "Completion executed a command."
        assert b"unmatched" not in output, output.decode(errors="replace")
        print(
            f"Quiet typing, inline suggestions, Tab selection/cancellation, path quoting and flag completion passed ({capture_mode})."
        )
    except BaseException:
        print(output[-8000:].decode(errors="replace"), file=sys.stderr)
        raise
    finally:
        os.close(terminal)
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
