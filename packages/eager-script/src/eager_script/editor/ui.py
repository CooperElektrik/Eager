"""Terminal dialogs and modal overlays for the Eager-Script editor."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from eager_script.editor.outline import SceneEntry


def draw_box(
    term: Any,
    top: int,
    left: int,
    width: int,
    height: int,
    title: str = "",
    border_color: Any = None,
) -> None:
    """Draw a framed box on the terminal at (left, top)."""
    color = border_color or term.cyan
    inner_width = max(0, width - 2)

    # Top border
    if title:
        header = f"┤ {title} ├"
        pad = inner_width - len(header)
        left_pad = pad // 2
        right_pad = pad - left_pad
        top_line = "┌" + ("─" * left_pad) + header + ("─" * right_pad) + "┐"
    else:
        top_line = "┌" + ("─" * inner_width) + "┐"

    print(term.move_xy(left, top) + color(top_line), end="")

    # Middle empty lines
    for r in range(1, height - 1):
        line = "│" + (" " * inner_width) + "│"
        print(term.move_xy(left, top + r) + color(line), end="")

    # Bottom border
    bot_line = "└" + ("─" * inner_width) + "┘"
    print(term.move_xy(left, top + height - 1) + color(bot_line), end="")


def prompt_input(term: Any, title: str, prompt: str, default: str = "") -> str | None:
    """Show a modal input box. Returns entered string or None on cancel (Esc/Ctrl+C)."""
    val = default
    w = min(max(len(title) + 10, len(prompt) + 30, 50), term.width - 4)
    h = 5
    top = max(1, (term.height - h) // 2)
    left = max(1, (term.width - w) // 2)

    while True:
        draw_box(term, top, left, w, h, title=title, border_color=term.bold_cyan)

        # Prompt & input field
        content_y = top + 2
        field_w = w - 4 - len(prompt)
        displayed_val = val
        if len(displayed_val) > field_w:
            displayed_val = displayed_val[-(field_w - 1) :]

        line_str = f" {prompt}{term.bold_white(displayed_val)}{term.reverse(' ')}"
        padded = line_str + " " * max(0, w - 2 - term.length(line_str))
        print(term.move_xy(left + 1, content_y) + padded, end="", flush=True)

        key = term.inkey()
        name = getattr(key, "name", "") or ""
        k_str = str(key) if key is not None else ""

        if name in ("KEY_ESCAPE", "KEY_CTRL_C") or k_str in ("\x1b", "\x03"):
            return None
        elif name == "KEY_ENTER" or k_str in ("\r", "\n"):
            return val
        elif name in ("KEY_BACKSPACE", "KEY_DELETE") or k_str in ("\x7f", "\x08"):
            if val:
                val = val[:-1]
        elif not getattr(key, "is_sequence", False) and k_str and k_str >= " ":
            val += k_str


def confirm_dialog(term: Any, message: str) -> str:
    """Ask user to confirm an action. Returns 'y', 'n', or 'cancel'."""
    opts = " [y/n/Esc]"
    full_msg = message + opts
    w = min(max(len(full_msg) + 6, 40), term.width - 4)
    h = 5
    top = max(1, (term.height - h) // 2)
    left = max(1, (term.width - w) // 2)

    draw_box(term, top, left, w, h, title="Confirm", border_color=term.bold_yellow)
    msg_str = f" {message} " + term.bold_yellow("[y]es / [n]o / [Esc]ancel")
    pad = w - 2 - term.length(msg_str)
    if pad > 0:
        msg_str += " " * pad
    print(term.move_xy(left + 1, top + 2) + msg_str, end="", flush=True)

    while True:
        key = term.inkey()
        name = getattr(key, "name", "") or ""
        k_str = str(key) if key is not None else ""

        if name in ("KEY_ESCAPE", "KEY_CTRL_C") or k_str in ("\x1b", "\x03", "c", "C"):
            return "cancel"
        elif k_str in ("y", "Y"):
            return "y"
        elif k_str in ("n", "N"):
            return "n"


def outline_dialog(term: Any, scenes: Sequence[SceneEntry]) -> SceneEntry | None:
    """Show interactive modal list of screenplay scenes to jump to."""
    if not scenes:
        w = 40
        h = 5
        top = max(1, (term.height - h) // 2)
        left = max(1, (term.width - w) // 2)
        draw_box(term, top, left, w, h, title="Scene Outline", border_color=term.bold_yellow)
        msg = " No scene labels ('##') found."
        print(term.move_xy(left + 1, top + 2) + msg, end="", flush=True)
        term.inkey()
        return None

    selected_idx = 0
    filter_text = ""

    while True:
        filtered = [
            s
            for s in scenes
            if filter_text.lower() in s.display_name.lower()
            or filter_text.lower() in s.label_id.lower()
        ]
        if selected_idx >= len(filtered):
            selected_idx = max(0, len(filtered) - 1)

        w = min(70, term.width - 4)
        h = min(18, term.height - 4)
        top = max(1, (term.height - h) // 2)
        left = max(1, (term.width - w) // 2)

        title = "Scene Outline"
        if filter_text:
            title += f" (Filter: {filter_text})"
        draw_box(term, top, left, w, h, title=title, border_color=term.bold_magenta)

        list_h = h - 3
        scroll_offset = 0
        if selected_idx >= list_h:
            scroll_offset = selected_idx - list_h + 1

        for row in range(list_h):
            idx = scroll_offset + row
            y = top + 1 + row
            if idx < len(filtered):
                scene = filtered[idx]
                line_str = f" {scene.line_number:4d} │ {scene.display_name} ({scene.label_id})"
                avail = w - 4
                if len(line_str) > avail:
                    line_str = line_str[: avail - 1] + "…"
                else:
                    line_str = line_str + " " * (avail - len(line_str))

                if idx == selected_idx:
                    styled = term.reverse(term.bold_white(f" {line_str} "))
                else:
                    styled = term.cyan(f" {line_str} ")
                print(term.move_xy(left + 1, y) + styled, end="")
            else:
                print(term.move_xy(left + 1, y) + " " * (w - 2), end="")

        footer = " [↑/↓] Navigate  [Enter] Jump  [Esc] Close  Type to filter "
        print(
            term.move_xy(left + 2, top + h - 1) + term.bright_black(footer[: w - 4]),
            end="",
            flush=True,
        )

        key = term.inkey()
        name = getattr(key, "name", "") or ""
        k_str = str(key) if key is not None else ""

        if name in ("KEY_ESCAPE", "KEY_CTRL_C", "KEY_CTRL_O") or k_str in ("\x1b", "\x03", "\x0f"):
            return None
        elif name == "KEY_ENTER" or k_str in ("\r", "\n"):
            return filtered[selected_idx] if filtered else None
        elif name == "KEY_UP":
            if selected_idx > 0:
                selected_idx -= 1
        elif name == "KEY_DOWN":
            if selected_idx < len(filtered) - 1:
                selected_idx += 1
        elif name in ("KEY_BACKSPACE", "KEY_DELETE") or k_str in ("\x7f", "\x08"):
            if filter_text:
                filter_text = filter_text[:-1]
                selected_idx = 0
        elif not getattr(key, "is_sequence", False) and k_str and k_str >= " ":
            filter_text += k_str
            selected_idx = 0


def help_dialog(term: Any) -> None:
    """Show Eager-Script screenplay DSL and editor keyboard shortcuts reference."""
    help_lines = [
        ("KEYBOARD SHORTCUTS", True),
        ("  Ctrl+S          Save current screenplay", False),
        ("  Ctrl+Q / Ctrl+X Quit editor (prompts if unsaved changes exist)", False),
        ("  Ctrl+O / Ctrl+J Open Scene Outline (jump to scene/label)", False),
        ("  Ctrl+F / Ctrl+W Find text in script", False),
        ("  Ctrl+G          Go to specific line number", False),
        ("  Ctrl+Z          Undo edit", False),
        ("  Ctrl+Y / Ctrl+R Redo edit", False),
        ("  Ctrl+K / Ctrl+D Delete current line", False),
        ("  Ctrl+H / F1     Display this help screen", False),
        ("  Arrows/Home/End Navigation", False),
        ("", False),
        ("EAGER-SCRIPT SCREENPLAY DSL REFERENCE", True),
        ("  ## Scene Title --- id       Scene label with custom identifier", False),
        ("  ## Scene Title              Scene label with auto-slug identifier", False),
        ("  Speaker: Text               Character dialogue beat", False),
        ("  Speaker (emotion): Text     Dialogue with emotion tag", False),
        ("  Speaker: {voice:clip} Text  Dialogue with voice audio tag", False),
        ("  - Text                      Append text to current dialogue", False),
        ("  / Text                      Start fresh dialogue box", False),
        ("  Narration line              Speakerless narrative beat", False),
        ("  ? Option text (target_id)   Interactive choice branch", False),
        ("  > target_id                 Unconditional jump to label", False),
        ("  >> target_id                Call subroutine", False),
        ("  <<                          Return from subroutine", False),
        ("  ~ hook_name                 Trigger engine hook / SFX", False),
        ("  # Comment                   Standalone or inline comment", False),
        ("  \\symbol                     Escape DSL character", False),
    ]

    w = min(76, term.width - 4)
    h = min(22, term.height - 4)
    top = max(1, (term.height - h) // 2)
    left = max(1, (term.width - w) // 2)

    scroll = 0
    max_scroll = max(0, len(help_lines) - (h - 3))

    while True:
        draw_box(
            term,
            top,
            left,
            w,
            h,
            title="Eager-Script Editor Help & DSL Reference",
            border_color=term.bold_green,
        )

        visible_rows = h - 3
        for r in range(visible_rows):
            line_idx = scroll + r
            y = top + 1 + r
            if line_idx < len(help_lines):
                text, is_header = help_lines[line_idx]
                avail = w - 4
                padded = text[:avail].ljust(avail)
                if is_header:
                    styled = term.bold_yellow(f" {padded} ")
                else:
                    styled = term.white(f" {padded} ")
                print(term.move_xy(left + 1, y) + styled, end="")
            else:
                print(term.move_xy(left + 1, y) + " " * (w - 2), end="")

        footer = " [↑/↓/PgUp/PgDn] Scroll  [Esc/Enter/q] Close "
        print(
            term.move_xy(left + 2, top + h - 1) + term.bright_black(footer[: w - 4]),
            end="",
            flush=True,
        )

        key = term.inkey()
        name = getattr(key, "name", "") or ""
        k_str = str(key) if key is not None else ""

        if name in ("KEY_ESCAPE", "KEY_CTRL_C", "KEY_ENTER", "KEY_F1") or k_str in (
            "\x1b",
            "\x03",
            "\r",
            "\n",
            "q",
            "Q",
        ):
            break
        elif name == "KEY_UP":
            if scroll > 0:
                scroll -= 1
        elif name == "KEY_DOWN":
            if scroll < max_scroll:
                scroll += 1
        elif name == "KEY_PGUP":
            scroll = max(0, scroll - 10)
        elif name == "KEY_PGDOWN":
            scroll = min(max_scroll, scroll + 10)
