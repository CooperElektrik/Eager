# Eager-Script

A zero-dependency screenplay DSL parser for visual novels and interactive fiction in Python.

It parses screenplay text into an abstract syntax tree (AST) and directed scene graph for game engines and narrative tools.

## Features

- Parses screenplay text into AST items and directed scene graphs
- Topological queries for reachability, branching points, hubs, and terminal scenes
- Inline choice blocks that lower into anonymous scenes (no label ceremony)
- Static validation for broken links, duplicate labels, dead code, and loops
- Exports to JSON, Graphviz DOT, and Mermaid
- Eager-SP mode for branching novels without engine markup
- Optional terminal text editor with live syntax highlighting and diagnostics

## Installation

```bash
pip install eager-script
```

To install the optional terminal editor:

```bash
pip install "eager-script[editor]"
```

## DSL Example

```es
## Courtyard --- courtyard

Narrator: Rain pours against the stone pavement.
- You pull your cloak tighter around your shoulders.

Guard: Who goes there? State your business.

? Announce yourself peacefully (peaceful_entry)
? Draw your sword
    $ reputation -= 5
    Guard (angry): So that's how it is.
    > combat_start

## Peaceful Entry --- peaceful_entry
~ play_chime
Guard: Welcome, traveler. Enter freely.
> finish

## Combat Start --- combat_start
Guard (angry): You will regret this!
> finish

## Finished --- finish
Narrator: The gates close behind you.
```

## Quickstart

```python
import eager_script

script = """
## Courtyard --- courtyard
Guard: State your business.
? Peace (peaceful_entry)
? Fight (combat_start)

## Peaceful Entry --- peaceful_entry
> finish

## Combat Start --- combat_start
> finish

## Finished --- finish
Narrator: The end.
"""

# Parse into AST items
items = eager_script.parse(script)

# Validate links
result = eager_script.validate(items)
print("Valid:", result.is_valid)

# Build directed scene graph
graph = eager_script.to_graph(items)
print("Entry:", graph.entry)
print("Successors:", graph.successors("courtyard"))
print("Terminal scenes:", graph.terminal_scenes())
```

## CLI

```bash
# Validate script
eager-script check script.es

# Parse to JSON AST
eager-script parse script.es -o script.json

# Export scene graph
eager-script graph script.es -o graph.json
eager-script graph script.es --format dot -o story.dot
eager-script graph script.es --format mermaid

# Open terminal editor
eager-script edit script.es
```

## Documentation

Detailed guides are in [docs/](docs/):

- [DSL Syntax Reference](docs/syntax.md): Syntax rules, Eager-SP mode, escaping
- [Directed Scene Graph](docs/scene-graph.md): Graph model, queries, DOT and Mermaid exports
- [Static Validation](docs/validation.md): Checks, errors, warnings
- [Terminal Editor](docs/editor.md): Editor controls, keybindings
- [API Reference](docs/api-reference.md): AST nodes, functions, exceptions
- [Benchmarks](docs/benchmarks.md): Performance numbers across script sizes

## Tests

```bash
cd packages/eager-script && pytest -q --tb=short -x
```

## License

MIT
