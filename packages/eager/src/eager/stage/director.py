"""Directs stage compositor actions from narrative engine events and script hooks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, overload

from eager.core.audio import AudioMixer
from eager.core.characters import CharacterConfig
from eager.core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager.core.exceptions import ColorParseError
from eager.core.types import BLACK, WHITE, Color
from eager.core.ui_state import UIState
from eager.script.hooks import HookArgs, parse_hook_args
from eager.stage.compositor import StageCompositor

__all__ = [
    "CharacterConfig",
    "StageDirector",
]


@overload
def _parse_hook_color(args: HookArgs, key: str, default: Color) -> Color: ...


@overload
def _parse_hook_color(args: HookArgs, key: str, default: None) -> Color | None: ...


def _parse_hook_color(args: HookArgs, key: str, default: Color | None) -> Color | None:
    raw = args.kwargs.get(key)
    if raw is None:
        return default
    try:
        return Color.from_hex(raw)
    except (ColorParseError, ValueError, TypeError):
        return default


class _EventDispatcherLike(Protocol):
    def on_hook(self, hook_name: str, /) -> Callable[[Callable[[str], object]], object]: ...

    def on_event(self, event_type: Any, /) -> Callable[[Callable[[Any], object]], object]: ...


class StageDirector:
    """Bridges Eager events and screenplay script hooks to the StageCompositor."""

    def __init__(
        self,
        compositor: StageCompositor,
        *,
        audio: AudioMixer | None = None,
        skip_mode_cb: Callable[[], bool] | None = None,
    ) -> None:
        self.compositor = compositor
        self.audio = audio
        self.skip_mode_cb = skip_mode_cb
        self.characters: dict[str, CharacterConfig] = {}
        self.scene_backgrounds: dict[str, tuple[str, str, float]] = {}
        self.ui_state: UIState = UIState()

    def step(self, dt: float) -> None:
        """Advance compositor timelines and animations by *dt* seconds."""
        self.compositor.step(dt)

    def finish_animations(self) -> None:
        """Immediately complete active stage animations."""
        self.compositor.finish_animations()

    def clear_stage(self) -> None:
        """Clear all stage compositor elements, sprite state, and dialogue UI."""
        self.compositor.clear()
        self.ui_state.clear_dialogue()
        self.ui_state.clear_choices()

    def save_ui_state(self) -> dict[str, Any]:
        """Serialize current UI state."""
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        """Restore UI state from serialized dictionary."""
        self.ui_state = UIState.from_dict(state)

    def save_visual_state(self) -> dict[str, Any]:
        """Serialize compositor and UI state."""
        return {
            "compositor": self.compositor.save_state(),
            "ui_state": self.save_ui_state(),
        }

    def load_visual_state(self, state: dict[str, Any]) -> None:
        """Restore compositor and UI state from a serialized dictionary."""
        if comp_state := state.get("compositor"):
            self.compositor.load_state(comp_state)
        if ui_state := state.get("ui_state"):
            self.ui_state = UIState.from_dict(ui_state)

    def register_character(
        self,
        character_id: str,
        *,
        name: str | None = None,
        asset_prefix: str | None = None,
        default_expression: str = "default",
        default_position: str = "center",
        side_image: str | None = None,
        color: str | Color | None = None,
        expressions: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Register default configuration for a character."""
        cid = character_id.strip().lower()
        parsed_color: Color | None = None
        if isinstance(color, str):
            try:
                parsed_color = Color.from_hex(color)
            except Exception:  # noqa: BLE001
                parsed_color = None
        elif isinstance(color, Color):
            parsed_color = color

        exprs = dict(expressions) if expressions is not None else {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                exprs[k] = v

        self.characters[cid] = CharacterConfig(
            character_id=cid,
            name=name,
            asset_prefix=asset_prefix,
            default_expression=default_expression,
            default_position=default_position,
            side_image=side_image,
            color=parsed_color,
            expressions=exprs,
        )

    def find_character(self, speaker: str | None, *, character_id: str | None = None) -> CharacterConfig | None:
        """Find CharacterConfig matching character_id or display name."""
        if character_id:
            cid = character_id.strip().lower()
            if cid in self.characters:
                return self.characters[cid]
        if not speaker:
            return None
        sid = speaker.strip().lower()
        if sid in self.characters:
            return self.characters[sid]
        for cfg in self.characters.values():
            if cfg.name and cfg.name.strip().lower() == sid:
                return cfg
        return None

    def register_scene_bg(
        self,
        scene_id: str,
        asset_id: str,
        *,
        transition: str = "crossfade",
        duration: float = 0.5,
    ) -> None:
        """Map a scene ID to automatically trigger a background change on SceneEnterEvent."""
        self.scene_backgrounds[scene_id] = (asset_id, transition, duration)

    def bind(self, dispatcher: _EventDispatcherLike) -> None:
        """Register hook handlers and event listeners on an Eager EventDispatcher."""
        def _wrap_hook(handler: Callable[[str], None]) -> Callable[[str], None]:
            def _wrapped(args: str) -> None:
                handler(args)
            return _wrapped

        # 1. Screenplay Engine Hook Listeners (~ hook)
        dispatcher.on_hook("bg")(_wrap_hook(self.handle_bg))
        dispatcher.on_hook("bg_clear")(_wrap_hook(self.handle_bg_clear))
        dispatcher.on_hook("scene")(_wrap_hook(self.handle_scene))
        dispatcher.on_hook("scene_bg")(_wrap_hook(self.handle_scene_bg))
        dispatcher.on_hook("image")(_wrap_hook(self.handle_image))
        dispatcher.on_hook("hide_image")(_wrap_hook(self.handle_hide_image))
        dispatcher.on_hook("hide_element")(_wrap_hook(self.handle_hide_element))
        dispatcher.on_hook("show")(_wrap_hook(self.handle_show))
        dispatcher.on_hook("hide")(_wrap_hook(self.handle_hide))
        dispatcher.on_hook("move")(_wrap_hook(self.handle_move))
        dispatcher.on_hook("expr")(_wrap_hook(self.handle_expr))
        dispatcher.on_hook("fade_in")(_wrap_hook(self.handle_fade_in))
        dispatcher.on_hook("fade_out")(_wrap_hook(self.handle_fade_out))
        dispatcher.on_hook("flash")(_wrap_hook(self.handle_flash))
        dispatcher.on_hook("shake")(_wrap_hook(self.handle_shake))
        dispatcher.on_hook("play")(_wrap_hook(self.handle_play))
        dispatcher.on_hook("stop")(_wrap_hook(self.handle_stop))
        dispatcher.on_hook("pause")(_wrap_hook(self.handle_pause))
        dispatcher.on_hook("resume")(_wrap_hook(self.handle_resume))
        dispatcher.on_hook("volume")(_wrap_hook(self.handle_volume))

        # 2. Narrative Event Listeners
        dispatcher.on_event(DialogueEvent)(self.handle_dialogue_event)
        dispatcher.on_event(AppendEvent)(self.handle_append_event)
        dispatcher.on_event(FreshBoxEvent)(self.handle_fresh_box_event)
        dispatcher.on_event(NarrationEvent)(self.handle_narration_event)
        dispatcher.on_event(SceneEnterEvent)(self.handle_scene_enter_event)
        dispatcher.on_event(SceneExitEvent)(self.handle_scene_exit_event)
        dispatcher.on_event(ChoicePromptEvent)(self.handle_choice_prompt_event)
        dispatcher.on_event(StoryEndEvent)(self.handle_story_end_event)

    # =========================================================================
    # Hook Handlers
    # =========================================================================

    def handle_bg(self, args: str) -> None:
        """Handle `~ bg asset_name [with transition] [duration=X]`."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        asset_id = parsed.positional[0]
        # Auto-prefix with 'bg/' if not provided and doesn't contain a slash
        if "/" not in asset_id:
            asset_id = f"bg/{asset_id}"

        transition = parsed.with_ or parsed.get_str("transition", "cut") or "cut"
        duration = parsed.get_float("duration", 0.5 if transition != "cut" else 0.0)

        self.compositor.set_background(
            asset_id=asset_id,
            transition=transition,
            duration=duration,
        )

    def handle_bg_clear(self, args: str) -> None:
        """Handle `~ bg_clear [with transition] [duration=X]`."""
        parsed = parse_hook_args(args)
        transition = parsed.with_ or parsed.get_str("transition", "cut") or "cut"
        duration = parsed.get_float("duration", 0.5 if transition != "cut" else 0.0)
        self.compositor.clear_background(transition=transition, duration=duration)

    def handle_scene(self, args: str) -> None:
        """Handle `~ scene asset_name [with transition] [duration=X]`: clears characters and sets background."""
        # Clear all character sprites
        char_layer = self.compositor.stage.get_layer("characters")
        if char_layer:
            char_layer.clear()
        # Set background
        self.handle_bg(args)

    def handle_image(self, args: str) -> None:
        """Handle `~ image name asset [at pos] [z=N] [opacity=X] [duration=X] [tint=color] [layer=name]`."""
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        name = parsed.positional[0].strip()
        asset = parsed.positional[1].strip()
        pos = parsed.at or "center"
        z = parsed.get_int("z", 50)
        layer = parsed.get_str("layer", "foreground") or "foreground"
        opacity = parsed.get_float("opacity", 1.0)
        duration = parsed.get_float("duration", 0.0)
        tint = _parse_hook_color(parsed, "tint", WHITE)
        self.compositor.show_element(
            layer=layer,
            element_id=name,
            asset_id=asset,
            position=pos,
            opacity=opacity,
            duration=duration,
            z_index=z,
            tint=tint,
        )

    def handle_hide_image(self, args: str) -> None:
        """Handle `~ hide_image name [duration=X] [layer=name]`."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return
        name = parsed.positional[0].strip()
        layer = parsed.get_str("layer", "foreground") or "foreground"
        duration = parsed.get_float("duration", 0.0)
        self.compositor.hide_element(layer=layer, element_id=name, duration=duration)

    def handle_hide_element(self, args: str) -> None:
        """Handle `~ hide_element [layer] name [duration=X]`."""
        parsed = parse_hook_args(args)
        pos = parsed.positional
        if len(pos) >= 2:
            layer = pos[0].strip()
            name = pos[1].strip()
        elif len(pos) == 1:
            layer = "foreground"
            name = pos[0].strip()
        else:
            return
        duration = parsed.get_float("duration", 0.0)
        self.compositor.hide_element(layer=layer, element_id=name, duration=duration)

    def handle_scene_bg(self, args: str) -> None:
        """Handle `~ scene_bg scene_id asset [with transition] [duration=X]`."""
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        scene_id = parsed.positional[0].strip()
        asset_id = parsed.positional[1].strip()
        transition = parsed.with_ or "crossfade"
        duration = parsed.get_float("duration", 0.5)
        self.register_scene_bg(scene_id, asset_id, transition=transition, duration=duration)

    def handle_show(self, args: str) -> None:
        """Handle `~ show character [expression] [at position] [with transition] [duration=X]`."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        raw_id = parsed.positional[0]
        cfg = self.find_character(raw_id)
        char_id = cfg.character_id if cfg is not None else raw_id.strip().lower()

        # Expression
        if len(parsed.positional) > 1:
            expr = parsed.positional[1]
        elif cfg is not None:
            expr = cfg.default_expression
        else:
            expr = "default"

        if cfg is not None:
            expr = cfg.resolve_expression(expr)

        # Position
        pos = parsed.at or (cfg.default_position if cfg else "center")

        # Transition
        transition = parsed.with_ or parsed.get_str("transition", "fade") or "fade"
        duration = parsed.get_float("duration", 0.3)
        flip_h = parsed.get_bool("flip_h", False)
        flip_v = parsed.get_bool("flip_v", False)
        scale = parsed.get_float("scale", 1.0)
        scale_x_raw = parsed.get_str("scale_x")
        scale_y_raw = parsed.get_str("scale_y")
        try:
            scale_x = float(scale_x_raw) if scale_x_raw is not None else None
        except ValueError:
            scale_x = None
        try:
            scale_y = float(scale_y_raw) if scale_y_raw is not None else None
        except ValueError:
            scale_y = None
        rotation = parsed.get_float("rotation", 0.0)
        tint_str = parsed.get_str("tint", None)
        tint = WHITE
        if tint_str:
            try:
                tint = Color.from_hex(tint_str)
            except (ColorParseError, ValueError, TypeError):
                tint = WHITE
        z_index = parsed.get_int("z", 0)

        asset_prefix = cfg.asset_prefix if cfg and cfg.asset_prefix else None

        self.compositor.show_character(
            character_id=char_id,
            expression=expr,
            position=pos,
            transition=transition,
            duration=duration,
            flip_h=flip_h,
            flip_v=flip_v,
            scale=scale,
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=rotation,
            tint=tint,
            z_index=z_index,
            asset_prefix=asset_prefix,
        )

    def handle_hide(self, args: str) -> None:
        """Handle `~ hide character [with transition] [duration=X]`."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        raw_id = parsed.positional[0]
        cfg = self.find_character(raw_id)
        char_id = cfg.character_id if cfg is not None else raw_id.strip().lower()
        transition = parsed.with_ or parsed.get_str("transition", "fade") or "fade"
        duration = parsed.get_float("duration", 0.3)

        self.compositor.hide_character(
            character_id=char_id,
            transition=transition,
            duration=duration,
        )

    def handle_move(self, args: str) -> None:
        """Handle `~ move character to position [duration=X] [easing=Y]`."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        raw_id = parsed.positional[0]
        cfg = self.find_character(raw_id)
        char_id = cfg.character_id if cfg is not None else raw_id.strip().lower()
        destination = parsed.to or (
            parsed.positional[1] if len(parsed.positional) > 1 else "center"
        )
        duration = parsed.get_float("duration", 0.5)
        easing = parsed.get_str("easing", "ease_in_out_quad") or "ease_in_out_quad"

        self.compositor.move_character(
            character_id=char_id,
            position=destination,
            duration=duration,
            easing=easing,
        )

    def handle_expr(self, args: str) -> None:
        """Handle `~ expr character expression`."""
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return

        raw_id = parsed.positional[0]
        cfg = self.find_character(raw_id)
        char_id = cfg.character_id if cfg is not None else raw_id.strip().lower()
        expr = parsed.positional[1].strip().lower()
        if cfg is not None:
            expr = cfg.resolve_expression(expr)
        asset_prefix = cfg.asset_prefix if cfg and cfg.asset_prefix else None
        self.compositor.set_expression(char_id, expr, asset_prefix=asset_prefix)

    def handle_fade_in(self, args: str) -> None:
        """Handle `~ fade_in [duration=X] [color=#000]`."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 1.0)
        color = _parse_hook_color(parsed, "color", BLACK)
        self.compositor.fade_in(duration=duration, color=color)

    def handle_fade_out(self, args: str) -> None:
        """Handle `~ fade_out [duration=X] [color=#000]`."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 1.0)
        color = _parse_hook_color(parsed, "color", BLACK)
        self.compositor.fade_out(duration=duration, color=color)

    def handle_flash(self, args: str) -> None:
        """Handle `~ flash [duration=X] [color=#fff]`."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 0.15)
        color = _parse_hook_color(parsed, "color", WHITE)
        self.compositor.flash(duration=duration, color=color)

    def handle_shake(self, args: str) -> None:
        """Handle `~ shake [intensity=X] [duration=Y]`."""
        parsed = parse_hook_args(args)
        intensity = parsed.get_float("intensity", 1.0)
        duration = parsed.get_float("duration", 0.3)
        self.compositor.shake(intensity=intensity, duration=duration)

    def _is_skip_active(self) -> bool:
        if self.skip_mode_cb is not None:
            try:
                return bool(self.skip_mode_cb())
            except Exception:  # noqa: BLE001
                return False
        return False

    def handle_play(self, args: str, channel: str | None = None) -> None:
        """Handle `~ play channel track [...]` or shorthand `~ play_<channel> track [...]`."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        track_arg = parsed.get_str("track")
        if channel is None:
            if not parsed.positional:
                return
            target_channel = parsed.positional[0].strip().lower()
            track = track_arg or (parsed.positional[1].strip() if len(parsed.positional) > 1 else "")
        else:
            target_channel = channel.strip().lower()
            track = track_arg or (parsed.positional[0].strip() if parsed.positional else "")

        if not track:
            return

        # In skip mode, drop sound and voice playback (music and ambient keep playing)
        if self._is_skip_active() and (
            target_channel in ("sound", "voice")
            or target_channel.startswith(("sound_", "voice_"))
        ):
            return

        fade_in = parsed.get_float("fade", 0.0) or parsed.get_float("fade_in", 0.0)
        # Omit volume (None) when the hook does not specify it so an
        # auto-allocated pool slot inherits the base channel's track volume.
        vol_raw = parsed.get_str("volume")
        try:
            volume = float(vol_raw) if vol_raw is not None else None
        except ValueError:
            volume = None
        loop_arg = parsed.get_bool("loop") if "loop" in parsed.kwargs else None
        loop_start = parsed.get_float("loop_start") if "loop_start" in parsed.kwargs else None
        loop_end = parsed.get_float("loop_end") if "loop_end" in parsed.kwargs else None

        self.audio.play(
            target_channel,
            track,
            loop=loop_arg,
            fade_in=fade_in,
            volume=volume,
            loop_start=loop_start,
            loop_end=loop_end,
        )

    def handle_stop(self, args: str, channel: str | None = None) -> None:
        """Handle `~ stop channel [fade=X]` or `~ stop_<channel> [fade=X]`."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if channel is None:
            target_channel = parsed.positional[0].strip().lower() if parsed.positional else "all"
        else:
            target_channel = channel.strip().lower()
        fade_out = parsed.get_float("fade", 0.0) or parsed.get_float("fade_out", 0.0)

        if target_channel == "all":
            self.audio.stop_all(fade_out=fade_out)
        else:
            self.audio.stop(target_channel, fade_out=fade_out)

    def handle_volume(self, args: str, channel: str | None = None) -> None:
        """Handle `~ volume channel level` or `~ volume_<channel> level`."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if channel is None:
            if len(parsed.positional) < 2:
                return
            target_channel = parsed.positional[0].strip().lower()
            raw_vol = parsed.positional[1].strip()
        else:
            target_channel = channel.strip().lower()
            raw_vol = parsed.get_str("volume") or (parsed.positional[0].strip() if parsed.positional else None)

        if raw_vol is None:
            return
        try:
            vol = float(raw_vol)
            if target_channel == "master":
                if hasattr(self.audio, "set_master_volume"):
                    self.audio.set_master_volume(vol)
            else:
                self.audio.set_volume(target_channel, vol)
        except ValueError:
            pass

    def handle_pause(self, args: str, channel: str | None = None) -> None:
        """Handle `~ pause [channel]` or `~ pause_<channel>`."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if channel is not None:
            target = channel.strip().lower()
        elif parsed.positional:
            target = parsed.positional[0].strip().lower()
        else:
            target = "all"

        if target == "all":
            if hasattr(self.audio, "pause_all"):
                self.audio.pause_all()
            else:
                for c in list(self.audio.channels):
                    self.audio.pause(c)
        else:
            self.audio.pause(target)

    def handle_resume(self, args: str, channel: str | None = None) -> None:
        """Handle `~ resume [channel]` or `~ resume_<channel>`."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if channel is not None:
            target = channel.strip().lower()
        elif parsed.positional:
            target = parsed.positional[0].strip().lower()
        else:
            target = "all"

        if target == "all":
            if hasattr(self.audio, "resume_all"):
                self.audio.resume_all()
            else:
                for c in list(self.audio.channels):
                    self.audio.resume(c)
        else:
            self.audio.resume(target)

    # =========================================================================
    # Narrative Event Handlers
    # =========================================================================

    def resolve_side_image(
        self,
        speaker: str | None,
        emotion: str | None = None,
        *,
        character_id: str | None = None,
    ) -> str | None:
        """Resolve the active side image asset ID for a character and expression."""
        cfg = self.find_character(speaker, character_id=character_id)
        if cfg and cfg.side_image:
            return cfg.side_image
        if cfg and cfg.asset_prefix:
            expr = emotion.strip().lower() if emotion else cfg.default_expression
            expr = cfg.resolve_expression(expr)
            return f"{cfg.asset_prefix}_{expr}"
        return None

    def handle_dialogue_event(self, event: DialogueEvent) -> None:
        """Update UI state, sync sprite, and play dialogue voice audio on the voice channel."""
        speaker = event.speaker
        text = event.text
        emotion = event.emotion
        voice = getattr(event, "voice", None)
        char_id = getattr(event, "character_id", None)

        char_cfg = self.find_character(speaker, character_id=char_id)
        self.ui_state.speaker = speaker
        self.ui_state.text = text
        self.ui_state.emotion = emotion
        self.ui_state.side_image = self.resolve_side_image(speaker, emotion, character_id=char_id)
        self.ui_state.speaker_color = char_cfg.color if char_cfg else None
        self.ui_state.clear_choices()

        if speaker and emotion:
            target_id = (
                self._resolve_speaker_element_id(speaker, character_id=char_id)
                or (char_cfg.character_id if char_cfg is not None else (char_id or speaker.strip().lower()))
            )
            resolved_expr = (
                char_cfg.resolve_expression(emotion.strip().lower())
                if char_cfg is not None
                else emotion.strip().lower()
            )
            asset_prefix = char_cfg.asset_prefix if char_cfg and char_cfg.asset_prefix else None
            self.compositor.set_expression(target_id, resolved_expr, asset_prefix=asset_prefix)

        # Voice audio management
        if self.audio is not None:
            if voice and not self._is_skip_active():
                self.audio.play("voice", str(voice), loop=False)
            else:
                self.audio.stop("voice")

    def _resolve_speaker_element_id(self, speaker: str | None, *, character_id: str | None = None) -> str | None:
        """Resolve a speaker name/id to an element_id on the characters layer."""
        char_layer = self.compositor.stage.get_layer("characters")
        if char_layer is None:
            return None

        if character_id:
            cid = character_id.strip().lower()
            if cid in char_layer.elements:
                return cid
            cfg = self.characters.get(cid)
            if cfg and cfg.character_id in char_layer.elements:
                return cfg.character_id

        if not speaker:
            return None

        # Check direct lowercase
        candidate = speaker.strip().lower()
        if candidate in char_layer.elements:
            return candidate

        # Check registered character aliases/keys
        for cid, cfg in self.characters.items():
            if (
                cid == candidate
                or (cfg.name and cfg.name.lower() == candidate)
                or (cfg.asset_prefix and cfg.asset_prefix.lower() == candidate)
            ) and cid in char_layer.elements:
                return cid

        # Fallback to direct key if match
        for key in char_layer.elements:
            if key.lower() == candidate:
                return key

        return None

    def handle_append_event(self, event: AppendEvent) -> None:
        """Append text to current UI dialogue buffer."""
        add_text = event.text
        current = self.ui_state.text or ""
        self.ui_state.text = f"{current} {add_text}".strip()
        self.ui_state.clear_choices()

    def handle_fresh_box_event(self, event: FreshBoxEvent) -> None:
        """Clear textbox content but preserve speaker for fresh box."""
        self.ui_state.text = event.text
        self.ui_state.clear_choices()

    def handle_narration_event(self, event: NarrationEvent) -> None:
        """Update UI state with narration text and stop active voice."""
        self.ui_state.speaker = None
        self.ui_state.text = event.text
        self.ui_state.emotion = None
        self.ui_state.side_image = None
        self.ui_state.clear_choices()

        if self.audio is not None:
            self.audio.stop("voice")

    def handle_scene_enter_event(self, event: SceneEnterEvent) -> None:
        """Trigger registered background transitions when entering new scenes."""
        scene_id = event.scene_id
        if scene_id and scene_id in self.scene_backgrounds:
            asset_id, trans, dur = self.scene_backgrounds[scene_id]
            self.compositor.set_background(asset_id, transition=trans, duration=dur)

    def handle_scene_exit_event(self, event: SceneExitEvent) -> None:
        """Clear dialogue and choices on scene exit and stop voice channel."""
        self.ui_state.clear_dialogue()
        self.ui_state.clear_choices()
        if self.audio is not None:
            self.audio.stop("voice")

    def handle_choice_prompt_event(self, event: ChoicePromptEvent) -> None:
        """Populate UI state choices from ChoicePromptEvent."""
        self.ui_state.choices = [
            ChoiceOption(
                index=opt.index,
                text=opt.text,
                target=opt.target,
                enabled=opt.enabled,
                condition=opt.condition,
            )
            for opt in event.options
        ]

    def handle_story_end_event(self, event: StoryEndEvent) -> None:
        """Mark UI state as finished and stop voice channel."""
        self.ui_state.is_finished = True
        if self.audio is not None:
            self.audio.stop("voice")
