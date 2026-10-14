"""Static validator for parsed Eager-Script screenplay AST."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager_script import ParsedItem


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


def validate(items: Sequence[ParsedItem], *, plain: bool = False) -> ValidationResult:
    """Validate a parsed screenplay AST for broken links, duplicate labels, and issues."""
    from eager_script import (
        ParsedAppend,
        ParsedCall,
        ParsedCharacter,
        ParsedChoiceSet,
        ParsedDefault,
        ParsedDialogue,
        ParsedElif,
        ParsedElse,
        ParsedEnd,
        ParsedFreshBox,
        ParsedHook,
        ParsedIf,
        ParsedJump,
        ParsedLabel,
        ParsedReturn,
        ParsedSet,
        slugify,
    )
    from eager_script.expr import ExprError, compile_expr

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

    for item in items:
        if plain:
            if isinstance(item, (ParsedCall, ParsedReturn)):
                errors.append(
                    ValidationError(
                        message="Subroutines ('>>', '<<') are not allowed in Eager-SP mode",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif isinstance(item, ParsedHook):
                errors.append(
                    ValidationError(
                        message="Engine hooks ('~') are not allowed in Eager-SP mode",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif isinstance(item, (ParsedAppend, ParsedFreshBox)):
                errors.append(
                    ValidationError(
                        message="Box control beats ('-', '/') are not allowed in Eager-SP mode",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif isinstance(item, (ParsedSet, ParsedDefault, ParsedCharacter, ParsedIf, ParsedElif, ParsedElse, ParsedEnd)):
                errors.append(
                    ValidationError(
                        message="Script logic and directives are not allowed in Eager-SP mode",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif isinstance(item, ParsedDialogue) and item.voice:
                errors.append(
                    ValidationError(
                        message="Voice tags ('{voice:...}') are not allowed in Eager-SP mode",
                        line_number=item.line_number,
                        level="error",
                    )
                )
            elif isinstance(item, ParsedChoiceSet):
                for opt in item.options:
                    if opt.condition:
                        errors.append(
                            ValidationError(
                                message="Conditional choices are not allowed in Eager-SP mode",
                                line_number=opt.line_number,
                                level="error",
                            )
                        )
            elif isinstance(item, ParsedLabel):
                expected_slug = slugify(item.display_name)
                if item.name != expected_slug:
                    errors.append(
                        ValidationError(
                            message=(
                                f"Explicit label identifier '{item.name}' does not match "
                                f"auto-slug of '{item.display_name}' (explicit IDs are not allowed in Eager-SP mode)"
                            ),
                            line_number=item.line_number,
                            level="error",
                        )
                    )

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
            references.append((item.target, item.line_number, "jump"))
        elif isinstance(item, ParsedCall):
            has_call = True
            if first_call_line == 0:
                first_call_line = item.line_number
            references.append((item.target, item.line_number, "call"))
        elif isinstance(item, ParsedReturn):
            has_return = True
        elif isinstance(item, ParsedChoiceSet):
            for opt in item.options:
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
        elif isinstance(item, ParsedSet):
            if not current_label_seen:
                errors.append(
                    ValidationError(
                        message="Variable set statement ('$') must appear inside a scene, not in preamble",
                        line_number=item.line_number,
                        level="error",
                    )
                )
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
    for item in items:
        if isinstance(item, ParsedLabel):
            terminator_info = None
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
        elif isinstance(item, ParsedChoiceSet):
            terminator_info = ("choice menu", item.line_number)

    # Check for unreferenced / orphan labels and unreachable labels from entry point
    referenced_targets = {target for target, _, _ in references}
    first_label_seen = False
    scene_targets: dict[str, list[str]] = {name: [] for name in labels}
    curr_scene: str | None = None
    curr_terminated = False

    for item in items:
        if isinstance(item, ParsedLabel):
            curr_scene = item.name
            curr_terminated = False
        elif curr_scene is not None and not curr_terminated:
            if isinstance(item, (ParsedJump, ParsedCall)):
                scene_targets[curr_scene].append(item.target)
                if isinstance(item, ParsedJump):
                    curr_terminated = True
            elif isinstance(item, ParsedChoiceSet):
                for opt in item.options:
                    scene_targets[curr_scene].append(opt.target)
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
            if isinstance(item, (ParsedChoiceSet, ParsedReturn)):
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
