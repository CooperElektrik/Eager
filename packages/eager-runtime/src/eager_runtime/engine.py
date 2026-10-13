"""Unified visual-novel engine facade for the Eager runtime.

The :class:`VisualEngine` ties together the four layers that an interactive
visual novel requires — the narrative VM, the event dispatcher, the stage
compositor, and the stage director — and exposes a single, ergonomic surface
area for CLI and programmatic use.

Import ``engine`` explicitly to pull in the graphics sub-system
(``eager_graphics``); a bare ``import eager_runtime`` is headless-only and
does **not** require graphics.

Dependency DAG (bottom → top): ``eager-script`` → ``eager-runtime`` →
``eager-graphics``.  Graphics components are imported at module level here;
because this module is itself imported lazily (via ``__getattr__`` in the
package ``__init__``), users who only need the headless VM never pay the
graphics import cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector
from eager_graphics.renderers.null import NullRenderer

# Graph parsing lives in eager_script
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.events import ChoicePromptEvent, StoryEvent
from eager_runtime.runtime import StoryVM
from eager_runtime.state import StorySnapshot


class StateCorruptionError(Exception):
    """Raised when a save slot cannot be restored atomically."""


@dataclass(frozen=True)
class SaveSlot:
    """Atomic save container holding both narrative and visual state.

    Attributes
    ----------
    story_state
        Serialized snapshot from ``StoryVM.save().to_dict()`` — scene ID,
        beat index, call stack, variables, visited scenes.
    visual_state
        Serialized snapshot from ``StageDirector.save_visual_state()`` —
        compositor stage, UI state, and visual history stack.
    """

    story_state: dict[str, Any]
    visual_state: dict[str, Any]


class VisualEngine:
    """High-level orchestrator that wires the story VM, compositor, director,
    and a rendering backend into a single manageable facade.

    Wraps a :class:`~eager_runtime.session.GameSession` while preserving full
    backward compatibility with existing methods and attributes.
    """

    # Backend name → renderer class import path (lazy)
    _BACKEND_NULL = "null"
    _BACKEND_PYGLET = "pyglet"
    _BACKEND_PIL = "pil"
    _BACKEND_RAYLIB = "raylib"

    def __init__(
        self,
        script_path: str | Path,
        *,
        backend: str = "null",
        audio_backend: Any = None,
        asset_dir: str | Path | None = None,
        virtual_width: int = 1920,
        virtual_height: int = 1080,
        plain: bool = False,
        max_history: int = 500,
    ) -> None:
        from eager_runtime.session import GameSession

        self.script_path = Path(script_path)
        self.backend = backend
        self.audio_backend = audio_backend
        if asset_dir is not None:
            self.asset_dir = Path(asset_dir)
        else:
            candidate = self.script_path.resolve().parent / "assets"
            self.asset_dir = candidate if candidate.is_dir() else None
        self.plain = plain
        # Create session wrapping the VM and director
        self.session = GameSession(
            self.script_path,
            backend=backend,
            audio_backend=audio_backend,
            asset_dir=self.asset_dir,
            virtual_width=virtual_width,
            virtual_height=virtual_height,
            plain=plain,
            rollback_limit=max_history,
        )

        # Mirror session components on VisualEngine for backwards compatibility
        self.vm: StoryVM = self.session.vm
        self.dispatcher: EventDispatcher = self.session.dispatcher
        self.compositor: StageCompositor = self.session.compositor
        self.director: StageDirector = self.session.director
        if max_history > 0:
            self.director.enable_visual_history(max_history=max_history)

        # --- 6. Instantiate the rendering backend --------------------
        self._renderer = self._create_renderer(backend)

        # Cached render list for quick inspection without re-rendering
        self._last_render_list: list[Any] = []

    def _create_renderer(self, backend: str) -> Any:
        if backend == self._BACKEND_NULL:
            return NullRenderer()
        elif backend == self._BACKEND_PYGLET:
            from eager_graphics.renderers.pyglet import PygletRenderer

            return PygletRenderer(asset_dir=self.asset_dir)
        elif backend == self._BACKEND_PIL:
            from eager_graphics.renderers.pil import PILRenderer

            return PILRenderer(asset_dir=self.asset_dir)
        elif backend == self._BACKEND_RAYLIB:
            from eager_graphics.renderers.raylib import RaylibRenderer

            return RaylibRenderer(asset_dir=self.asset_dir)
        else:
            msg = f"Unknown backend '{backend}'. Use 'null', 'pyglet', 'pil', or 'raylib'."
            raise ValueError(msg)

    @property
    def renderer(self) -> Any:
        """The active rendering backend instance."""
        return self._renderer

    def advance(self) -> StoryEvent | None:
        """Advance the story by one beat, dispatching all generated events."""
        self.director.snapshot_visual_state()
        return self.dispatcher.run_until_pause(self.vm)

    def step_frame(self, dt: float = 1.0 / 60.0) -> None:
        """Advance compositor animations by *dt* seconds."""
        self.compositor.update(dt)

    def render(self, window_width: int = 1280, window_height: int = 720) -> None:
        """Render one frame through the active backend."""
        if hasattr(self.renderer, "render_compositor"):
            self.renderer.render_compositor(self.compositor, window_width, window_height)
        self._last_render_list = self.compositor.render_list()

    @property
    def render_items(self) -> list[Any]:
        """Return the most recently rendered draw-call list."""
        return self._last_render_list

    def run_headless(
        self,
        *,
        dt: float = 1.0 / 60.0,
        max_steps: int | None = None,
        auto_choose: int | str | None = None,
    ) -> dict[str, Any]:
        """Run the story to completion in a headless loop (no window)."""
        steps = 0
        render_frames = 0

        while not self.vm.is_ended:
            if max_steps is not None and steps >= max_steps:
                break

            event = self.advance()
            steps += 1

            if isinstance(event, ChoicePromptEvent):
                if auto_choose is not None:
                    self.vm.choose(auto_choose)
                    continue
                break

            if event is None:
                break

            self.step_frame(dt)
            self.render()
            render_frames += 1

        return {
            "steps": steps,
            "ended": self.vm.is_ended,
            "render_frames": render_frames,
            "final_ui_state": self.director.ui_state,
        }

    def make_choice(self, choice: int | str) -> StoryEvent | None:
        """Select a choice option (by index or target text) and advance."""
        self.vm.choose(choice)
        return self.advance()

    def can_rollback(self) -> bool:
        """Return *True* if a rollback is available."""
        return self.vm.can_rollback

    def save_slot(self) -> SaveSlot:
        """Capture an atomic snapshot of both narrative and visual state."""
        return SaveSlot(
            story_state=self.vm.save().to_dict(),
            visual_state=self.director.save_visual_state(),
        )

    def load_save_slot(self, slot: SaveSlot) -> None:
        """Transactionally restore a :class:`SaveSlot`."""
        backup_story = self.vm.save()
        backup_visual = self.director.save_visual_state()

        try:
            self.vm.load(StorySnapshot.from_dict(slot.story_state))
            self.director.load_visual_state(slot.visual_state)
        except Exception as exc:
            self.vm.load(backup_story)
            self.director.load_visual_state(backup_visual)
            raise StateCorruptionError(f"Failed to restore save slot cleanly: {exc}") from exc

    def rollback(self) -> bool:
        """Synchronised rollback across story VM and visual state stack."""
        story_ok = self.vm.rollback()
        visual_ok = self.director.rollback_visual_state()
        return story_ok and visual_ok
