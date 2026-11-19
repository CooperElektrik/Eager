"""Compact, deterministic PCG32 pseudo-random number generator for StoryVM."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

_MASK32 = 0xFFFFFFFF
_MASK64 = 0xFFFFFFFFFFFFFFFF
_MULT64 = 6364136223846793005
_DEFAULT_SEQ = 0xDA3E39CB94B95BDB


class PCG32:
    """PCG-XSH-RR 32-bit PRNG with 128 bits of serializable state (state, inc)."""

    __slots__ = ("_inc", "_state")

    def __init__(self, seed: int | None = None, *, seq: int = _DEFAULT_SEQ) -> None:
        self._state = 0
        self._inc = 1
        self.seed(seed, seq=seq)

    def seed(self, seed: int | None = None, *, seq: int = _DEFAULT_SEQ) -> None:
        """Initialize the generator deterministically from *seed* and *seq*."""
        if seed is None:
            seed = int.from_bytes(os.urandom(8), "little")
        self._state = 0
        self._inc = (((seq & _MASK64) << 1) | 1) & _MASK64
        self._next_u32()
        self._state = (self._state + (seed & _MASK64)) & _MASK64
        self._next_u32()

    def _next_u32(self) -> int:
        oldstate = self._state
        self._state = (oldstate * _MULT64 + self._inc) & _MASK64
        xorshifted = (((oldstate >> 18) ^ oldstate) >> 27) & _MASK32
        rot = (oldstate >> 59) & 0x1F
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & _MASK32

    def _randbelow(self, n: int) -> int:
        """Return a uniformly distributed integer in [0, n)."""
        if n <= 0:
            msg = "n must be positive"
            raise ValueError(msg)
        if n <= 1 << 32:
            threshold = (1 << 32) % n
            while True:
                r = self._next_u32()
                if r >= threshold:
                    return r % n
        k = n.bit_length()
        words = (k + 31) // 32
        while True:
            r = 0
            for _ in range(words):
                r = (r << 32) | self._next_u32()
            r >>= words * 32 - k
            if r < n:
                return r

    def random(self) -> float:
        """Return a uniformly distributed float in [0.0, 1.0) with 53-bit precision."""
        high = self._next_u32() >> 5
        low = self._next_u32() >> 6
        return ((high << 26) | low) / 9007199254740992.0

    def randint(self, a: int, b: int) -> int:
        """Return a random integer N such that a <= N <= b."""
        if a > b:
            msg = f"empty range for randint({a}, {b})"
            raise ValueError(msg)
        return a + self._randbelow(b - a + 1)

    def uniform(self, a: float, b: float) -> float:
        """Return a random float N in [a, b] (or [b, a] if b < a)."""
        return a + (b - a) * self.random()

    def getstate(self) -> list[int]:
        """Return JSON-serializable [state, inc] pair."""
        return [self._state, self._inc]

    def setstate(self, state: Sequence[int] | Any) -> None:
        """Restore state from a [state, inc] sequence."""
        if not isinstance(state, Sequence) or isinstance(state, (str, bytes)) or len(state) != 2:
            msg = "PCG32 state must be a 2-element [state, inc] sequence"
            raise ValueError(msg)
        s, inc = state[0], state[1]
        if isinstance(s, bool) or not isinstance(s, int) or isinstance(inc, bool) or not isinstance(inc, int):
            msg = "PCG32 state elements must be integers"
            raise TypeError(msg)
        self._state = s & _MASK64
        self._inc = (inc & _MASK64) | 1
