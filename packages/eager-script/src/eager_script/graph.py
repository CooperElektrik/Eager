"""Directed scene graph model and transformation for Eager-S screenplay AST."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager_script import ParsedItem


@dataclass(frozen=True, slots=True)
class SceneNode:
    """A scene (label block) in the narrative graph."""

    id: str
    display_name: str
    line_number: int
    body: tuple[ParsedItem, ...]
    speakers: tuple[str, ...]
    hooks: tuple[str, ...]

    def to_dict(self, include_body: bool = True) -> dict[str, Any]:
        """Convert scene node to a dictionary."""
        data: dict[str, Any] = {
            "id": self.id,
            "display_name": self.display_name,
            "line_number": self.line_number,
            "speakers": list(self.speakers),
            "hooks": list(self.hooks),
        }
        if include_body:
            data["body"] = [item.to_dict() for item in self.body]
        return data


@dataclass(frozen=True, slots=True)
class SceneEdge:
    """A directed transition between scenes."""

    source: str
    target: str
    kind: str  # "jump" | "call" | "choice"
    label: str | None
    line_number: int
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert edge to a dictionary."""
        data: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "label": self.label,
            "line_number": self.line_number,
        }
        if self.condition is not None:
            data["condition"] = self.condition
        return data


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
        """Return scene IDs with no outgoing transitions."""
        return [nid for nid in self.nodes if not self.successors(nid)]

    def hubs(self, threshold: int = 2) -> list[str]:
        """Return scene IDs with in-degree (predecessors) >= threshold."""
        return [nid for nid in self.nodes if len(self.predecessors(nid)) >= threshold]

    def branching_points(self) -> list[str]:
        """Return scene IDs with more than one outgoing transition."""
        return [nid for nid in self.nodes if len(self.successors(nid)) > 1]

    def terminal_scenes(self) -> list[str]:
        """Return reachable scenes that end the story (no outgoing transitions and no return)."""
        from eager_script import ParsedReturn

        terminals: list[str] = []
        for nid in self.nodes:
            if self.is_reachable(nid) and not self.successors(nid):
                node = self.nodes[nid]
                has_return = any(isinstance(item, ParsedReturn) for item in node.body)
                if not has_return:
                    terminals.append(nid)
        return terminals

    def to_dict(self, include_body: bool = True) -> dict[str, Any]:
        """Convert graph into a JSON-serializable dictionary."""
        data: dict[str, Any] = {
            "entry": self.entry,
            "preamble": [item.to_dict() for item in self.preamble] if include_body else [],
            "nodes": {
                nid: node.to_dict(include_body=include_body) for nid, node in self.nodes.items()
            },
            "edges": [edge.to_dict() for edge in self.edges],
            "characters": self.characters,
            "defaults": [d.to_dict() for d in self.defaults],
        }
        return data

    def to_json(self, include_body: bool = True, indent: int | None = 2) -> str:
        """Serialize scene graph to a JSON string."""
        import json

        return json.dumps(self.to_dict(include_body=include_body), indent=indent)

    def to_dot(self) -> str:
        """Export scene graph to Graphviz DOT format."""
        lines = [
            "digraph SceneGraph {",
            '  rankdir="LR";',
            '  node [shape="box", style="rounded,filled", fillcolor="#f9f9f9", fontname="sans-serif"];',
            '  edge [fontname="sans-serif", fontsize=10];',
            "",
        ]

        for nid, node in self.nodes.items():
            label_text = f"{node.display_name}\\n({node.id})"
            safe_label = label_text.replace('"', '\\"')
            safe_nid = nid.replace('"', '\\"')
            if nid == self.entry:
                lines.append(
                    f'  "{safe_nid}" [label="{safe_label}", penwidth=2.0, color="#1976d2"];'
                )
            else:
                lines.append(f'  "{safe_nid}" [label="{safe_label}"];')

        if self.nodes and self.edges:
            lines.append("")

        for edge in self.edges:
            safe_src = edge.source.replace('"', '\\"')
            safe_tgt = edge.target.replace('"', '\\"')
            attrs: list[str] = []
            if edge.kind == "choice" and edge.label:
                safe_edge_label = edge.label.replace('"', '\\"')
                if edge.condition:
                    safe_edge_label += f" [if {edge.condition}]"
                attrs.append(f'label="{safe_edge_label}"')
            elif edge.kind == "call":
                attrs.append('label="call"')
                attrs.append('style="dashed"')

            attr_str = f" [{', '.join(attrs)}]" if attrs else ""
            lines.append(f'  "{safe_src}" -> "{safe_tgt}"{attr_str};')

        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """Export scene graph to Mermaid flowchart format."""
        lines = ["flowchart TD"]

        for nid, node in self.nodes.items():
            safe_label = node.display_name.replace('"', "'")
            lines.append(f'    {nid}["{safe_label}"]')

        for edge in self.edges:
            src = edge.source
            tgt = edge.target
            if edge.kind == "choice":
                if edge.label:
                    lbl = edge.label
                    if edge.condition:
                        lbl += f" (if {edge.condition})"
                    safe_choice = lbl.replace("|", "/").replace('"', "'")
                    lines.append(f"    {src} -->|{safe_choice}| {tgt}")
                else:
                    lines.append(f"    {src} --> {tgt}")
            elif edge.kind == "call":
                lines.append(f"    {src} -.->|call| {tgt}")
            else:
                lines.append(f"    {src} --> {tgt}")

        return "\n".join(lines)


def _lower_scene_body(body: list[ParsedItem]) -> tuple[ParsedItem, ...]:
    """Lower nested @if/@elif/@else/@end blocks into flat ParsedCondJump and ParsedLocalJump."""
    from eager_script import (
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
                branches: list[tuple[str | None, list[Any], int]] = []
                curr_cond: str | None = item.expr_src
                curr_line = item.line_number
                curr_branch_body: list[Any] = []
                i += 1
                while i < len(items):
                    sub = items[i]
                    if isinstance(sub, ParsedIf):
                        # Nested if!
                        nested_blocks, next_i = parse_blocks(items, i)
                        curr_branch_body.extend(nested_blocks)
                        i = next_i
                    elif isinstance(sub, ParsedElif):
                        branches.append((curr_cond, curr_branch_body, curr_line))
                        curr_cond = sub.expr_src
                        curr_line = sub.line_number
                        curr_branch_body = []
                        i += 1
                    elif isinstance(sub, ParsedElse):
                        branches.append((curr_cond, curr_branch_body, curr_line))
                        curr_cond = None
                        curr_line = sub.line_number
                        curr_branch_body = []
                        i += 1
                    elif isinstance(sub, ParsedEnd):
                        branches.append((curr_cond, curr_branch_body, curr_line))
                        i += 1
                        break
                    else:
                        curr_branch_body.append(sub)
                        i += 1
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
            if isinstance(elem, tuple) and elem[0] == "if_structure":
                branches = elem[1]
                # For each branch:
                # branch_k:
                #   if cond_k is not None:
                #     ParsedCondJump(cond_k, target = start of branch_{k+1} or end)
                #   body_k
                #   if not last branch: ParsedLocalJump(end)
                #
                # Notice we need indices, so we can do placeholder patching.
                end_placeholder_patches: list[int] = []
                for b_idx, (cond, b_body, line_no) in enumerate(branches):
                    is_last = (b_idx == len(branches) - 1)
                    cond_patch_idx: int | None = None
                    if cond is not None:
                        cond_patch_idx = len(flat)
                        flat.append(ParsedCondJump(condition=cond, target_index=0, line_number=line_no))
                    
                    flatten(b_body)

                    if not is_last:
                        local_patch_idx = len(flat)
                        flat.append(ParsedLocalJump(target_index=0, line_number=line_no))
                        end_placeholder_patches.append(local_patch_idx)

                    # Next branch starts here at len(flat)
                    if cond_patch_idx is not None:
                        flat[cond_patch_idx] = ParsedCondJump(
                            condition=flat[cond_patch_idx].condition,  # type: ignore[attr-defined]
                            target_index=len(flat),
                            line_number=flat[cond_patch_idx].line_number,  # type: ignore[attr-defined]
                        )
                # All branches finish here: len(flat) is end
                end_idx = len(flat)
                for patch_idx in end_placeholder_patches:
                    flat[patch_idx] = ParsedLocalJump(
                        target_index=end_idx,
                        line_number=flat[patch_idx].line_number,  # type: ignore[attr-defined]
                    )
            else:
                flat.append(elem)

    flatten(structured_items)
    return tuple(flat)


def to_graph(items: Sequence[ParsedItem] | Iterable[ParsedItem]) -> SceneGraph:
    """Build a SceneGraph from a sequence or iterator of parsed AST items."""
    from eager_script import (
        ParsedCall,
        ParsedCharacter,
        ParsedChoiceSet,
        ParsedDefault,
        ParsedDialogue,
        ParsedHook,
        ParsedJump,
        ParsedLabel,
        ParsedNarration,
    )

    preamble: list[ParsedItem] = []
    characters: dict[str, Any] = {}
    defaults: list[ParsedDefault] = []
    preamble_append = preamble.append

    item_iter = iter(items)
    current_label: ParsedLabel | None = None

    for item in item_iter:
        if type(item) is ParsedLabel:
            current_label = item
            break
        if isinstance(item, ParsedCharacter):
            characters[item.id] = {
                "name": item.name,
                "attrs": dict(item.attrs),
                "line_number": item.line_number,
            }
        elif isinstance(item, ParsedDefault):
            defaults.append(item)
        preamble_append(item)

    if current_label is None:
        return SceneGraph(
            entry=None,
            nodes={},
            edges=(),
            preamble=tuple(preamble) if preamble else (),
            characters=characters,
            defaults=tuple(defaults),
        )

    nodes: dict[str, SceneNode] = {}
    edges: list[SceneEdge] = []
    edges_append = edges.append

    current_label_name = current_label.name
    entry = current_label_name

    current_body: list[ParsedItem] = []
    current_body_append = current_body.append
    current_speakers: list[str] = []
    current_speakers_append = current_speakers.append
    seen_speakers: set[str] = set()
    seen_speakers_add = seen_speakers.add
    current_hooks: list[str] = []
    current_hooks_append = current_hooks.append
    seen_hooks: set[str] = set()
    seen_hooks_add = seen_hooks.add

    from eager_script import ParsedElif, ParsedElse, ParsedEnd, ParsedIf

    cond_stack: list[str] = []

    def _active_cond() -> str | None:
        if not cond_stack:
            return None
        valid = [c for c in cond_stack if c]
        if not valid:
            return None
        if len(valid) == 1:
            return valid[0]
        return " and ".join(f"({c})" for c in valid)

    for item in item_iter:
        if type(item) is ParsedNarration:
            current_body_append(item)
        elif type(item) is ParsedDialogue:
            current_body_append(item)
            spk = item.speaker
            if spk not in seen_speakers:
                seen_speakers_add(spk)
                current_speakers_append(spk)
        elif type(item) is ParsedLabel:
            cond_stack.clear()
            lowered_body = _lower_scene_body(current_body)
            nodes[current_label_name] = SceneNode(
                current_label_name,
                current_label.display_name,
                current_label.line_number,
                lowered_body,
                tuple(current_speakers) if current_speakers else (),
                tuple(current_hooks) if current_hooks else (),
            )
            current_label = item
            current_label_name = item.name
            current_body.clear()
            if current_speakers:
                current_speakers.clear()
                seen_speakers.clear()
            if current_hooks:
                current_hooks.clear()
                seen_hooks.clear()
        elif type(item) is ParsedJump:
            current_body_append(item)
            edges_append(SceneEdge(current_label_name, item.target, "jump", None, item.line_number, condition=_active_cond()))
        elif type(item) is ParsedHook:
            current_body_append(item)
            h = item.hook_name
            if h not in seen_hooks:
                seen_hooks_add(h)
                current_hooks_append(h)
        elif type(item) is ParsedChoiceSet:
            current_body_append(item)
            active = _active_cond()
            for opt in item.options:
                opt_cond = opt.condition
                if active:
                    opt_cond = f"{active} and ({opt.condition})" if opt.condition else active
                edges_append(
                    SceneEdge(
                        current_label_name,
                        opt.target,
                        "choice",
                        opt.text,
                        opt.line_number,
                        condition=opt_cond,
                    )
                )
        elif type(item) is ParsedCall:
            current_body_append(item)
            edges_append(SceneEdge(current_label_name, item.target, "call", None, item.line_number, condition=_active_cond()))
        elif type(item) is ParsedIf:
            cond_stack.append(item.expr_src)
            current_body_append(item)
        elif type(item) is ParsedElif:
            if cond_stack:
                cond_stack[-1] = item.expr_src
            current_body_append(item)
        elif type(item) is ParsedElse:
            if cond_stack and cond_stack[-1]:
                cond_stack[-1] = f"not ({cond_stack[-1]})"
            current_body_append(item)
        elif type(item) is ParsedEnd:
            if cond_stack:
                cond_stack.pop()
            current_body_append(item)
        elif type(item) is ParsedCharacter:
            characters[item.id] = {
                "name": item.name,
                "attrs": dict(item.attrs),
                "line_number": item.line_number,
            }
            preamble_append(item)
        elif type(item) is ParsedDefault:
            defaults.append(item)
            preamble_append(item)
        else:
            current_body_append(item)

    assert current_label is not None
    lowered_body = _lower_scene_body(current_body)
    nodes[current_label_name] = SceneNode(
        current_label_name,
        current_label.display_name,
        current_label.line_number,
        lowered_body,
        tuple(current_speakers) if current_speakers else (),
        tuple(current_hooks) if current_hooks else (),
    )

    return SceneGraph(
        entry=entry,
        nodes=nodes,
        edges=tuple(edges),
        preamble=tuple(preamble) if preamble else (),
        characters=characters,
        defaults=tuple(defaults),
    )


def parse_graph(text: str, *, plain: bool = False) -> SceneGraph:
    """Parse screenplay text directly into a SceneGraph."""
    from eager_script import parse

    return to_graph(parse(text, plain=plain))

