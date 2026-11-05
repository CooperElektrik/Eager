"""Shared, dependency-free leaf subsystems for the Eager narrative engine."""

from __future__ import annotations

from eager_core.audio import (
    AudioBackend,
    AudioMixer,
    BaseAudioBackend,
    ChannelState,
    NullAudioBackend,
)
from eager_core.backlog import (
    Backlog,
    BacklogEntry,
)
from eager_core.characters import (
    CharacterConfig,
)
from eager_core.dispatcher import (
    EventDispatcher,
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
from eager_core.exceptions import (
    AudioError,
    ColorParseError,
    EagerCoreError,
    I18nError,
    StorageError,
)
from eager_core.headless import (
    HeadlessUIState,
    NullCompositor,
    NullRenderer,
    NullScreenManager,
    NullStage,
    NullUI,
)
from eager_core.i18n import (
    TranslationCatalog,
    TranslationManager,
    strip_explicit_id,
)
from eager_core.input import (
    InputAction,
    Keymap,
    normalize_keysym,
)
from eager_core.layout import (
    LayoutResolver,
    PositionFactory,
    ViewportTransform,
)
from eager_core.lighting import (
    AmbientLight,
    LightKind,
    LightmapState,
    PointLight,
)
from eager_core.persistent import (
    PersistentData,
)
from eager_core.preferences import (
    Preferences,
)
from eager_core.protocols import (
    RenderBackend,
    RenderItem,
    ScreenManagerProtocol,
    StageProtocol,
    UIDrawBackend,
    UIProtocol,
    UIStateProtocol,
)
from eager_core.saves import (
    SaveData,
    SaveManager,
    SaveMetadata,
    SaveMigrationError,
)
from eager_core.state import (
    CallFrame,
    Checkpoint,
    CheckpointHistory,
    StorySnapshot,
)
from eager_core.storage import (
    atomic_write_json,
    get_default_save_dir,
    safe_read_json,
)
from eager_core.text import (
    FormattedText,
    PausePoint,
    TextAnchor,
    TextReveal,
    TextSegment,
    _get_wrapped_lines,
    parse_text_tags,
    wrap_text,
)
from eager_core.theme import (
    Theme,
)
from eager_core.timeline import (
    Timeline,
    Tween,
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
    Anchor,
    Color,
    DebugOverlayMode,
    Rect,
    RenderPreset,
    ScaleMode,
    TransitionKind,
    Vec2,
)
from eager_core.ui_state import (
    NVLEntry,
    UIState,
)
from eager_core.watcher import (
    FileWatcher,
)

__version__ = "0.7.0"

__all__ = [
    "BLACK",
    "BLUE",
    "EASING_MAP",
    "GREEN",
    "RED",
    "TRANSPARENT",
    "WHITE",
    "AmbientLight",
    "Anchor",
    "AppendEvent",
    "AudioBackend",
    "AudioError",
    "AudioMixer",
    "Backlog",
    "BacklogEntry",
    "BaseAudioBackend",
    "CallFrame",
    "ChannelState",
    "CharacterConfig",
    "Checkpoint",
    "CheckpointHistory",
    "ChoiceOption",
    "ChoicePromptEvent",
    "Color",
    "ColorParseError",
    "DebugOverlayMode",
    "DialogueEvent",
    "EagerCoreError",
    "EasingFunc",
    "EventDispatcher",
    "FileWatcher",
    "FormattedText",
    "FrameClock",
    "FreshBoxEvent",
    "HeadlessUIState",
    "HookEvent",
    "I18nError",
    "InputAction",
    "InputPromptEvent",
    "Keymap",
    "LayoutResolver",
    "LightKind",
    "LightmapState",
    "NVLEntry",
    "NarrationEvent",
    "NullAudioBackend",
    "NullCompositor",
    "NullRenderer",
    "NullScreenManager",
    "NullStage",
    "NullUI",
    "PausePoint",
    "PersistentData",
    "PointLight",
    "PositionFactory",
    "Preferences",
    "Rect",
    "RenderBackend",
    "RenderItem",
    "RenderPreset",
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SaveMigrationError",
    "ScaleMode",
    "SceneEnterEvent",
    "SceneExitEvent",
    "ScreenManagerProtocol",
    "StageProtocol",
    "StorageError",
    "StoryEndEvent",
    "StoryEvent",
    "StorySnapshot",
    "TextAnchor",
    "TextReveal",
    "TextSegment",
    "Theme",
    "Timeline",
    "TransitionKind",
    "TranslationCatalog",
    "TranslationManager",
    "Tween",
    "UIDrawBackend",
    "UIProtocol",
    "UIState",
    "UIStateProtocol",
    "Vec2",
    "ViewportTransform",
    "_get_wrapped_lines",
    "atomic_write_json",
    "get_default_save_dir",
    "get_easing",
    "linear",
    "normalize_keysym",
    "parse_text_tags",
    "safe_read_json",
    "strip_explicit_id",
    "wrap_text",
]
