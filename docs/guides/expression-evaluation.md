# Expression Evaluation

Eager uses a whitelisted AST parsing and compilation pipeline for screenplay expressions. Arbitrary `eval()`/`exec()` is prohibited.

## Compilation

```python
from eager_script.expr import compile_expr

expr = compile_expr(expr_string)
result = expr.evaluate(context_variables)
```

## Example

```python
expr = compile_expr("reputation >= 50 and not visited('dungeon')")
result = expr.evaluate(context_variables)
```

## Security

`compile_expr` parses the expression into an AST, validates every node against a whitelist of allowed node types, and compiles it to a safe evaluator. Calls to `eval()` or `exec()` are never used.
