"""Shared, dependency-free leaf subsystems for the Eager narrative engine."""

from __future__ import annotations

from eager.core.assets import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    AssetCheckReport,
    AssetKind,
    AssetReference,
    MissingAssetIssue,
    check_assets,
    extract_asset_references,
    resolve_candidate_paths,
)
from eager.core.audio import (
    AudioBackend,
    AudioMixer,
    BaseAudioBackend,
    ChannelState,
    NullAudioBackend,
)
from eager.core.backlog import (
    Backlog,
    BacklogEntry,
)
from eager.core.characters import (
    CharacterConfig,
)
from eager.core.dispatcher import (
    EventDispatcher,
)
from eager.core.easing import (
    EASING_MAP,
    EasingFunc,
    get_easing,
    linear,
)
from eager.core.events import (
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
from eager.core.exceptions import (
    AudioError,
    ColorParseError,
    EagerCoreError,
    I18nError,
    StorageError,
)
from eager.core.i18n import (
    TranslationCatalog,
    TranslationManager,
    compute_beat_id,
    get_beat_occurrence,
    strip_explicit_id,
)
from eager.core.input import (
    InputAction,
    Keymap,
    normalize_keysym,
)
from eager.core.layout import (
    LayoutResolver,
    PositionFactory,
    ViewportTransform,
)
from eager.core.lighting import (
    LightmapState,
    PointLight,
)
from eager.core.persistent import (
    PersistentData,
)
from eager.core.preferences import (
    Preferences,
)
from eager.core.saves import (
    SaveData,
    SaveManager,
    SaveMetadata,
    SaveMigrationError,
)
from eager.core.state import (
    CallFrame,
    Checkpoint,
    CheckpointHistory,
    StorySnapshot,
)
from eager.core.storage import (
    atomic_write_json,
    get_default_save_dir,
    safe_read_json,
)
from eager.core.text import (
    FormattedText,
    PausePoint,
    TextAnchor,
    TextReveal,
    TextSegment,
    clear_wrap_cache,
    get_wrapped_lines,
    parse_text_tags,
    wrap_text,
)
from eager.core.theme import (
    Theme,
)
from eager.core.timeline import (
    Timeline,
    Tween,
)
from eager.core.timing import (
    FrameClock,
)
from eager.core.types import (
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
from eager.core.ui_state import (
    NVLEntry,
    UIState,
)
from eager.core.watcher import (
    FileWatcher,
)

__version__ = "0.9.0"

__all__ = [
    "AUDIO_EXTENSIONS",
    "BLACK",
    "BLUE",
    "EASING_MAP",
    "GREEN",
    "IMAGE_EXTENSIONS",
    "RED",
    "TRANSPARENT",
    "WHITE",
    "Anchor",
    "AppendEvent",
    "AssetCheckReport",
    "AssetKind",
    "AssetReference",
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
    "HookEvent",
    "I18nError",
    "InputAction",
    "InputPromptEvent",
    "Keymap",
    "LayoutResolver",
    "LightmapState",
    "MissingAssetIssue",
    "NVLEntry",
    "NarrationEvent",
    "NullAudioBackend",
    "PausePoint",
    "PersistentData",
    "PointLight",
    "PositionFactory",
    "Preferences",
    "Rect",
    "RenderPreset",
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SaveMigrationError",
    "ScaleMode",
    "SceneEnterEvent",
    "SceneExitEvent",
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
    "UIState",
    "Vec2",
    "ViewportTransform",
    "atomic_write_json",
    "check_assets",
    "clear_wrap_cache",
    "compute_beat_id",
    "extract_asset_references",
    "get_beat_occurrence",
    "get_default_save_dir",
    "get_easing",
    "get_wrapped_lines",
    "linear",
    "normalize_keysym",
    "parse_text_tags",
    "resolve_candidate_paths",
    "safe_read_json",
    "strip_explicit_id",
    "wrap_text",
]
