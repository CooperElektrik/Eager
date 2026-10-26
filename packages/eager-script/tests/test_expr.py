"""Tests for the safe expression evaluator."""

import pytest

from eager_script.expr import ExprError, compile_expr


def test_compile_and_eval_simple_arithmetic() -> None:
    expr = compile_expr("1 + 2 * 3")
    assert expr.evaluate({}) == 7


def test_compile_and_eval_variables() -> None:
    expr = compile_expr("gold >= 10 and has_key")
    assert expr.evaluate({"gold": 15, "has_key": True}) is True
    assert expr.evaluate({"gold": 5, "has_key": True}) is False


def test_literals_case_insensitivity() -> None:
    expr = compile_expr("true and not false")
    assert expr.evaluate({}) is True


def test_persistent_attribute_access_allowed() -> None:
    class MockPersistent:
        ending_a = True

    expr = compile_expr("persistent.ending_a")
    assert expr.evaluate({"persistent": MockPersistent()}) is True


def test_reject_arbitrary_attribute_access() -> None:
    with pytest.raises(ExprError, match="Attribute access .* is forbidden"):
        compile_expr("user.__class__")

    with pytest.raises(ExprError, match="Attribute access .* is forbidden"):
        compile_expr("player.inventory")


def test_reject_unauthorized_functions() -> None:
    with pytest.raises(ExprError, match="Function 'eval' is not in the whitelist"):
        compile_expr("eval('1 + 1')")

    with pytest.raises(ExprError, match="Calls to complex expressions or attributes are forbidden"):
        compile_expr("__import__('os').system('ls')")


def test_reject_persistent_private_or_dunder_attribute_access() -> None:
    with pytest.raises(ExprError, match="Access to private or dunder attribute '__class__' is forbidden"):
        compile_expr("persistent.__class__")

    with pytest.raises(ExprError, match="Access to private or dunder attribute '_secret' is forbidden"):
        compile_expr("persistent._secret")


def test_whitelisted_functions() -> None:
    expr = compile_expr("max(10, min(gold, 20))")
    assert expr.evaluate({"gold": 15}) == 15
    assert expr.evaluate({"gold": 25}) == 20


@pytest.mark.parametrize(
    "expr_src",
    [
        "10 / 0",
        "10 // 0",
        "10 % 0",
        "10 / 0.0",
        "10 // 0.0",
        "10 % 0.0",
    ],
)
def test_eval_division_by_zero_raises_expr_error(expr_src: str) -> None:
    with pytest.raises(ExprError, match="Division by zero"):
        compile_expr(expr_src).evaluate({})


def test_eval_variable_division_by_zero() -> None:
    compiled = compile_expr("total / count")
    with pytest.raises(ExprError, match="Division by zero"):
        compiled.evaluate({"total": 100, "count": 0})


@pytest.mark.parametrize(
    "invalid_binop",
    [
        "'abc' - 5",
        "'hello' + 5",
        "None + 5",
        "5 * 'hello' * 2.5",
        "'hello' / 2",
    ],
)
def test_binary_op_type_mismatch_raises_expr_error(invalid_binop: str) -> None:
    compiled = compile_expr(invalid_binop)
    with pytest.raises(ExprError, match="Binary operation failed"):
        compiled.evaluate({})


def test_eval_unsupported_unary_operand_raises_expr_error() -> None:
    compiled = compile_expr("-'text'")
    with pytest.raises(ExprError, match="Unary operation failed"):
        compiled.evaluate({})


@pytest.mark.parametrize(
    "invalid_cmp",
    [
        "'abc' < 5",
        "5 < 'abc'",
        "5 in 123",
        "'a' in None",
    ],
)
def test_comparison_type_mismatch_raises_expr_error(invalid_cmp: str) -> None:
    compiled = compile_expr(invalid_cmp)
    with pytest.raises(ExprError, match="Comparison operation failed"):
        compiled.evaluate({})


@pytest.mark.parametrize(
    "invalid_call",
    [
        "len(42)",
        "int('invalid')",
        "round('string')",
        "abs('string')",
    ],
)
def test_eval_function_call_error_raises_expr_error(invalid_call: str) -> None:
    compiled = compile_expr(invalid_call)
    with pytest.raises(ExprError, match="Function call '.*' failed"):
        compiled.evaluate({})


@pytest.mark.parametrize(
    "unsupported_src",
    [
        "a & b",
        "a | b",
        "a ^ b",
        "~a",
        "a << 2",
        "a >> 2",
        "a @ b",
        "a ** 2",
    ],
)
def test_unsupported_operators_rejected_at_compile(unsupported_src: str) -> None:
    with pytest.raises(ExprError):
        compile_expr(unsupported_src)


@pytest.mark.parametrize(
    "forbidden_syntax",
    [
        "items[0]",
        "items[1:3]",
        "(lambda x: x + 1)(5)",
        "[x * 2 for x in items]",
        "{x for x in items}",
        "{'a': 1, 'b': 2}",
        "{1, 2, 3}",
        "(x := 10)",
        "open('secret.txt')",
        "items.append(5)",
    ],
)
def test_disallowed_ast_syntax_rejected_at_compile(forbidden_syntax: str) -> None:
    with pytest.raises(ExprError):
        compile_expr(forbidden_syntax)


@pytest.mark.parametrize(
    "empty_or_broken",
    [
        "",
        "   ",
        "\t\n",
        "1 +",
        "(1 + 2",
        "'unclosed string",
        "x and",
        "not",
    ],
)
def test_empty_and_syntax_error_expressions_raise_expr_error(empty_or_broken: str) -> None:
    with pytest.raises(ExprError):
        compile_expr(empty_or_broken)


def test_undefined_variable_raises_expr_error() -> None:
    compiled = compile_expr("missing_var + 10")
    with pytest.raises(ExprError, match="Variable 'missing_var' is not defined"):
        compiled.evaluate({})

