"""Static validator for parsed Eager-Script screenplay AST."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager.script.ast import ParsedItem

__all__ = [
    "ValidationError",
    "ValidationResult",
    "validate",
]


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Represents a validation issue (error or warning)."""

    message: str
    line_number: int
    level: str = "error"  # "error" or "warning"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of validating an Eager-Script script AST."""

    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationError, ...]

    @property
    def is_valid(self) -> bool:
        """True if there are no errors."""
        return len(self.errors) == 0


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PERSISTENT_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _validate_set_target(target: str, line_number: int) -> ValidationError | None:
    """Validate that a `$ target = ...` assignment target is a legal variable name."""
    if target.startswith("persistent."):
        key = target[len("persistent.") :]
        if not key or not _PERSISTENT_KEY_RE.match(key):
            return ValidationError(
                message=f"Invalid persistent variable target '{target}'",
                line_number=line_number,
                level="error",
            )
        return None
    if not _IDENT_RE.match(target):
        return ValidationError(
            message=f"Invalid variable target '{target}'",
            line_number=line_number,
            level="error",
        )
    return None


def _iter_choice_bodies(items: Sequence[Any]) -> Iterator[Any]:
    """Yield every item nested inside inline choice option bodies (depth-first)."""
    from eager.script.ast import ParsedChoiceSet

    for item in items:
        if isinstance(item, ParsedChoiceSet):
            for opt in item.options:
                yield from opt.body
                yield from _iter_choice_bodies(opt.body)


def validate(items: Sequence[ParsedItem]) -> ValidationResult:
    """Validate a parsed screenplay AST for broken links, duplicate labels, and issues."""
    from eager.script.ast import (
        ParsedCall,
        ParsedChoiceSet,
        ParsedDefault,
        ParsedDialogue,
        ParsedElif,
        ParsedElse,
        ParsedEnd,
        ParsedIf,
        ParsedJump,
        ParsedLabel,
        ParsedNarration,
        ParsedReturn,
        ParsedSet,
    )
    from eager.script.expr import ExprError, compile_expr

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    labels: dict[str, int] = {}
    references: list[tuple[str, int, str]] = []  # (target, line_number, reference_type)
    has_return = False
    has_call = False
    first_call_line = 0

    # Stack for tracking open @if blocks: stores list of line numbers and whether else was seen
    if_stack: list[dict[str, Any]] = []
    current_label_seen = False

    def scan_inline_body(nested_items: Sequence[Any]) -> None:
        """Validate references and expressions inside an inline choice block body."""
        nonlocal has_call, first_call_line, has_return
        terminator: tuple[str, int] | None = None
        inline_if_stack: list[dict[str, Any]] = []

        for sub in nested_items:
            if isinstance(sub, (ParsedIf, ParsedElif, ParsedElse, ParsedEnd)):
                terminator = None
            if terminator is not None:
                warnings.append(
                    ValidationError(
                        message=(
                            f"Unreachable code: statement after {terminator[0]} "
                            f"(line {terminator[1]}) will never execute"
                        ),
                        line_number=sub.line_number,
                        level="warning",
                    )
                )
            elif isinstance(sub, ParsedJump):
                references.append((sub.target, sub.line_number, "jump"))
                terminator = ("jump", sub.line_number)
            elif isinstance(sub, ParsedCall):
                has_call = True
                if first_call_line == 0:
                    first_call_line = sub.line_number
                references.append((sub.target, sub.line_number, "call"))
            elif isinstance(sub, ParsedReturn):
                has_return = True
                terminator = ("return ('<<')", sub.line_number)
            elif isinstance(sub, ParsedChoiceSet):
                for opt in sub.options:
                    if opt.target is not None:
                        references.append((opt.target, opt.line_number, "choice"))
                    if opt.condition:
                        try:
                            compile_expr(opt.condition)
                        except ExprError as e:
                            errors.append(
                                ValidationError(
                                    message=f"Invalid choice condition '{opt.condition}': {e}",
                                    line_number=opt.line_number,
                                    level="error",
                                )
                            )
                    if opt.body:
                        scan_inline_body(opt.body)
                if not any(opt.body for opt in sub.options):
                    terminator = ("choice menu", sub.line_number)
            elif isinstance(sub, ParsedSet):
                target_err = _validate_set_target(sub.target, sub.line_number)
                if target_err is not None:
                    errors.append(target_err)
                try:
                    compile_expr(sub.expr_src)
                except ExprError as e:
                    errors.append(
                        ValidationError(
                            message=f"Invalid expression in set statement: {e}",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
            elif isinstance(sub, ParsedIf):
                try:
                    compile_expr(sub.expr_src)
                except ExprError as e:
                    errors.append(
                        ValidationError(
                            message=f"Invalid expression in condition: {e}",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                inline_if_stack.append({"line": sub.line_number, "has_else": False})
            elif isinstance(sub, ParsedElif):
                if not inline_if_stack:
                    errors.append(
                        ValidationError(
                            message="@elif without matching @if",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                elif inline_if_stack[-1]["has_else"]:
                    errors.append(
                        ValidationError(
                            message="@elif cannot follow @else",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                else:
                    try:
                        compile_expr(sub.expr_src)
                    except ExprError as e:
                        errors.append(
                            ValidationError(
                                message=f"Invalid expression in condition: {e}",
                                line_number=sub.line_number,
                                level="error",
                            )
                        )
            elif isinstance(sub, ParsedElse):
                if not inline_if_stack:
                    errors.append(
                        ValidationError(
                            message="@else without matching @if",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                elif inline_if_stack[-1]["has_else"]:
                    errors.append(
                        ValidationError(
                            message="Multiple @else clauses in single @if block",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                else:
                    inline_if_stack[-1]["has_else"] = True
            elif isinstance(sub, ParsedEnd):
                if not inline_if_stack:
                    errors.append(
                        ValidationError(
                            message="@end without matching @if",
                            line_number=sub.line_number,
                            level="error",
                        )
                    )
                else:
                    inline_if_stack.pop()

        if inline_if_stack:
            for frame in inline_if_stack:
                errors.append(
                    ValidationError(
                        message=f"Unclosed @if block (started at line {frame['line']})",
                        line_number=frame["line"],
                        level="error",
                    )
                )

    for item in items:
        if isinstance(item, ParsedLabel):
            if current_label_seen and if_stack:
                errors.append(
                    ValidationError(
                        message=f"Unclosed @if block (started at line {if_stack[-1]['line']}) before new scene label",
                        line_number=item.line_number,
                        level="error",
                    )
                )
                if_stack.clear()
            current_label_seen = True
            if item.name in labels:
                errors.append(
                    ValidationError(
                        message=(
                            f"Duplicate label identifier '{item.name}' "
                            f"(previously defined at line {labels[item.name]})"
                        ),
                        line_number=item.line_number,
                        level="error",
                    )
                )
            else:
                labels[item.name] = item.line_number
        elif isinstance(item, ParsedJump):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Jump statement ('->') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            references.append((item.target, item.line_number, "jump"))
        elif isinstance(item, ParsedCall):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Call statement ('>>') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            has_call = True
            if first_call_line == 0:
                first_call_line = item.line_number
            references.append((item.target, item.line_number, "call"))
        elif isinstance(item, ParsedReturn):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Return statement ('<<') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            has_return = True
        elif isinstance(item, (ParsedDialogue, ParsedNarration)):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Dialogue and narration must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
        elif isinstance(item, ParsedChoiceSet):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Choice menu ('?') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            for opt in item.options:
                if opt.target is not None:
                    references.append((opt.target, opt.line_number, "choice"))
                if opt.condition:
                    try:
                        compile_expr(opt.condition)
                    except ExprError as e:
                        errors.append(
                            ValidationError(
                                message=f"Invalid choice condition '{opt.condition}': {e}",
                                line_number=opt.line_number,
                                level="error",
                            )
                        )
                if opt.body:
                    scan_inline_body(opt.body)
        elif isinstance(item, ParsedSet):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Variable set statement ('$') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            target_err = _validate_set_target(item.target, item.line_number)
            if target_err is not None:
                errors.append(target_err)
            try:
                compile_expr(item.expr_src)
            except ExprError as e:
                errors.append(
                    ValidationError(
                        message=f"Invalid expression in set statement: {e}",
                        line_number=item.line_number,
                        level="error",
                    )
                )
        elif isinstance(item, ParsedDefault):
            try:
                compile_expr(item.expr_src)
            except ExprError as e:
                errors.append(
                    ValidationError(
                        message=f"Invalid expression in @default: {e}",
                        line_number=item.line_number,
                        level="error",
                    )
                )
        elif isinstance(item, ParsedIf):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="@if block must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            try:
                compile_expr(item.expr_src)
            except ExprError as e:
                errors.append(
                    ValidationError(
                        message=f"Invalid expression in @if: {e}",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            if_stack.append({"line": item.line_number, "has_else": False})
        elif isinstance(item, ParsedElif):
            if not if_stack:
                errors.append(
                    ValidationError(
                        message="@elif without matching @if",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif if_stack[-1]["has_else"]:
                errors.append(
                    ValidationError(
                        message="@elif cannot follow @else",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            else:
                try:
                    compile_expr(item.expr_src)
                except ExprError as e:
                    errors.append(
                        ValidationError(
                            message=f"Invalid expression in @elif: {e}",
                            line_number=item.line_number,
                            level="error",
                        )
                    )
        elif isinstance(item, ParsedElse):
            if not if_stack:
                errors.append(
                    ValidationError(
                        message="@else without matching @if",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif if_stack[-1]["has_else"]:
                errors.append(
                    ValidationError(
                        message="Multiple @else clauses in single @if block",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            else:
                if_stack[-1]["has_else"] = True
        elif isinstance(item, ParsedEnd):
            if not if_stack:
                errors.append(
                    ValidationError(
                        message="@end without matching @if",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            else:
                if_stack.pop()

    if if_stack:
        for frame in if_stack:
            errors.append(
                ValidationError(
                    message=f"Unclosed @if block (started at line {frame['line']})",
                    line_number=frame["line"],
                    level="error",
                )
            )

    # Check for undefined targets
    for target, line_num, ref_type in references:
        if target not in labels:
            errors.append(
                ValidationError(
                    message=f"Undefined target label '{target}' in {ref_type}",
                    line_number=line_num,
                    level="error",
                )
            )

    # Check for unreturned subroutine calls
    if has_call and not has_return:
        warnings.append(
            ValidationError(
                message="Subroutine call ('>>') found, but script contains no return ('<<')",
                line_number=first_call_line,
                level="warning",
            )
        )

    # Check for unreferenced / orphan labels (excluding first label in script)
    # Check for unreachable statements within scene blocks (dead code after terminating statements)
    terminator_info: tuple[str, int] | None = None
    if_term_stack: list[tuple[str, int] | None] = []
    for item in items:
        if isinstance(item, ParsedLabel):
            terminator_info = None
            if_term_stack.clear()
        elif isinstance(item, ParsedIf):
            if terminator_info is not None:
                term_desc, term_line = terminator_info
                warnings.append(
                    ValidationError(
                        message=(
                            f"Unreachable code: statement after {term_desc} "
                            f"(line {term_line}) will never execute"
                        ),
                        line_number=item.line_number,
                        level="warning",
                    )
                )
            if_term_stack.append(terminator_info)
        elif isinstance(item, (ParsedElif, ParsedElse)):
            terminator_info = if_term_stack[-1] if if_term_stack else None
        elif isinstance(item, ParsedEnd):
            terminator_info = if_term_stack.pop() if if_term_stack else None
        elif terminator_info is not None:
            term_desc, term_line = terminator_info
            warnings.append(
                ValidationError(
                    message=(
                        f"Unreachable code: statement after {term_desc} "
                        f"(line {term_line}) will never execute"
                    ),
                    line_number=item.line_number,
                    level="warning",
                )
            )
        elif isinstance(item, ParsedJump):
            terminator_info = ("jump", item.line_number)
        elif isinstance(item, ParsedReturn):
            terminator_info = ("return ('<<')", item.line_number)
        elif isinstance(item, ParsedChoiceSet) and not any(opt.body for opt in item.options):
            terminator_info = ("choice menu", item.line_number)

    # Check for unreferenced / orphan labels and unreachable labels from entry point
    referenced_targets = {target for target, _, _ in references}
    first_label_seen = False
    scene_targets: dict[str, list[str]] = {name: [] for name in labels}
    curr_scene: str | None = None
    curr_terminated = False
    reach_if_stack: list[bool] = []

    for item in items:
        if isinstance(item, ParsedLabel):
            curr_scene = item.name
            curr_terminated = False
            reach_if_stack.clear()
        elif isinstance(item, ParsedIf):
            reach_if_stack.append(curr_terminated)
        elif isinstance(item, (ParsedElif, ParsedElse)):
            curr_terminated = reach_if_stack[-1] if reach_if_stack else False
        elif isinstance(item, ParsedEnd):
            curr_terminated = reach_if_stack.pop() if reach_if_stack else False
        elif curr_scene is not None and not curr_terminated:
            if isinstance(item, (ParsedJump, ParsedCall)):
                scene_targets[curr_scene].append(item.target)
                if isinstance(item, ParsedJump):
                    curr_terminated = True
            elif isinstance(item, ParsedChoiceSet):
                for opt in item.options:
                    if opt.target is not None:
                        scene_targets[curr_scene].append(opt.target)
                for sub in _iter_choice_bodies([item]):
                    if isinstance(sub, (ParsedJump, ParsedCall)):
                        scene_targets[curr_scene].append(sub.target)
                    elif isinstance(sub, ParsedChoiceSet):
                        for nested_opt in sub.options:
                            if nested_opt.target is not None:
                                scene_targets[curr_scene].append(nested_opt.target)
                if not any(opt.body for opt in item.options):
                    curr_terminated = True
            elif isinstance(item, ParsedReturn):
                curr_terminated = True

    reachable_labels: set[str] = set()
    entry_label: str | None = None
    if labels:
        entry_label = next(iter(labels))
        reachable_labels.add(entry_label)
        queue = [entry_label]
        while queue:
            node = queue.pop()
            for target in scene_targets.get(node, []):
                if target in labels and target not in reachable_labels:
                    reachable_labels.add(target)
                    queue.append(target)

    for label_name, line_num in labels.items():
        if not first_label_seen:
            first_label_seen = True
            continue  # Entry point label
        if label_name == entry_label:
            continue
        if label_name not in referenced_targets:
            warnings.append(
                ValidationError(
                    message=f"Label '{label_name}' is defined but never targeted by any jump, call, or choice",
                    line_number=line_num,
                    level="warning",
                )
            )
        elif label_name not in reachable_labels:
            warnings.append(
                ValidationError(
                    message=f"Label '{label_name}' is unreachable from the script entry point ('{entry_label}')",
                    line_number=line_num,
                    level="warning",
                )
            )

    # Check for cyclical traversal (unconditional loops with no player choices or exit)
    unconditional_exits: dict[str, tuple[str, int]] = {}
    current_scene_label: str | None = None
    scene_has_branch_or_exit = False

    for item in items:
        if isinstance(item, ParsedLabel):
            current_scene_label = item.name
            scene_has_branch_or_exit = False
        elif current_scene_label is not None:
            if isinstance(item, (ParsedChoiceSet, ParsedReturn, ParsedIf)):
                scene_has_branch_or_exit = True
            elif (
                isinstance(item, ParsedJump)
                and not scene_has_branch_or_exit
                and current_scene_label not in unconditional_exits
            ):
                unconditional_exits[current_scene_label] = (item.target, item.line_number)

    visited: set[str] = set()
    reported_cycles: set[frozenset[str]] = set()

    for start_label in labels:
        if start_label in visited:
            continue

        path: list[str] = []
        path_index: dict[str, int] = {}
        curr = start_label

        while curr in unconditional_exits:
            target, _jump_line = unconditional_exits[curr]
            if target not in labels:
                break

            if curr in path_index:
                cycle_start = path_index[curr]
                cycle_nodes = path[cycle_start:]
                cycle_key = frozenset(cycle_nodes)

                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    closing_node = path[-1]
                    _, closing_jump_line = unconditional_exits[closing_node]
                    cycle_str = " -> ".join(cycle_nodes + [curr])
                    warnings.append(
                        ValidationError(
                            message=(
                                f"Cyclical traversal detected: {cycle_str} "
                                "(unconditional loop with no player choices or exit)"
                            ),
                            line_number=closing_jump_line,
                            level="warning",
                        )
                    )
                break

            if curr in visited:
                break

            visited.add(curr)
            path_index[curr] = len(path)
            path.append(curr)
            curr = target

    return ValidationResult(errors=tuple(errors), warnings=tuple(warnings))
