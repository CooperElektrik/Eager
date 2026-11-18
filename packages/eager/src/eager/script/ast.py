"""AST node definitions and serialization helpers for Eager-Script."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias, runtime_checkable


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


@dataclass(frozen=True, slots=True)
class ParsedChoiceOption(AstNode):
    """Parsed choice menu option ('? Text (target)' or '? Text' + indented block).

    A named option carries a ``target`` scene label.  An *inline* option omits the
    target and instead carries an indented ``body`` that is lowered into an
    anonymous scene (see :func:`eager.script.to_graph`).
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
]
