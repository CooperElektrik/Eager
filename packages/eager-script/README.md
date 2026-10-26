# Eager-Script

A zero-dependency screenplay DSL parser, expression compiler, and scene graph analyzer for visual novels and interactive fiction in Python.

`eager-script` parses human-friendly screenplay text into an abstract syntax tree (AST) and directed scene graph for game engines and narrative tools, with zero external runtime dependencies.

---

## Features

- **Screenplay DSL Parser**: Converts screenplay text into strongly typed, immutable AST nodes.
- **Streaming Parser & Incremental Parsing**: Generator-based token stream parsing with `parse_iter` and stateful `ScreenplayParser`.
- **Inline Choice Lowering**: Flattens nested choice blocks into anonymous scenes without requiring manual label ceremony.
- **Safe Expression Compiler**: Whitelisted AST expression compiler (`compile_expr`) evaluating conditionals and math with zero `eval()`/`exec()` exposure.
- **Hook & Input Parsing**: Structured argument parsing for engine hooks (`~ play`, `~ show`) and text input prompts (`~ input`).
- **Directed Scene Graph**: Graph representation providing reachability, cycle detection, branching hub analysis, and terminal scene queries.
- **Static Validation**: Checks for broken jumps/calls, duplicate labels, orphan scenes, dead code, and unreachable branches.
- **Graph Exports**: Exports scene graphs to JSON, Graphviz DOT, and Mermaid diagrams.

---

## Screenplay DSL Syntax

```es
@default gold = 100
@character guard "Town Guard" #e74c3c

## Courtyard --- courtyard

Narrator: Rain pours against the stone pavement.
- You pull your cloak tighter around your shoulders.

guard: Who goes there? State your business.

? Announce yourself peacefully (peaceful_entry)
? Draw your sword
    $ gold -= 10
    guard (angry): So that's how it is.
    > combat_start

## Peaceful Entry --- peaceful_entry
~ play_chime volume=0.8
guard: Welcome, traveler. Enter freely.
>> royal_greeting
> finish

## Royal Greeting --- royal_greeting
guard: Present your credentials.
<<

## Combat Start --- combat_start
guard (angry): You will regret this!
> finish

## Finished --- finish
Narrator: The gates close behind you.
```

---

## Parser API & AST Nodes

### Top-Level Parser Functions

```python
import eager_script

# Parse full source into a list of AST nodes
items = eager_script.parse(script_text)

# Streaming iterator yielding AST nodes one by one
for item in eager_script.parse_iter(script_text):
    print(item.type, item.line_number)

# Instantiate stateful parser directly
parser = eager_script.ScreenplayParser()
items = parser.parse(script_text)

# Parse directly into a directed SceneGraph
graph = eager_script.parse_graph(script_text)
```

### AST Node Catalog

All AST items are immutable dataclasses implementing `.type: str`, `.line_number: int`, and `.to_dict() -> dict[str, Any]`:

- `ParsedLabel`: Scene label declaration (`## Title --- id` or `## Title`).
- `ParsedDialogue`: Spoken dialogue (`Speaker: Text`, with optional `(emotion)` and `{voice:...}`).
- `ParsedAppend`: Text appending to current dialogue box (`- Text`).
- `ParsedFreshBox`: New dialogue box under same speaker (`/ Text`).
- `ParsedNarration`: Speakerless narrative text.
- `ParsedChoiceOption`: Individual choice line (`? Text (target)` or inline `? Text` with nested body).
- `ParsedChoiceSet`: Grouped block of consecutive choice options.
- `ParsedJump`: Unconditional scene jump (`> target`).
- `ParsedCall`: Subroutine invocation pushing call frame (`>> target`).
- `ParsedReturn`: Subroutine return popping call frame (`<<`).
- `ParsedHook`: Engine hook trigger (`~ hook_name args`).
- `ParsedSet`: State mutation (`$ var = expr` or `$ var += expr`).
- `ParsedDefault`: Default variable initialization (`@default var = expr`).
- `ParsedCharacter`: Character definition (`@character id "Display Name" [color] [attr=val]`).
- `ParsedIf`, `ParsedElif`, `ParsedElse`, `ParsedEnd`: Flow control conditional blocks.
- `ParsedCondJump`: Conditional jump generated during flow control lowering.
- `ParsedLocalJump`: Internal jump node for local branching within a scene.

---

## Expression Compilation & Safe Evaluation

Expressions in variable assignments (`$`), conditionals (`@if`, `@elif`), and choice conditions are compiled into bytecode AST wrappers using `compile_expr`:

```python
from eager_script.expr import compile_expr, ExprError

# Whitelisted AST parsing and compilation (NEVER uses eval() or exec())
expr = compile_expr("gold >= 50 and not poisoned")

context = {"gold": 100, "poisoned": False}
result = expr.evaluate(context)  # Returns True

# Arithmetic with error wrapping
safe_math = compile_expr("100 / count")
try:
    value = safe_math.evaluate({"count": 0})
except ExprError as err:
    print(f"Safe evaluation error: {err}")  # Catches ZeroDivisionError wrapped in ExprError
```

### Supported Operators & Functions
- **Comparison**: `==`, `!=`, `<`, `<=`, `>`, `>=`
- **Boolean**: `and`, `or`, `not`
- **Arithmetic**: `+`, `-`, `*`, `/`, `//`, `%`
- **Safe built-ins**: `visited()`, `seen()`, `random()`, `chance()`, `min()`, `max()`, `abs()`, `len()`, `int()`, `str()`, `round()`

---

## Hook & Input Parsing

Engine hooks (`~ command args`) are parsed into structured arguments via `eager_script.hooks`:

```python
from eager_script.hooks import parse_hook_args, is_input_hook, parse_input_args

# Parse generic hook
hook = parse_hook_args("play_music track='battle.ogg' volume=0.8 loop")
print(hook.name)        # "play_music"
print(hook.positional)  # []
print(hook.named)       # {"track": "battle.ogg", "volume": 0.8}
print(hook.flags)       # {"loop"}

# Parse text input prompt hook (~ input name "Enter your name:" default="Hero")
if is_input_hook("input"):
    input_args = parse_input_args('name "Enter your name:" default="Hero"')
    print(input_args.variable)  # "name"
    print(input_args.prompt)    # "Enter your name:"
    print(input_args.default)   # "Hero"
```

---

## Static Validation & Scene Graph

```python
import eager_script

# Validate script structure
result = eager_script.validate(items)
if not result.is_valid:
    for error in result.errors:
        print(f"Line {error.line_number}: {error.message}")

# Analyze scene graph
graph = eager_script.to_graph(items)
print("Entry scene:", graph.entry)
print("Hub scenes:", graph.hubs())
print("Terminal scenes:", graph.terminal_scenes())
print("Reachable scenes:", graph.reachable_scenes())

# Export formats
mermaid_markup = graph.to_mermaid()
dot_markup = graph.to_dot()
json_dump = graph.to_json()
```

---

## CLI Tools

```bash
# Validate screenplay syntax and link integrity
eager-script check story.es

# Parse to structured JSON AST
eager-script parse story.es -o story.json

# Export directed scene graph
eager-script graph story.es --format mermaid
eager-script graph story.es --format dot -o story.dot
```

---

## Installation

```bash
pip install eager-script
```

---

## License

MIT
