"""Device output decoding, prompt detection, and pagination cleanup."""

from __future__ import annotations

import re
from collections.abc import Iterable


# A real prompt line must contain at least one non-whitespace,
# non-prompt char before the final prompt char.  ``\S`` is enough
# to reject bare ``>``/``#`` lines that some devices emit as
# separators, while still accepting ``Switch>``/``Switch#``.
# ``%`` is included so legacy SDT firmware that uses ``cli%``
# (unprivileged shell) is still recognised.
PROMPT_RE = re.compile(
    r"(?:^|[\r\n])\S[^\r\n]*[>#$%]\s*$"
)
PAGINATION_MARKERS = (
    "More:",
    "--More--",
    "---More---",
    "<--- More --->",
    "(more)",
    "Press any key to continue",
    "Press RETURN to continue",
    "space/ctrl+c/other",
)

# Substrings that mark a line as a menu/option/confirmation prompt
# rather than a shell prompt.  These never end in ``>``/``#`` but
# were getting misclassified by the old single-char suffix fallback
# because they end in ``]``.
_MENU_PROMPT_MARKERS = (
    "[y/n]",
    "[yes/no]",
    "[enter]",
    "[return]",
    "[ok]",
    "[continue]",
    "[continue?]",
    "press any key to continue",
    "are you sure",
)


def decode_bytes(value: bytes | str, encodings: Iterable[str]) -> str:
    if isinstance(value, str):
        return value
    for encoding in encodings:
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode(next(iter(encodings), "utf-8"), errors="replace")


def _looks_like_menu_prompt(line: str) -> bool:
    lowered = line.lower()
    if any(marker in lowered for marker in _MENU_PROMPT_MARKERS):
        return True
    # Generic question/option heuristic: a line ending in ``?``
    # is almost never a real device prompt.  It is always a
    # confirmation ("Are you sure? [Y/N]") or a menu option.
    if line.rstrip().endswith("?"):
        return True
    return False


def has_prompt(output: str) -> bool:
    """
    Return True when the last non-empty line of output looks
    like a device prompt (e.g. Switch>, R1#, [SW1]>).

    The decision is made on the **last** non-empty line because
    network devices always emit the command echo + output + prompt
    in that order.  The original heuristic matched any line ending
    in one of ``> # ] $ %`` which silently misclassified
    confirmation menus (``[Y/N]``) and ``Press any key to continue
    [Enter]`` as prompts, truncating the next command's output.
    """
    stripped = output.rstrip()
    if not stripped:
        return False
    last_line = stripped.rsplit("\n", 1)[-1].rstrip()
    if not last_line:
        return False
    if _looks_like_menu_prompt(last_line):
        return False
    if PROMPT_RE.search("\n" + last_line):
        return True
    # Bracketed prompts like ``[hostname]>`` or ``[hostname]`` are
    # the SDT default.  We require the line to actually start with
    # ``[`` so we don't catch trailing ``]`` from menu lists.
    if last_line.startswith("["):
        if last_line.endswith(("]", "$", "%")):
            return True
        if last_line.endswith(("]>", "]#")):
            return True
    return False
def has_pagination(output: str) -> bool:
    lowered = output.lower()
    return any(marker.lower() in lowered for marker in PAGINATION_MARKERS)


def normalize_output(output: str) -> str:
    lines = []
    previous_blank = False
    for raw_line in output.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip("\t ")
        blank = not line.strip()
        if blank and previous_blank:
            continue
        lines.append(line)
        previous_blank = blank
    result = "\n".join(lines).strip("\n")
    return result + ("\n" if result else "")


def filter_output(output: str, command: str | None = None) -> str:
    filtered: list[str] = []
    for line in output.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            filtered.append(line)
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        if any(marker.lower() in stripped.lower() for marker in PAGINATION_MARKERS):
            continue
        if command and stripped == command.strip():
            continue
        filtered.append(line)
    return normalize_output("\n".join(filtered))
