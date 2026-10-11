"""Directs stage compositor actions from narrative engine events and script hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eager_core.audio import AudioMixer
from eager_script import HookArgs, parse_hook_args

from eager_graphics.compositor import StageCompositor
from eager_graphics.history import VisualHistoryManager
from eager_graphics.types import BLACK, WHITE, Color
from eager_graphics.ui_state import ChoiceOption, NVLEntry, UIState


def _hook_color(args: HookArgs, key: str, default: Color) -> Color:
    """Decode a hook argument into a :class:`Color`, falling back to *default*.

    The hook-argument parser lives in ``eager_script`` and is rendering-agnostic
    (it returns raw strings), so colour decoding happens here where the type
    lives.
    """
    raw = args.get_str(key)
    if raw is None:
        return default
    try:
        return Color.from_hex(raw)
    except ValueError:
        return default


@dataclass
class CharacterConfig:
    """Registration metadata for a story character."""

    character_id: str
    asset_prefix: str | None = None
    default_expression: str = "default"
    default_position: str = "center"
    side_image: str | None = None


class StageDirector:
    """Bridges Eager events and screenplay script hooks to the StageCompositor."""

    def __init__(
        self,
        compositor: StageCompositor,
        *,
        audio: AudioMixer | None = None,
        skip_mode_cb: Any = None,
    ) -> None:
        self.compositor = compositor
        self.audio = audio
        self.skip_mode_cb = skip_mode_cb
        self.characters: dict[str, CharacterConfig] = {}
        self.scene_backgrounds: dict[str, tuple[str, str, float]] = {}
        self.ui_state: UIState = UIState()
        self._visual_history: VisualHistoryManager | None = None

    def enable_visual_history(self, max_history: int = 500) -> None:
        """Enable visual state rollback tracking with the specified history capacity."""
        self._visual_history = VisualHistoryManager(max_history=max_history)

    def snapshot_visual_state(self) -> None:
        """Capture and push current visual and UI state into the visual history stack."""
        if self._visual_history is None:
            return
        snapshot = {
            "compositor": self.compositor.save_state(),
            "ui_state": self.ui_state.to_dict(),
        }
        self._visual_history.push(snapshot)

    def rollback_visual_state(self) -> bool:
        """Pop and restore the previous visual state snapshot from history."""
        if self._visual_history is None:
            return False
        snapshot = self._visual_history.pop()
        if snapshot is None:
            return False

        if "compositor" in snapshot:
            self.compositor.load_state(snapshot["compositor"])
        if "ui_state" in snapshot:
            self.ui_state = UIState.from_dict(snapshot["ui_state"])
        return True

    def save_visual_state(self) -> dict[str, Any]:
        """Return a complete dictionary containing compositor, ui_state, and history stack."""
        return {
            "compositor": self.compositor.save_state(),
            "ui_state": self.ui_state.to_dict(),
            "history": self._visual_history.to_dict() if self._visual_history is not None else None,
        }

    def load_visual_state(self, state: dict[str, Any]) -> None:
        """Restore compositor, UI state, and history stack from a serialized dictionary."""
        if comp_state := state.get("compositor"):
            self.compositor.load_state(comp_state)
        if ui_state := state.get("ui_state"):
            self.ui_state = UIState.from_dict(ui_state)
        if hist_state := state.get("history"):
            self._visual_history = VisualHistoryManager.from_dict(hist_state)

    def register_character(
        self,
        character_id: str,
        *,
        asset_prefix: str | None = None,
        default_expression: str = "default",
        default_position: str = "center",
        side_image: str | None = None,
    ) -> None:
        """Register default configuration for a character."""
        cid = character_id.strip().lower()
        self.characters[cid] = CharacterConfig(
            character_id=cid,
            asset_prefix=asset_prefix,
            default_expression=default_expression,
            default_position=default_position,
            side_image=side_image,
        )

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

    def on_beat_step(self) -> None:
        """Explicit callback to snapshot visual and UI state before advancing a narrative beat."""
        self.snapshot_visual_state()

    def bind(self, dispatcher: Any) -> None:
        """Register hook handlers and event listeners on an Eager EventDispatcher."""
        def _wrap_hook(handler: Any) -> Any:
            def _wrapped(args: str) -> None:
                handler(args)
            return _wrapped

        # 1. Screenplay Engine Hook Listeners (~ hook)
        dispatcher.on_hook("bg")(_wrap_hook(self.handle_bg))
        dispatcher.on_hook("bg_clear")(_wrap_hook(self.handle_bg_clear))
        dispatcher.on_hook("scene")(_wrap_hook(self.handle_scene))
        dispatcher.on_hook("image")(_wrap_hook(self.handle_image))
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
        dispatcher.on_hook("volume")(_wrap_hook(self.handle_volume))
        dispatcher.on_hook("nvl")(_wrap_hook(self.handle_nvl))
        dispatcher.on_hook("nvl_clear")(_wrap_hook(self.handle_nvl_clear))


        # 2. Wildcard Event Listener — dispatch on event.type string.
        #    This keeps eager_graphics free of any eager_runtime dependency
        #    (the director works with any dispatcher that supports
        #    on_any_event, including mock dispatchers in tests).
        dispatcher.on_any_event(self.handle_generic_event)

    # =========================================================================
    # Hook Handlers
    # =========================================================================

    def handle_bg(self, args: str) -> None:
        """Handle '~ bg asset_name [with transition] [duration=X]'."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        asset_id = parsed.positional[0]
        # Auto-prefix with 'bg/' if not provided and doesn't contain a slash
        if "/" not in asset_id:
            asset_id = f"bg/{asset_id}"

        transition = parsed.with_ or parsed.get_str("transition", "cut")
        duration = parsed.get_float("duration", 0.5 if transition != "cut" else 0.0)

        self.compositor.set_background(
            asset_id=asset_id,
            transition=transition,
            duration=duration,
        )

    def handle_bg_clear(self, args: str) -> None:
        """Handle '~ bg_clear [with transition] [duration=X]'."""
        parsed = parse_hook_args(args)
        transition = parsed.with_ or parsed.get_str("transition", "cut")
        duration = parsed.get_float("duration", 0.5 if transition != "cut" else 0.0)
        self.compositor.clear_background(transition=transition, duration=duration)

    def handle_scene(self, args: str) -> None:
        """Handle '~ scene asset_name [with transition] [duration=X]': clears characters and sets background."""
        # Clear all character sprites
        char_layer = self.compositor.stage.get_layer("characters")
        if char_layer:
            char_layer.clear()
        # Set background
        self.handle_bg(args)

    def handle_image(self, args: str) -> None:
        """Handle '~ image name asset [at pos] [z=N]': arbitrary image display on foreground layer."""
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        name = parsed.positional[0].strip()
        asset = parsed.positional[1].strip()
        pos = parsed.at or "center"
        z = parsed.get_int("z", 50)
        fg_layer = self.compositor.stage.get_or_create_layer("foreground", z_order=200)
        from eager_graphics.stage import ElementState, StageElement
        resolved_pos = self.compositor.layout.resolve_position(pos)
        elem = StageElement(
            element_id=name,
            state=ElementState(
                asset_id=asset,
                position=resolved_pos,
                z_index=z,
            ),
        )
        fg_layer.add_element(elem)

    def handle_show(self, args: str) -> None:
        """Handle '~ show character [expression] [at position] [with transition] [duration=X]'."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        raw_id = parsed.positional[0]
        char_id = raw_id.strip().lower()
        cfg = self.characters.get(char_id)

        # Expression
        if len(parsed.positional) > 1:
            expr = parsed.positional[1]
        elif cfg is not None:
            expr = cfg.default_expression
        else:
            expr = "default"

        # Position
        pos = parsed.at or (cfg.default_position if cfg else "center")

        # Transition
        transition = parsed.with_ or parsed.get_str("transition", "fade")
        duration = parsed.get_float("duration", 0.3)
        flip_h = parsed.get_bool("flip_h", False)
        z_index = parsed.get_int("z", 0)

        self.compositor.show_character(
            character_id=char_id,
            expression=expr,
            position=pos,
            transition=transition,
            duration=duration,
            flip_h=flip_h,
            z_index=z_index,
        )

    def handle_hide(self, args: str) -> None:
        """Handle '~ hide character [with transition] [duration=X]'."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        char_id = parsed.positional[0].strip().lower()
        transition = parsed.with_ or parsed.get_str("transition", "fade")
        duration = parsed.get_float("duration", 0.3)

        self.compositor.hide_character(
            character_id=char_id,
            transition=transition,
            duration=duration,
        )

    def handle_move(self, args: str) -> None:
        """Handle '~ move character to position [duration=X] [easing=Y]'."""
        parsed = parse_hook_args(args)
        if not parsed.positional:
            return

        char_id = parsed.positional[0].strip().lower()
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
        """Handle '~ expr character expression'."""
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return

        char_id = parsed.positional[0].strip().lower()
        expr = parsed.positional[1].strip().lower()
        self.compositor.set_expression(char_id, expr)

    def handle_fade_in(self, args: str) -> None:
        """Handle '~ fade_in [duration=X]'."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 1.0)
        self.compositor.fade_in(duration=duration)

    def handle_fade_out(self, args: str) -> None:
        """Handle '~ fade_out [duration=X] [color=#000]'."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 1.0)
        color = _hook_color(parsed, "color", BLACK)
        self.compositor.fade_out(duration=duration, color=color)

    def handle_flash(self, args: str) -> None:
        """Handle '~ flash [duration=X] [color=#fff]'."""
        parsed = parse_hook_args(args)
        duration = parsed.get_float("duration", 0.15)
        color = _hook_color(parsed, "color", WHITE)
        self.compositor.flash(duration=duration, color=color)

    def handle_shake(self, args: str) -> None:
        """Handle '~ shake [intensity=X] [duration=Y]'."""
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

    def handle_play(self, args: str) -> None:
        """Handle '~ play channel track [fade=X] [volume=Y] [loop=True/False] [loop_start=Z] [loop_end=W]'."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        channel = parsed.positional[0].strip().lower()
        track = parsed.positional[1].strip()

        # In skip mode, drop sound and voice playback (music and ambient keep playing)
        if self._is_skip_active() and channel in ("sound", "voice"):
            return

        fade_in = parsed.get_float("fade", 0.0) or parsed.get_float("fade_in", 0.0)
        volume = parsed.get_float("volume", 1.0)
        loop_arg = parsed.get_bool("loop", None)
        loop_start = parsed.get_float("loop_start", None)
        loop_end = parsed.get_float("loop_end", None)

        self.audio.play(
            channel,
            track,
            loop=loop_arg,
            fade_in=fade_in,
            volume=volume,
            loop_start=loop_start,
            loop_end=loop_end,
        )

    def handle_stop(self, args: str) -> None:
        """Handle '~ stop channel [fade=X]' or '~ stop all'."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        channel = parsed.positional[0].strip().lower() if parsed.positional else "all"
        fade_out = parsed.get_float("fade", 0.0) or parsed.get_float("fade_out", 0.0)

        if channel == "all":
            self.audio.stop_all(fade_out=fade_out)
        else:
            self.audio.stop(channel, fade_out=fade_out)

    def handle_volume(self, args: str) -> None:
        """Handle '~ volume channel level'."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        channel = parsed.positional[0].strip().lower()
        try:
            vol = float(parsed.positional[1].strip())
            self.audio.set_volume(channel, vol)
        except ValueError:
            pass

    def handle_nvl(self, args: str) -> None:
        """Handle '~ nvl [on/off/clear]'."""
        arg = args.strip().lower() if args else "on"
        if arg in ("off", "false", "0"):
            self.ui_state.nvl_mode = False
        elif arg == "clear":
            self.ui_state.clear_nvl()
        else:
            self.ui_state.nvl_mode = True

    def handle_nvl_clear(self, args: str) -> None:
        """Handle '~ nvl_clear'."""
        self.ui_state.clear_nvl()

    # =========================================================================
    # Narrative Event Handlers
    # =========================================================================

    def _resolve_side_image(self, speaker: str | None, emotion: str | None) -> str | None:
        if not speaker:
            return None
        char_id = speaker.strip().lower()
        cfg = self.characters.get(char_id)
        if cfg and cfg.side_image:
            return cfg.side_image
        if cfg and cfg.asset_prefix:
            expr = emotion.strip().lower() if emotion else cfg.default_expression
            return f"{cfg.asset_prefix}_{expr}"
        return None

    def handle_dialogue_event(self, event: Any) -> None:
        """Update UI state, sync sprite, and play dialogue voice audio on the voice channel."""
        speaker = getattr(event, "speaker", None)
        text = getattr(event, "text", "")
        emotion = getattr(event, "emotion", None)
        voice = getattr(event, "voice", None)

        self.ui_state.speaker = speaker
        self.ui_state.text = text
        self.ui_state.emotion = emotion
        self.ui_state.side_image = self._resolve_side_image(speaker, emotion)
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=speaker, text=text, emotion=emotion))

        if speaker and emotion:
            char_id = speaker.strip().lower()
            self.compositor.set_expression(char_id, emotion.strip().lower())

        # Voice audio management
        if self.audio is not None:
            if voice and not self._is_skip_active():
                self.audio.play("voice", str(voice), loop=False)
            else:
                self.audio.stop("voice")

    def handle_append_event(self, event: Any) -> None:
        """Append text to current UI dialogue buffer."""
        add_text = getattr(event, "text", "")
        current = self.ui_state.text or ""
        self.ui_state.text = f"{current} {add_text}".strip()
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode and self.ui_state.nvl_entries:
            last = self.ui_state.nvl_entries[-1]
            last.text = f"{last.text} {add_text}".strip()

    def handle_fresh_box_event(self, event: Any) -> None:
        """Clear textbox content but preserve speaker for fresh box."""
        self.ui_state.text = getattr(event, "text", "")
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=self.ui_state.speaker, text=self.ui_state.text, emotion=self.ui_state.emotion))

    def handle_narration_event(self, event: Any) -> None:
        """Update UI state with narration text and stop active voice."""
        self.ui_state.speaker = None
        self.ui_state.text = getattr(event, "text", "")
        self.ui_state.emotion = None
        self.ui_state.side_image = None
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=None, text=self.ui_state.text))

        if self.audio is not None:
            self.audio.stop("voice")

    def handle_scene_enter_event(self, event: Any) -> None:
        """Trigger registered background transitions when entering new scenes."""
        scene_id = getattr(event, "scene_id", None)
        if scene_id and scene_id in self.scene_backgrounds:
            asset_id, trans, dur = self.scene_backgrounds[scene_id]
            self.compositor.set_background(asset_id, transition=trans, duration=dur)

    def handle_scene_exit_event(self, event: Any) -> None:
        """Clear dialogue and choices on scene exit and stop voice channel."""
        self.ui_state.clear_dialogue()
        self.ui_state.clear_choices()
        if self.audio is not None:
            self.audio.stop("voice")

    def handle_choice_prompt_event(self, event: Any) -> None:
        """Populate UI state choices from ChoicePromptEvent."""
        raw_options = getattr(event, "options", [])
        self.ui_state.choices = [
            ChoiceOption(
                index=getattr(opt, "index", idx),
                text=getattr(opt, "text", ""),
                target=getattr(opt, "target", None),
                enabled=getattr(opt, "enabled", True),
                condition=getattr(opt, "condition", None),
            )
            for idx, opt in enumerate(raw_options)
        ]

    def handle_story_end_event(self, event: Any) -> None:
        """Mark UI state as finished and stop voice channel."""
        self.ui_state.is_finished = True
        if self.audio is not None:
            self.audio.stop("voice")

    def handle_generic_event(self, event: Any) -> None:
        """Fallback handler if Eager classes were not directly importable at bind time."""
        event_type = getattr(event, "type", None)
        if event_type == "dialogue":
            self.handle_dialogue_event(event)
        elif event_type == "append":
            self.handle_append_event(event)
        elif event_type == "fresh_box":
            self.handle_fresh_box_event(event)
        elif event_type == "narration":
            self.handle_narration_event(event)
        elif event_type == "scene_enter":
            self.handle_scene_enter_event(event)
        elif event_type == "scene_exit":
            self.handle_scene_exit_event(event)
        elif event_type == "choice_prompt":
            self.handle_choice_prompt_event(event)
        elif event_type == "story_end":
            self.handle_story_end_event(event)
