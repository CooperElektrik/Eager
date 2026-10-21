"""Animation timeline and tweening engine for smooth parameter transitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from eager_core.easing import EasingFunc, linear
from eager_core.types import Color, Vec2


@dataclass
class Tween:
    """An active parameter interpolation targeting an object property."""

    target: Any
    property_name: str
    start_value: Any
    end_value: Any
    duration: float
    easing: EasingFunc = linear
    delay: float = 0.0
    elapsed: float = 0.0
    on_complete: Callable[[], Any] | None = None
    on_update: Callable[[Any], Any] | None = None
    finished: bool = False

    def finish(self) -> None:
        """Immediately complete the tween at its end_value and invoke callbacks."""
        if self.finished:
            return
        self.finished = True
        self._apply_value(self.end_value)
        if self.on_update is not None:
            self.on_update(self.end_value)
        if self.on_complete is not None:
            self.on_complete()

    def update(self, dt: float) -> bool:
        """Advance the tween by dt seconds. Returns True if tween is still running."""
        if self.finished:
            return False

        self.elapsed += dt
        if self.elapsed < self.delay:
            return True

        active_time = self.elapsed - self.delay
        if self.duration <= 0.0 or active_time >= self.duration:
            self.finish()
            return False

        # Compute normalized progress
        t = active_time / self.duration
        eased_t = self.easing(max(0.0, min(1.0, t)))
        current_val = self._interpolate(self.start_value, self.end_value, eased_t)
        self._apply_value(current_val)

        if self.on_update is not None:
            self.on_update(current_val)

        return True

    def _interpolate(self, start: Any, end: Any, t: float) -> Any:
        """Interpolate between start and end values given factor t in [0.0, 1.0]."""
        if isinstance(start, Vec2) and isinstance(end, Vec2):
            return start.lerp(end, t)
        if isinstance(start, Color) and isinstance(end, Color):
            return start.lerp(end, t)
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            return float(start) + (float(end) - float(start)) * t
        # Non-interpolatable types snap at completion
        return end if t >= 1.0 else start

    def _apply_value(self, val: Any) -> None:
        """Assign the interpolated value to the target object's property."""
        if hasattr(self.target, self.property_name):
            setattr(self.target, self.property_name, val)
        elif isinstance(self.target, dict):
            self.target[self.property_name] = val


class Timeline:
    """Manages concurrent tweens and drives animation updates."""

    def __init__(self) -> None:
        self._tweens: list[Tween] = []

    @property
    def active_count(self) -> int:
        """Number of currently running tweens."""
        return len(self._tweens)

    def active_tweens(self) -> list[dict[str, Any]]:
        """Return a debug-friendly summary of all active tweens.

        Each entry is a plain dict containing the target's debug identifier
        (its ``element_id``/``id`` attribute or ``repr``), the property name,
        normalized progress in ``[0.0, 1.0]``, and remaining time. This lets
        callers (e.g. ``StageCompositor.debug_info``) introspect the timeline
        without touching private tween state or rendering values to the screen.
        """
        summaries: list[dict[str, Any]] = []
        for tween in self._tweens:
            if tween.duration <= 0.0:
                progress = 1.0
            else:
                active_time = max(0.0, tween.elapsed - tween.delay)
                progress = min(1.0, active_time / tween.duration)
            remaining = max(0.0, tween.duration - (tween.elapsed - tween.delay))

            target = tween.target
            if hasattr(target, "element_id"):
                target_id = target.element_id  # type: ignore[attr-defined]
            elif hasattr(target, "asset_id"):
                target_id = target.asset_id  # type: ignore[attr-defined]
            elif hasattr(target, "__dict__") and "element_id" in target.__dict__:
                target_id = target.__dict__["element_id"]  # type: ignore[index]
            else:
                # Fall back to a short, stable repr (no sensitive data)
                target_id = repr(target)[:80]

            summaries.append(
                {
                    "target": target_id,
                    "property": tween.property_name,
                    "progress": round(progress, 4),
                    "duration": round(tween.duration, 4),
                    "remaining": round(remaining, 4),
                    "delay": round(tween.delay, 4),
                }
            )
        return summaries

    def add_tween(
        self,
        target: Any,
        property_name: str,
        end_value: Any,
        duration: float,
        *,
        start_value: Any = None,
        easing: EasingFunc = linear,
        delay: float = 0.0,
        on_complete: Callable[[], Any] | None = None,
        on_update: Callable[[Any], Any] | None = None,
    ) -> Tween:
        """Create, register, and return a new tween."""
        # Determine starting value
        if start_value is None:
            if hasattr(target, property_name):
                start_value = getattr(target, property_name)
            elif isinstance(target, dict):
                start_value = target.get(property_name)
            else:
                msg = f"Cannot read initial property '{property_name}' from target"
                raise AttributeError(msg)

        tween = Tween(
            target=target,
            property_name=property_name,
            start_value=start_value,
            end_value=end_value,
            duration=max(0.0, duration),
            easing=easing,
            delay=max(0.0, delay),
            on_complete=on_complete,
            on_update=on_update,
        )

        # Cancel any existing tween targeting the same property on this target
        self.cancel_tweens_for(target, property_name)

        if duration <= 0.0 and delay <= 0.0:
            # Immediate assignment
            tween.update(0.0)
            return tween

        self._tweens.append(tween)
        return tween

    def cancel_tweens_for(self, target: Any, property_name: str | None = None) -> None:
        """Cancel active tweens targeting a specific object, optionally for a specific property."""
        remaining: list[Tween] = []
        for t in self._tweens:
            if t.target is target and (property_name is None or t.property_name == property_name):
                t.finished = True
            else:
                remaining.append(t)
        self._tweens = remaining

    def has_tweens(self, target: Any = None) -> bool:
        """Check if any tweens are active, optionally filtering by target."""
        if target is None:
            return bool(self._tweens)
        return any(t.target is target for t in self._tweens)

    def update(self, dt: float) -> None:
        """Advance all active tweens by dt seconds."""
        if not self._tweens:
            return

        # Snapshot current list so on_complete/on_update callbacks can safely add/cancel tweens
        current = list(self._tweens)
        for tween in current:
            if not tween.finished:
                tween.update(dt)

        self._tweens = [t for t in self._tweens if not t.finished]

    def finish_all(self) -> None:
        """Complete all active tweens immediately, snapping to end values and running callbacks."""
        iterations = 0
        while self._tweens and iterations < 100:
            iterations += 1
            current = list(self._tweens)
            self._tweens.clear()
            for tween in current:
                if not tween.finished:
                    tween.finish()

    def flush(self) -> None:
        """Alias for finish_all()."""
        self.finish_all()

    def clear(self) -> None:
        """Cancel and remove all active tweens."""
        for t in self._tweens:
            t.finished = True
        self._tweens.clear()
