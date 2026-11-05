"""Headless and stub implementations for stage, UI, screen manager, and renderer."""

from __future__ import annotations

from typing import Any

from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    StoryEndEvent,
)
from eager_core.protocols import (
    RenderBackend,
    RenderItem,
    ScreenManagerProtocol,
    StageProtocol,
    UIDrawBackend,
    UIProtocol,
)
from eager_core.timing import FrameClock
from eager_core.types import BLACK, WHITE, Color
from eager_core.ui_state import UIState

HeadlessUIState = UIState

__all__ = [
    "HeadlessUIState",
    "NullCompositor",
    "NullRenderer",
    "NullScreenManager",
    "NullStage",
    "NullUI",
]


class NullRenderer(RenderBackend, UIDrawBackend):
    """A no-op renderer that records draw calls instead of issuing GPU commands."""

    def __init__(self) -> None:
        self.last_frame: list[RenderItem] = []
        self._frame_buffer: list[RenderItem] = []
        self.last_particle_batches: list[tuple[str, int]] = []
        self.last_lightmaps: list[tuple[bool, int]] = []
        self.frame_count: int = 0
        self.clear_color: Color = BLACK
        self._in_frame: bool = False
        self.clock: FrameClock = FrameClock()
        self.ui_calls: list[dict[str, Any]] = []

    def begin_frame(self) -> None:
        """Begin a new frame."""
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RuntimeError(msg)
        self._frame_buffer = []
        self._in_frame = True

    def clear(self, color: Color) -> None:
        """Record the framebuffer clear color."""
        self.clear_color = color

    def draw_item(self, item: RenderItem) -> None:
        """Record a render item."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        self._frame_buffer.append(item)

    def draw_particles(self, batch: Any) -> None:
        """Record a particle batch draw call."""
        if not self._in_frame:
            msg = "draw_particles called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        emitter_id = getattr(batch, "emitter_id", "")
        particles = getattr(batch, "particles", [])
        self.last_particle_batches.append((emitter_id, len(particles)))

    def render_lightmap(self, lightmap: Any) -> None:
        """Record a screen-space lightmap draw call."""
        if not self._in_frame:
            msg = "render_lightmap called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        enabled = getattr(lightmap, "enabled", False)
        lights = getattr(lightmap, "lights", [])
        self.last_lightmaps.append((enabled, len(lights)))

    def end_frame(self) -> None:
        """Finalize the current frame, publishing draw calls."""
        if not self._in_frame:
            msg = "end_frame called without matching begin_frame"
            raise RuntimeError(msg)
        self.last_frame = self._frame_buffer
        self._frame_buffer = []
        self._in_frame = False
        self.frame_count += 1
        self.clock.tick()

    @property
    def fps(self) -> float:
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        return self.clock.fps_overall

    def render_compositor(
        self,
        compositor: Any,
        window_width: int,
        window_height: int,
    ) -> None:
        self.begin_frame()
        self.clear(BLACK)
        items = compositor.render_list()
        for item in items:
            self.draw_item(item)
        if hasattr(compositor, "get_particle_batches") and hasattr(compositor, "layout"):
            transform = compositor.layout.compute_viewport_transform(window_width, window_height)
            for batch in compositor.get_particle_batches(transform):
                self.draw_particles(batch)
        if hasattr(compositor, "lighting") and compositor.lighting.enabled:
            self.render_lightmap(compositor.lighting)
        self.end_frame()

    def draw_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        border_color: Color | None = None,
        border_width: float = 0.0,
    ) -> None:
        self.ui_calls.append(
            {
                "kind": "rect",
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "color": color.to_hex(),
                "border_color": border_color.to_hex() if border_color else None,
                "border_width": float(border_width),
            }
        )

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        self.ui_calls.append(
            {
                "kind": "gradient_rect",
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "top_color": top_color.to_hex(),
                "bottom_color": bottom_color.to_hex(),
            }
        )

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        bold: bool = False,
        italic: bool = False,
        anchor_x: str = "left",
        anchor_y: str = "top",
        cache: bool = True,
    ) -> None:
        self.ui_calls.append(
            {
                "kind": "text",
                "x": float(x),
                "y": float(y),
                "text": text,
                "font_size": int(font_size),
                "color": color.to_hex(),
                "bold": bold,
                "italic": italic,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "cache": cache,
            }
        )

    def draw_image(
        self,
        asset_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        tint: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        self.ui_calls.append(
            {
                "kind": "image",
                "asset_id": asset_id,
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "tint": tint.to_hex(),
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
            }
        )

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
        cache: bool = True,
    ) -> tuple[float, float]:
        longest = max((len(line) for line in text.splitlines()), default=0)
        return (longest * font_size * 0.5, float(font_size) * 1.2)

    def clear_ui_calls(self) -> None:
        self.ui_calls.clear()

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"NullRenderer(frame_count={self.frame_count}, "
            f"last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )


class NullCompositor:
    """Headless compositor stub."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height

    def step(self, dt: float) -> None:
        pass

    def finish_animations(self) -> None:
        pass

    def render_list(self) -> list[Any]:
        return []

    def save_state(self) -> dict[str, Any]:
        return {}

    def load_state(self, state: dict[str, Any]) -> None:
        pass


class NullStage(StageProtocol):
    """Headless stage implementing StageProtocol."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        self.ui_state = UIState()
        self.compositor = NullCompositor(virtual_width, virtual_height)
        self.characters: dict[str, dict[str, Any]] = {}

    def register_character(
        self,
        character_id: str,
        *,
        name: str | None = None,
        asset_prefix: str | None = None,
        default_expression: str = "default",
        default_position: str = "center",
        side_image: str | None = None,
        color: Any = None,
        expressions: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        cid = character_id.strip().lower()
        parsed_color = color
        if isinstance(color, str):
            try:
                parsed_color = Color.from_hex(color)
            except Exception:  # noqa: BLE001
                parsed_color = None

        exprs = dict(expressions) if expressions is not None else {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                exprs[k] = v

        self.characters[cid] = {
            "name": name,
            "asset_prefix": asset_prefix,
            "default_expression": default_expression,
            "default_position": default_position,
            "side_image": side_image,
            "color": parsed_color,
            "expressions": exprs,
        }

    def _find_character_config(self, speaker: str | None) -> dict[str, Any] | None:
        if not speaker:
            return None
        sid = speaker.strip().lower()
        if sid in self.characters:
            return self.characters[sid]
        for cinfo in self.characters.values():
            if cinfo.get("name") and str(cinfo["name"]).strip().lower() == sid:
                return cinfo
        return None

    def bind(self, dispatcher: Any) -> None:
        dispatcher.on_event(DialogueEvent)(self._on_dialogue)
        dispatcher.on_event(NarrationEvent)(self._on_narration)
        dispatcher.on_event(AppendEvent)(self._on_append)
        dispatcher.on_event(FreshBoxEvent)(self._on_fresh_box)
        dispatcher.on_event(ChoicePromptEvent)(self._on_choice)
        dispatcher.on_event(StoryEndEvent)(self._on_story_end)

    def _on_dialogue(self, event: DialogueEvent) -> None:
        char_info: dict[str, Any] | None = None
        if event.speaker:
            sid = event.speaker.strip().lower()
            if sid in self.characters:
                char_info = self.characters[sid]
            else:
                for cinfo in self.characters.values():
                    if cinfo.get("name") and str(cinfo["name"]).strip().lower() == sid:
                        char_info = cinfo
                        break

        self.ui_state.speaker = event.speaker
        self.ui_state.text = event.text
        self.ui_state.emotion = event.emotion
        self.ui_state.visible_chars = None
        self.ui_state.speaker_color = char_info.get("color") if char_info else None
        self.ui_state.side_image = char_info.get("side_image") if char_info else None
        self.ui_state.clear_choices()

    def _on_narration(self, event: NarrationEvent) -> None:
        self.ui_state.speaker = None
        self.ui_state.text = event.text
        self.ui_state.emotion = None
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_append(self, event: AppendEvent) -> None:
        add_text = event.text
        current = self.ui_state.text or ""
        self.ui_state.text = f"{current} {add_text}".strip()
        self.ui_state.clear_choices()

    def _on_fresh_box(self, event: FreshBoxEvent) -> None:
        self.ui_state.text = event.text
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_choice(self, event: ChoicePromptEvent) -> None:
        self.ui_state.choices = list(event.options)

    def _on_story_end(self, event: StoryEndEvent) -> None:
        self.ui_state.is_finished = True

    def step(self, dt: float) -> None:
        self.compositor.step(dt)

    def finish_animations(self) -> None:
        self.compositor.finish_animations()

    def clear_stage(self) -> None:
        self.compositor.clear(Color(0, 0, 0, 1))
        self.ui_state.clear_dialogue()
        self.ui_state.clear_choices()
        self.ui_state.clear_nvl()

    def save_visual_state(self) -> dict[str, Any]:
        return {
            "compositor": self.compositor.save_state(),
            "ui_state": self.save_ui_state(),
        }

    def load_visual_state(self, state: dict[str, Any]) -> None:
        if comp := state.get("compositor"):
            self.compositor.load_state(comp)
        if ui := state.get("ui_state"):
            self.ui_state = UIState.from_dict(ui)

    def save_ui_state(self) -> dict[str, Any]:
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        self.ui_state = UIState.from_dict(state)


class NullUI(UIProtocol):
    """Headless UI stub implementing UIProtocol."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.error_overlay: str | None = None
        self.choice_menu: Any = None
        self.dialogue_box: Any = None
        self.input_box: Any = None
        self.quick_menu: Any = None
        self._selected_choice: int | None = None
        self._hovered_quick_action: str | None = None
        self._input_text: str = ""

    def set_viewport(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def sync(self, *args: Any, **kwargs: Any) -> None:
        pass

    def hit_test_choice(self, x: float, y: float) -> int | None:
        return None

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        return None

    def get_selected_choice(self) -> int | None:
        return self._selected_choice

    def set_selected_choice(self, index: int | None) -> None:
        self._selected_choice = index

    def set_choice_options(self, options: Any) -> None:
        pass

    def set_input_text(self, text: str) -> None:
        self._input_text = text

    def update_input(self, dt: float) -> None:
        pass

    def set_dialogue_visible_chars(
        self,
        visible_chars: int | None = None,
        *,
        show_arrow: bool = True,
    ) -> None:
        pass

    def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
        pass

    def get_hovered_quick_action(self) -> str | None:
        return self._hovered_quick_action

    def set_hovered_quick_action(self, action: str | None) -> None:
        self._hovered_quick_action = action


class NullScreenManager(ScreenManagerProtocol):
    """Headless screen manager stub implementing ScreenManagerProtocol."""

    def __init__(self) -> None:
        self.screens: dict[str, Any] = {}
        self.active_screen: Any = None

    @property
    def is_active(self) -> bool:
        return False

    def register(self, screen: Any) -> None:
        name = getattr(screen, "name", None)
        if name:
            self.screens[name] = screen

    def show(self, name: str, session: Any) -> bool:
        return False

    def hide(self, session: Any) -> None:
        pass

    def hide_all(self, session: Any) -> None:
        pass

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def handle_mouse_move(self, x: float, y: float) -> bool:
        return False

    def set_viewport(self, width: int, height: int) -> None:
        pass

    def handle_mouse_click(self, x: float, y: float) -> bool:
        return False

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        return False
