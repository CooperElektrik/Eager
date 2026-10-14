"""Syntax highlighter for Eager-Script screenplay DSL scripts using Blessed formatting."""

from __future__ import annotations

import re
from typing import Any

from eager_script import CHOICE_PATTERN, SPEAKER_PATTERN, VOICE_PATTERN

COMMENT_RE = re.compile(r"(?<!\\)\s+#.*$")


class EagerSHighlighter:
    """Applies ANSI styling to Eager-Script script lines using Blessed Terminal capabilities."""

    def __init__(self, term: Any) -> None:
        self.term = term

    def highlight_line(self, line: str) -> str:
        """Highlight a single line of Eager-Script screenplay text."""
        t = self.term

        # Check for full-line comment
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("##"):
            return t.bright_black(line)

        # Check for inline comment
        comment_match = COMMENT_RE.search(line)
        inline_comment = ""
        main_content = line
        if comment_match:
            start = comment_match.start()
            main_content = line[:start]
            inline_comment = t.bright_black(line[start:])

        leading_spaces_len = len(main_content) - len(main_content.lstrip())
        leading = main_content[:leading_spaces_len]
        trimmed = main_content[leading_spaces_len:]

        highlighted_body = self._highlight_content(trimmed)
        return leading + highlighted_body + inline_comment

    def _highlight_content(self, text: str) -> str:
        t = self.term
        if not text:
            return ""

        # Scene label: ## Title --- id or ## Title
        if text.startswith("##"):
            return self._highlight_label(text)

        # Subroutine call: >> target
        if text.startswith(">>"):
            prefix = t.bold_blue(">>")
            target = text[2:]
            return prefix + t.blue(target)

        # Subroutine return: <<
        if text.startswith("<<"):
            return t.bold_blue("<<") + t.blue(text[2:])

        # Unconditional jump: > target
        if text.startswith(">"):
            prefix = t.bold_red(">")
            target = text[1:]
            return prefix + t.red(target)

        # Hook: ~ hook_name
        if text.startswith("~"):
            prefix = t.bold_magenta("~")
            hook = text[1:]
            return prefix + t.magenta(hook)

        # Variable mutation: $ var = expr
        if text.startswith("$"):
            return t.bold_yellow("$") + t.yellow(text[1:])

        # Directives: @default, @character, @if, @elif, @else, @end
        if text.startswith("@"):
            parts = text.split(None, 1)
            directive = parts[0]
            rest = (" " + parts[1]) if len(parts) > 1 else ""
            return t.bold_cyan(directive) + t.cyan(rest)

        # Choice: ? Option (target)
        if text.startswith("?"):
            return self._highlight_choice(text)

        # Append beat: - Text
        if text.startswith("-"):
            return t.bold_green("-") + t.white(text[1:])

        # Fresh box beat: / Text
        if text.startswith("/"):
            return t.bold_cyan("/") + t.white(text[1:])

        # Dialogue beat: Speaker (emotion): Text or Speaker: Text
        if ":" in text:
            dialogue = self._highlight_dialogue(text)
            if dialogue is not None:
                return dialogue

        # Narration (speakerless text)
        return t.white(text)

    def _highlight_label(self, text: str) -> str:
        t = self.term
        prefix = text[:2]
        rest = text[2:]
        leading_len = len(rest) - len(rest.lstrip())
        leading_space = rest[:leading_len]
        body = rest[leading_len:]

        if "---" in body:
            display, label_id = body.split("---", 1)
            disp_strip = display.rstrip()
            disp_trail = display[len(disp_strip) :]
            id_lead = label_id[: len(label_id) - len(label_id.lstrip())]
            id_strip = label_id.strip()
            return (
                t.bold_magenta(prefix)
                + leading_space
                + t.bold_white(disp_strip)
                + disp_trail
                + t.bright_black("---")
                + id_lead
                + t.bold_cyan(id_strip)
            )
        return t.bold_magenta(prefix) + leading_space + t.bold_white(body)

    def _highlight_choice(self, text: str) -> str:
        t = self.term
        match = CHOICE_PATTERN.match(text)
        if match:
            opt_text = match.group(1)
            target = match.group(2)
            prefix_end = text.index(opt_text)
            q_mark = text[0]
            spaces = text[1:prefix_end]
            return (
                t.bold_green(q_mark)
                + spaces
                + t.green(opt_text)
                + t.white(" (")
                + t.bold_cyan(target)
                + t.white(")")
            )
        # Malformed choice, highlight prefix green
        return t.bold_green("?") + t.white(text[1:])

    def _highlight_dialogue(self, text: str) -> str | None:
        t = self.term
        match = SPEAKER_PATTERN.match(text)
        if not match:
            return None

        speaker, emotion, raw_text = match.groups()
        if raw_text is None:
            raw_text = ""

        # Rebuild formatted string
        res = t.bold_yellow(speaker)
        if emotion:
            res += t.bright_black(" (") + t.cyan(emotion) + t.bright_black(")")
        res += t.bold_yellow(":")

        if not raw_text:
            return res

        # Check for voice tag in raw_text
        content = raw_text
        res += " "
        voice_match = VOICE_PATTERN.match(content)
        if voice_match:
            voice_clip = f"{{voice:{voice_match.group(1)}}}"
            trailing_len = voice_match.end() - len(voice_clip)
            trailing_spaces = " " * trailing_len
            content = content[voice_match.end() :]
            res += t.magenta(voice_clip) + trailing_spaces

        res += t.white(content)
        return res
