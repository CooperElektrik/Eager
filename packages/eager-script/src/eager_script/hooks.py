"""Parser for Eager screenplay engine hook arguments.

This is a pure, dependency-free parser for the argument tail of a screenplay
hook line (``~ hook_name <args>``).  It understands positional tokens,
contextual keywords (``at``/``with``/``to``), ``key=value`` pairs, and quoted
strings.  Because it belongs to the parsing layer it deliberately knows nothing
about rendering types (such as ``Color``) — callers decode typed values from the
raw string getters.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HookArgs:
    """Structured representation of parsed engine hook arguments."""

    positional: tuple[str, ...] = ()
    at: str | None = None
    with_: str | None = None
    to: str | None = None
    kwargs: dict[str, str] = field(default_factory=dict)

    def get_str(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a string argument by keyword name."""
        return self.kwargs.get(key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Retrieve a floating-point argument by keyword name."""
        val = self.kwargs.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except ValueError:
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        """Retrieve an integer argument by keyword name."""
        val = self.kwargs.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Retrieve a boolean argument (e.g. true/false/yes/no/1/0)."""
        val = self.kwargs.get(key)
        if val is None:
            return default
        lower = val.strip().lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
        return default

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "positional": list(self.positional),
            "at": self.at,
            "with": self.with_,
            "to": self.to,
            "kwargs": dict(self.kwargs),
        }


def parse_hook_args(raw_args: str) -> HookArgs:
    """Parse a raw screenplay hook argument string into a structured HookArgs object.

    Handles positional tokens, contextual keywords ('at', 'with', 'to'),
    key=value pairs, and quoted strings.

    Examples:
        >>> parse_hook_args("castle_gate")
        HookArgs(positional=('castle_gate',), at=None, with_=None, to=None, kwargs={})

        >>> parse_hook_args("alice happy at left with dissolve duration=0.8")
        HookArgs(positional=('alice', 'happy'), at='left', with_='dissolve', to=None, kwargs={'duration': '0.8'})

        >>> parse_hook_args("bob to right duration=0.5 easing=ease_out_quad")
        HookArgs(positional=('bob',), at=None, with_=None, to='right', kwargs={'duration': '0.5', 'easing': 'ease_out_quad'})
    """
    if not raw_args or not raw_args.strip():
        return HookArgs()

    try:
        tokens = shlex.split(raw_args)
    except ValueError:
        # Fallback to simple split if shlex fails on unmatched quotes
        tokens = raw_args.strip().split()

    positional: list[str] = []
    at_val: str | None = None
    with_val: str | None = None
    to_val: str | None = None
    kwargs: dict[str, str] = {}

    idx = 0
    num_tokens = len(tokens)

    while idx < num_tokens:
        tok = tokens[idx]

        # Key-value pair (e.g. duration=1.5 or color=#fff)
        if "=" in tok:
            k, v = tok.split("=", 1)
            kwargs[k.strip()] = v.strip()
            idx += 1
            continue

        # Contextual keywords: 'at', 'with', 'to'
        tok_lower = tok.lower()
        if tok_lower == "at" and idx + 1 < num_tokens and "=" not in tokens[idx + 1]:
            at_val = tokens[idx + 1]
            idx += 2
            continue

        if tok_lower == "with" and idx + 1 < num_tokens and "=" not in tokens[idx + 1]:
            with_val = tokens[idx + 1]
            idx += 2
            continue

        if tok_lower == "to" and idx + 1 < num_tokens and "=" not in tokens[idx + 1]:
            to_val = tokens[idx + 1]
            idx += 2
            continue

        # Positional token
        positional.append(tok)
        idx += 1

    return HookArgs(
        positional=tuple(positional),
        at=at_val,
        with_=with_val,
        to=to_val,
        kwargs=kwargs,
    )
