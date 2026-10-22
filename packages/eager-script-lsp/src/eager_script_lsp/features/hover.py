"""Rich Markdown hover provider for scenes, characters, assets, and i18n previews."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager_runtime.i18n import compute_beat_id
from lsprotocol.types import (
    Hover,
    MarkupContent,
    MarkupKind,
    Position,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

HOOK_DOCS: dict[str, str] = {
    "bg": "**Engine Hook: `~ bg`**\n\nChanges the background image.\n\n*Usage:* `~ bg <image_id> [with <transition>] [duration=<seconds>]`",
    "bg_clear": "**Engine Hook: `~ bg_clear`**\n\nClears the active background.\n\n*Usage:* `~ bg_clear [with <transition>] [duration=<seconds>]`",
    "scene": "**Engine Hook: `~ scene`**\n\nClears all character sprites and sets a new background.\n\n*Usage:* `~ scene <image_id>`",
    "show": "**Engine Hook: `~ show`**\n\nDisplays a character sprite.\n\n*Usage:* `~ show <char_id> [<emotion>] [at <position>] [with <transition>] [duration=<seconds>]`",
    "hide": "**Engine Hook: `~ hide`**\n\nRemoves a character sprite from the stage.\n\n*Usage:* `~ hide <char_id> [with <transition>] [duration=<seconds>]`",
    "move": "**Engine Hook: `~ move`**\n\nAnimates a character sprite to a new stage position.\n\n*Usage:* `~ move <char_id> to <position> [duration=<seconds>] [easing=<func>]`",
    "expr": "**Engine Hook: `~ expr`**\n\nSwaps a character's facial expression sprite.\n\n*Usage:* `~ expr <char_id> <emotion>`",
    "play": "**Engine Hook: `~ play`**\n\nStarts playback of an audio track.\n\n*Usage:* `~ play [channel] <track> [fade=<seconds>] [volume=<float>] [loop=true/false]`",
    "stop": "**Engine Hook: `~ stop`**\n\nStops audio on a channel.\n\n*Usage:* `~ stop [channel] [fade=<seconds>]`",
    "fade_in": "**Engine Hook: `~ fade_in`**\n\nFades in the stage from black or a specified color.\n\n*Usage:* `~ fade_in [duration=<seconds>] [color=#hex]`",
    "fade_out": "**Engine Hook: `~ fade_out`**\n\nFades out the stage to a color.\n\n*Usage:* `~ fade_out [duration=<seconds>] [color=#hex]`",
    "flash": "**Engine Hook: `~ flash`**\n\nFlashes the screen with a color effect.\n\n*Usage:* `~ flash [duration=<seconds>] [color=#hex]`",
    "shake": "**Engine Hook: `~ shake`**\n\nCamera shake effect.\n\n*Usage:* `~ shake [duration=<seconds>] [intensity=<float>]`",
    "input": "**Engine Hook: `~ input`**\n\nPrompts the user to enter text and stores it in a variable.\n\n*Usage:* `~ input <variable_name>`",
}

FUNCTION_DOCS: dict[str, str] = {
    "visited": "**Built-in Function: `visited(scene_id)`**\n\nReturns `True` if `scene_id` was visited during the current story session.",
    "seen": "**Built-in Function: `seen(scene_id)`**\n\nReturns `True` if `scene_id` was ever visited across all playthroughs (persistent).",
    "random": "**Built-in Function: `random(a, b)`**\n\nReturns a pseudo-random integer between `a` and `b` inclusive.",
    "chance": "**Built-in Function: `chance(probability)`**\n\nReturns `True` with probability `p` (from `0.0` to `1.0`).",
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
    if token.kind in ("character_id", "character_name", "speaker"):
        char_id = token.value.lower()
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

    # 6. Asset hover (background, character emotion, voice, audio)
    if token.kind in ("hook_arg", "emotion", "voice_path"):
        asset_kind = token.metadata.get("asset_kind")
        disk_path = None
        if asset_kind == "background":
            disk_path = workspace.asset_index.file_paths.get(f"bg:{token.value}")
        elif asset_kind == "voice":
            disk_path = workspace.asset_index.file_paths.get(f"voice:{token.value}")
        elif asset_kind == "character" or token.kind == "emotion":
            char_id = token.metadata.get("character", "")
            expr = token.value.lower()
            disk_path = workspace.asset_index.file_paths.get(f"char:{char_id}/{expr}")
        elif asset_kind == "audio":
            disk_path = workspace.asset_index.file_paths.get(f"audio:{token.value}")

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
            beat_id = compute_beat_id(scene_id, item, occurrence=1)
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
