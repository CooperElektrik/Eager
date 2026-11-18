"""AST node definitions and serialization helpers for Eager-Script."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, runtime_checkable


class EagerScriptError(Exception):
    """Base exception for all errors raised within eager-script."""


class ParseError(EagerScriptError):
    """Raised when screenplay syntax is invalid."""

    line_number: int
    start_col: int
    end_col: int

    def __init__(self, message: str, line_number: int, start_col: int = 0, end_col: int = 0) -> None:
        super().__init__(f"Line {line_number}: {message}")
        self.line_number = line_number
        self.start_col = start_col
        self.end_col = end_col


@runtime_checkable
class AstNode(Protocol):
    """Protocol for all parsed Eager-Script AST nodes."""

    line_number: int
    start_col: int
    end_col: int

    @property
    def type(self) -> str:
        """Node type discriminator string."""
        ...

    def to_dict(self) -> dict[str, object]:
        """Serialize AST node to a dictionary."""
        ...


@dataclass(frozen=True, slots=True)
class ParsedInclude(AstNode):
    """Parsed @include directive."""

    path: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('include')."""
        return "include"

    def to_dict(self) -> dict[str, object]:
        """Serialize include node to a dictionary."""
        return {
            "type": self.type,
            "path": self.path,
            "line_number": self.line_number,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass(frozen=True, slots=True)
class ParsedError(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedLabel(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedDialogue(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedAppend(AstNode):
    """Parsed append beat ('-')."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('append')."""
        return "append"

    def to_dict(self) -> dict[str, object]:
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
class ParsedFreshBox(AstNode):
    """Parsed fresh box beat ('/')."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('fresh_box')."""
        return "fresh_box"

    def to_dict(self) -> dict[str, object]:
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
class ParsedNarration(AstNode):
    """Parsed speakerless narration."""

    text: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('narration')."""
        return "narration"

    def to_dict(self) -> dict[str, object]:
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
class ParsedChoiceOption(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedChoiceSet(AstNode):
    """Parsed collection of consecutive choice options."""

    options: tuple[ParsedChoiceOption, ...]
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('choice_set')."""
        return "choice_set"

    def to_dict(self) -> dict[str, object]:
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
class ParsedJump(AstNode):
    """Parsed unconditional jump ('>')."""

    target: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('jump')."""
        return "jump"

    def to_dict(self) -> dict[str, object]:
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
class ParsedCall(AstNode):
    """Parsed subroutine call ('>>')."""

    target: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('call')."""
        return "call"

    def to_dict(self) -> dict[str, object]:
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
class ParsedReturn(AstNode):
    """Parsed subroutine return ('<<')."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('return')."""
        return "return"

    def to_dict(self) -> dict[str, object]:
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
class ParsedHook(AstNode):
    """Parsed hook invocation ('~')."""

    hook_name: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('hook')."""
        return "hook"

    def to_dict(self) -> dict[str, object]:
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
class ParsedSet(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedDefault(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedCharacter(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedIf(AstNode):
    """Parsed '@if expr'."""

    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('if')."""
        return "if"

    def to_dict(self) -> dict[str, object]:
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
class ParsedElif(AstNode):
    """Parsed '@elif expr'."""

    expr_src: str
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('elif')."""
        return "elif"

    def to_dict(self) -> dict[str, object]:
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
class ParsedElse(AstNode):
    """Parsed '@else'."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('else')."""
        return "else"

    def to_dict(self) -> dict[str, object]:
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
class ParsedEnd(AstNode):
    """Parsed '@end'."""

    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('end')."""
        return "end"

    def to_dict(self) -> dict[str, object]:
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
class ParsedCondJump(AstNode):
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

    def to_dict(self) -> dict[str, object]:
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
class ParsedLocalJump(AstNode):
    """Internal lowered unconditional local jump within a scene."""

    target_index: int
    line_number: int
    start_col: int = 0
    end_col: int = 0

    @property
    def type(self) -> str:
        """Node type discriminator string ('local_jump')."""
        return "local_jump"

    def to_dict(self) -> dict[str, object]:
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
    | ParsedChoiceOption
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


def to_dict(items: Sequence[ParsedItem]) -> list[dict[str, object]]:
    """Convert a sequence of parsed AST items into dictionaries."""
    return [item.to_dict() for item in items]


def to_json(items: Sequence[ParsedItem], *, indent: int | None = 2) -> str:
    """Serialize parsed AST items to a JSON string."""
    return json.dumps(to_dict(items), indent=indent)


def from_dict(data: dict[str, Any]) -> ParsedItem:
    """Polymorphically deserialize a dictionary to a ParsedItem AST node."""
    if not isinstance(data, dict):
        raise TypeError(f"AST node data must be a dict, got {type(data).__name__}")
    node_type = data.get("type")
    line_number = int(data.get("line_number", 0))
    start_col = int(data.get("start_col", 0))
    end_col = int(data.get("end_col", 0))

    match node_type:
        case "include":
            return ParsedInclude(
                path=str(data["path"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "error":
            return ParsedError(
                message=str(data["message"]),
                line_number=line_number,
                line_text=str(data.get("line_text", "")),
                start_col=start_col,
                end_col=end_col,
            )
        case "label":
            return ParsedLabel(
                name=str(data["name"]),
                display_name=str(data.get("display_name", "")),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "dialogue":
            return ParsedDialogue(
                speaker=str(data["speaker"]),
                text=str(data["text"]),
                voice=data.get("voice"),
                line_number=line_number,
                emotion=data.get("emotion"),
                start_col=start_col,
                end_col=end_col,
            )
        case "append":
            return ParsedAppend(
                text=str(data["text"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "fresh_box":
            return ParsedFreshBox(
                text=str(data["text"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "narration":
            return ParsedNarration(
                text=str(data["text"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "choice_option":
            body = tuple(from_dict(item) for item in data.get("body", []))
            return ParsedChoiceOption(
                text=str(data["text"]),
                target=data.get("target"),
                line_number=line_number,
                condition=data.get("condition"),
                body=body,
                start_col=start_col,
                end_col=end_col,
            )
        case "choice_set":
            options = tuple(
                ParsedChoiceOption(
                    text=str(opt["text"]),
                    target=opt.get("target"),
                    line_number=int(opt.get("line_number", 0)),
                    condition=opt.get("condition"),
                    body=tuple(from_dict(item) for item in opt.get("body", [])),
                    start_col=int(opt.get("start_col", 0)),
                    end_col=int(opt.get("end_col", 0)),
                )
                if isinstance(opt, dict)
                else opt
                for opt in data.get("options", [])
            )
            return ParsedChoiceSet(
                options=options,
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "jump":
            return ParsedJump(
                target=str(data["target"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "call":
            return ParsedCall(
                target=str(data["target"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "return":
            return ParsedReturn(
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "hook":
            return ParsedHook(
                hook_name=str(data.get("hook_name") or data.get("name", "")),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "set":
            return ParsedSet(
                target=str(data.get("target") or data.get("name", "")),
                op=str(data.get("op", "=")),
                expr_src=str(data["expr_src"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "default":
            return ParsedDefault(
                name=str(data["name"]),
                expr_src=str(data["expr_src"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "character":
            attrs_raw = data.get("attrs", ())
            if isinstance(attrs_raw, dict):
                attrs = tuple((str(k), str(v)) for k, v in attrs_raw.items())
            else:
                attrs = tuple(
                    (str(pair[0]), str(pair[1]))
                    for pair in attrs_raw
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2
                )
            return ParsedCharacter(
                id=str(data.get("id") or data.get("identifier", "")),
                name=str(data.get("name", "")),
                attrs=attrs,
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "if":
            return ParsedIf(
                expr_src=str(data.get("expr_src") or data.get("condition", "")),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "elif":
            return ParsedElif(
                expr_src=str(data.get("expr_src") or data.get("condition", "")),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "else":
            return ParsedElse(
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "end":
            return ParsedEnd(
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "cond_jump":
            return ParsedCondJump(
                condition=str(data["condition"]),
                target_index=int(data["target_index"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case "local_jump":
            return ParsedLocalJump(
                target_index=int(data["target_index"]),
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
            )
        case _:
            raise ValueError(f"Unknown AST node type: {node_type!r}")


def from_json(json_str: str) -> list[ParsedItem]:
    """Deserialize a JSON string into a list of ParsedItem AST nodes."""
    raw = json.loads(json_str)
    if not isinstance(raw, list):
        raise TypeError(f"Expected list in JSON for AST items, got {type(raw).__name__}")
    return [from_dict(item) for item in raw]


__all__ = [
    "AstNode",
    "EagerScriptError",
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
    "from_dict",
    "from_json",
    "to_dict",
    "to_json",
]
