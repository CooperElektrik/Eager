"""Core visual stage compositor, animation driver, and render list generator."""

from __future__ import annotations

import math
from typing import Any

from eager.backends.types import RenderItem
from eager.core.easing import get_easing
from eager.core.layout import LayoutResolver
from eager.core.timeline import Timeline
from eager.core.types import BLACK, WHITE, Anchor, Color, TransitionKind, Vec2
from eager.stage.stage import ElementState, Stage, StageElement

__all__ = [
    "StageCompositor",
]


class StageCompositor:
    """Renderer-agnostic stage compositor managing visual layers, animations, and transitions."""

    def __init__(
        self,
        virtual_width: int = 1920,
        virtual_height: int = 1080,
        *,
        ground_y: float = 1080.0,
    ) -> None:
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height
        self.stage = Stage()
        self.timeline = Timeline()
        self.layout = LayoutResolver(
            virtual_width=virtual_width,
            virtual_height=virtual_height,
            ground_y=ground_y,
        )

        # Layers that are exempt from camera screen shake (e.g. textboxes, HUD, overlay)
        self.shake_exempt_layers: set[str] = {"ui", "overlay"}

        # Camera shake state
        self._shake_intensity: float = 0.0
        self._shake_duration: float = 0.0
        self._shake_elapsed: float = 0.0
        self._shake_offset: Vec2 = Vec2(0.0, 0.0)

    @property
    def shake_offset(self) -> Vec2:
        """Current camera shake offset applied to non-exempt layers."""
        return self._shake_offset

    # =========================================================================
    # Background Operations
    # =========================================================================

    def set_background(
        self,
        asset_id: str,
        *,
        transition: str | TransitionKind = TransitionKind.CUT,
        duration: float = 0.5,
    ) -> None:
        """Set or swap the active background image with an optional transition."""
        trans_kind = (
            TransitionKind.from_str(transition) if isinstance(transition, str) else transition
        )
        bg_layer = self.stage.get_or_create_layer("background", z_order=0)

        # Full-screen default position & anchor
        bg_pos = Vec2(0.0, 0.0)
        bg_anchor = Anchor.TOP_LEFT

        if trans_kind == TransitionKind.CUT or duration <= 0.0:
            # Instant swap: cancel tweens on bg layer and replace
            self.timeline.cancel_tweens_for(bg_layer)
            for elem in list(bg_layer.elements.values()):
                self.timeline.cancel_tweens_for(elem.state)
            bg_layer.clear()

            new_elem = StageElement(
                element_id="bg_main",
                state=ElementState(
                    asset_id=asset_id,
                    position=bg_pos,
                    anchor=bg_anchor,
                    opacity=1.0,
                    z_index=0,
                ),
            )
            bg_layer.add_element(new_elem)
            return

        # Smooth transitions: cancel any in-flight background tweens first
        self.timeline.cancel_tweens_for(bg_layer)
        for elem in list(bg_layer.elements.values()):
            self.timeline.cancel_tweens_for(elem.state)

        existing_incoming = bg_layer.get_element("bg_incoming")
        if existing_incoming is not None:
            bg_layer.remove_element("bg_incoming")
            for old_id in list(bg_layer.elements):
                bg_layer.remove_element(old_id)
            existing_incoming.element_id = "bg_main"
            existing_incoming.state.z_index = 0
            existing_incoming.state.opacity = 1.0
            existing_incoming.state.position = bg_pos
            bg_layer.add_element(existing_incoming)

        old_elems = list(bg_layer.elements.values())

        is_slide = trans_kind in (
            TransitionKind.SLIDE_LEFT,
            TransitionKind.SLIDE_RIGHT,
            TransitionKind.SLIDE_UP,
            TransitionKind.SLIDE_DOWN,
        )

        incoming_pos = bg_pos
        match trans_kind:
            case TransitionKind.SLIDE_LEFT:
                incoming_pos = bg_pos + Vec2(float(self.virtual_width), 0.0)
            case TransitionKind.SLIDE_RIGHT:
                incoming_pos = bg_pos - Vec2(float(self.virtual_width), 0.0)
            case TransitionKind.SLIDE_UP:
                incoming_pos = bg_pos + Vec2(0.0, float(self.virtual_height))
            case TransitionKind.SLIDE_DOWN:
                incoming_pos = bg_pos - Vec2(0.0, float(self.virtual_height))
            case _:
                pass

        new_elem = StageElement(
            element_id="bg_incoming",
            state=ElementState(
                asset_id=asset_id,
                position=incoming_pos,
                anchor=bg_anchor,
                opacity=1.0 if is_slide else 0.0,
                z_index=10,
            ),
        )
        bg_layer.add_element(new_elem)

        def _cleanup_old_bg() -> None:
            for old in old_elems:
                bg_layer.remove_element(old.element_id)
            # Re-label incoming as main
            bg_layer.remove_element("bg_incoming")
            new_elem.element_id = "bg_main"
            new_elem.state.z_index = 0
            new_elem.state.position = bg_pos
            bg_layer.add_element(new_elem)

        if is_slide:
            # Slide: tween position, keep opacity at 1.0
            self.timeline.add_tween(
                target=new_elem.state,
                property_name="position",
                end_value=bg_pos,
                duration=duration,
                easing=get_easing("ease_in_out_quad"),
                on_complete=_cleanup_old_bg,
            )
            # Also slide old backgrounds out in the matching direction
            for old in old_elems:
                slide_target = old.position
                match trans_kind:
                    case TransitionKind.SLIDE_LEFT:
                        slide_target = old.position - Vec2(float(self.virtual_width), 0.0)
                    case TransitionKind.SLIDE_RIGHT:
                        slide_target = old.position + Vec2(float(self.virtual_width), 0.0)
                    case TransitionKind.SLIDE_UP:
                        slide_target = old.position - Vec2(0.0, float(self.virtual_height))
                    case TransitionKind.SLIDE_DOWN:
                        slide_target = old.position + Vec2(0.0, float(self.virtual_height))
                self.timeline.add_tween(
                    target=old.state,
                    property_name="position",
                    end_value=slide_target,
                    duration=duration,
                    easing=get_easing("ease_in_out_quad"),
                )
        else:
            # Crossfade / Dissolve: fade in incoming background over current background,
            # keeping old background opaque until the incoming transition completes.
            # This ensures standard alpha blending (t * new + (1 - t) * old) produces
            # an exact linear crossfade without any brightness dip to black.
            self.timeline.add_tween(
                target=new_elem.state,
                property_name="opacity",
                end_value=1.0,
                duration=duration,
                on_complete=_cleanup_old_bg,
            )

    def clear_background(
        self,
        *,
        transition: str | TransitionKind = TransitionKind.CUT,
        duration: float = 0.5,
    ) -> None:
        """Clear the background, optionally fading out to black."""
        trans_kind = (
            TransitionKind.from_str(transition) if isinstance(transition, str) else transition
        )
        bg_layer = self.stage.get_layer("background")
        if bg_layer is None or not bg_layer.elements:
            return

        if trans_kind == TransitionKind.CUT or duration <= 0.0:
            for elem in list(bg_layer.elements.values()):
                self.timeline.cancel_tweens_for(elem.state)
            bg_layer.clear()
            return

        # Fade out all current backgrounds
        remaining = len(bg_layer.elements)

        def _on_fade_done() -> None:
            nonlocal remaining
            remaining -= 1
            if remaining <= 0:
                bg_layer.clear()

        for elem in list(bg_layer.elements.values()):
            self.timeline.cancel_tweens_for(elem.state)
            self.timeline.add_tween(
                target=elem.state,
                property_name="opacity",
                end_value=0.0,
                duration=duration,
                on_complete=_on_fade_done,
            )

    # =========================================================================
    # Character Sprite Operations
    # =========================================================================

    def show_character(
        self,
        character_id: str,
        expression: str = "default",
        *,
        position: str | Vec2 | tuple[float, float] = "center",
        transition: str | TransitionKind = TransitionKind.FADE,
        duration: float = 0.3,
        z_index: int = 0,
        flip_h: bool = False,
        flip_v: bool = False,
        scale: float | Vec2 = 1.0,
        scale_x: float | None = None,
        scale_y: float | None = None,
        rotation: float = 0.0,
        tint: Color = WHITE,
        asset_prefix: str | None = None,
    ) -> None:
        """Place or transition a character sprite on the stage."""
        char_layer = self.stage.get_or_create_layer("characters", z_order=100)
        target_pos = self.layout.resolve_position(position)
        prefix = asset_prefix or character_id
        asset_id = f"{prefix}/{expression}"
        trans_kind = (
            TransitionKind.from_str(transition) if isinstance(transition, str) else transition
        )

        if isinstance(scale, Vec2):
            scale_vec = Vec2(
                scale.x if scale_x is None else scale_x,
                scale.y if scale_y is None else scale_y,
            )
        else:
            sx = scale if scale_x is None else scale_x
            sy = scale if scale_y is None else scale_y
            scale_vec = Vec2(float(sx), float(sy))

        existing = char_layer.get_element(character_id)

        if existing is not None:
            # Character is already on stage: update expression and position
            self.timeline.cancel_tweens_for(existing.state)
            existing.asset_id = asset_id
            existing.state.flip_h = flip_h
            existing.state.flip_v = flip_v
            if existing.state.z_index != z_index:
                existing.state.z_index = z_index
                char_layer.invalidate_sort_cache()
            existing.state.scale = scale_vec
            existing.state.rotation = rotation
            existing.state.tint = tint

            if duration <= 0.0 or trans_kind == TransitionKind.CUT:
                existing.position = target_pos
                existing.opacity = 1.0
                existing.visible = True
            else:
                # Compute start position for slide transitions
                start_pos = existing.position
                match trans_kind:
                    case TransitionKind.SLIDE_LEFT:
                        start_pos = target_pos + Vec2(300.0, 0.0)
                        existing.position = start_pos
                    case TransitionKind.SLIDE_RIGHT:
                        start_pos = target_pos - Vec2(300.0, 0.0)
                        existing.position = start_pos
                    case TransitionKind.SLIDE_UP:
                        start_pos = target_pos + Vec2(0.0, 200.0)
                        existing.position = start_pos
                    case TransitionKind.SLIDE_DOWN:
                        start_pos = target_pos - Vec2(0.0, 200.0)
                        existing.position = start_pos
                    case _:
                        pass  # FADE/DISSOLVE — keep current position

                # Always tween to target position if not already there
                if existing.position != target_pos:
                    self.timeline.add_tween(
                        target=existing.state,
                        property_name="position",
                        end_value=target_pos,
                        duration=duration,
                        easing=get_easing("ease_out_quad"),
                    )
                if existing.opacity < 1.0 or not existing.visible:
                    existing.visible = True
                    self.timeline.add_tween(
                        target=existing.state,
                        property_name="opacity",
                        end_value=1.0,
                        duration=duration,
                    )
            return

        # New character arriving on stage
        start_pos = target_pos
        start_opacity = 0.0

        if trans_kind == TransitionKind.CUT or duration <= 0.0:
            start_opacity = 1.0
            duration = 0.0
        else:
            match trans_kind:
                case TransitionKind.SLIDE_LEFT:
                    # Slide in from right towards left
                    start_pos = target_pos + Vec2(300.0, 0.0)
                case TransitionKind.SLIDE_RIGHT:
                    # Slide in from left towards right
                    start_pos = target_pos - Vec2(300.0, 0.0)
                case TransitionKind.SLIDE_UP:
                    start_pos = target_pos + Vec2(0.0, 200.0)
                case TransitionKind.SLIDE_DOWN:
                    start_pos = target_pos - Vec2(0.0, 200.0)
                case _:
                    # Default FADE / DISSOLVE
                    start_pos = target_pos
                    start_opacity = 0.0

        state = ElementState(
            asset_id=asset_id,
            position=start_pos,
            anchor=Anchor.BOTTOM_CENTER,
            opacity=start_opacity,
            scale=scale_vec,
            rotation=rotation,
            tint=tint,
            visible=True,
            flip_h=flip_h,
            flip_v=flip_v,
            z_index=z_index,
        )
        element = StageElement(element_id=character_id, state=state)
        char_layer.add_element(element)

        if duration > 0.0:
            self.timeline.add_tween(
                target=state,
                property_name="opacity",
                end_value=1.0,
                duration=duration,
            )
            if start_pos != target_pos:
                self.timeline.add_tween(
                    target=state,
                    property_name="position",
                    end_value=target_pos,
                    duration=duration,
                    easing=get_easing("ease_out_quad"),
                )

    def hide_character(
        self,
        character_id: str,
        *,
        transition: str | TransitionKind = TransitionKind.FADE,
        duration: float = 0.3,
    ) -> None:
        """Fade out or remove a character from the stage."""
        found = self.stage.find_element(character_id)
        if found is None:
            return
        layer_name, elem = found
        target_layer = self.stage.get_layer(layer_name)
        if target_layer is None:
            return

        trans_kind = (
            TransitionKind.from_str(transition) if isinstance(transition, str) else transition
        )

        self.timeline.cancel_tweens_for(elem.state)

        if duration <= 0.0 or trans_kind == TransitionKind.CUT:
            target_layer.remove_element(character_id)
            return

        def _remove() -> None:
            target_layer.remove_element(character_id)

        self.timeline.add_tween(
            target=elem.state,
            property_name="opacity",
            end_value=0.0,
            duration=duration,
            on_complete=_remove,
        )

        # Optional slide out on exit
        if trans_kind == TransitionKind.SLIDE_LEFT:
            target_pos = elem.position - Vec2(300.0, 0.0)
            self.timeline.add_tween(
                target=elem.state,
                property_name="position",
                end_value=target_pos,
                duration=duration,
            )
        elif trans_kind == TransitionKind.SLIDE_RIGHT:
            target_pos = elem.position + Vec2(300.0, 0.0)
            self.timeline.add_tween(
                target=elem.state,
                property_name="position",
                end_value=target_pos,
                duration=duration,
            )

    def move_character(
        self,
        character_id: str,
        position: str | Vec2 | tuple[float, float],
        *,
        duration: float = 0.5,
        easing: str = "ease_in_out_quad",
    ) -> None:
        """Smoothly slide an existing character to a new stage position."""
        found = self.stage.find_element(character_id)
        if found is None:
            return
        _layer_name, elem = found

        target_pos = self.layout.resolve_position(position)
        self.timeline.cancel_tweens_for(elem.state, "position")

        if duration <= 0.0:
            elem.position = target_pos
            return

        self.timeline.add_tween(
            target=elem.state,
            property_name="position",
            end_value=target_pos,
            duration=duration,
            easing=get_easing(easing),
        )

    def set_expression(
        self,
        character_id: str,
        expression: str,
        *,
        asset_prefix: str | None = None,
    ) -> bool:
        """Update a character's expression if they are currently mounted on stage."""
        prefix = asset_prefix or character_id
        found = self.stage.find_element(character_id)
        if found is None:
            return False
        _layer_name, elem = found
        elem.asset_id = f"{prefix}/{expression}"
        return True

    # =========================================================================
    # Generic Element Operations
    # =========================================================================

    def show_element(
        self,
        layer: str,
        element_id: str,
        asset_id: str,
        *,
        position: str | Vec2 | tuple[float, float] = "center",
        anchor: Anchor = Anchor.CENTER,
        opacity: float = 1.0,
        duration: float = 0.0,
        z_index: int = 0,
        tint: Color = WHITE,
    ) -> None:
        """Add or show an arbitrary visual element on any layer."""
        st_layer = self.stage.get_or_create_layer(layer)
        pos = self.layout.resolve_position(position)

        elem = st_layer.get_element(element_id)
        if elem is None:
            state = ElementState(
                asset_id=asset_id,
                position=pos,
                anchor=anchor,
                opacity=0.0 if duration > 0.0 else opacity,
                tint=tint,
                z_index=z_index,
            )
            elem = StageElement(element_id=element_id, state=state)
            st_layer.add_element(elem)
        else:
            self.timeline.cancel_tweens_for(elem.state)
            elem.asset_id = asset_id
            elem.state.anchor = anchor
            elem.state.tint = tint
            if elem.state.z_index != z_index:
                elem.state.z_index = z_index
                st_layer.invalidate_sort_cache()

        if duration > 0.0:
            self.timeline.add_tween(
                target=elem.state,
                property_name="opacity",
                end_value=opacity,
                duration=duration,
            )
            if elem.position != pos:
                self.timeline.add_tween(
                    target=elem.state,
                    property_name="position",
                    end_value=pos,
                    duration=duration,
                )
        else:
            elem.position = pos
            elem.opacity = opacity

    def hide_element(
        self,
        layer: str,
        element_id: str,
        *,
        duration: float = 0.0,
    ) -> None:
        """Hide or remove an arbitrary element from a layer."""
        st_layer = self.stage.get_layer(layer)
        if st_layer is None:
            return

        elem = st_layer.get_element(element_id)
        if elem is None:
            return

        self.timeline.cancel_tweens_for(elem.state)

        if duration <= 0.0:
            st_layer.remove_element(element_id)
            return

        def _remove() -> None:
            st_layer.remove_element(element_id)

        self.timeline.add_tween(
            target=elem.state,
            property_name="opacity",
            end_value=0.0,
            duration=duration,
            on_complete=_remove,
        )

    # =========================================================================
    # Screen Transitions & Camera Effects
    # =========================================================================

    def fade_in(
        self,
        *,
        duration: float = 1.0,
        color: Color | None = None,
    ) -> None:
        """Fade in from a solid color overlay (default black) to reveal the stage."""
        overlay_layer = self.stage.get_or_create_layer("overlay", z_order=400)
        target_color = color if color is not None else BLACK
        fade_elem = overlay_layer.get_element("__screen_fade__")
        if fade_elem is None:
            state = ElementState(
                asset_id="__builtin_color_rect__",
                position=Vec2(0.0, 0.0),
                anchor=Anchor.TOP_LEFT,
                scale=Vec2(float(self.virtual_width), float(self.virtual_height)),
                opacity=1.0,
                tint=target_color,
                z_index=100,
            )
            fade_elem = StageElement("__screen_fade__", state)
            overlay_layer.add_element(fade_elem)
        else:
            fade_elem.opacity = 1.0
            fade_elem.state.tint = target_color

        def _cleanup() -> None:
            overlay_layer.remove_element("__screen_fade__")

        self.timeline.add_tween(
            target=fade_elem.state,
            property_name="opacity",
            end_value=0.0,
            duration=duration,
            on_complete=_cleanup,
        )

    def fade_out(
        self,
        *,
        duration: float = 1.0,
        color: Color | None = None,
    ) -> None:
        """Fade out the stage to a solid color (default black)."""
        overlay_layer = self.stage.get_or_create_layer("overlay", z_order=400)
        target_color = color if color is not None else BLACK
        fade_elem = overlay_layer.get_element("__screen_fade__")

        if fade_elem is None:
            state = ElementState(
                asset_id="__builtin_color_rect__",
                position=Vec2(0.0, 0.0),
                anchor=Anchor.TOP_LEFT,
                scale=Vec2(float(self.virtual_width), float(self.virtual_height)),
                opacity=0.0,
                tint=target_color,
                z_index=100,
            )
            fade_elem = StageElement("__screen_fade__", state)
            overlay_layer.add_element(fade_elem)
        else:
            fade_elem.state.tint = target_color

        self.timeline.add_tween(
            target=fade_elem.state,
            property_name="opacity",
            end_value=1.0,
            duration=duration,
        )

    def flash(
        self,
        *,
        duration: float = 0.15,
        color: Color | None = None,
    ) -> None:
        """Trigger an instant full-screen flash that quickly decays to transparent."""
        overlay_layer = self.stage.get_or_create_layer("overlay", z_order=400)
        existing_flash = overlay_layer.get_element("__screen_flash__")
        if existing_flash is not None:
            self.timeline.cancel_tweens_for(existing_flash.state)
        flash_color = color if color is not None else WHITE
        elem = StageElement(
            element_id="__screen_flash__",
            state=ElementState(
                asset_id="__builtin_color_rect__",
                position=Vec2(0.0, 0.0),
                anchor=Anchor.TOP_LEFT,
                scale=Vec2(float(self.virtual_width), float(self.virtual_height)),
                opacity=1.0,
                tint=flash_color,
                z_index=200,
            ),
        )
        overlay_layer.add_element(elem)

        def _cleanup() -> None:
            overlay_layer.remove_element("__screen_flash__")

        self.timeline.add_tween(
            target=elem.state,
            property_name="opacity",
            end_value=0.0,
            duration=duration,
            easing=get_easing("ease_out_quad"),
            on_complete=_cleanup,
        )

    def shake(self, *, intensity: float = 1.0, duration: float = 0.3) -> None:
        """Trigger a camera screen shake with smooth decay."""
        self._shake_intensity = max(0.0, intensity)
        self._shake_duration = max(0.0, duration)
        self._shake_elapsed = 0.0

    # =========================================================================
    # Lifecycle & Render Output
    # =========================================================================

    def update(self, dt: float) -> None:
        """Advance animations, camera shake, and stage timelines by dt seconds."""
        # 1. Update tweens
        self.timeline.update(dt)

        # 2. Update screen shake
        if self._shake_elapsed < self._shake_duration:
            self._shake_elapsed += dt
            decay = max(0.0, 1.0 - (self._shake_elapsed / self._shake_duration))
            amp = self._shake_intensity * 25.0 * decay
            # Damped sinusoidal shake frequencies
            ox = amp * math.sin(self._shake_elapsed * 60.0)
            oy = amp * math.cos(self._shake_elapsed * 45.0)
            self._shake_offset = Vec2(ox, oy)
        else:
            self._shake_offset = Vec2(0.0, 0.0)

    def step(self, dt: float = 1.0 / 60.0) -> None:
        """Advance the compositor by a single fixed-timestep frame."""
        self.update(dt)

    def render_list(self) -> list[RenderItem]:
        """Compute and yield an ordered list of RenderItems ready for drawing."""
        items: list[RenderItem] = []

        for layer in self.stage.get_sorted_layers():
            if not layer.visible or layer.opacity <= 0.0:
                continue

            apply_shake = layer.name not in self.shake_exempt_layers
            shake_ox = self._shake_offset.x if apply_shake else 0.0
            shake_oy = self._shake_offset.y if apply_shake else 0.0

            for elem in layer.get_sorted_elements():
                if not elem.visible or elem.opacity <= 0.0:
                    continue

                effective_opacity = max(0.0, min(1.0, elem.opacity * layer.opacity))
                pos_x = elem.position.x + shake_ox
                pos_y = elem.position.y + shake_oy

                global_z = layer.z_order * 1000 + elem.state.z_index

                item = RenderItem(
                    asset_id=elem.asset_id,
                    x=pos_x,
                    y=pos_y,
                    opacity=effective_opacity,
                    scale_x=elem.state.scale.x,
                    scale_y=elem.state.scale.y,
                    rotation=elem.state.rotation,
                    anchor=elem.state.anchor,
                    tint=elem.state.tint,
                    flip_h=elem.state.flip_h,
                    flip_v=elem.state.flip_v,
                    layer=layer.name,
                    z_order=global_z,
                )
                items.append(item)

        return items

    # =========================================================================
    # Snapshot & Serialization
    # =========================================================================

    def finish_animations(self) -> None:
        """Immediately complete all active timeline tweens."""
        self.timeline.finish_all()

    def save_state(self) -> dict[str, Any]:
        """Create a complete serializable snapshot of the visual stage state.

        Active animations are evaluated to their settled end states in the
        serialized snapshot so checkpoints and rollback do not store transitory
        mid-transition states, while live animations continue undisturbed.
        """
        stage_dict = self.stage.to_dict()
        if not self.timeline.has_tweens():
            return {
                "stage": stage_dict,
                "virtual_width": self.virtual_width,
                "virtual_height": self.virtual_height,
            }

        # Build mapping from ElementState id to (layer_name, element_id)
        state_map: dict[int, tuple[str, str]] = {}
        for layer_name, layer in self.stage.layers.items():
            for elem_id, elem in layer.elements.items():
                state_map[id(elem.state)] = (layer_name, elem_id)

        layers_dict: dict[str, Any] = stage_dict.get("layers", {})
        elements_to_remove: set[tuple[str, str]] = set()

        for t in self.timeline._tweens:
            target_key = state_map.get(id(t.target))
            if target_key is None:
                continue

            layer_name, elem_id = target_key
            layer_data = layers_dict.get(layer_name)
            if not layer_data:
                continue
            elements_data = layer_data.get("elements", {})
            elem_data = elements_data.get(elem_id)
            if not elem_data:
                continue

            elem_state_dict = elem_data.get("state", elem_data)

            # If tween ends with removal (e.g. hide_character, clear_background, or fade out with on_complete)
            if t.property_name == "opacity" and t.end_value == 0.0 and t.on_complete is not None:
                elements_to_remove.add((layer_name, elem_id))
                continue

            end_val = t.end_value
            if isinstance(end_val, (Vec2, Color)):
                elem_state_dict[t.property_name] = end_val.to_dict()
            else:
                elem_state_dict[t.property_name] = end_val

        # Handle background transition cleanup if an incoming background is present
        bg_layer_data = layers_dict.get("background")
        if bg_layer_data:
            bg_elements = bg_layer_data.get("elements", {})
            if "bg_incoming" in bg_elements:
                incoming_data = bg_elements.pop("bg_incoming")
                incoming_data["element_id"] = "bg_main"
                incoming_state = incoming_data.get("state", incoming_data)
                incoming_state["opacity"] = 1.0
                incoming_state["z_index"] = 0
                bg_elements.clear()
                bg_elements["bg_main"] = incoming_data

        # Remove elements scheduled for deletion upon tween completion
        for layer_name, elem_id in elements_to_remove:
            layer_data = layers_dict.get(layer_name)
            if layer_data and elem_id in layer_data.get("elements", {}):
                del layer_data["elements"][elem_id]

        return {
            "stage": stage_dict,
            "virtual_width": self.virtual_width,
            "virtual_height": self.virtual_height,
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore stage state exactly from a snapshot dictionary."""
        self.timeline.clear()
        self._shake_offset = Vec2(0.0, 0.0)
        self._shake_elapsed = 0.0
        self._shake_duration = 0.0

        if "stage" in state:
            self.stage = Stage.from_dict(state["stage"])
        if "virtual_width" in state:
            self.virtual_width = int(state["virtual_width"])
        if "virtual_height" in state:
            self.virtual_height = int(state["virtual_height"])

    def clear(self) -> None:
        """Clear all animations and reset all stage layers."""
        self.timeline.clear()
        self.stage.clear()
