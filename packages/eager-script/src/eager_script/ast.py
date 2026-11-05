"""AST node definitions and serialization helpers for Eager-Script."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias


class ParseError(Exception):
    """Raised when screenplay syntax is invalid."""

    line_number: int
    start_col: int
    end_col: int

    def __init__(self, message: str, line_number: int, start_col: int = 0, end_col: int = 0) -> None:
        super().__init__(f"Line {line_number}: {message}")
        self.line_number = line_number
        self.start_col = start_col
        self.end_col = end_col


@dataclass(frozen=True, slots=True)
class ParsedInclude:
    """Parsed @include directive."""

    path: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('include')."""
        return "include"

    def to_dict(self) -> dict[str, Any]:
        """Serialize include node to a dictionary."""
        return {
            "type": self.type,
            "path": self.path,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedError:
    """Parsed error node recorded during resilient parsing."""

    message: str
    line_number: int
    line_text: str = ""
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('error')."""
        return "error"

    def to_dict(self) -> dict[str, Any]:
        """Serialize error node to a dictionary."""
        return {
            "type": self.type,
            "message": self.message,
            "line_number": self.line_number,
            "line_text": self.line_text,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedLabel:
    """Parsed section label."""

    name: str
    display_name: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('label')."""
        return "label"

    def to_dict(self) -> dict[str, Any]:
        """Serialize section label node to a dictionary.

        Returns:
            Dictionary containing node type, label name, line number, and column span.
        """
        return {
            "type": self.type,
            "name": self.name,
            "display_name": self.display_name,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedDialogue:
    """Parsed character dialogue beat."""

    speaker: str
    text: str
    voice: str | None
    line_number: int
    emotion: str | None = None
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('dialogue')."""
        return "dialogue"

    def to_dict(self) -> dict[str, Any]:
        """Serialize dialogue node to a dictionary.

        Returns:
            Dictionary containing speaker, text, voice, emotion, line number, and column span.
        """
        return {
            "type": self.type,
            "speaker": self.speaker,
            "text": self.text,
            "voice": self.voice,
            "emotion": self.emotion,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedAppend:
    """Parsed append beat ('-')."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('append')."""
        return "append"

    def to_dict(self) -> dict[str, Any]:
        """Serialize append beat node to a dictionary.

        Returns:
            Dictionary containing node type, append text, line number, and column span.
        """
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedFreshBox:
    """Parsed fresh box beat ('/')."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('fresh_box')."""
        return "fresh_box"

    def to_dict(self) -> dict[str, Any]:
        """Serialize fresh box beat node to a dictionary.

        Returns:
            Dictionary containing node type, text, line number, and column span.
        """
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedNarration:
    """Parsed speakerless narration."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('narration')."""
        return "narration"

    def to_dict(self) -> dict[str, Any]:
        """Serialize narration beat node to a dictionary.

        Returns:
            Dictionary containing node type, narration text, line number, and column span.
        """
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedChoiceOption:
    """Parsed choice menu option ('? Text (target)' or '? Text' + indented block).

    A named option carries a ``target`` scene label.  An *inline* option omits the
    target and instead carries an indented ``body`` that is lowered into an
    anonymous scene (see :func:`eager_script.to_graph`).
    """

    text: str
    target: str | None
    line_number: int
    condition: str | None = None
    body: tuple[ParsedItem, ...] = ()
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('choice_option')."""
        return "choice_option"

    @property
    def is_inline(self) -> bool:
        """True when the option carries an anonymous inline block instead of a target."""
        return bool(self.body)

    def to_dict(self) -> dict[str, Any]:
        """Serialize choice option node to a dictionary.

        Returns:
            Dictionary containing choice option fields, column span, and lowering metadata.
        """
        return {
            "type": self.type,
            "text": self.text,
            "target": self.target,
            "line_number": self.line_number,
            "condition": self.condition,
            "body": [item.to_dict() for item in self.body],
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedChoiceSet:
    """Parsed collection of consecutive choice options."""

    options: tuple[ParsedChoiceOption, ...]
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('choice_set')."""
        return "choice_set"

    def to_dict(self) -> dict[str, Any]:
        """Serialize choice set node to a dictionary.

        Returns:
            Dictionary containing serialized choice options list, line number, and column span.
        """
        return {
            "type": self.type,
            "options": [option.to_dict() for option in self.options],
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedJump:
    """Parsed unconditional jump ('>')."""

    target: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('jump')."""
        return "jump"

    def to_dict(self) -> dict[str, Any]:
        """Serialize jump node to a dictionary.

        Returns:
            Dictionary containing target scene ID, line number, and column span.
        """
        return {
            "type": self.type,
            "target": self.target,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedCall:
    """Parsed subroutine call ('>>')."""

    target: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('call')."""
        return "call"

    def to_dict(self) -> dict[str, Any]:
        """Serialize call node to a dictionary.

        Returns:
            Dictionary containing subroutine target scene ID, line number, and column span.
        """
        return {
            "type": self.type,
            "target": self.target,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedReturn:
    """Parsed subroutine return ('<<')."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('return')."""
        return "return"

    def to_dict(self) -> dict[str, Any]:
        """Serialize return node to a dictionary.

        Returns:
            Dictionary containing node type, line number, and column span.
        """
        return {
            "type": self.type,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedHook:
    """Parsed hook invocation ('~')."""

    hook_name: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('hook')."""
        return "hook"

    def to_dict(self) -> dict[str, Any]:
        """Serialize hook node to a dictionary.

        Returns:
            Dictionary containing hook name, line number, and column span.
        """
        return {
            "type": self.type,
            "hook_name": self.hook_name,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedSet:
    """Parsed variable set/mutation statement ('$ target op expr')."""

    target: str
    op: str
    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('set')."""
        return "set"

    def to_dict(self) -> dict[str, Any]:
        """Serialize set node to a dictionary.

        Returns:
            Dictionary containing target variable, operator, expression, line number, and column span.
        """
        return {
            "type": self.type,
            "target": self.target,
            "op": self.op,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedDefault:
    """Parsed default variable definition ('@default name = expr')."""

    name: str
    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('default')."""
        return "default"

    def to_dict(self) -> dict[str, Any]:
        """Serialize default variable definition node to a dictionary.

        Returns:
            Dictionary containing variable name, expression, line number, and column span.
        """
        return {
            "type": self.type,
            "name": self.name,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedCharacter:
    """Parsed character definition ('@character id \"name\" ...')."""

    id: str
    name: str
    attrs: tuple[tuple[str, str], ...]
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('character')."""
        return "character"

    def to_dict(self) -> dict[str, Any]:
        """Serialize character definition node to a dictionary.

        Returns:
            Dictionary containing character id, display name, attributes, line number, and column span.
        """
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "attrs": list(self.attrs),
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedIf:
    """Parsed '@if expr'."""

    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('if')."""
        return "if"

    def to_dict(self) -> dict[str, Any]:
        """Serialize if node to a dictionary.

        Returns:
            Dictionary containing expression source, line number, and column span.
        """
        return {
            "type": self.type,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedElif:
    """Parsed '@elif expr'."""

    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('elif')."""
        return "elif"

    def to_dict(self) -> dict[str, Any]:
        """Serialize elif node to a dictionary.

        Returns:
            Dictionary containing expression source, line number, and column span.
        """
        return {
            "type": self.type,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedElse:
    """Parsed '@else'."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('else')."""
        return "else"

    def to_dict(self) -> dict[str, Any]:
        """Serialize else node to a dictionary.

        Returns:
            Dictionary containing node type, line number, and column span.
        """
        return {
            "type": self.type,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedEnd:
    """Parsed '@end'."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('end')."""
        return "end"

    def to_dict(self) -> dict[str, Any]:
        """Serialize end node to a dictionary.

        Returns:
            Dictionary containing node type, line number, and column span.
        """
        return {
            "type": self.type,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedCondJump:
    """Internal lowered conditional jump (jumps to target_index in scene if condition is false)."""

    condition: str
    target_index: int
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('cond_jump')."""
        return "cond_jump"

    def to_dict(self) -> dict[str, Any]:
        """Serialize conditional jump node to a dictionary.

        Returns:
            Dictionary containing condition expression, target index, line number, and column span.
        """
        return {
            "type": self.type,
            "condition": self.condition,
            "target_index": self.target_index,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedLocalJump:
    """Internal lowered unconditional local jump within a scene."""

    target_index: int
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('local_jump')."""
        return "local_jump"

    def to_dict(self) -> dict[str, Any]:
        """Serialize local jump node to a dictionary.

        Returns:
            Dictionary containing target index, line number, and column span.
        """
        return {
            "type": self.type,
            "target_index": self.target_index,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


ParsedItem: TypeAlias = (
    ParsedLabel
    | ParsedDialogue
    | ParsedAppend
    | ParsedFreshBox
    | ParsedNarration
    | ParsedChoiceSet
    | ParsedJump
    | ParsedCall
    | ParsedReturn
    | ParsedHook
    | ParsedSet
    | ParsedDefault
    | ParsedCharacter
    | ParsedIf
    | ParsedElif
    | ParsedElse
    | ParsedEnd
    | ParsedInclude
    | ParsedError
    | ParsedCondJump
    | ParsedLocalJump
)


def to_dict(items: Sequence[ParsedItem]) -> list[dict[str, Any]]:
    """Convert a sequence of parsed AST items into dictionaries."""
    return [item.to_dict() for item in items]


def to_json(items: Sequence[ParsedItem], *, indent: int | None = 2) -> str:
    """Serialize parsed AST items to a JSON string."""
    return json.dumps(to_dict(items), indent=indent)


__all__ = [
    "ParseError",
    "ParsedAppend",
    "ParsedCall",
    "ParsedCharacter",
    "ParsedChoiceOption",
    "ParsedChoiceSet",
    "ParsedCondJump",
    "ParsedDefault",
    "ParsedDialogue",
    "ParsedElif",
    "ParsedElse",
    "ParsedEnd",
    "ParsedError",
    "ParsedFreshBox",
    "ParsedHook",
    "ParsedIf",
    "ParsedInclude",
    "ParsedItem",
    "ParsedJump",
    "ParsedLabel",
    "ParsedLocalJump",
    "ParsedNarration",
    "ParsedReturn",
    "ParsedSet",
    "to_dict",
    "to_json",
]
