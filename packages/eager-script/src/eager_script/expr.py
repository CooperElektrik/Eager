"""Safe expression evaluation engine for Eager-S screenplay scripts."""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from typing import Any


class ExprError(Exception):
    """Raised when an expression fails to compile or evaluate safely."""


_ALLOWED_OPERATORS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_ALLOWED_FUNCTIONS: set[str] = {
    "visited",
    "seen",
    "random",
    "chance",
    "min",
    "max",
    "abs",
    "len",
    "int",
    "str",
    "round",
}


_LITERAL_REGEX = re.compile(
    r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(?<![\.\w])\b(true|false|none)\b'
)


def _replace_literals(source: str) -> str:
    """Normalize boolean/none identifiers to Python case without modifying string contents."""
    def repl(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            return m.group(1)
        ident = m.group(2)
        if ident == "true":
            return "True"
        if ident == "false":
            return "False"
        return "None"

    return _LITERAL_REGEX.sub(repl, source)


class CompiledExpr:
    """A compiled AST expression validated against the safe node whitelist."""

    def __init__(self, source: str, tree: ast.AST) -> None:
        self.source = source
        self.tree = tree

    def evaluate(self, env: dict[str, Any]) -> Any:
        """Evaluate the compiled expression in the given environment."""
        return _eval_node(self.tree, env)


def compile_expr(src: str) -> CompiledExpr:
    """Compile and validate an expression string against the node whitelist.

    Raises ExprError on syntax or security validation errors.
    """
    clean_src = src.strip()
    if not clean_src:
        raise ExprError("Empty expression")

    normalized = _replace_literals(clean_src)

    try:
        parsed = ast.parse(normalized, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"Expression syntax error: {e.msg}") from e

    _validate_node(parsed.body)
    return CompiledExpr(clean_src, parsed.body)


def _validate_node(node: ast.AST) -> None:
    """Recursively validate that AST nodes only use whitelisted constructs."""
    if isinstance(node, ast.Constant):
        return

    if isinstance(node, ast.Name):
        return

    if isinstance(node, ast.Attribute):
        # Attribute access is ONLY allowed on persistent and cannot access private/dunder attrs
        if isinstance(node.value, ast.Name) and node.value.id == "persistent":
            if node.attr.startswith("_"):
                raise ExprError(f"Access to private or dunder attribute '{node.attr}' is forbidden")
            return
        raise ExprError(f"Attribute access '{getattr(node, 'attr', '')}' is forbidden")

    if isinstance(node, ast.UnaryOp):
        if type(node.op) in _ALLOWED_OPERATORS:
            _validate_node(node.operand)
            return
        raise ExprError(f"Unary operator {type(node.op).__name__} is not allowed")

    if isinstance(node, ast.BinOp):
        if type(node.op) in _ALLOWED_OPERATORS:
            _validate_node(node.left)
            _validate_node(node.right)
            return
        raise ExprError(f"Binary operator {type(node.op).__name__} is not allowed")

    if isinstance(node, ast.BoolOp):
        for val in node.values:
            _validate_node(val)
        return

    if isinstance(node, ast.Compare):
        _validate_node(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _ALLOWED_OPERATORS:
                raise ExprError(f"Comparison operator {type(op).__name__} is not allowed")
            _validate_node(comparator)
        return

    if isinstance(node, ast.IfExp):
        _validate_node(node.test)
        _validate_node(node.body)
        _validate_node(node.orelse)
        return

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id not in _ALLOWED_FUNCTIONS:
                raise ExprError(f"Function '{node.func.id}' is not in the whitelist")
            for arg in node.args:
                _validate_node(arg)
            for kw in node.keywords:
                _validate_node(kw.value)
            return
        raise ExprError("Calls to complex expressions or attributes are forbidden")

    if isinstance(node, (ast.List, ast.Tuple)):
        for el in node.elts:
            _validate_node(el)
        return

    raise ExprError(f"AST node '{type(node).__name__}' is not allowed in expressions")


def _eval_node(node: ast.AST, env: dict[str, Any]) -> Any:
    """Evaluate an AST node within the provided environment."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _ALLOWED_FUNCTIONS and node.id in env:
            return env[node.id]
        raise ExprError(f"Variable '{node.id}' is not defined")

    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "persistent":
            if node.attr.startswith("_"):
                raise ExprError(f"Access to private or dunder attribute '{node.attr}' is forbidden")
            persistent = env.get("persistent")
            if persistent is None:
                return None
            if hasattr(persistent, node.attr):
                return getattr(persistent, node.attr)
            if isinstance(persistent, dict):
                return persistent.get(node.attr)
            return None
        raise ExprError("Illegal attribute access")

    if isinstance(node, ast.UnaryOp):
        op_fn = _ALLOWED_OPERATORS[type(node.op)]
        val = _eval_node(node.operand, env)
        return op_fn(val)

    if isinstance(node, ast.BinOp):
        op_fn = _ALLOWED_OPERATORS[type(node.op)]
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        return op_fn(left, right)

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            res = True
            for val in node.values:
                res = _eval_node(val, env)
                if not res:
                    return res
            return res
        elif isinstance(node.op, ast.Or):
            res = False
            for val in node.values:
                res = _eval_node(val, env)
                if res:
                    return res
            return res

    if isinstance(node, ast.Compare):
        left_val = _eval_node(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            comp_val = _eval_node(comp, env)
            op_fn = _ALLOWED_OPERATORS[type(op)]
            if not op_fn(left_val, comp_val):
                return False
            left_val = comp_val
        return True

    if isinstance(node, ast.IfExp):
        test_val = _eval_node(node.test, env)
        if test_val:
            return _eval_node(node.body, env)
        return _eval_node(node.orelse, env)

    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        fn_name = node.func.id
        fn = env.get(fn_name)
        if fn is None:
            if fn_name == "min":
                fn = min
            elif fn_name == "max":
                fn = max
            elif fn_name == "abs":
                fn = abs
            elif fn_name == "len":
                fn = len
            elif fn_name == "int":
                fn = int
            elif fn_name == "str":
                fn = str
            elif fn_name == "round":
                fn = round
            else:
                raise ExprError(f"Function '{fn_name}' is not provided in execution environment")

        args = [_eval_node(arg, env) for arg in node.args]
        kwargs = {kw.arg: _eval_node(kw.value, env) for kw in node.keywords if kw.arg is not None}
        return fn(*args, **kwargs)

    if isinstance(node, ast.List):
        return [_eval_node(el, env) for el in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(el, env) for el in node.elts)

    raise ExprError(f"Unsupported node type: {type(node).__name__}")
