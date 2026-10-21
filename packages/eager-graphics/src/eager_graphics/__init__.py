"""Eager-Graphics: Renderer-agnostic, resolution-independent Graphics & Stage Compositor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager_core.easing import (
    EasingFunc,
    ease_in_back,
    ease_in_bounce,
    ease_in_cubic,
    ease_in_expo,
    ease_in_out_back,
    ease_in_out_bounce,
    ease_in_out_cubic,
    ease_in_out_expo,
    ease_in_out_quad,
    ease_in_out_quart,
    ease_in_out_sine,
    ease_in_quad,
    ease_in_quart,
    ease_in_sine,
    ease_out_back,
    ease_out_bounce,
    ease_out_cubic,
    ease_out_expo,
    ease_out_quad,
    ease_out_quart,
    ease_out_sine,
    get_easing,
    linear,
)
from eager_core.text import (
    FormattedText,
    PausePoint,
    TextReveal,
    TextSegment,
    parse_text_tags,
)
from eager_core.types import (
    BLACK,
    BLUE,
    GREEN,
    RED,
    TRANSPARENT,
    WHITE,
    Color,
    Rect,
    Vec2,
)

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import CharacterConfig, StageDirector
from eager_graphics.history import VisualHistoryManager
from eager_graphics.layout import LayoutResolver, ViewportTransform
from eager_graphics.protocol import RenderBackend, RenderItem, UIDrawBackend
from eager_graphics.stage import ElementState, Layer, Stage, StageElement
from eager_graphics.timeline import Timeline, Tween
from eager_graphics.types import Anchor, DebugOverlayMode, ScaleMode, TransitionKind
from eager_graphics.ui_components import (
    ChoiceMenu,
    ChoiceMenuStyle,
    DialogueBox,
    DialogueBoxLayout,
    EndNotice,
    InputBox,
    TextAnchor,
    TextboxStyle,
    UIOverlay,
)
from eager_graphics.ui_state import ChoiceOption, UIState

__version__ = "0.2.0"

__all__ = [
    "BLACK",
    "BLUE",
    "GREEN",
    "RED",
    "TRANSPARENT",
    "WHITE",
    "Anchor",
    "CharacterConfig",
    "ChoiceMenu",
    "ChoiceMenuStyle",
    "ChoiceOption",
    "Color",
    "DebugOverlayMode",
    "DialogueBox",
    "DialogueBoxLayout",
    "EasingFunc",
    "ElementState",
    "EndNotice",
    "FormattedText",
    "InputBox",
    "Layer",
    "LayoutResolver",
    "PausePoint",
    "Rect",
    "RenderBackend",
    "RenderItem",
    "ScaleMode",
    "Stage",
    "StageCompositor",
    "StageDirector",
    "StageElement",
    "TextAnchor",
    "TextReveal",
    "TextSegment",
    "TextboxStyle",
    "Timeline",
    "TransitionKind",
    "Tween",
    "UIDrawBackend",
    "UIOverlay",
    "UIState",
    "Vec2",
    "ViewportTransform",
    "VisualHistoryManager",
    "ease_in_back",
    "ease_in_bounce",
    "ease_in_cubic",
    "ease_in_expo",
    "ease_in_out_back",
    "ease_in_out_bounce",
    "ease_in_out_cubic",
    "ease_in_out_expo",
    "ease_in_out_quad",
    "ease_in_out_quart",
    "ease_in_out_sine",
    "ease_in_quad",
    "ease_in_quart",
    "ease_in_sine",
    "ease_out_back",
    "ease_out_bounce",
    "ease_out_cubic",
    "ease_out_expo",
    "ease_out_quad",
    "ease_out_quart",
    "ease_out_sine",
    "get_easing",
    "linear",
    "parse_text_tags",
]

# NullRenderer is dependency-free and always available for headless rendering.
from eager_core.timing import FrameClock  # noqa: F401

from eager_graphics.player import BasePlayer  # noqa: F401
from eager_graphics.renderers.null import NullRenderer  # noqa: F401

if TYPE_CHECKING:
    from eager_graphics.renderers import (
        PILAssetResolver as PILAssetResolver,
    )
    from eager_graphics.renderers import (
        PILPlayer as PILPlayer,
    )
    from eager_graphics.renderers import (
        PILRenderer as PILRenderer,
    )
    from eager_graphics.renderers import (
        PygletAssetResolver as PygletAssetResolver,
    )
    from eager_graphics.renderers import (
        PygletPlayer as PygletPlayer,
    )
    from eager_graphics.renderers import (
        PygletRenderer as PygletRenderer,
    )

__all__.append("NullRenderer")
__all__.append("FrameClock")
__all__.append("BasePlayer")

# Optional backends (Pyglet, PIL) are NOT eagerly imported here to
# avoid side effects — e.g. Pyglet initialises GTK/EGL on Wayland.
# They are resolved lazily via renderers.__getattr__ when accessed.
__all__.extend([
    "PILAssetResolver",
    "PILPlayer",
    "PILRenderer",
    "PygletAssetResolver",
    "PygletPlayer",
    "PygletRenderer",
])


def __getattr__(name: str) -> object:
    """Lazily delegate optional backend names to ``renderers.__getattr__``."""
    from eager_graphics import renderers

    if name in renderers.__all__:
        return getattr(renderers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
