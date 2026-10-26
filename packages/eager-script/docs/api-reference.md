# AST & API Reference

All parsed nodes in `eager_script` are immutable dataclasses exported directly at the top level of the package. Expression compilation, hook parsing, and scene graph utilities are provided in dedicated, sealed submodules.

---

## AST Node Catalog

All nodes implement:
- `.type: str`: String discriminator (e.g. `"label"`, `"dialogue"`, `"jump"`).
- `.line_number: int`: 1-indexed source line.
- `.to_dict() -> dict[str, Any]`: Converts node into a JSON-compatible dictionary.

### Narrative & Structural Nodes

#### `ParsedLabel`
Represents scene/heading declarations (`## Name --- id` or `## Name`).
- `name: str`: Unique scene identifier / slug.
- `display_name: str`: Human-readable label text.
- `line_number: int`

#### `ParsedDialogue`
Represents spoken character speech (`Speaker: Text`).
- `speaker: str`: Character identifier or display name.
- `text: str`: Dialogue text content.
- `voice: str | None`: Path to voice audio file (when `{voice:...}` tag is present).
- `emotion: str | None`: Character emotion/sprite state (when `Speaker (emotion):` syntax is used).
- `line_number: int`

#### `ParsedAppend`
Represents an append beat (`- Text`) extending the current dialogue box.
- `text: str`: Dialogue text to append.
- `line_number: int`

#### `ParsedFreshBox`
Represents a fresh text box beat (`/ Text`) under the active speaker without changing character context.
- `text: str`: Text starting the new dialogue box.
- `line_number: int`

#### `ParsedNarration`
Represents speakerless descriptive or narrative text.
- `text: str`: Narration text (consecutive plain narrative lines are buffered and combined).
- `line_number: int`

### Choice & Branching Nodes

#### `ParsedChoiceOption`
Represents an individual choice line (`? Option (target)`) or an inline option with an indented body (`? Option` + block).
- `text: str`: Option text presented to the player.
- `target: str | None`: Target scene identifier, or `None` for inline blocks.
- `condition: str | None`: Optional visibility condition expression (`if ...`).
- `body: tuple[ParsedItem, ...]`: The indented AST block for inline choices. Lowered into an anonymous scene during `to_graph()`.
- `is_inline: bool` (property): Returns `True` when `body` contains nested AST items.
- `line_number: int`

#### `ParsedChoiceSet`
Represents a contiguous block of one or more choice options presented simultaneously.
- `options: tuple[ParsedChoiceOption, ...]`: Tuple of available choice options.
- `line_number: int`: Line number of the first option.

### Control Flow & Subroutine Nodes

#### `ParsedJump`
Represents an unconditional scene jump (`> target`).
- `target: str`: Target scene identifier.
- `line_number: int`

#### `ParsedCall`
Represents a subroutine invocation (`>> target`) that pushes a return address onto the StoryVM call stack.
- `target: str`: Target scene identifier.
- `line_number: int`

#### `ParsedReturn`
Represents a return from a subroutine (`<<`) that pops the top frame from the call stack.
- `line_number: int`

#### `ParsedHook`
Represents an engine hook invocation (`~ hook_name args...`).
- `hook_name: str`: Name of the engine hook command.
- `line_number: int`

### State & Variable Nodes

#### `ParsedSet`
Represents a variable mutation statement (`$ variable = expr` or compound assignment `$ variable += expr`).
- `variable: str`: Target variable name.
- `expression: str`: Expression string to evaluate.
- `operator: str`: Assignment operator (`"="`, `"+="`, `"-="`, `"*="`, `"/="`).
- `line_number: int`

#### `ParsedDefault`
Represents a top-level default variable declaration (`@default variable = expr`).
- `variable: str`: Target variable name.
- `expression: str`: Default initial expression string.
- `line_number: int`

#### `ParsedCharacter`
Represents a screenplay character declaration (`@character id "Display Name" [color] [attr=val]`).
- `id: str`: Short character identifier.
- `display_name: str`: Formatted display name for dialogue nameplates.
- `color: str | None`: Nameplate color in hex or named format.
- `attributes: dict[str, str]`: Optional custom metadata dictionary.
- `line_number: int`

### Lowering & Conditional Nodes

#### `ParsedIf`, `ParsedElif`, `ParsedElse`, `ParsedEnd`
Represent flow control conditional blocks (`@if expr`, `@elif expr`, `@else`, `@end`).
- `condition: str | None` (for `ParsedIf` and `ParsedElif`): Condition expression string.
- `line_number: int`

#### `ParsedCondJump`
Generated during AST lowering to implement conditional branching within scenes.
- `condition: str`: Condition expression evaluated by StoryVM.
- `target: str`: Target scene identifier.
- `line_number: int`

#### `ParsedLocalJump`
Generated during AST lowering to flatten `@if` structures into local jump offsets.
- `target: str`: Target local label or block identifier.
- `line_number: int`

---

## Parser API

Module: `eager_script`

```python
import eager_script
```

### `parse(text: str) -> list[ParsedItem]`
Parses screenplay source text into a linear list of AST nodes.
- Raises: `ParseError` on syntax or indentation errors.

### `parse_iter(text: str) -> Iterator[ParsedItem]`
Streaming generator yielding AST nodes sequentially as they are parsed from source text.

### `ScreenplayParser`
Stateful parser class providing configuration options and incremental parsing.
```python
parser = eager_script.ScreenplayParser()
items = parser.parse(script_text)
```

### `parse_graph(text: str) -> SceneGraph`
Convenience helper that parses source text and transforms it directly into a directed `SceneGraph`.

### `to_graph(items: Sequence[ParsedItem]) -> SceneGraph`
Transforms an AST item sequence into a directed `SceneGraph`. Inline choice blocks are automatically lowered into anonymous scenes (`SceneNode.is_anonymous = True`).

### `validate(items: Sequence[ParsedItem]) -> ValidationResult`
Performs static analysis across AST items:
- Checks for undefined scene jump/call targets.
- Detects duplicate scene label IDs.
- Flags orphan (unreachable) scenes and terminal dead-ends.
- Returns `ValidationResult` with `.is_valid: bool`, `.errors: list[ValidationError]`, and `.warnings: list[ValidationError]`.

### `to_dict(items: Sequence[ParsedItem]) -> list[dict[str, Any]]`
Converts AST nodes into dictionaries with `"type"` discriminators.

### `to_json(items: Sequence[ParsedItem], *, indent: int | None = 2) -> str`
Serializes AST nodes to a formatted JSON string.

---

## Expression Compilation & Safe Evaluation

Module: `eager_script.expr`

Expressions in variable mutations, conditionals, and choice conditions are safely compiled and evaluated without ever invoking Python's `eval()` or `exec()`:

```python
from eager_script.expr import compile_expr, CompiledExpr, ExprError

# 1. Compile expression string into a compiled AST object
expr: CompiledExpr = compile_expr("reputation >= 10 and not hostile")

# 2. Evaluate against a context mapping
context = {"reputation": 15, "hostile": False}
result: bool = expr.evaluate(context)  # Returns True

# 3. Arithmetic and type safety error wrapping
math_expr = compile_expr("100 / divisor")
try:
    val = math_expr.evaluate({"divisor": 0})
except ExprError as err:
    print(f"Evaluation failed safely: {err}")  # ZeroDivisionError wrapped in ExprError
```

### Expression Language Grammar
- **Binary Operations**: `+`, `-`, `*`, `/`, `//`, `%`
- **Unary Operations**: `+`, `-`, `not`
- **Comparisons**: `==`, `!=`, `<`, `<=`, `>`, `>=`
- **Boolean Logic**: `and`, `or`
- **Literals**: Numbers, strings, booleans (`True`, `False`), `None`
- **Safe Built-in Functions**:
  - `visited("scene_id")`: Checks if scene has been visited in current playthrough.
  - `seen("scene_id")`: Checks if scene has ever been unlocked in persistent data.
  - `random(a, b)`: Uniform random integer between `a` and `b`.
  - `chance(pct)`: Probability check from `0.0` to `1.0`.
  - `min(...)`, `max(...)`, `abs(...)`, `len(...)`, `int(...)`, `str(...)`, `round(...)`.

---

## Hook & Input Parsing API

Module: `eager_script.hooks`

Engine hooks (`~ command args...`) connect screenplay markup to gameplay systems:

```python
from eager_script.hooks import parse_hook_args, is_input_hook, parse_input_args

# Generic hook argument parsing
hook = parse_hook_args("play_bgm track='theme.ogg' volume=0.8 fade=1.5 loop")
print(hook.name)        # "play_bgm"
print(hook.named)       # {"track": "theme.ogg", "volume": 0.8, "fade": 1.5}
print(hook.flags)       # {"loop"}

# Input prompt hook parsing (~ input var_name "Prompt message" default="Default")
if is_input_hook("input"):
    input_args = parse_input_args('player_name "What is your name?" default="Hero"')
    print(input_args.variable)  # "player_name"
    print(input_args.prompt)    # "What is your name?"
    print(input_args.default)   # "Hero"
```

---

## Text Pacing & `{fast}` Tag Semantics

Module: `eager_core.text`

While general text formatting tags (`{b}`, `{i}`, `{color}`, `{size}`) style text, the `{fast}` tag governs typewriter animation pacing for dialogue:

```python
from eager_core.text import parse_text_tags, TextReveal

# Parse dialogue with {fast} tag
raw = "Previously displayed text.{fast} New typewriter text."
formatted = parse_text_tags(raw)

print(formatted.plain_text)   # "Previously displayed text. New typewriter text."
print(formatted.fast_index)   # 26 (character index where {fast} occurred)
```

### `{fast}` Semantics in Visual Novels
1. **Instant Prefix Reveal**: In visual novels, when dialogue is appended (`- Text`) or previous lines are shown in full, the `{fast}` marker ensures characters prior to `fast_index` appear immediately on the first render frame (`visible_chars >= fast_index`).
2. **Pause Suppression**: Any wait/pause markers (`{w=0.5}`, `{p}`) that occurred *prior* to `{fast}` are immediately bypassed.
3. **Typewriter Continuity**: Characters located *after* `fast_index` continue animating at normal typewriter speed (`chars_per_second`).

```python
# TextReveal respects fast_index automatically upon initialization
reveal = TextReveal(formatted, chars_per_second=30.0)
print(reveal.visible_chars)  # 26.0 (characters 0..25 are visible instantly)
```

---

## Error Handling

### `ParseError`
Exception raised when screenplay syntax or structure violates language grammar:
- `message: str`: Explanation of parse failure.
- `line_number: int`: 1-indexed source line.

### `ExprError`
Exception raised when an expression fails during safe evaluation:
- Wraps `ZeroDivisionError`, `TypeError`, `ValueError`, and undefined variable lookups.

---

## License

MIT
