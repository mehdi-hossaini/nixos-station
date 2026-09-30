"""Terminal presentation only; this module never reads or changes disks."""

import os
import shutil
import subprocess
import sys

plain = False
verbose = False
demo = False


def geometry():
    size = shutil.get_terminal_size()
    return max(1, min(60, size.columns - 4)), max(1, min(10, size.lines - 12))


def enabled():
    return (
        not plain
        and sys.stdin.isatty()
        and sys.stdout.isatty()
        and os.environ.get("TERM", "dumb") != "dumb"
        and shutil.which("gum") is not None
        # Plain prompts remain usable in tiny terminals and with large fonts.
        and shutil.get_terminal_size().columns >= 40
        and shutil.get_terminal_size().lines >= 18
    )


def environment():
    # Inherited Gum defaults must not prefill confirmations or set timeouts.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GUM_")}
    for component in ("CHOOSE", "FILTER", "INPUT"):
        env[f"GUM_{component}_HEADER_FOREGROUND"] = "6"
        env[f"GUM_{component}_CURSOR_FOREGROUND"] = "6"
    env["GUM_CHOOSE_SELECTED_FOREGROUND"] = "6"
    env["GUM_FILTER_MATCH_FOREGROUND"] = "6"
    env["GUM_SPIN_SPINNER_FOREGROUND"] = "6"
    return env


def gum(*args):
    result = subprocess.run(
        ["gum", *args], text=True, stdout=subprocess.PIPE, env=environment(), check=False
    )
    if result.returncode in (1, 130):
        raise KeyboardInterrupt
    result.check_returncode()
    return result.stdout.rstrip("\n")


def clean(value):
    """Keep device metadata and saved values on one printable terminal line."""
    return "".join(char if char.isprintable() else " " for char in str(value))


def screen(title, subtitle):
    if demo:
        subtitle = "DEMO — fictional disk; nothing will be installed.\n" + subtitle
    if enabled():
        print("\033[2J\033[H", end="", flush=True)
        width = max(20, min(76, shutil.get_terminal_size().columns - 10))
        subprocess.run(
            [
                "gum",
                "style",
                "--border",
                "rounded",
                "--border-foreground",
                "6",
                "--padding",
                "1 2",
                "--margin",
                "1 2",
                "--width",
                str(width),
                "--",
                f"WORKSTATION  /  {title}\n\n{subtitle}",
            ],
            env=environment(),
            check=True,
        )
    else:
        print(f"\n{title}\n{subtitle}")


def select(title, choices, current=None, search=False):
    """Return only a value supplied by the caller, never arbitrary filter text."""
    rows = {f"{index + 1:2}. {clean(label)}": key for index, (key, label) in enumerate(choices)}
    if not enabled():
        print(title)
        for row in rows:
            print(row)
        answer = input("Number: ").strip()
        if not answer.isdecimal() or not 1 <= int(answer) <= len(rows):
            raise ValueError("No valid selection. Nothing was confirmed.")
        return list(rows.values())[int(answer) - 1]
    arguments = [
        "filter" if search else "choose",
        "--header",
        title,
        "--height",
        str(geometry()[1]),
    ]
    if search:
        arguments += ["--strict", "--placeholder", "Type to search; arrows to browse"]
    elif current is not None:
        selected = next((row for row, key in rows.items() if key == current), None)
        if selected:
            arguments += ["--selected", selected]
    answer = gum(*arguments, "--", *rows)
    if answer not in rows:
        raise ValueError("No valid selection. Nothing was confirmed.")
    return rows[answer]


def choose_value(label, choices, current=None):
    """Small numbered pages work on a plain VT without terminal dependencies."""
    if enabled():
        entries = [(value, f"{title} ({value})") for value, title in choices.items()]
        if current in choices:
            entries.insert(0, (current, f"Keep {choices[current]}"))
        return select(label, entries, search=True)
    page_size = 12
    query, page = "", 0
    while True:
        matches = [
            (value, title)
            for value, title in choices.items()
            if query.casefold() in f"{value} {title}".casefold()
        ]
        visible = matches[page * page_size : (page + 1) * page_size]
        print(f"\n{label}" + (f" — filter: {query}" if query else ""))
        for index, (value, title) in enumerate(visible, 1):
            print(f"  {index}. {title}" + (f" ({value})" if title != value else ""))
        print(f"  Page {page + 1}/{max(1, (len(matches) + page_size - 1) // page_size)}")
        keep = f"Enter keeps {choices[current]}; " if current in choices else ""
        answer = input(keep + "number, n/p page, search text, / clear, q cancel: ").strip()
        if not answer and current in choices:
            return current
        if answer.lower() == "q":
            raise KeyboardInterrupt
        if answer.isdigit():
            if 1 <= int(answer) <= len(visible):
                return visible[int(answer) - 1][0]
            print("Choose one of the displayed numbers.")
        elif answer in choices:
            return answer
        elif answer.lower() in ("n", "p"):
            last = max(0, (len(matches) - 1) // page_size)
            page = min(last, page + 1) if answer.lower() == "n" else max(0, page - 1)
        elif answer == "/":
            query, page = "", 0
        elif answer:
            if any(
                answer.casefold() in f"{value} {title}".casefold()
                for value, title in choices.items()
            ):
                query, page = answer, 0
            else:
                print("No matches. Try a shorter name or browse with n/p.")


def checklist(title, choices, selected):
    rows = {clean(label): key for key, label in choices}
    if not enabled():
        print(title)
        for index, (row, key) in enumerate(rows.items(), 1):
            print(f"{index}. [{'x' if key in selected else ' '}] {row}")
        answer = input("Selected numbers separated by spaces (empty selects none): ").split()
        if any(not number.isdecimal() or not 1 <= int(number) <= len(rows) for number in answer):
            raise ValueError("Invalid optional-app selection.")
        return {list(rows.values())[int(number) - 1] for number in answer}
    arguments = [
        "choose",
        "--no-limit",
        "--height",
        str(min(8, geometry()[1])),
        "--header",
        title,
        "--selected-prefix",
        "[x] ",
        "--unselected-prefix",
        "[ ] ",
        "--cursor-prefix",
        "[ ] ",
    ]
    for row, key in rows.items():
        if key in selected:
            arguments += ["--selected", row]
    output = gum(*arguments, "--", *rows)
    answers = output.splitlines() if output else []
    if any(answer not in rows for answer in answers):
        raise ValueError("Invalid optional-app selection.")
    return {rows[answer] for answer in answers}


def text(label, default="", placeholder=""):
    if not enabled():
        return input(f"{label}" + (f" [{default}]" if default else "") + ": ")
    return gum(
        "input",
        "--header",
        label,
        "--value",
        str(default),
        "--placeholder",
        placeholder,
        "--width",
        str(geometry()[0]),
    )


def progress_command(args, capture=False):
    """Decorate only noninteractive Nix work; password tools keep their own TTY."""
    if not enabled() or verbose:
        return args
    title = "Checking configuration…"
    if "build" in args:
        title = "Downloading / building — please wait; the target disk is unchanged"
    flags = ["--show-stdout"] if capture else []
    return ("gum", "spin", "--show-error", *flags, "--title", title, "--", *args)
