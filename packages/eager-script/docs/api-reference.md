# AST & API Reference

All parsed nodes in `eager_s` are immutable dataclasses exported directly at the top level of the package.

---

## AST Node Types

All nodes implement:
- `.type: str`: The string discriminator (e.g. `"label"`, `"dialogue"`, `"jump"`).
- `.line_number: int`: 1-indexed source line.
- `.to_dict() -> dict[str, Any]`: Converts node into a JSON-compatible dictionary.

### `ParsedLabel`
Represents scene/heading declarations (`## Name --- id` or `## Name`).
- `name: str`: Unique identifier / slug.
- `display_name: str`: Human-readable label text.
- `line_number: int`

### `ParsedDialogue`
Represents character speech (`Speaker: Text`).
- `speaker: str`: Character identifier or display name.
- `text: str`: Dialogue text.
- `voice: str | None`: Voice audio file path (if `{voice:...}` was present).
- `emotion: str | None`: Sprite/emotion tag (if `Speaker (emotion):` was present).
- `line_number: int`

### `ParsedAppend`
Represents an append beat (`- Text`).
- `text: str`: Text to append to the active dialogue box.
- `line_number: int`

### `ParsedFreshBox`
Represents a fresh text box beat (`/ Text`).
- `text: str`: Text starting a new box under the current speaker.
- `line_number: int`

### `ParsedNarration`
Represents speakerless descriptive text.
- `text: str`: Narration text (consecutive lines combined).
- `line_number: int`

### `ParsedChoiceOption`
Represents an individual choice line (`? Option (target)`).
- `text: str`: Option text shown to the player.
- `target: str`: Target scene label identifier.
- `line_number: int`

### `ParsedChoiceSet`
Represents a grouped block of consecutive choice options.
- `options: tuple[ParsedChoiceOption, ...]`: Tuple of choices.
- `line_number: int`: Line of the first choice option.

### `ParsedJump`
Represents an unconditional jump (`> target`).
- `target: str`: Target scene label identifier.
- `line_number: int`

### `ParsedCall`
Represents a subroutine call (`>> target`).
- `target: str`: Target scene label identifier.
- `line_number: int`

### `ParsedReturn`
Represents a return from subroutine (`<<`).
- `line_number: int`

### `ParsedHook`
Represents an engine hook invocation (`~ hook_name`).
- `hook_name: str`: Name of the hook event or command.
- `line_number: int`

---

## Core Functions

### `parse(text: str, *, plain: bool = False) -> list[ParsedItem]`
Parses screenplay source text into a linear list of AST nodes.
Raises `ParseError` on syntax errors.

### `to_dict(items: Sequence[ParsedItem]) -> list[dict[str, Any]]`
Converts AST nodes into dictionaries with `"type"` discriminators.

### `to_json(items: Sequence[ParsedItem], *, indent: int | None = 2) -> str`
Serializes AST nodes directly to a JSON string.

### `validate(items: Sequence[ParsedItem], *, plain: bool = False) -> ValidationResult`
Validates AST items for broken links, duplicate labels, orphan scenes, and infinite loops.

### `to_graph(items: Sequence[ParsedItem]) -> SceneGraph`
Transforms an AST item sequence into a directed scene graph.

### `parse_graph(text: str, *, plain: bool = False) -> SceneGraph`
Parses screenplay text directly into a directed scene graph.

---

## Error Handling

### `ParseError`
Exception raised when encountering invalid script syntax.
- `message: str`: Description of parse failure.
- `line_number: int`: Line number where syntax error occurred.
