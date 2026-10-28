# Hook Parsing

Engine hooks (`~ hook_name args`) are parsed in the script layer and handled in the graphics/runtime layer.

## Parsing hook arguments

```python
from eager_script import parse_hook_args

args = parse_hook_args(raw_hook_string)
```

`parse_hook_args` returns a `HookArgs` (or `InputHookArgs` for input hooks) with typed accessors for positional tokens and key-value pairs.

## Handling hooks

Hook handlers are registered on the runtime event dispatcher. `StageDirector.bind(dispatcher)` wires each hook name (`bg`, `show`, `move`, `play`, `shake`, etc.) to a stage compositor action:

```python
from eager_graphics.director import StageDirector

director = StageDirector(compositor)
director.bind(dispatcher)
```

The parser is rendering-agnostic; the graphics layer decides how to act on each hook.
