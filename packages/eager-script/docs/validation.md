# Static Validation

`eager_script` includes a static validator that analyzes screenplay scripts before runtime to detect narrative inconsistencies, broken branching links, dead code, and infinite loops.

---

## Checks Performed

| Check | Level | Description |
| :--- | :--- | :--- |
| **Undefined Target** | `error` | A jump (`>`), subroutine call (`>>`), or choice option (`?`) points to a non-existent scene label. Targets inside inline choice blocks are checked too. |
| **Duplicate Label** | `error` | Two or more scenes declare the same identifier. |
| **Unreturned Subroutine** | `warning` | A subroutine call (`>>`) exists, but the script contains no return instruction (`<<`). |
| **Dead Code / Unreachable Statements** | `warning` | Statements located after an unconditional jump (`>`), return (`<<`), or a choice menu with no inline blocks within the same scene (and inside inline choice blocks). |
| **Orphan Scene Label** | `warning` | A scene label is declared but never targeted by any jump, call, or choice. |
| **Unreachable From Entry** | `warning` | A scene exists in the script but cannot be reached by traversing from the first scene (entry point). |
| **Cyclical Traversal** | `warning` | An unconditional loop exists where scenes jump to one another in an infinite loop without player choices or exit points. |

---

## Inline Choice Blocks

Because an inline choice block returns to the line after the menu, statements that follow a menu containing at least one inline option are treated as reachable and are **not** flagged as dead code. Undefined targets, invalid expressions, and unreachable statements inside the block itself are validated with the same rules as a normal scene.

---

## Python API

```python
import eager_script

items = eager_script.parse(script)
result = eager_script.validate(items)

if not result.is_valid:
    print(f"Validation failed with {len(result.errors)} errors.")
    for err in result.errors:
        print(f"ERROR: Line {err.line_number}: {err.message}")

for warn in result.warnings:
    print(f"WARNING: Line {warn.line_number}: {warn.message}")
```

### Data Structures

- **`ValidationResult`**:
  - `.errors`: Tuple of `ValidationError` objects with level `"error"`.
  - `.warnings`: Tuple of `ValidationError` objects with level `"warning"`.
  - `.is_valid`: Boolean, `True` if `len(errors) == 0`.
- **`ValidationError`**:
  - `.message`: Human-readable description of the issue.
  - `.line_number`: 1-indexed source line number.
  - `.level`: `"error"` or `"warning"`.

---

## CLI Usage

Validate scripts directly in terminal or CI/CD pipelines:

```bash
# Validate screenplay DSL
eager-script check script.es
```

Example output:
```text
WARNING: Line 42: Label 'forgotten_shrine' is defined but never targeted by any jump, call, or choice
✓ Script 'script.es' is valid (68 AST items, 1 warning(s)).
```

The command exits with `0` when valid (warnings allowed) and `1` on syntax or validation errors.
