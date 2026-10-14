"""Directed scene graph model and transformation for Eager-Script screenplay AST."""

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

    def to_html(self, title: str = "Scene Graph") -> str:
        """Export scene graph to a self-contained, interactive HTML document."""
        import html
        import json

        safe_title = html.escape(title)
        mermaid_src = self.to_mermaid()

        entry_node = self.entry or ""
        branch_nodes = set(self.branching_points())
        hub_nodes = set(self.hubs())
        terminal_nodes = set(self.terminal_scenes())
        dead_end_nodes = set(self.dead_ends())

        nodes_meta: list[dict[str, Any]] = []
        for nid, node in self.nodes.items():
            tags: list[str] = []
            if nid == entry_node:
                tags.append("entry")
            if nid in branch_nodes:
                tags.append("branch")
            if nid in hub_nodes:
                tags.append("hub")
            if nid in terminal_nodes:
                tags.append("terminal")
            elif nid in dead_end_nodes:
                tags.append("dead_end")

            # Extract dialogue/narration excerpts for quick preview
            body_previews: list[str] = []
            for item in node.body:
                item_dict = item.to_dict()
                itype = item_dict.get("type")
                if itype == "dialogue":
                    spk = item_dict.get("speaker", "")
                    txt = item_dict.get("text", "")
                    body_previews.append(f"{spk}: {txt}")
                elif itype == "narration":
                    txt = item_dict.get("text", "")
                    body_previews.append(txt)
                elif itype == "choice":
                    opts = item_dict.get("options", [])
                    opt_labels = [f"? {o.get('text', '')}" for o in opts]
                    body_previews.extend(opt_labels)
                if len(body_previews) >= 6:
                    break

            incoming = [
                {
                    "source": e.source,
                    "kind": e.kind,
                    "label": e.label,
                    "condition": e.condition,
                }
                for e in self.edges
                if e.target == nid
            ]
            outgoing = [
                {
                    "target": e.target,
                    "kind": e.kind,
                    "label": e.label,
                    "condition": e.condition,
                }
                for e in self.edges
                if e.source == nid
            ]

            nodes_meta.append(
                {
                    "id": nid,
                    "display_name": node.display_name,
                    "line_number": node.line_number,
                    "speakers": list(node.speakers),
                    "hooks": list(node.hooks),
                    "tags": tags,
                    "incoming": incoming,
                    "outgoing": outgoing,
                    "preview": body_previews,
                }
            )

        meta_json = json.dumps(nodes_meta)
        escaped_mermaid = html.escape(mermaid_src)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} - Eager Scene Graph</title>
  <style>
    :root {{
      --bg: #0f111a;
      --panel: #181b2a;
      --panel-hover: #22263d;
      --border: #2a2f4c;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-border: #60a5fa;
      --badge-entry: #3b82f6;
      --badge-branch: #f59e0b;
      --badge-hub: #8b5cf6;
      --badge-term: #10b981;
      --badge-dead: #ef4444;
      --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-ui);
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 10px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-shrink: 0;
    }}
    .header-title {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .stats-bar {{
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 12px;
      color: var(--text-muted);
    }}
    .stat-pill {{
      background: #101321;
      border: 1px solid var(--border);
      padding: 3px 8px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }}
    .stat-pill strong {{ color: #fff; }}
    .main-layout {{
      display: flex;
      flex: 1;
      height: calc(100vh - 51px);
      overflow: hidden;
    }}
    .sidebar-left {{
      width: 320px;
      background: var(--panel);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }}
    .sidebar-header {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
    }}
    .search-input {{
      width: 100%;
      background: #0f111a;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 7px 10px;
      border-radius: 4px;
      font-size: 13px;
      font-family: var(--font-ui);
      outline: none;
    }}
    .search-input:focus {{
      border-color: var(--primary);
    }}
    .scene-list {{
      flex: 1;
      overflow-y: auto;
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .scene-item {{
      background: #141724;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 8px 10px;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }}
    .scene-item:hover {{
      background: var(--panel-hover);
      border-color: #3b4267;
    }}
    .scene-item.active {{
      background: #1e2540;
      border-color: var(--primary);
    }}
    .scene-item-title {{
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .scene-item-id {{
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .badge {{
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: var(--font-mono);
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.5px;
    }}
    .badge-entry {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }}
    .badge-branch {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-hub {{ background: rgba(139, 92, 246, 0.2); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.4); }}
    .badge-terminal {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-dead_end {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge-tag-row {{ display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }}

    .center-canvas {{
      flex: 1;
      position: relative;
      background: var(--bg);
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .canvas-viewport {{
      width: 100%;
      height: 100%;
      cursor: grab;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .canvas-viewport:active {{
      cursor: grabbing;
    }}
    .canvas-content {{
      transform-origin: center center;
      transition: transform 0.05s ease-out;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .floating-toolbar {{
      position: absolute;
      top: 14px;
      right: 14px;
      display: flex;
      gap: 6px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 4px;
      z-index: 10;
    }}
    .tool-btn {{
      background: transparent;
      border: 1px solid transparent;
      color: var(--text);
      padding: 4px 8px;
      font-size: 12px;
      border-radius: 4px;
      cursor: pointer;
      font-family: var(--font-mono);
      transition: background 0.15s;
    }}
    .tool-btn:hover {{
      background: var(--panel-hover);
      border-color: var(--border);
    }}

    .sidebar-right {{
      width: 360px;
      background: var(--panel);
      border-left: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
      overflow-y: auto;
    }}
    .inspector-header {{
      padding: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .inspector-title {{
      font-size: 16px;
      font-weight: 700;
      color: #fff;
    }}
    .inspector-id {{
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    .inspector-section {{
      padding: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .section-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 8px;
      font-weight: 700;
    }}
    .transition-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .transition-card {{
      background: #141724;
      border: 1px solid var(--border);
      padding: 6px 8px;
      border-radius: 4px;
      font-size: 12px;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .transition-card:hover {{
      background: var(--panel-hover);
    }}
    .transition-card .tgt {{
      font-family: var(--font-mono);
      color: var(--primary-border);
      font-weight: 600;
    }}
    .transition-card .lbl {{
      color: var(--text);
      margin-top: 2px;
    }}
    .transition-card .cond {{
      color: #f59e0b;
      font-family: var(--font-mono);
      font-size: 11px;
    }}
    .pill-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .pill {{
      background: #141724;
      border: 1px solid var(--border);
      padding: 3px 6px;
      border-radius: 4px;
      font-size: 11px;
      font-family: var(--font-mono);
    }}
    .preview-box {{
      background: #101321;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.5;
      color: #cbd5e1;
      max-height: 220px;
      overflow-y: auto;
      font-family: var(--font-mono);
      white-space: pre-wrap;
    }}
    .fallback-view {{
      padding: 24px;
      color: var(--text);
      max-width: 800px;
      text-align: left;
    }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body>
  <header>
    <div class="header-title">
      <span>Eager Scene Graph:</span>
      <span style="color: var(--primary-border);">{safe_title}</span>
    </div>
    <div class="stats-bar">
      <div class="stat-pill">Scenes: <strong>{len(self.nodes)}</strong></div>
      <div class="stat-pill">Transitions: <strong>{len(self.edges)}</strong></div>
      <div class="stat-pill">Branch Points: <strong>{len(branch_nodes)}</strong></div>
      <div class="stat-pill">Hubs: <strong>{len(hub_nodes)}</strong></div>
      <div class="stat-pill">Terminals: <strong>{len(terminal_nodes)}</strong></div>
    </div>
  </header>

  <div class="main-layout">
    <!-- Left: Scene Navigator -->
    <div class="sidebar-left">
      <div class="sidebar-header">
        <input type="text" id="search-input" class="search-input" placeholder="Search scene title, ID, speaker...">
      </div>
      <div class="scene-list" id="scene-list"></div>
    </div>

    <!-- Center: Interactive Graph -->
    <div class="center-canvas">
      <div class="floating-toolbar">
        <button class="tool-btn" id="btn-zoom-in">[+]</button>
        <button class="tool-btn" id="btn-zoom-out">[-]</button>
        <button class="tool-btn" id="btn-zoom-reset">[1:1]</button>
        <button class="tool-btn" id="btn-copy-mermaid">[Copy Mermaid]</button>
      </div>
      <div class="canvas-viewport" id="viewport">
        <div class="canvas-content" id="canvas-content">
          <div class="mermaid" id="mermaid-graph">
{escaped_mermaid}
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Scene Inspector -->
    <div class="sidebar-right" id="inspector">
      <div class="inspector-header">
        <div class="inspector-title" id="insp-title">Select a Scene</div>
        <div class="inspector-id" id="insp-id">Click a scene in the list or graph to inspect</div>
        <div class="badge-tag-row" id="insp-badges"></div>
      </div>
      <div class="inspector-section">
        <div class="section-label">Outgoing Transitions</div>
        <div class="transition-list" id="insp-outgoing">
          <div style="font-size: 12px; color: var(--text-muted);">None</div>
        </div>
      </div>
      <div class="inspector-section">
        <div class="section-label">Incoming Transitions</div>
        <div class="transition-list" id="insp-incoming">
          <div style="font-size: 12px; color: var(--text-muted);">None</div>
        </div>
      </div>
      <div class="inspector-section">
        <div class="section-label">Characters / Speakers</div>
        <div class="pill-list" id="insp-speakers">
          <div style="font-size: 12px; color: var(--text-muted);">None</div>
        </div>
      </div>
      <div class="inspector-section">
        <div class="section-label">Engine Hooks</div>
        <div class="pill-list" id="insp-hooks">
          <div style="font-size: 12px; color: var(--text-muted);">None</div>
        </div>
      </div>
      <div class="inspector-section">
        <div class="section-label">Dialogue & Beats Preview</div>
        <div class="preview-box" id="insp-preview">No scene selected.</div>
      </div>
    </div>
  </div>

  <script id="nodes-data" type="application/json">{meta_json}</script>
  <script>
    const nodes = JSON.parse(document.getElementById('nodes-data').textContent);
    const nodesById = new Map(nodes.map(n => [n.id, n]));
    let selectedId = nodes.length > 0 ? nodes[0].id : null;

    // Pan & Zoom
    let scale = 1.0;
    let panX = 0;
    let panY = 0;
    let isDragging = false;
    let startX = 0;
    let startY = 0;

    const viewport = document.getElementById('viewport');
    const content = document.getElementById('canvas-content');

    function updateTransform() {{
      content.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
    }}

    viewport.addEventListener('mousedown', (e) => {{
      if (e.target.closest('.floating-toolbar') || e.target.closest('.node')) return;
      isDragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
    }});

    window.addEventListener('mousemove', (e) => {{
      if (!isDragging) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      updateTransform();
    }});

    window.addEventListener('mouseup', () => {{
      isDragging = false;
    }});

    viewport.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      scale = Math.min(Math.max(0.2, scale * zoomFactor), 4.0);
      updateTransform();
    }}, {{ passive: false }});

    document.getElementById('btn-zoom-in').onclick = () => {{
      scale = Math.min(scale * 1.25, 4.0);
      updateTransform();
    }};
    document.getElementById('btn-zoom-out').onclick = () => {{
      scale = Math.max(scale / 1.25, 0.2);
      updateTransform();
    }};
    document.getElementById('btn-zoom-reset').onclick = () => {{
      scale = 1.0;
      panX = 0;
      panY = 0;
      updateTransform();
    }};
    document.getElementById('btn-copy-mermaid').onclick = () => {{
      const text = document.getElementById('mermaid-graph').textContent;
      navigator.clipboard.writeText(text.trim()).then(() => {{
        const btn = document.getElementById('btn-copy-mermaid');
        const prev = btn.textContent;
        btn.textContent = '[Copied!]';
        setTimeout(() => {{ btn.textContent = prev; }}, 1500);
      }});
    }};

    // Render Scene List
    const sceneListEl = document.getElementById('scene-list');
    function renderSceneList(filter = '') {{
      sceneListEl.innerHTML = '';
      const lowerFilter = filter.toLowerCase().trim();

      nodes.forEach(node => {{
        const matchTitle = node.display_name.toLowerCase().includes(lowerFilter);
        const matchId = node.id.toLowerCase().includes(lowerFilter);
        const matchSpk = node.speakers.some(s => s.toLowerCase().includes(lowerFilter));
        if (lowerFilter && !matchTitle && !matchId && !matchSpk) return;

        const item = document.createElement('div');
        item.className = 'scene-item' + (node.id === selectedId ? ' active' : '');
        item.onclick = () => selectScene(node.id);

        let tagsHtml = '';
        if (node.tags.length > 0) {{
          tagsHtml = '<div class="badge-tag-row">' +
            node.tags.map(t => `<span class="badge badge-${{t}}">[${{t}}]</span>`).join('') +
            '</div>';
        }}

        item.innerHTML = `
          <div class="scene-item-title">
            <span>${{escapeHtml(node.display_name)}}</span>
            <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">L${{node.line_number}}</span>
          </div>
          <div class="scene-item-id">${{escapeHtml(node.id)}}</div>
          ${{tagsHtml}}
        `;
        sceneListEl.appendChild(item);
      }});
    }}

    function selectScene(nid) {{
      selectedId = nid;
      const node = nodesById.get(nid);
      if (!node) return;

      // Update list active states
      document.querySelectorAll('.scene-item').forEach(el => {{
        const idEl = el.querySelector('.scene-item-id');
        if (idEl && idEl.textContent === nid) {{
          el.classList.add('active');
          el.scrollIntoView({{ block: 'nearest', behavior: 'smooth' }});
        }} else {{
          el.classList.remove('active');
        }}
      }});

      // Update Inspector
      document.getElementById('insp-title').textContent = node.display_name;
      document.getElementById('insp-id').textContent = `ID: ${{node.id}}  |  Line: ${{node.line_number}}`;

      const badgeRow = document.getElementById('insp-badges');
      badgeRow.innerHTML = node.tags.map(t => `<span class="badge badge-${{t}}">[${{t}}]</span>`).join('');

      // Outgoing
      const outEl = document.getElementById('insp-outgoing');
      if (node.outgoing.length === 0) {{
        outEl.innerHTML = '<div style="font-size: 12px; color: var(--text-muted);">(None / Concluding scene)</div>';
      }} else {{
        outEl.innerHTML = node.outgoing.map(o => `
          <div class="transition-card" onclick="selectScene('${{escapeHtml(o.target)}}')">
            <div class="tgt">&gt; ${{escapeHtml(o.target)}} <span style="font-size: 10px; color: var(--text-muted);">[${{o.kind}}]</span></div>
            ${{o.label ? `<div class="lbl">? ${{escapeHtml(o.label)}}</div>` : ''}}
            ${{o.condition ? `<div class="cond">[if ${{escapeHtml(o.condition)}}]</div>` : ''}}
          </div>
        `).join('');
      }}

      // Incoming
      const inEl = document.getElementById('insp-incoming');
      if (node.incoming.length === 0) {{
        inEl.innerHTML = '<div style="font-size: 12px; color: var(--text-muted);">(None / Entry scene)</div>';
      }} else {{
        inEl.innerHTML = node.incoming.map(i => `
          <div class="transition-card" onclick="selectScene('${{escapeHtml(i.source)}}')">
            <div class="tgt">&lt; ${{escapeHtml(i.source)}} <span style="font-size: 10px; color: var(--text-muted);">[${{i.kind}}]</span></div>
            ${{i.label ? `<div class="lbl">? ${{escapeHtml(i.label)}}</div>` : ''}}
            ${{i.condition ? `<div class="cond">[if ${{escapeHtml(i.condition)}}]</div>` : ''}}
          </div>
        `).join('');
      }}

      // Speakers
      const spkEl = document.getElementById('insp-speakers');
      spkEl.innerHTML = node.speakers.length > 0
        ? node.speakers.map(s => `<span class="pill">${{escapeHtml(s)}}</span>`).join('')
        : '<div style="font-size: 12px; color: var(--text-muted);">(None)</div>';

      // Hooks
      const hksEl = document.getElementById('insp-hooks');
      hksEl.innerHTML = node.hooks.length > 0
        ? node.hooks.map(h => `<span class="pill">~ ${{escapeHtml(h)}}</span>`).join('')
        : '<div style="font-size: 12px; color: var(--text-muted);">(None)</div>';

      // Preview
      const prevEl = document.getElementById('insp-preview');
      prevEl.textContent = node.preview.length > 0
        ? node.preview.join('\\n')
        : '(Empty or pure directive scene)';
    }}

    function escapeHtml(str) {{
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }}

    // Search filter
    document.getElementById('search-input').addEventListener('input', (e) => {{
      renderSceneList(e.target.value);
    }});

    // Initialize Mermaid
    if (window.mermaid) {{
      mermaid.initialize({{
        startOnLoad: true,
        theme: 'dark',
        themeVariables: {{
          darkMode: true,
          background: '#0f111a',
          primaryColor: '#1e2540',
          primaryTextColor: '#e2e8f0',
          primaryBorderColor: '#3b82f6',
          lineColor: '#60a5fa',
          secondaryColor: '#141724',
          tertiaryColor: '#181b2a',
        }},
        flowchart: {{
          curve: 'basis',
          nodeSpacing: 50,
          rankSpacing: 60,
        }}
      }});

      // Bind node clicks after Mermaid rendering
      setTimeout(() => {{
        document.querySelectorAll('.node').forEach(nodeEl => {{
          nodeEl.style.cursor = 'pointer';
          nodeEl.addEventListener('click', () => {{
            const id = nodeEl.id ? nodeEl.id.replace(/^flowchart-/, '').split('-')[0] : '';
            if (nodesById.has(id)) {{
              selectScene(id);
            }}
          }});
        }});
      }}, 500);
    }}

    renderSceneList();
    if (selectedId) {{
      selectScene(selectedId);
    }}
  </script>
</body>
</html>
"""


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
                flat.append(elem)  # type: ignore[arg-type]

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

