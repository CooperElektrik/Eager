"""Rich Markdown hover provider for scenes, characters, assets, and i18n previews."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.core.i18n import compute_beat_id
from lsprotocol.types import (
    Hover,
    MarkupContent,
    MarkupKind,
    Position,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

__all__ = [
    "FUNCTION_DOCS",
    "HOOK_DOCS",
    "compute_hover",
]

HOOK_DOCS: dict[str, str] = {
    "bg": "**Engine Hook: `~ bg`**\n\nChanges the background image.\n\n*Usage:* `~ bg <image_id> [with <transition>] [duration=<seconds>]`",
    "bg_clear": "**Engine Hook: `~ bg_clear`**\n\nClears the active background.\n\n*Usage:* `~ bg_clear [with <transition>] [duration=<seconds>]`",
    "scene": "**Engine Hook: `~ scene`**\n\nClears all character sprites and sets a new background.\n\n*Usage:* `~ scene <image_id>`",
    "show": "**Engine Hook: `~ show`**\n\nDisplays a character sprite.\n\n*Usage:* `~ show <char_id> [<emotion>] [at <position>] [with <transition>] [duration=<seconds>]`",
    "hide": "**Engine Hook: `~ hide`**\n\nRemoves a character sprite from the stage.\n\n*Usage:* `~ hide <char_id> [with <transition>] [duration=<seconds>]`",
    "move": "**Engine Hook: `~ move`**\n\nAnimates a character sprite to a new stage position.\n\n*Usage:* `~ move <char_id> to <position> [duration=<seconds>] [easing=<func>]`",
    "expr": "**Engine Hook: `~ expr`**\n\nSwaps a character's facial expression sprite.\n\n*Usage:* `~ expr <char_id> <emotion>`",
    "image": "**Engine Hook: `~ image`**\n\nDisplays an arbitrary image element on a stage layer.\n\n*Usage:* `~ image <name> <asset> [at <pos>] [z=<z>] [opacity=<float>] [duration=<seconds>] [tint=#hex]`",
    "hide_image": "**Engine Hook: `~ hide_image`**\n\nRemoves an arbitrary image element from a stage layer.\n\n*Usage:* `~ hide_image <name> [duration=<seconds>] [layer=<layer>]`",
    "hide_element": "**Engine Hook: `~ hide_element`**\n\nRemoves a named element from a specific layer.\n\n*Usage:* `~ hide_element [layer] <name> [duration=<seconds>]`",
    "scene_bg": "**Engine Hook: `~ scene_bg`**\n\nMaps a scene ID to automatically change the background upon entry.\n\n*Usage:* `~ scene_bg <scene_id> <asset> [with <transition>] [duration=<seconds>]`",
    "speaker_highlight": "**Engine Hook: `~ speaker_highlight`**\n\nConfigures automatic active speaker dimming and sprite popping.\n\n*Usage:* `~ speaker_highlight [on/off] [dim=#hex] [duration=<seconds>] [scale=<float>] [hop=<float>]`",
    "play": "**Engine Hook: `~ play`**\n\nStarts playback of an audio track.\n\n*Usage:* `~ play [channel] <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "queue": "**Engine Hook: `~ queue`**\n\nQueues an audio track to play immediately after the current playback finishes.\n\n*Usage:* `~ queue [channel] <track>`",
    "pause": "**Engine Hook: `~ pause`**\n\nPauses active playback on a channel or all channels.\n\n*Usage:* `~ pause [channel]`",
    "resume": "**Engine Hook: `~ resume`**\n\nResumes paused playback on a channel or all channels.\n\n*Usage:* `~ resume [channel]`",
    "queue_bgm": "**Engine Hook: `~ queue_bgm`**\n\nQueues a background music track on the music channel.\n\n*Usage:* `~ queue_bgm <track>`",
    "queue_music": "**Engine Hook: `~ queue_music`**\n\nQueues a music track on the music channel.\n\n*Usage:* `~ queue_music <track>`",
    "queue_sound": "**Engine Hook: `~ queue_sound`**\n\nQueues a sound effect on the sound channel.\n\n*Usage:* `~ queue_sound <track>`",
    "queue_sfx": "**Engine Hook: `~ queue_sfx`**\n\nQueues a sound effect on the sound channel.\n\n*Usage:* `~ queue_sfx <track>`",
    "queue_voice": "**Engine Hook: `~ queue_voice`**\n\nQueues a voice clip on the voice channel.\n\n*Usage:* `~ queue_voice <track>`",
    "pause_bgm": "**Engine Hook: `~ pause_bgm`**\n\nPauses background music playback.\n\n*Usage:* `~ pause_bgm`",
    "pause_music": "**Engine Hook: `~ pause_music`**\n\nPauses music channel playback.\n\n*Usage:* `~ pause_music`",
    "pause_sound": "**Engine Hook: `~ pause_sound`**\n\nPauses sound effect playback.\n\n*Usage:* `~ pause_sound`",
    "pause_sfx": "**Engine Hook: `~ pause_sfx`**\n\nPauses sound effect playback.\n\n*Usage:* `~ pause_sfx`",
    "pause_voice": "**Engine Hook: `~ pause_voice`**\n\nPauses voice playback.\n\n*Usage:* `~ pause_voice`",
    "resume_bgm": "**Engine Hook: `~ resume_bgm`**\n\nResumes background music playback.\n\n*Usage:* `~ resume_bgm`",
    "resume_music": "**Engine Hook: `~ resume_music`**\n\nResumes music channel playback.\n\n*Usage:* `~ resume_music`",
    "resume_sound": "**Engine Hook: `~ resume_sound`**\n\nResumes sound effect playback.\n\n*Usage:* `~ resume_sound`",
    "resume_sfx": "**Engine Hook: `~ resume_sfx`**\n\nResumes sound effect playback.\n\n*Usage:* `~ resume_sfx`",
    "resume_voice": "**Engine Hook: `~ resume_voice`**\n\nResumes voice playback.\n\n*Usage:* `~ resume_voice`",
    "stop": "**Engine Hook: `~ stop`**\n\nStops audio on a channel.\n\n*Usage:* `~ stop [channel] [fade=<seconds>]`",
    "fade_in": "**Engine Hook: `~ fade_in`**\n\nFades in the stage from black or a specified color.\n\n*Usage:* `~ fade_in [duration=<seconds>] [color=#hex]`",
    "fade_out": "**Engine Hook: `~ fade_out`**\n\nFades out the stage to a color.\n\n*Usage:* `~ fade_out [duration=<seconds>] [color=#hex]`",
    "flash": "**Engine Hook: `~ flash`**\n\nFlashes the screen with a color effect.\n\n*Usage:* `~ flash [duration=<seconds>] [color=#hex]`",
    "shake": "**Engine Hook: `~ shake`**\n\nCamera shake effect.\n\n*Usage:* `~ shake [duration=<seconds>] [intensity=<float>]`",
    "weather": "**Engine Hook: `~ weather`**\n\nSimulates a weather particle effect (rain, snow, sakura, embers, clear).\n\n*Usage:* `~ weather <preset> [count=<int>]`",
    "particles": "**Engine Hook: `~ particles`**\n\nSimulates a particle effect preset or clears active emitters.\n\n*Usage:* `~ particles <preset> [count=<int>]`",
    "ambient": "**Engine Hook: `~ ambient`**\n\nSets ambient stage lighting color and intensity.\n\n*Usage:* `~ ambient <#hex|clear> [intensity=<float>]`",
    "light": "**Engine Hook: `~ light`**\n\nAdds or clears dynamic stage point lights.\n\n*Usage:* `~ light add x=<x> y=<y> radius=<r> [color=#hex] [intensity=<float>] [mode=multiply/screen]`",
    "play_bgm": "**Engine Hook: `~ play_bgm`**\n\nPlays a background music track.\n\n*Usage:* `~ play_bgm <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "play_music": "**Engine Hook: `~ play_music`**\n\nPlays a music track.\n\n*Usage:* `~ play_music <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "play_sound": "**Engine Hook: `~ play_sound`**\n\nPlays a sound effect.\n\n*Usage:* `~ play_sound <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "play_sfx": "**Engine Hook: `~ play_sfx`**\n\nPlays a sound effect.\n\n*Usage:* `~ play_sfx <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "play_voice": "**Engine Hook: `~ play_voice`**\n\nPlays a voice clip.\n\n*Usage:* `~ play_voice <track> [volume=<float>]`",
    "stop_bgm": "**Engine Hook: `~ stop_bgm`**\n\nStops background music playback.\n\n*Usage:* `~ stop_bgm [fade=<seconds>]`",
    "stop_music": "**Engine Hook: `~ stop_music`**\n\nStops music playback.\n\n*Usage:* `~ stop_music [fade=<seconds>]`",
    "stop_sound": "**Engine Hook: `~ stop_sound`**\n\nStops sound effect playback.\n\n*Usage:* `~ stop_sound [fade=<seconds>]`",
    "stop_sfx": "**Engine Hook: `~ stop_sfx`**\n\nStops sound effect playback.\n\n*Usage:* `~ stop_sfx [fade=<seconds>]`",
    "stop_voice": "**Engine Hook: `~ stop_voice`**\n\nStops voice playback.\n\n*Usage:* `~ stop_voice [fade=<seconds>]`",
    "play_ambient": "**Engine Hook: `~ play_ambient`**\n\nPlays an ambient audio loop.\n\n*Usage:* `~ play_ambient <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "stop_ambient": "**Engine Hook: `~ stop_ambient`**\n\nStops ambient audio playback.\n\n*Usage:* `~ stop_ambient [fade=<seconds>]`",
    "queue_ambient": "**Engine Hook: `~ queue_ambient`**\n\nQueues an ambient audio track.\n\n*Usage:* `~ queue_ambient <track>`",
    "pause_ambient": "**Engine Hook: `~ pause_ambient`**\n\nPauses ambient audio playback.\n\n*Usage:* `~ pause_ambient`",
    "resume_ambient": "**Engine Hook: `~ resume_ambient`**\n\nResumes ambient audio playback.\n\n*Usage:* `~ resume_ambient`",
    "volume": "**Engine Hook: `~ volume`**\n\nSets the volume for an audio channel or master.\n\n*Usage:* `~ volume <channel|master> <level>`",
    "volume_bgm": "**Engine Hook: `~ volume_bgm`**\n\nSets the music channel volume.\n\n*Usage:* `~ volume_bgm <level>`",
    "volume_music": "**Engine Hook: `~ volume_music`**\n\nSets the music channel volume.\n\n*Usage:* `~ volume_music <level>`",
    "volume_sound": "**Engine Hook: `~ volume_sound`**\n\nSets the sound effect channel volume.\n\n*Usage:* `~ volume_sound <level>`",
    "volume_sfx": "**Engine Hook: `~ volume_sfx`**\n\nSets the sound effect channel volume.\n\n*Usage:* `~ volume_sfx <level>`",
    "volume_voice": "**Engine Hook: `~ volume_voice`**\n\nSets the voice channel volume.\n\n*Usage:* `~ volume_voice <level>`",
    "volume_ambient": "**Engine Hook: `~ volume_ambient`**\n\nSets the ambient channel volume.\n\n*Usage:* `~ volume_ambient <level>`",
    "nvl": "**Engine Hook: `~ nvl`**\n\nToggles NVL full-screen narrative mode.\n\n*Usage:* `~ nvl [on|off]`",
    "nvl_clear": "**Engine Hook: `~ nvl_clear`**\n\nClears all accumulated entries in the NVL mode buffer.\n\n*Usage:* `~ nvl_clear`",
    "input": "**Engine Hook: `~ input`**\n\nPrompts the user to enter text and stores it in a variable.\n\n*Usage:* `~ input <variable_name>`",
}

FUNCTION_DOCS: dict[str, str] = {
    "visited": "**Built-in Function: `visited(scene_id)`**\n\nReturns `True` if `scene_id` was visited during the current story session.",
    "seen": "**Built-in Function: `seen(scene_id)`**\n\nReturns `True` if `scene_id` was ever visited across all playthroughs (persistent).",
    "random": "**Built-in Function: `random(a, b)`**\n\nReturns a pseudo-random integer between `a` and `b` inclusive.",
    "chance": "**Built-in Function: `chance(probability)`**\n\nReturns `True` with probability `p` (from `0.0` to `1.0`).",
    "min": "**Built-in Function: `min(a, b)`**\n\nReturns the smaller of two numbers.",
    "max": "**Built-in Function: `max(a, b)`**\n\nReturns the larger of two numbers.",
    "abs": "**Built-in Function: `abs(x)`**\n\nReturns the absolute value of `x`.",
    "len": "**Built-in Function: `len(x)`**\n\nReturns the length of a string.",
    "int": "**Built-in Function: `int(x)`**\n\nConverts `x` to an integer.",
    "str": "**Built-in Function: `str(x)`**\n\nConverts `x` to a string.",
    "round": "**Built-in Function: `round(x)`**\n\nReturns `x` rounded to the nearest integer.",
}


def compute_hover(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
) -> Hover | None:
    """Provide rich Markdown hover information at position."""
    token = doc.get_token_at(position.line, position.character)
    if token is None:
        return None

    # 1. Scene label or jump/call target
    if token.kind in ("label_id", "label_title", "jump_target", "call_target", "choice_target", "label_ref"):
        scene_id = token.metadata.get("scene_id", token.value) if token.metadata else token.value
        sym = workspace.get_scene(scene_id)
        if sym is not None:
            md_lines: list[str] = [
                f"### Scene: `{sym.display_name}` (`{sym.id}`)",
                f"**Location:** `{sym.uri}`",
            ]
            if sym.docstring:
                md_lines.append(f"> {sym.docstring}\n")

            in_count = len(sym.predecessors)
            out_count = len(sym.successors)
            md_lines.append(f"**Topology:** {in_count} incoming · {out_count} outgoing transitions")

            if sym.first_lines:
                md_lines.append("\n**Dialogue Preview:**")
                for line in sym.first_lines:
                    md_lines.append(f"- *{line}*")

            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value="\n".join(md_lines)),
                range=token.range,
            )

    # 2. Character definition or speaker
    if token.kind in ("character_id", "character_name", "speaker") or (
        token.kind == "hook_arg" and token.metadata.get("character")
    ):
        char_id = (token.metadata.get("character") or token.value).lower()
        char_sym = workspace.get_character(char_id)
        if char_sym is not None:
            md_lines = [
                f"### Character: `{char_sym.name}` (`{char_sym.id}`)",
                f"- **Lines spoken:** {char_sym.dialogue_lines}",
            ]
            if char_sym.attrs:
                md_lines.append("- **Attributes:**")
                for k, v in char_sym.attrs.items():
                    if k == "color" and v.startswith("#"):
                        md_lines.append(f"  - `{k}`: `{v}` 🎨")
                    else:
                        md_lines.append(f"  - `{k}`: `{v}`")

            # Available expression sprites on disk
            sprites = workspace.asset_index.characters.get(char_id)
            if sprites:
                md_lines.append(f"- **Sprite expressions:** {', '.join(sorted(sprites))}")

            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value="\n".join(md_lines)),
                range=token.range,
            )

    # 3. Variable definition or read/mutation
    if token.kind == "variable":
        var_name = token.value
        var_sym = workspace.get_variable(var_name)
        if var_sym is not None:
            md_lines = [
                f"### Variable: `${var_name}`",
                f"- **Initial default:** `{var_sym.default_val or 'undefined'}`",
                f"- **Mutations:** {len(var_sym.mutations)} site(s)",
                f"- **Reads:** {len(var_sym.reads)} site(s)",
            ]
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value="\n".join(md_lines)),
                range=token.range,
            )

    # 4. Engine hook documentation
    if token.kind == "hook_name":
        doc_text = HOOK_DOCS.get(token.value)
        if doc_text:
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value=doc_text),
                range=token.range,
            )

    # 5. Built-in expression function documentation
    if token.value in FUNCTION_DOCS:
        return Hover(
            contents=MarkupContent(kind=MarkupKind.Markdown, value=FUNCTION_DOCS[token.value]),
            range=token.range,
        )

    # 6. Asset hover (background, image, character emotion, voice, audio)
    if token.kind in ("hook_arg", "emotion", "voice_path"):
        asset_kind = token.metadata.get("asset_kind")
        if asset_kind is None and token.kind == "emotion":
            asset_kind = "character"
        disk_path = workspace.asset_index.resolve_asset_path(
            asset_kind,
            token.value,
            character=token.metadata.get("character", ""),
        )

        if disk_path is not None and disk_path.is_file():
            md_lines = [
                f"### Asset: `{token.value}`",
                f"- **File:** `{disk_path.as_posix()}`",
                f"- **Size:** {disk_path.stat().st_size:,} bytes",
            ]
            # Try to get image dimensions with PIL
            if disk_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    from PIL import Image
                    with Image.open(disk_path) as im:
                        md_lines.append(f"- **Dimensions:** {im.width}×{im.height} px")
                    md_lines.append(f"\n![preview]({disk_path.as_uri()})")
                except (ImportError, OSError, ValueError):
                    pass

            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value="\n".join(md_lines)),
                range=token.range,
            )

    # 7. Dialogue line (i18n translation table preview)
    if token.kind in ("dialogue_text", "speaker"):
        item = doc.get_item_at_line(position.line)
        scene_id = doc.get_scene_at_line(position.line)
        if item is not None and scene_id is not None and workspace.translation_catalogs:
            occ = doc.get_beat_occurrence(position.line)
            beat_id = compute_beat_id(scene_id, item, occurrence=occ)
            md_lines = [
                f"### Localization: `{beat_id}`",
                "\n| Locale | Translation |",
                "|:---|:---|",
            ]
            for loc_code, cat in sorted(workspace.translation_catalogs.items()):
                trans = cat.strings.get(beat_id, "*(missing)*")
                md_lines.append(f"| **{loc_code}** | {trans} |")

            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value="\n".join(md_lines)),
                range=token.range,
            )

    return None
