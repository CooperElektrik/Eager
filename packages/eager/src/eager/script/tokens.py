"""Lexical token spans and shared comment/tokenization helpers for Eager-Script."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from eager.script.ast import ParsedItem

_CALL_FUNC_PATTERN = re.compile(r"\b(visited|seen)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_VAR_INTERPOLATION_PATTERN = re.compile(r"\[([A-Za-z_][A-Za-z0-9_\.]*)\]")
_TAG_PATTERN = re.compile(r"\{([^\}]+)\}")
_VOICE_TAG_PATTERN = re.compile(r"\{voice:([^}]+)\}")
_COLOR_TAG_PATTERN = re.compile(r"\{color=(#[0-9a-fA-F]{3,8})\}")
_BEAT_ID_TAG_PATTERN = re.compile(r"\{id=([a-zA-Z0-9_-]+)\}")
_TOKEN_PATTERN = re.compile(r'"([^"]*)"|\'([^\']*)\'|(\S+)')
_STRING_LITERAL_PATTERN = re.compile(r"(\"[^\"]*\"|'[^']*')")
_IDENT_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b")

_BUILTIN_FUNCS = frozenset(
    {"visited", "seen", "random", "chance", "min", "max", "abs", "len", "int", "str", "round"}
)
_EXPR_KEYWORDS = frozenset({"True", "False", "None", "and", "or", "not", "is", "in", "persistent"})
_AUDIO_CHANNELS = frozenset({"bgm", "music", "sound", "sfx", "voice", "ambient"})


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """A range within a screenplay document associated with a semantic token or syntax element."""

    kind: str
    start_line: int  # 0-based
    start_col: int  # 0-based
    end_line: int  # 0-based
    end_col: int  # 0-based
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def contains_position(self, line: int, col: int) -> bool:
        """Return True if (line, col) falls inside this span."""
        if line < self.start_line or line > self.end_line:
            return False
        if line == self.start_line and col < self.start_col:
            return False
        return not (line == self.end_line and col > self.end_col)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Combined AST items and token spans produced by parsing a screenplay."""

    items: list[ParsedItem]
    spans: list[TokenSpan]


def _has_closing_quote(text: str, start_idx: int, quote_char: str) -> bool:
    """Return True if an unescaped matching quote_char appears after start_idx."""
    idx = start_idx + 1
    while idx < len(text):
        if text[idx] == quote_char and text[idx - 1] != "\\":
            return True
        idx += 1
    return False


def strip_inline_comment(raw_line: str) -> tuple[str, int | None]:
    """Split a raw source line into ``(content_line, comment_start_col)``.

    Handles standalone ``#`` comments (excluding ``##`` labels) and inline ``#``
    comments while ignoring ``#`` inside quoted strings, escaped ``\\#``, and
    non-comment hashes like ``#1`` or ``#ff0000``.
    """
    if "#" not in raw_line:
        return raw_line, None

    stripped = raw_line.lstrip(" \t")
    if stripped.startswith("#") and not stripped.startswith("##"):
        return "", len(raw_line) - len(stripped)

    in_quote: str | None = None
    line_len = len(raw_line)
    for idx, ch in enumerate(raw_line):
        if ch in ('"', "'") and (idx == 0 or raw_line[idx - 1] != "\\"):
            if in_quote == ch:
                in_quote = None
            elif in_quote is None:
                # Treat apostrophes inside words (e.g. "It's") as non-quote characters.
                if (
                    ch == "'"
                    and idx > 0
                    and raw_line[idx - 1].isalnum()
                    and idx + 1 < line_len
                    and raw_line[idx + 1].isalnum()
                ):
                    continue
                if _has_closing_quote(raw_line, idx, ch):
                    in_quote = ch
        elif (
            ch == "#"
            and in_quote is None
            and idx > 0
            and raw_line[idx - 1] in (" ", "\t")
            and (idx < 2 or raw_line[idx - 2] != "\\")
            and (idx + 1 == line_len or raw_line[idx + 1] in (" ", "\t"))
        ):
            return raw_line[:idx].rstrip(), idx

    return raw_line, None


def emit_inline_text_spans(
    spans: list[TokenSpan], line_idx: int, text: str, text_start_col: int
) -> None:
    """Emit TokenSpans for inline voice tags, beat IDs, colors, text tags, and interpolations."""
    for m in _VOICE_TAG_PATTERN.finditer(text):
        v_start = text_start_col + m.start()
        v_end = text_start_col + m.end()
        path = m.group(1).strip()
        path_start = text_start_col + m.start(1)
        spans.append(
            TokenSpan(
                kind="voice_tag",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=m.group(0),
            )
        )
        spans.append(
            TokenSpan(
                kind="voice_path",
                start_line=line_idx,
                start_col=path_start,
                end_line=line_idx,
                end_col=path_start + len(path),
                value=path,
                metadata={"asset_kind": "voice"},
            )
        )

    for m in _BEAT_ID_TAG_PATTERN.finditer(text):
        spans.append(
            TokenSpan(
                kind="beat_id_tag",
                start_line=line_idx,
                start_col=text_start_col + m.start(),
                end_line=line_idx,
                end_col=text_start_col + m.end(),
                value=m.group(1),
            )
        )

    for m in _COLOR_TAG_PATTERN.finditer(text):
        color_hex = m.group(1)
        c_start = text_start_col + m.start(1)
        spans.append(
            TokenSpan(
                kind="color_literal",
                start_line=line_idx,
                start_col=c_start,
                end_line=line_idx,
                end_col=c_start + len(color_hex),
                value=color_hex,
            )
        )

    for m in _TAG_PATTERN.finditer(text):
        full_tag = m.group(0)
        if full_tag.startswith(("{voice:", "{id=", "{color=")):
            continue
        spans.append(
            TokenSpan(
                kind="text_tag",
                start_line=line_idx,
                start_col=text_start_col + m.start(),
                end_line=line_idx,
                end_col=text_start_col + m.end(),
                value=full_tag,
            )
        )

    for m in _VAR_INTERPOLATION_PATTERN.finditer(text):
        spans.append(
            TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=text_start_col + m.start(1),
                end_line=line_idx,
                end_col=text_start_col + m.end(1),
                value=m.group(1),
                metadata={"role": "read"},
            )
        )


def emit_expression_spans(
    spans: list[TokenSpan], line_idx: int, expr_str: str, expr_start_col: int
) -> None:
    """Emit TokenSpans for scene label refs, built-in functions, and variable reads."""
    for m in _CALL_FUNC_PATTERN.finditer(expr_str):
        target = m.group(2)
        t_start = expr_start_col + m.start(2)
        spans.append(
            TokenSpan(
                kind="label_ref",
                start_line=line_idx,
                start_col=t_start,
                end_line=line_idx,
                end_col=t_start + len(target),
                value=target,
            )
        )

    clean_expr = _STRING_LITERAL_PATTERN.sub(lambda m: " " * len(m.group(0)), expr_str)
    for m in _IDENT_PATTERN.finditer(clean_expr):
        ident = m.group(1)
        i_start = expr_start_col + m.start(1)
        i_end = expr_start_col + m.end(1)
        if ident in _BUILTIN_FUNCS:
            spans.append(
                TokenSpan(
                    kind="builtin_func",
                    start_line=line_idx,
                    start_col=i_start,
                    end_line=line_idx,
                    end_col=i_end,
                    value=ident,
                )
            )
            continue
        if ident in _EXPR_KEYWORDS:
            continue
        spans.append(
            TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=i_start,
                end_line=line_idx,
                end_col=i_end,
                value=ident,
                metadata={"role": "read"},
            )
        )


def emit_hook_spans(
    spans: list[TokenSpan], line_idx: int, content_line: str, hook_start_offset: int
) -> None:
    """Emit TokenSpans for a hook invocation and its positional/keyword arguments."""
    raw_tokens: list[tuple[str, int, int]] = []
    for m in _TOKEN_PATTERN.finditer(content_line[hook_start_offset:]):
        val = m.group(1) or m.group(2) or m.group(3)
        raw_tokens.append((val, hook_start_offset + m.start(), hook_start_offset + m.end()))

    if not raw_tokens:
        return

    hook_name, h_start, h_end = raw_tokens[0]
    spans.append(
        TokenSpan(
            kind="hook_name",
            start_line=line_idx,
            start_col=h_start,
            end_line=line_idx,
            end_col=h_end,
            value=hook_name,
        )
    )

    arg_tokens = raw_tokens[1:]
    if hook_name in ("bg", "scene"):
        if arg_tokens:
            bg_name, b_start, b_end = arg_tokens[0]
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=b_start,
                    end_line=line_idx,
                    end_col=b_end,
                    value=bg_name,
                    metadata={"asset_kind": "background"},
                )
            )
    elif hook_name == "scene_bg":
        if arg_tokens:
            sc_name, sc_start, sc_end = arg_tokens[0]
            spans.append(
                TokenSpan(
                    kind="jump_target",
                    start_line=line_idx,
                    start_col=sc_start,
                    end_line=line_idx,
                    end_col=sc_end,
                    value=sc_name,
                )
            )
        if len(arg_tokens) >= 2 and "=" not in arg_tokens[1][0]:
            bg_name, b_start, b_end = arg_tokens[1]
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=b_start,
                    end_line=line_idx,
                    end_col=b_end,
                    value=bg_name,
                    metadata={"asset_kind": "background"},
                )
            )
    elif hook_name == "image":
        if len(arg_tokens) >= 2 and "=" not in arg_tokens[1][0]:
            asset_name, a_start, a_end = arg_tokens[1]
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=a_start,
                    end_line=line_idx,
                    end_col=a_end,
                    value=asset_name,
                    metadata={"asset_kind": "image"},
                )
            )
    elif hook_name in ("show", "hide", "move", "expr"):
        if arg_tokens:
            char_name, c_start, c_end = arg_tokens[0]
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=c_start,
                    end_line=line_idx,
                    end_col=c_end,
                    value=char_name,
                    metadata={"character": char_name.lower()},
                )
            )
            if (
                len(arg_tokens) > 1
                and not arg_tokens[1][0].startswith(("at", "with", "to"))
                and "=" not in arg_tokens[1][0]
            ):
                expr_name, e_start, e_end = arg_tokens[1]
                spans.append(
                    TokenSpan(
                        kind="emotion",
                        start_line=line_idx,
                        start_col=e_start,
                        end_line=line_idx,
                        end_col=e_end,
                        value=expr_name,
                        metadata={"character": char_name.lower()},
                    )
                )
    elif hook_name in ("play", "queue") or hook_name.startswith(("play_", "queue_")):
        _emit_audio_hook_spans(spans, line_idx, hook_name, arg_tokens)
    elif hook_name in ("stop", "pause", "resume", "volume") or hook_name.startswith(
        ("stop_", "pause_", "resume_", "volume_")
    ):
        for tok, t_start, t_end in arg_tokens:
            if "=" not in tok:
                spans.append(
                    TokenSpan(
                        kind="hook_arg",
                        start_line=line_idx,
                        start_col=t_start,
                        end_line=line_idx,
                        end_col=t_end,
                        value=tok,
                    )
                )
    elif hook_name == "input" and arg_tokens:
        var_tok, v_start, v_end = arg_tokens[0]
        spans.append(
            TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=var_tok,
                metadata={"role": "mutation"},
            )
        )

    for tok_val, t_start, t_end in arg_tokens:
        if tok_val in ("at", "with", "to"):
            spans.append(
                TokenSpan(
                    kind="hook_keyword",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=tok_val,
                )
            )
        elif "=" in tok_val:
            k, _, v = tok_val.partition("=")
            k_end = t_start + len(k)
            v_start = k_end + 1
            spans.append(
                TokenSpan(
                    kind="hook_kwarg_key",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=k_end,
                    value=k,
                )
            )
            spans.append(
                TokenSpan(
                    kind="color_literal" if v.startswith("#") else "hook_kwarg_val",
                    start_line=line_idx,
                    start_col=v_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=v,
                )
            )


def _emit_audio_hook_spans(
    spans: list[TokenSpan],
    line_idx: int,
    hook_name: str,
    arg_tokens: list[tuple[str, int, int]],
) -> None:
    """Emit audio track asset TokenSpans for play/queue hooks."""
    is_shorthand = hook_name.startswith(("play_", "queue_"))
    chan_default = hook_name.replace("play_", "").replace("queue_", "") if is_shorthand else "music"
    track_emitted = False

    if arg_tokens:
        first_tok, f_start, f_end = arg_tokens[0]
        is_chan = (not is_shorthand) and first_tok in _AUDIO_CHANNELS
        if is_chan and len(arg_tokens) > 1 and "=" not in arg_tokens[1][0]:
            track_name, t_start, t_end = arg_tokens[1]
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=track_name,
                    metadata={"asset_kind": "audio", "channel": first_tok},
                )
            )
            track_emitted = True
        elif not is_chan and "=" not in first_tok:
            spans.append(
                TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=f_start,
                    end_line=line_idx,
                    end_col=f_end,
                    value=first_tok,
                    metadata={"asset_kind": "audio", "channel": chan_default},
                )
            )
            track_emitted = True

    if not track_emitted:
        chan_val = chan_default
        for tok, _, _ in arg_tokens:
            if tok.startswith("channel="):
                chan_val = tok.split("=", 1)[1].strip("\"'") or chan_val
        for tok, t_start, _ in arg_tokens:
            if tok.startswith("track="):
                track_val = tok.split("=", 1)[1].strip("\"'")
                if track_val:
                    val_start = t_start + len("track=")
                    if tok[len("track=") :].startswith(('"', "'")):
                        val_start += 1
                    spans.append(
                        TokenSpan(
                            kind="hook_arg",
                            start_line=line_idx,
                            start_col=val_start,
                            end_line=line_idx,
                            end_col=val_start + len(track_val),
                            value=track_val,
                            metadata={"asset_kind": "audio", "channel": chan_val},
                        )
                    )
                    break


__all__ = [
    "ParseResult",
    "TokenSpan",
    "emit_expression_spans",
    "emit_hook_spans",
    "emit_inline_text_spans",
    "strip_inline_comment",
]
