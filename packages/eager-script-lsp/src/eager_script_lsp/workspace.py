"""Multi-file workspace index for scenes, symbols, assets, and localization."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from eager_core.i18n import TranslationCatalog
from eager_runtime.assets import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS
from eager_runtime.project import ProjectConfig, merge_graphs
from eager_script import SceneGraph, SceneNode
from lsprotocol.types import Range
from pygls.uris import from_fs_path, to_fs_path

from eager_script_lsp.document import ScriptDocument

logger = logging.getLogger(__name__)


def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a filesystem Path."""
    if uri.startswith("file://"):
        fs_path = to_fs_path(uri)
        return Path(fs_path) if fs_path else Path(uri[7:])
    return Path(uri)


def path_to_uri(path: Path) -> str:
    """Convert a filesystem Path to a file:// URI."""
    uri = from_fs_path(str(path.resolve()))
    return uri if uri is not None else path.resolve().as_uri()


@dataclass
class SceneSymbol:
    """A scene label definition indexed in the workspace."""

    id: str
    display_name: str
    uri: str
    range: Range
    node: SceneNode | None = None
    docstring: str | None = None
    speakers: set[str] = field(default_factory=set)
    predecessors: set[str] = field(default_factory=set)
    successors: set[str] = field(default_factory=set)
    first_lines: list[str] = field(default_factory=list)


@dataclass
class CharacterSymbol:
    """A character declaration or speaker occurrence."""

    id: str
    name: str
    uri: str | None = None
    range: Range | None = None
    attrs: dict[str, str] = field(default_factory=dict)
    is_defined: bool = False
    dialogue_lines: int = 0


@dataclass
class VariableSymbol:
    """A global or persistent screenplay variable."""

    name: str
    default_val: str | None = None
    default_uri: str | None = None
    default_range: Range | None = None
    mutations: list[tuple[str, Range]] = field(default_factory=list)
    reads: list[tuple[str, Range]] = field(default_factory=list)


@dataclass
class AssetIndex:
    """Indexed media files on disk for fast auto-completion and navigation."""

    backgrounds: set[str] = field(default_factory=set)
    characters: dict[str, set[str]] = field(default_factory=dict)
    audio: set[str] = field(default_factory=set)
    voice: set[str] = field(default_factory=set)
    file_paths: dict[str, Path] = field(default_factory=dict)

    def scan_assets(self, asset_dir: Path) -> None:
        """Scan directory and index all background, character, audio, and voice assets."""
        self.backgrounds.clear()
        self.characters.clear()
        self.audio.clear()
        self.voice.clear()
        self.file_paths.clear()

        if not asset_dir.is_dir():
            return

        for p in asset_dir.rglob("*"):
            if not p.is_file() or p.name.startswith("."):
                continue

            rel = p.relative_to(asset_dir)
            rel_str = str(rel).replace("\\", "/")
            stem = p.stem
            ext = p.suffix.lower()

            if ext in IMAGE_EXTENSIONS and ext != "":
                # Check backgrounds
                if rel.parts[0] in ("bg", "backgrounds"):
                    # Record both 'bg/name' and 'name'
                    self.backgrounds.add(rel_str)
                    self.backgrounds.add(stem)
                    if len(rel.parts) > 1:
                        sub_id = "/".join(rel.parts[1:])
                        sub_stem = Path(sub_id).with_suffix("").as_posix()
                        self.backgrounds.add(sub_stem)
                        self.file_paths[f"bg:{sub_stem}"] = p
                    self.file_paths[f"bg:{stem}"] = p
                    self.file_paths[f"bg:{rel_str}"] = p
                # Check character sprites
                elif rel.parts[0] in ("characters", "chars") and len(rel.parts) >= 3:
                    cid = rel.parts[1].lower()
                    expr = rel.parts[2].rpartition(".")[0].lower()
                    self.characters.setdefault(cid, set()).add(expr)
                    self.file_paths[f"char:{cid}/{expr}"] = p
                elif len(rel.parts) == 2:
                    # e.g. assets/hoshiko/smile.png
                    cid = rel.parts[0].lower()
                    expr = stem.lower()
                    self.characters.setdefault(cid, set()).add(expr)
                    self.file_paths[f"char:{cid}/{expr}"] = p
                elif "_" in stem:
                    # e.g. assets/hoshiko_smile.png
                    cid, _, expr = stem.lower().partition("_")
                    self.characters.setdefault(cid, set()).add(expr)
                    self.file_paths[f"char:{cid}/{expr}"] = p
                else:
                    # Generic image/background
                    self.backgrounds.add(stem)
                    self.file_paths[f"bg:{stem}"] = p

            elif ext in AUDIO_EXTENSIONS and ext != "":
                # Check audio / voice
                if rel.parts[0] in ("voice", "voices"):
                    self.voice.add(rel_str)
                    self.voice.add(stem)
                    self.file_paths[f"voice:{rel_str}"] = p
                    self.file_paths[f"voice:{stem}"] = p
                else:
                    self.audio.add(stem)
                    self.audio.add(rel_str)
                    self.file_paths[f"audio:{stem}"] = p
                    self.file_paths[f"audio:{rel_str}"] = p


class WorkspaceIndex:
    """Multi-file workspace manager for an Eager screenplay project."""

    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path.resolve()
        self.config: ProjectConfig = ProjectConfig()
        self.asset_dir: Path = self.root_path / "assets"
        self.locales_dir: Path = self.root_path / "locales"

        self.documents: dict[str, ScriptDocument] = {}
        self.labels: dict[str, SceneSymbol] = {}
        self.characters: dict[str, CharacterSymbol] = {}
        self.variables: dict[str, VariableSymbol] = {}
        self.references: dict[str, list[tuple[str, Range]]] = {}
        self.asset_index: AssetIndex = AssetIndex()
        self.translation_catalogs: dict[str, TranslationCatalog] = {}
        self.merged_graph: SceneGraph | None = None
        self.merge_errors: list[str] = []

    def initialize(self) -> None:
        """Scan workspace, load configuration, discover assets, locales, and .es files."""
        # 1. Load project config
        game_toml = self.root_path / "game.toml"
        if game_toml.is_file():
            self.config = ProjectConfig.load(game_toml)

        # Resolve asset and locales dir
        if not self.asset_dir.is_dir() and (self.root_path.parent / "assets").is_dir():
            self.asset_dir = self.root_path.parent / "assets"
        if not self.locales_dir.is_dir() and (self.root_path.parent / "locales").is_dir():
            self.locales_dir = self.root_path.parent / "locales"

        # 2. Index assets & locales
        self.asset_index.scan_assets(self.asset_dir)
        self._load_locales()

        # 3. Discover and index all .es screenplay files
        es_files: list[Path] = []
        if self.root_path.is_file() and self.root_path.suffix == ".es":
            es_files.append(self.root_path)
        elif self.root_path.is_dir():
            for p in self.root_path.rglob("*.es"):
                if not p.is_file() or any(
                    part.startswith((".", "venv", "__pycache__")) or part == "dist" for part in p.parts
                ):
                    continue
                es_files.append(p)

        for es_path in es_files:
            try:
                text = es_path.read_text(encoding="utf-8")
                uri = path_to_uri(es_path)
                doc = ScriptDocument(uri, text)
                self.documents[uri] = doc
            except (OSError, UnicodeDecodeError, ValueError) as e:
                logger.error("Failed to read and parse %s: %s", es_path, e)

        # 4. Build workspace symbols & merged graph
        self._rebuild_index()

    def _is_excluded_uri(self, uri: str) -> bool:
        """Return True if the URI points to a build artifact directory such as dist/."""
        try:
            path = uri_to_path(uri)
        except (ValueError, TypeError):
            return False
        return "dist" in path.parts

    def update_document(self, uri: str, text: str) -> ScriptDocument:
        """Incrementally update or add a document and refresh symbols.

        Build artifact directories (e.g. ``dist/``) are excluded so that
        compiled copies of screenplay files do not produce false duplicate
        scene label diagnostics against their source counterparts.
        """
        if self._is_excluded_uri(uri):
            return self.documents.get(uri, ScriptDocument(uri, text))
        doc = ScriptDocument(uri, text)
        self.documents[uri] = doc
        self._rebuild_index()
        return doc

    def remove_document(self, uri: str) -> None:
        """Remove a document from the workspace and refresh symbols."""
        if uri in self.documents:
            del self.documents[uri]
            self._rebuild_index()

    def get_document(self, uri: str) -> ScriptDocument | None:
        """Retrieve indexed ScriptDocument by URI."""
        return self.documents.get(uri)

    def get_scene(self, scene_id: str) -> SceneSymbol | None:
        """Look up indexed scene symbol by identifier."""
        return self.labels.get(scene_id)

    def get_character(self, char_id: str) -> CharacterSymbol | None:
        """Look up indexed character symbol by identifier."""
        return self.characters.get(char_id.lower())

    def get_variable(self, var_name: str) -> VariableSymbol | None:
        """Look up indexed variable symbol by name."""
        return self.variables.get(var_name)

    def _load_locales(self) -> None:
        """Load JSON translation catalogs from locales directory."""
        self.translation_catalogs.clear()
        if not self.locales_dir.is_dir():
            return
        for p in self.locales_dir.glob("*.json"):
            if not p.is_file() or p.name.startswith((".", "template")):
                continue
            locale_code = p.stem
            try:
                cat = TranslationCatalog.load_json(p)
                self.translation_catalogs[locale_code] = cat
            except (OSError, ValueError) as e:
                logger.error("Failed to load locale %s: %s", p, e)

    def _rebuild_index(self) -> None:
        """Reconstruct symbol tables and attempt cross-file graph merge."""
        self.labels.clear()
        self.characters.clear()
        self.variables.clear()
        self.references.clear()
        self.merge_errors.clear()

        # Step 1: Collect symbols from each document
        valid_graphs: list[SceneGraph] = []

        for uri, doc in self.documents.items():
            if doc.scene_graph is not None:
                valid_graphs.append(doc.scene_graph)

            # Discover docstrings (leading comments before labels)
            for occ in doc.occurrences:
                if occ.kind == "label_def":
                    scene_id = occ.name
                    # Find leading comments right above label
                    docstring_lines: list[str] = []
                    curr_line = occ.span.start_line - 1
                    while curr_line >= 0:
                        prev_line_text = doc.lines[curr_line].strip()
                        if prev_line_text.startswith("#") and not prev_line_text.startswith("##"):
                            docstring_lines.insert(0, prev_line_text.lstrip("#").strip())
                            curr_line -= 1
                        else:
                            break

                    docstring = "\n".join(docstring_lines) if docstring_lines else None
                    node = doc.scene_graph.nodes.get(scene_id) if doc.scene_graph else None

                    # Extract first 3 dialogue lines for hover preview
                    first_lines: list[str] = []
                    if node:
                        for it in node.body:
                            speaker = getattr(it, "speaker", None)
                            text_val = getattr(it, "text", None)
                            if speaker and text_val:
                                first_lines.append(f"{speaker}: {text_val}")
                            elif text_val:
                                first_lines.append(str(text_val))
                            if len(first_lines) >= 3:
                                break

                    sym = SceneSymbol(
                        id=scene_id,
                        display_name=occ.metadata.get("display_name", scene_id),
                        uri=uri,
                        range=occ.span.range,
                        node=node,
                        docstring=docstring,
                        first_lines=first_lines,
                    )
                    self.labels[scene_id] = sym

                elif occ.kind == "character_def":
                    char_id = occ.name
                    attrs_dict: dict[str, str] = {}
                    raw_attrs = occ.metadata.get("raw_attrs", "")
                    if raw_attrs:
                        for tok in raw_attrs.split():
                            if "=" in tok:
                                k, _, v = tok.partition("=")
                                attrs_dict[k.strip()] = v.strip()

                    self.characters[char_id] = CharacterSymbol(
                        id=char_id,
                        name=occ.metadata.get("name", char_id.capitalize()),
                        uri=uri,
                        range=occ.span.range,
                        attrs=attrs_dict,
                        is_defined=True,
                    )

                elif occ.kind == "character_ref":
                    char_id = occ.name
                    if char_id not in self.characters:
                        self.characters[char_id] = CharacterSymbol(
                            id=char_id,
                            name=occ.metadata.get("display_name", char_id.capitalize()),
                            is_defined=False,
                        )
                    self.characters[char_id].dialogue_lines += 1

                elif occ.kind == "variable_def":
                    var_name = occ.name
                    self.variables[var_name] = VariableSymbol(
                        name=var_name,
                        default_val=occ.metadata.get("default_value"),
                        default_uri=uri,
                        default_range=occ.span.range,
                    )

                elif occ.kind == "variable_mutation":
                    var_name = occ.name
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableSymbol(name=var_name)
                    self.variables[var_name].mutations.append((uri, occ.span.range))

                elif occ.kind == "variable_read":
                    var_name = occ.name
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableSymbol(name=var_name)
                    self.variables[var_name].reads.append((uri, occ.span.range))

                elif occ.kind == "label_ref":
                    target_id = occ.name
                    self.references.setdefault(target_id, []).append((uri, occ.span.range))

        # Step 2: Cross-file graph topology & predecessor/successor linkage
        try:
            if valid_graphs:
                self.merged_graph = merge_graphs(valid_graphs, strict=False)
            else:
                self.merged_graph = None
        except (ValueError, TypeError, KeyError) as e:
            self.merge_errors.append(str(e))
            self.merged_graph = None

        # Populate predecessors & successors on SceneSymbols
        for target_id, ref_list in self.references.items():
            if target_id in self.labels:
                for src_uri, src_range in ref_list:
                    src_doc = self.documents.get(src_uri)
                    if src_doc:
                        src_scene = src_doc.get_scene_at_line(src_range.start.line)
                        if src_scene and src_scene in self.labels:
                            self.labels[target_id].predecessors.add(src_scene)
                            self.labels[src_scene].successors.add(target_id)
