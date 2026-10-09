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

