"""Directs stage compositor actions from narrative engine events and script hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eager_core.audio import AudioMixer
from eager_core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager_core.types import BLACK, WHITE, Color, Vec2
from eager_script import HookArgs, parse_hook_args

from eager_graphics.compositor import StageCompositor
from eager_graphics.ui_state import NVLEntry, UIState

__all__ = [
    "CharacterConfig",
    "StageDirector",
]


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
    name: str | None = None
    asset_prefix: str | None = None
    default_expression: str = "default"
    default_position: str = "center"
    side_image: str | None = None
    color: Color | None = None


class StageDirector:
    """Bridges Eager events and screenplay script hooks to the StageCompositor."""

    def __init__(
        self,
        compositor: StageCompositor,
        *,
        audio: AudioMixer | None = None,
        skip_mode_cb: Any = None,
        auto_highlight_speaker: bool = False,
        dim_color: Color | None = None,
        highlight_duration: float = 0.25,
        pop_scale: float | None = None,
        pop_hop: float | None = None,
    ) -> None:
        self.compositor = compositor
        self.audio = audio
        self.skip_mode_cb = skip_mode_cb
        self.auto_highlight_speaker = auto_highlight_speaker
        self.dim_color = dim_color if dim_color is not None else Color(0.65, 0.65, 0.70, 1.0)
        self.highlight_duration = highlight_duration
        self.pop_scale = pop_scale
        self.pop_hop = pop_hop
        self.characters: dict[str, CharacterConfig] = {}
        self.scene_backgrounds: dict[str, tuple[str, str, float]] = {}
        self.ui_state: UIState = UIState()
        self._sprite_base_y: dict[str, float] = {}

    def step(self, dt: float) -> None:
        """Advance compositor timelines and animations by *dt* seconds."""
        self.compositor.step(dt)

    def finish_animations(self) -> None:
        """Immediately complete active stage animations."""
        self.compositor.finish_animations()

    def save_ui_state(self) -> dict[str, Any]:
        """Serialize current UI state."""
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        """Restore UI state from serialized dictionary."""
        self.ui_state = UIState.from_dict(state)

    def save_visual_state(self) -> dict[str, Any]:
        """Serialize compositor stage state."""
        return {
            "compositor": self.compositor.save_state(),
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

        self.characters[cid] = CharacterConfig(
            character_id=cid,
            name=name,
            asset_prefix=asset_prefix,
            default_expression=default_expression,
            default_position=default_position,
            side_image=side_image,
            color=parsed_color,
        )

    def _find_character_config(self, speaker: str | None) -> CharacterConfig | None:
        """Find CharacterConfig matching character_id or display name."""
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


        # 2. Narrative Event Listeners
        dispatcher.on_event(DialogueEvent)(self.handle_dialogue_event)
        dispatcher.on_event(AppendEvent)(self.handle_append_event)
        dispatcher.on_event(FreshBoxEvent)(self.handle_fresh_box_event)
        dispatcher.on_event(NarrationEvent)(self.handle_narration_event)
        dispatcher.on_event(SceneEnterEvent)(self.handle_scene_enter_event)
        dispatcher.on_event(SceneExitEvent)(self.handle_scene_exit_event)
        dispatcher.on_event(ChoicePromptEvent)(self.handle_choice_prompt_event)
        dispatcher.on_event(InputPromptEvent)(self.handle_input_prompt_event)
        dispatcher.on_event(StoryEndEvent)(self.handle_story_end_event)

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

        transition = parsed.with_ or parsed.get_str("transition", "cut") or "cut"
        duration = parsed.get_float("duration", 0.5 if transition != "cut" else 0.0)

        self.compositor.set_background(
            asset_id=asset_id,
            transition=transition,
            duration=duration,
        )

    def handle_bg_clear(self, args: str) -> None:
        """Handle '~ bg_clear [with transition] [duration=X]'."""
        parsed = parse_hook_args(args)
        transition = parsed.with_ or parsed.get_str("transition", "cut") or "cut"
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
        cfg = self._find_character_config(raw_id)
        char_id = cfg.character_id if cfg is not None else raw_id.strip().lower()

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
        transition = parsed.with_ or parsed.get_str("transition", "fade") or "fade"
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
        transition = parsed.with_ or parsed.get_str("transition", "fade") or "fade"
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
        """Handle '~ play channel track [fade=X] [volume=Y] [loop=True/False] [loop_start=Z] [loop_end=W] [auto_channels=True/False] [max_polyphony=N]'."""
        if self.audio is None:
            return
        parsed = parse_hook_args(args)
        if len(parsed.positional) < 2:
            return
        channel = parsed.positional[0].strip().lower()
        track = parsed.positional[1].strip()

        # In skip mode, drop sound and voice playback (music and ambient keep playing)
        if self._is_skip_active() and (
            channel in ("sound", "voice")
            or channel.startswith(("sound_", "voice_"))
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
        # Sound effects are polyphonic by default so overlapping SFX spawn
        # pool slots (sound_0, sound_1, …) instead of cutting each other off.
        # Other channels stay single-voice unless opted in. Explicit pool
        # names (sound_0) always address that slot directly.
        auto_channels = parsed.get_bool("auto_channels", channel == "sound")
        poly_raw = parsed.get_str("max_polyphony")
        try:
            max_polyphony = int(poly_raw) if poly_raw is not None else None
        except ValueError:
            max_polyphony = None

        self.audio.play(
            channel,
            track,
            loop=loop_arg,
            fade_in=fade_in,
            volume=volume,
            loop_start=loop_start,
            loop_end=loop_end,
            auto_channels=auto_channels,
            max_polyphony=max_polyphony,
        )

    def handle_stop(self, args: str) -> None:
        """Handle '~ stop channel [fade=X]' or '~ stop all'.

        Stopping a base channel (e.g. ``sound``) also stops its polyphonic
        pool members (``sound_0``, ``sound_1``, …).
        """
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
        """Handle '~ volume channel level'.

        Volume changes on a base channel fan out to its polyphonic pool
        members.
        """
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
        cfg = self._find_character_config(speaker)
        if cfg and cfg.side_image:
            return cfg.side_image
        if cfg and cfg.asset_prefix:
            expr = emotion.strip().lower() if emotion else cfg.default_expression
            return f"{cfg.asset_prefix}_{expr}"
        return None

    def handle_dialogue_event(self, event: Any) -> None:
        """Update UI state, sync sprite, and play dialogue voice audio on the voice channel."""
        speaker = event.speaker
        text = event.text
        emotion = event.emotion
        voice = getattr(event, "voice", None)

        char_cfg = self._find_character_config(speaker)
        self.ui_state.speaker = speaker
        self.ui_state.text = text
        self.ui_state.emotion = emotion
        self.ui_state.side_image = self._resolve_side_image(speaker, emotion)
        self.ui_state.speaker_color = char_cfg.color if char_cfg else None
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=speaker, text=text, emotion=emotion))

        if speaker and emotion:
            char_id = speaker.strip().lower()
            self.compositor.set_expression(char_id, emotion.strip().lower())

        if self.auto_highlight_speaker:
            self._apply_speaker_highlight(speaker)

        # Voice audio management
        if self.audio is not None:
            if voice and not self._is_skip_active():
                self.audio.play("voice", str(voice), loop=False)
            else:
                self.audio.stop("voice")

    def _resolve_speaker_element_id(self, speaker: str | None) -> str | None:
        """Resolve a speaker name/id to an element_id on the characters layer."""
        if not speaker:
            return None
        char_layer = self.compositor.stage.get_layer("characters")
        if char_layer is None:
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

    def _apply_speaker_highlight(self, speaker: str | None) -> None:
        """Auto-highlight active speaker sprite and dim non-speaking sprites on characters layer."""
        char_layer = self.compositor.stage.get_layer("characters")
        if char_layer is None or not char_layer.elements:
            return

        speaker_elem_id = self._resolve_speaker_element_id(speaker)
        dur = self.highlight_duration

        for elem_id, elem in char_layer.elements.items():
            if speaker_elem_id is not None and elem_id == speaker_elem_id:
                # Active speaker: tint -> WHITE
                if elem.state.tint != WHITE:
                    if dur > 0.0:
                        self.compositor.timeline.add_tween(
                            target=elem.state,
                            property_name="tint",
                            end_value=WHITE,
                            duration=dur,
                        )
                    else:
                        elem.state.tint = WHITE

                # Optional scale pop
                if self.pop_scale is not None:
                    target_scale = Vec2(self.pop_scale, self.pop_scale)
                    if elem.state.scale != target_scale:
                        if dur > 0.0:
                            self.compositor.timeline.add_tween(
                                target=elem.state,
                                property_name="scale",
                                end_value=target_scale,
                                duration=dur,
                            )
                        else:
                            elem.state.scale = target_scale

                # Optional hop (tiny y hop)
                if self.pop_hop is not None:
                    base_y = self._sprite_base_y.get(elem_id)
                    if base_y is None:
                        base_y = elem.state.position.y
                        self._sprite_base_y[elem_id] = base_y
                    target_pos = Vec2(elem.state.position.x, base_y - self.pop_hop)
                    if elem.state.position != target_pos:
                        if dur > 0.0:
                            self.compositor.timeline.add_tween(
                                target=elem.state,
                                property_name="position",
                                end_value=target_pos,
                                duration=dur,
                            )
                        else:
                            elem.state.position = target_pos
            else:
                # Non-speaking character or restore when speaker not on layer:
                # When speaker_elem_id is not None, this character is dimmed.
                # When speaker_elem_id is None, restore to WHITE.
                target_tint = self.dim_color if speaker_elem_id is not None else WHITE
                if elem.state.tint != target_tint:
                    if dur > 0.0:
                        self.compositor.timeline.add_tween(
                            target=elem.state,
                            property_name="tint",
                            end_value=target_tint,
                            duration=dur,
                        )
                    else:
                        elem.state.tint = target_tint

                if self.pop_scale is not None:
                    target_scale = Vec2(1.0, 1.0)
                    if elem.state.scale != target_scale:
                        if dur > 0.0:
                            self.compositor.timeline.add_tween(
                                target=elem.state,
                                property_name="scale",
                                end_value=target_scale,
                                duration=dur,
                            )
                        else:
                            elem.state.scale = target_scale

                if self.pop_hop is not None:
                    base_y = self._sprite_base_y.get(elem_id)
                    if base_y is not None:
                        target_pos = Vec2(elem.state.position.x, base_y)
                        if elem.state.position != target_pos:
                            if dur > 0.0:
                                self.compositor.timeline.add_tween(
                                    target=elem.state,
                                    property_name="position",
                                    end_value=target_pos,
                                    duration=dur,
                                )
                            else:
                                elem.state.position = target_pos

    def handle_append_event(self, event: Any) -> None:
        """Append text to current UI dialogue buffer."""
        add_text = event.text
        current = self.ui_state.text or ""
        self.ui_state.text = f"{current} {add_text}".strip()
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode and self.ui_state.nvl_entries:
            last = self.ui_state.nvl_entries[-1]
            last.text = f"{last.text} {add_text}".strip()

    def handle_fresh_box_event(self, event: Any) -> None:
        """Clear textbox content but preserve speaker for fresh box."""
        self.ui_state.text = event.text
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=self.ui_state.speaker, text=self.ui_state.text, emotion=self.ui_state.emotion))

    def handle_narration_event(self, event: Any) -> None:
        """Update UI state with narration text and stop active voice."""
        self.ui_state.speaker = None
        self.ui_state.text = event.text
        self.ui_state.emotion = None
        self.ui_state.side_image = None
        self.ui_state.clear_choices()

        if self.ui_state.nvl_mode:
            self.ui_state.nvl_entries.append(NVLEntry(speaker=None, text=self.ui_state.text))

        if self.auto_highlight_speaker:
            self._apply_speaker_highlight(None)

        if self.audio is not None:
            self.audio.stop("voice")

    def handle_scene_enter_event(self, event: Any) -> None:
        """Trigger registered background transitions when entering new scenes."""
        scene_id = event.scene_id
        if scene_id and scene_id in self.scene_backgrounds:
            asset_id, trans, dur = self.scene_backgrounds[scene_id]
            self.compositor.set_background(asset_id, transition=trans, duration=dur)

    def handle_scene_exit_event(self, event: Any) -> None:
        """Clear dialogue and choices on scene exit and stop voice channel."""
        self.ui_state.clear_dialogue()
        self.ui_state.clear_choices()
        self.ui_state.active_input_prompt = None
        if self.audio is not None:
            self.audio.stop("voice")

    def handle_choice_prompt_event(self, event: Any) -> None:
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

    def handle_input_prompt_event(self, event: Any) -> None:
        """Record active input prompt on UI state."""
        self.ui_state.active_input_prompt = event

    def handle_story_end_event(self, event: Any) -> None:
        """Mark UI state as finished and stop voice channel."""
        self.ui_state.is_finished = True
        if self.audio is not None:
            self.audio.stop("voice")
