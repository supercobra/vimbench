"""Core harness: translate a human-readable keystroke notation into bytes,
replay them into headless vim, and return the resulting buffer.

Notation:
    <Esc>   Escape            <CR>  Enter / carriage return
    <Tab>   Tab               <Space>  literal space
    <BS>    Backspace         <NL>  newline (0x0a)
    <C-X>   Ctrl+X for any letter X (e.g. <C-V> visual block, <C-R> redo)
    <<      literal '<' character (escape for the token syntax)
Everything else is passed through as literal UTF-8 bytes.
"""

import os
import re
import subprocess
import tempfile

VIM_BIN = os.environ.get("VIMBENCH_VIM", "vi")
TIMEOUT_S = 10

_TOKEN_RE = re.compile(r"<(Esc|CR|NL|Tab|Space|BS|C-[A-Za-z])>")

_TOKEN_BYTES = {
    "Esc": b"\x1b",
    "CR": b"\x0d",
    "NL": b"\x0a",
    "Tab": b"\x09",
    "Space": b" ",
    "BS": b"\x08",
}


def notation_to_bytes(notation: str) -> bytes:
    """Convert keystroke notation to the raw bytes fed to vim's -s script."""
    out = bytearray()
    i = 0
    n = len(notation)
    while i < n:
        ch = notation[i]
        if ch == "<":
            if notation.startswith("<<", i):
                out += b"<"
                i += 2
                continue
            m = _TOKEN_RE.match(notation, i)
            if not m:
                raise ValueError(
                    f"Invalid token at offset {i}: {notation[i:i+14]!r} "
                    "(use << for a literal '<')"
                )
            tok = m.group(1)
            if tok.startswith("C-"):
                out += bytes([ord(tok[2].upper()) - ord("A") + 1])
            else:
                out += _TOKEN_BYTES[tok]
            i = m.end()
        else:
            out += ch.encode("utf-8")
            i += 1
    return bytes(out)


# Appended to every script so vim always saves whatever state it is in and
# exits (prevents hangs when the model forgets :wq or leaves insert mode).
_SAFETY_SUFFIX = b"\x1b:wq!\r"


def run_vim(start_text: str, notation: str, timeout: int = TIMEOUT_S):
    """Replay keystrokes into vim starting from start_text.

    Returns (final_text, error). error is None on a clean run, otherwise a
    short reason string ('timeout', 'vim-error', 'bad-notation').
    """
    try:
        keys = notation_to_bytes(notation) + _SAFETY_SUFFIX
    except ValueError as e:
        return start_text, f"bad-notation: {e}"

    with tempfile.TemporaryDirectory(prefix="vimbench-") as d:
        buf_path = os.path.join(d, "buf.txt")
        keys_path = os.path.join(d, "keys")
        with open(buf_path, "w", encoding="utf-8") as f:
            f.write(start_text)
        with open(keys_path, "wb") as f:
            f.write(keys)
        try:
            subprocess.run(
                [VIM_BIN, "-u", "NONE", "-N", "-n",
                 # Anti-cheat: no shelling out (:!cmd, :r !cmd) — this is a
                 # vim-skill benchmark, not a shell benchmark.
                 "--cmd", "set shell=/bin/false",
                 "-s", keys_path, buf_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                env={**os.environ, "TERM": "dumb"},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return start_text, f"timeout: keystrokes did not finish in {timeout}s"
        try:
            with open(buf_path, encoding="utf-8") as f:
                return f.read(), None
        except OSError:
            return start_text, "vim-error: buffer unreadable after run"


def keystroke_count(notation: str) -> int:
    """Number of actual keystrokes (bytes) the notation expands to."""
    return len(notation_to_bytes(notation))


def tokenize(notation: str) -> list:
    """Split notation into atomic units (tokens like <Esc> or single chars),
    for safe chunking that never splits mid-token."""
    units = []
    i, n = 0, len(notation)
    while i < n:
        if notation.startswith("<<", i):
            units.append("<<")
            i += 2
        elif notation[i] == "<":
            m = _TOKEN_RE.match(notation, i)
            if not m:
                raise ValueError(f"Invalid token at offset {i}")
            units.append(notation[i:m.end()])
            i = m.end()
        else:
            units.append(notation[i])
            i += 1
    return units
