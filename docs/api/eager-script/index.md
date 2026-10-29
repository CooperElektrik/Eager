# eager-script

Zero-dependency screenplay DSL parser for interactive narrative and visual novels. `eager-script` parses human-friendly screenplay text into an abstract syntax tree (AST) and directed scene graph, with zero external runtime dependencies.

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_script import parse_screenplay, parse_hook_args
from eager_script.expr import compile_expr
from eager_script.graph import SceneGraph, SceneNode
from eager_script.validator import validate_screenplay
```

## Modules

| Module | Description |
|--------|-------------|
| [parser](parser.md) | Screenplay parser, tokenization, line parsing, and AST generation. |
| [expr](expr.md) | Safe, whitelisted expression compilation and evaluation (`compile_expr`). |
| [graph](graph.md) | Scene graph representation, node branching, and anonymous choice scenes. |
| [hooks](hooks.md) | Hook arguments parsing (`parse_hook_args`) for engine directives. |
| [validator](validator.md) | Static screenplay validation, unreachable node detection, and linting. |
| [cli](cli.md) | Command-line interface for checking and inspecting `.es` script files. |
