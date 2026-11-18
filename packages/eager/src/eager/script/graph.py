"""Directed scene graph model and transformation for Eager-Script screenplay AST."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager.script.ast import ParsedItem

__all__ = [
    "EdgeKind",
    "SceneEdge",
    "SceneGraph",
    "SceneNode",
    "parse_graph",
    "to_graph",
]


class EdgeKind(str, Enum):
    """Transition kind for directed scene transitions."""

    JUMP = "jump"
    CALL = "call"
    CHOICE = "choice"


def _anon_scene_id(scene_id: str, line_number: int) -> str:
    """Build the stable id of an anonymous scene lowered from an inline choice block."""
    return f"{scene_id}__anon_{line_number}"


@dataclass(frozen=True, slots=True)
class SceneNode:
    """A scene (label block) in the narrative graph."""

    id: str
    display_name: str
    line_number: int
    body: tuple[ParsedItem, ...]
    speakers: tuple[str, ...]
    hooks: tuple[str, ...]
    is_anonymous: bool = False


@dataclass(frozen=True, slots=True)
class SceneEdge:
    """A directed transition between scenes."""

    source: str
    target: str
    kind: EdgeKind | str
    label: str | None
    line_number: int
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class SceneGraph:
    """Directed graph of narrative scenes and transitions."""

    entry: str | None
    nodes: dict[str, SceneNode]
    edges: tuple[SceneEdge, ...]
    preamble: tuple[ParsedItem, ...]
    characters: dict[str, Any] = field(default_factory=dict)
    defaults: tuple[ParsedItem, ...] = ()

    def successors(self, node_id: str) -> list[str]:
        """Return unique scene IDs immediately reachable from node_id."""
        seen: set[str] = set()
        res: list[str] = []
        for edge in self.edges:
            if edge.source == node_id and edge.target not in seen:
                seen.add(edge.target)
                res.append(edge.target)
        return res

    def predecessors(self, node_id: str) -> list[str]:
        """Return unique scene IDs that transition directly into node_id."""
        seen: set[str] = set()
        res: list[str] = []
        for edge in self.edges:
            if edge.target == node_id and edge.source not in seen:
                seen.add(edge.source)
                res.append(edge.source)
        return res

    def reachable_from(self, node_id: str) -> set[str]:
        """Return all scene IDs reachable by traversing transitions from node_id."""
        if node_id not in self.nodes:
            return set()
        visited: set[str] = {node_id}
        queue: deque[str] = deque([node_id])
        while queue:
            curr = queue.popleft()
            for nxt in self.successors(curr):
                if nxt in self.nodes and nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return visited

    def is_reachable(self, node_id: str) -> bool:
        """Return True if node_id is reachable from the graph entry point."""
        if not self.entry:
            return False
        return node_id in self.reachable_from(self.entry)

    def dead_ends(self) -> list[str]:
        """Return scene IDs with no outgoing transitions (excluding anonymous scenes)."""
        return [nid for nid, node in self.nodes.items() if not node.is_anonymous and not self.successors(nid)]

    def hubs(self, threshold: int = 2) -> list[str]:
        """Return scene IDs with in-degree (predecessors) >= threshold."""
        return [nid for nid in self.nodes if len(self.predecessors(nid)) >= threshold]

    def branching_points(self) -> list[str]:
        """Return scene IDs with more than one outgoing transition."""
        return [nid for nid in self.nodes if len(self.successors(nid)) > 1]

    def anonymous_scenes(self) -> list[str]:
        """Return scene IDs that were lowered from inline choice blocks."""
        return [nid for nid, node in self.nodes.items() if node.is_anonymous]

    def terminal_scenes(self) -> list[str]:
        """Return reachable scenes that end the story (no outgoing transitions and no return)."""
        from eager.script.ast import ParsedReturn

        terminals: list[str] = []
        for nid in self.nodes:
            if self.is_reachable(nid) and not self.successors(nid):
                node = self.nodes[nid]
                has_return = any(isinstance(item, ParsedReturn) for item in node.body)
                if not has_return:
                    terminals.append(nid)
        return terminals


def _lower_scene_body(body: list[ParsedItem]) -> tuple[ParsedItem, ...]:
    """Lower nested @if/@elif/@else/@end blocks into flat ParsedCondJump and ParsedLocalJump."""
    from eager.script.ast import (
        ParsedCondJump,
        ParsedElif,
        ParsedElse,
        ParsedEnd,
        ParsedIf,
        ParsedLocalJump,
    )

    # Check if there are any if-directives to lower
    has_if = any(isinstance(item, (ParsedIf, ParsedElif, ParsedElse, ParsedEnd)) for item in body)
    if not has_if:
        return tuple(body)

    # We do a lowering pass.
    # We can model @if as a block tree first, then flatten with target indices.
    # Block structure:
    # An if-structure consists of:
    # branches: list of (condition: str | None, body_items: list[Any])
    # where condition is None for @else.
    
    # Recursive lowering helper
    def parse_blocks(items: list[ParsedItem], idx: int = 0) -> tuple[list[Any], int]:
        out: list[Any] = []
        i = idx
        while i < len(items):
            item = items[i]
            if isinstance(item, ParsedIf):
                # Start of if-structure
                branches: list[tuple[str | None, list[Any], int, int, int]] = []
                curr_cond: str | None = item.expr_src
                curr_line = item.line_number
                curr_start = item.start_col
                curr_end = item.end_col
                curr_branch_body: list[Any] = []
                i += 1
                closed = False
                while i < len(items):
                    sub = items[i]
                    if isinstance(sub, ParsedIf):
                        # Nested if!
                        nested_blocks, next_i = parse_blocks(items, i)
                        curr_branch_body.extend(nested_blocks)
                        i = next_i
                    elif isinstance(sub, ParsedElif):
                        branches.append((curr_cond, curr_branch_body, curr_line, curr_start, curr_end))
                        curr_cond = sub.expr_src
                        curr_line = sub.line_number
                        curr_start = sub.start_col
                        curr_end = sub.end_col
                        curr_branch_body = []
                        i += 1
                    elif isinstance(sub, ParsedElse):
                        branches.append((curr_cond, curr_branch_body, curr_line, curr_start, curr_end))
                        curr_cond = None
                        curr_line = sub.line_number
                        curr_start = sub.start_col
                        curr_end = sub.end_col
                        curr_branch_body = []
                        i += 1
                    elif isinstance(sub, ParsedEnd):
                        branches.append((curr_cond, curr_branch_body, curr_line, curr_start, curr_end))
                        closed = True
                        i += 1
                        break
                    else:
                        curr_branch_body.append(sub)
                        i += 1
                if not closed and (curr_branch_body or curr_cond is not None):
                    branches.append((curr_cond, curr_branch_body, curr_line, curr_start, curr_end))
                out.append(("if_structure", branches))
            elif isinstance(item, (ParsedElif, ParsedElse, ParsedEnd)):
                # Return out to parent if-block parser
                return out, i
            else:
                out.append(item)
                i += 1
        return out, i

    structured_items, _ = parse_blocks(body)

    # Flatten structured items into flat list with indices
    flat: list[ParsedItem] = []

    def flatten(elements: list[Any]) -> None:
        for elem in elements:
            if isinstance(elem, tuple):
                if elem[0] == "if_structure":
                    branches = elem[1]
                    end_placeholder_patches: list[int] = []
                    for b_idx, (cond, b_body, line_no, start_col, end_col) in enumerate(branches):
                        is_last = (b_idx == len(branches) - 1)
                        cond_patch_idx: int | None = None
                        if cond is not None:
                            cond_patch_idx = len(flat)
                            flat.append(
                                ParsedCondJump(
                                    condition=cond,
                                    target_index=0,
                                    line_number=line_no,
                                    start_col=start_col,
                                    end_col=end_col,
                                    )
                            )
                        
                        flatten(b_body)

                        if not is_last:
                            local_patch_idx = len(flat)
                            flat.append(
                                ParsedLocalJump(
                                    target_index=0,
                                    line_number=line_no,
                                    start_col=start_col,
                                    end_col=end_col,
                                )
                            )
                            end_placeholder_patches.append(local_patch_idx)

                        # Next branch starts here at len(flat)
                        if cond_patch_idx is not None:
                            target_cond = flat[cond_patch_idx]
                            if isinstance(target_cond, ParsedCondJump):
                                flat[cond_patch_idx] = ParsedCondJump(
                                    condition=target_cond.condition,
                                    target_index=len(flat),
                                    line_number=target_cond.line_number,
                                    start_col=target_cond.start_col,
                                    end_col=target_cond.end_col,
                                )
                    # All branches finish here: len(flat) is end
                    end_idx = len(flat)
                    for patch_idx in end_placeholder_patches:
                        target_local = flat[patch_idx]
                        flat[patch_idx] = ParsedLocalJump(
                            target_index=end_idx,
                            line_number=target_local.line_number,
                            start_col=target_local.start_col,
                            end_col=target_local.end_col,
                        )
            else:
                flat.append(elem)

    flatten(structured_items)
    return tuple(flat)


def _process_scene_body(
    body: list[ParsedItem],
    scene_id: str,
    nodes: dict[str, SceneNode],
    edges: list[SceneEdge],
) -> tuple[tuple[ParsedItem, ...], tuple[str, ...], tuple[str, ...]]:
    """Lower one scene body, flattening ``@if`` blocks and resolving inline choices.

    Consecutive transition edges (jumps, calls, choices) are emitted as each item is
    inspected while the enclosing ``@if`` condition stack is active.  An inline choice
    option is lowered into an anonymous :class:`SceneNode` (whose body ends in an
    implicit return) and the option's ``target`` is rewritten to that anonymous scene
    id so the runtime can branch into it and resume after the menu.

    Returns the flattened body along with its ordered unique speakers and hooks.
    """
    from eager.script.ast import (
        ParsedCall,
        ParsedChoiceSet,
        ParsedDialogue,
        ParsedElif,
        ParsedElse,
        ParsedEnd,
        ParsedHook,
        ParsedIf,
        ParsedJump,
        ParsedReturn,
    )

    flat: list[ParsedItem] = []
    flat_append = flat.append
    speakers: list[str] = []
    speakers_append = speakers.append
    seen_speakers: set[str] = set()
    hooks: list[str] = []
    hooks_append = hooks.append
    seen_hooks: set[str] = set()

    branch_stack: list[tuple[list[str], str | None]] = []

    def _active_cond() -> str | None:
        level_conds: list[str] = []
        for priors, current in branch_stack:
            parts = [f"not ({p})" for p in priors]
            if current is not None:
                parts.append(current)
            if not parts:
                continue
            if len(parts) == 1:
                level_conds.append(parts[0])
            else:
                level_conds.append(" and ".join(f"({p})" for p in parts))
        if not level_conds:
            return None
        if len(level_conds) == 1:
            return level_conds[0]
        return " and ".join(f"({c})" for c in level_conds)

    for item in body:
        if isinstance(item, ParsedJump):
            flat_append(item)
            edges.append(SceneEdge(scene_id, item.target, EdgeKind.JUMP, None, item.line_number, condition=_active_cond()))
        elif isinstance(item, ParsedCall):
            flat_append(item)
            edges.append(SceneEdge(scene_id, item.target, EdgeKind.CALL, None, item.line_number, condition=_active_cond()))
        elif isinstance(item, ParsedChoiceSet):
            active = _active_cond()
            resolved_options: list[Any] = []
            for opt in item.options:
                opt_cond = opt.condition
                if active:
                    opt_cond = f"{active} and ({opt.condition})" if opt.condition else active
                if opt.body:
                    anon_id = _anon_scene_id(scene_id, opt.line_number)
                    edges.append(
                        SceneEdge(scene_id, anon_id, EdgeKind.CHOICE, opt.text, opt.line_number, condition=opt_cond)
                    )
                    anon_body, anon_speakers, anon_hooks = _process_scene_body(
                        list(opt.body), anon_id, nodes, edges
                    )
                    anon_body = anon_body + (ParsedReturn(line_number=opt.line_number),)
                    nodes[anon_id] = SceneNode(
                        anon_id,
                        opt.text,
                        opt.line_number,
                        anon_body,
                        anon_speakers,
                        anon_hooks,
                        True,
                    )
                    resolved_options.append(replace(opt, target=anon_id))
                elif opt.target is not None:
                    edges.append(
                        SceneEdge(scene_id, opt.target, EdgeKind.CHOICE, opt.text, opt.line_number, condition=opt_cond)
                    )
                    resolved_options.append(opt)
                else:
                    resolved_options.append(opt)
            flat_append(replace(item, options=tuple(resolved_options)))
        elif isinstance(item, ParsedDialogue):
            flat_append(item)
            spk = item.speaker
            if spk not in seen_speakers:
                seen_speakers.add(spk)
                speakers_append(spk)
        elif isinstance(item, ParsedHook):
            flat_append(item)
            h = item.hook_name
            if h not in seen_hooks:
                seen_hooks.add(h)
                hooks_append(h)
        elif isinstance(item, ParsedIf):
            branch_stack.append(([], item.expr_src))
            flat_append(item)
        elif isinstance(item, ParsedElif):
            if branch_stack:
                priors, current = branch_stack[-1]
                if current is not None:
                    priors.append(current)
                branch_stack[-1] = (priors, item.expr_src)
            flat_append(item)
        elif isinstance(item, ParsedElse):
            if branch_stack:
                priors, current = branch_stack[-1]
                if current is not None:
                    priors.append(current)
                branch_stack[-1] = (priors, None)
            flat_append(item)
        elif isinstance(item, ParsedEnd):
            if branch_stack:
                branch_stack.pop()
            flat_append(item)
        else:
            flat_append(item)

    return (
        _lower_scene_body(flat),
        tuple(speakers),
        tuple(hooks),
    )


def to_graph(items: Sequence[ParsedItem] | Iterable[ParsedItem]) -> SceneGraph:
    """Build a SceneGraph from a sequence or iterator of parsed AST items.

    Inline choice blocks (indented reactions beneath a ``?`` option) are lowered into
    anonymous scenes by :func:`_process_scene_body`.
    """
    from eager.script.ast import (
        ParsedCharacter,
        ParsedDefault,
        ParsedInclude,
        ParsedLabel,
    )

    preamble: list[ParsedItem] = []
    characters: dict[str, Any] = {}
    defaults: list[ParsedDefault] = []

    first_label: ParsedLabel | None = None
    scene_order: list[tuple[ParsedLabel, list[ParsedItem]]] = []
    current_body: list[ParsedItem] = []

    for item in items:
        if getattr(item, "type", "") == "error":
            continue

        if type(item) is ParsedLabel:
            if first_label is None:
                first_label = item
            else:
                scene_order.append((first_label, current_body))
                first_label = item
                current_body = []
            continue

        if isinstance(item, ParsedInclude):
            continue

        if isinstance(item, ParsedCharacter):
            characters[item.id] = {
                "name": item.name,
                "attrs": dict(item.attrs),
                "line_number": item.line_number,
            }
            preamble.append(item)
            continue
        if isinstance(item, ParsedDefault):
            defaults.append(item)
            preamble.append(item)
            continue

        if first_label is None:
            preamble.append(item)
        else:
            current_body.append(item)

    if first_label is None:
        return SceneGraph(
            entry=None,
            nodes={},
            edges=(),
            preamble=tuple(preamble) if preamble else (),
            characters=characters,
            defaults=tuple(defaults),
        )

    scene_order.append((first_label, current_body))

    nodes: dict[str, SceneNode] = {}
    edges: list[SceneEdge] = []
    entry = scene_order[0][0].name

    for label, body in scene_order:
        lowered, speakers, hooks = _process_scene_body(body, label.name, nodes, edges)
        nodes[label.name] = SceneNode(
            label.name,
            label.display_name,
            label.line_number,
            lowered,
            speakers,
            hooks,
        )

    return SceneGraph(
        entry=entry,
        nodes=nodes,
        edges=tuple(edges),
        preamble=tuple(preamble) if preamble else (),
        characters=characters,
        defaults=tuple(defaults),
    )


def parse_graph(text: str) -> SceneGraph:
    """Parse screenplay text directly into a SceneGraph."""
    from eager.script.parser import parse

    return to_graph(parse(text))

