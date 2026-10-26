"""Shared, dependency-free leaf subsystems for the Eager narrative engine."""

from __future__ import annotations

from eager_core.audio import (
    AudioBackend,
    AudioMixer,
    BaseAudioBackend,
    ChannelState,
    NullAudioBackend,
)
from eager_core.easing import (
    EASING_MAP,
    EasingFunc,
    get_easing,
    linear,
)
from eager_core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_core.i18n import (
    TranslationCatalog,
    TranslationManager,
)
from eager_core.input import (
    InputAction,
    Keymap,
)
from eager_core.protocols import (
    ScreenManagerProtocol,
    StageProtocol,
    UIProtocol,
    UIStateProtocol,
)
from eager_core.storage import (
    atomic_write_json,
    get_default_save_dir,
    safe_read_json,
)
from eager_core.text import (
    FormattedText,
    PausePoint,
    TextReveal,
    TextSegment,
    parse_text_tags,
)
from eager_core.timing import (
    FrameClock,
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

__version__ = "0.6.0"

__all__ = [
    # Types & Geometry
    "BLACK",
    "BLUE",
    # Easing
    "EASING_MAP",
    "GREEN",
    "RED",
    "TRANSPARENT",
    "WHITE",
    # Events
    "AppendEvent",
    # Audio
    "AudioBackend",
    "AudioMixer",
    "BaseAudioBackend",
    "ChannelState",
    "ChoiceOption",
    "ChoicePromptEvent",
    "Color",
    "DialogueEvent",
    "EasingFunc",
    # Text
    "FormattedText",
    # Timing
    "FrameClock",
    "FreshBoxEvent",
    "HookEvent",
    # Input
    "InputAction",
    "InputPromptEvent",
    "Keymap",
    "NarrationEvent",
    "NullAudioBackend",
    "PausePoint",
    "Rect",
    "SceneEnterEvent",
    "SceneExitEvent",
    "ScreenManagerProtocol",
    "StageProtocol",
    "StoryEndEvent",
    "StoryEvent",
    "TextReveal",
    "TextSegment",
    "TranslationCatalog",
    "TranslationManager",
    "UIProtocol",
    "UIStateProtocol",
    "Vec2",
    # Storage
    "atomic_write_json",
    "get_default_save_dir",
    "get_easing",
    "linear",
    "parse_text_tags",
    "safe_read_json",
]
