"""Adversarial stress harness for eager-script expression evaluation (M1 Challenger 1).

Probes compile_expr and CompiledExpr.evaluate against malicious AST nodes, deep nesting,
disallowed operators, runtime zero-division, type mismatches, and sandbox escape vectors.
"""

from __future__ import annotations

import pytest

from eager_script.expr import ExprError, compile_expr


class TestExprSecurityAdversarial:
    """Stress testing the AST expression security sandbox against malicious constructs."""

    def test_forbidden_dunder_and_attribute_access(self) -> None:
        """Introspection attributes (__class__, __subclasses__, __globals__, etc.) must be blocked."""
        malicious_expressions = [
            "().__class__",
            "().__class__.__base__",
            "(1).__class__.__bases__[0].__subclasses__()",
            "persistent.__class__",
            "persistent.__dict__",
            "persistent.__globals__",
            "persistent._private",
            "persistent._secret_key",
            "target.attribute",
            "foo.bar.baz",
            "user.name",
        ]

        for expr_str in malicious_expressions:
            with pytest.raises(ExprError) as exc_info:
                compile_expr(expr_str)
            assert (
                "forbidden" in str(exc_info.value).lower()
                or "not allowed" in str(exc_info.value).lower()
            )

    def test_forbidden_builtins_and_function_calls(self) -> None:
        """Calls to dangerous Python builtins or non-whitelisted functions must be blocked at compile time."""
        dangerous_calls = [
            "eval('1 + 1')",
            "exec('x = 1')",
            "open('/etc/passwd')",
            "__import__('os').system('ls')",
            "getattr(persistent, 'flag')",
            "setattr(persistent, 'flag', True)",
            "delattr(persistent, 'flag')",
            "globals()",
            "locals()",
            "vars()",
            "dir()",
            "exit()",
            "quit()",
            "breakpoint()",
            "input()",
            "print('hello')",
            "help()",
            "compile('1+1', '', 'eval')",
        ]

        for call_str in dangerous_calls:
            with pytest.raises(ExprError):
                compile_expr(call_str)

    def test_disallowed_syntax_constructs(self) -> None:
        """Complex Python AST nodes (comprehensions, lambdas, subscripts, walrus) must be rejected."""
        disallowed_nodes = [
            "lambda x: x * 2",
            "[x for x in [1, 2, 3]]",
            "{x: x for x in [1, 2]}",
            "{x for x in [1, 2]}",
            "(x for x in [1, 2])",
            "{'a': 1, 'b': 2}",  # Dict literal not allowed
            "{1, 2, 3}",  # Set literal not allowed
            "items[0]",  # Subscript not allowed
            "data['key']",
            "items[1:3]",
            "f'Value: {x}'",  # JoinedStr / f-string
            "(x := 10)",  # NamedExpr / walrus
        ]

        for code in disallowed_nodes:
            with pytest.raises(ExprError):
                compile_expr(code)

    def test_disallowed_operators(self) -> None:
        """Unwhitelisted operators (pow, bitwise, shifts, matmult) must be rejected at compile time."""
        disallowed_ops = [
            "2 ** 10",  # Pow (prevents CPU DoS via 2**1000000)
            "5 & 3",  # BitAnd
            "5 | 3",  # BitOr
            "5 ^ 3",  # BitXor
            "~5",  # Invert
            "1 << 10",  # LShift
            "16 >> 2",  # RShift
            "a @ b",  # MatMult
        ]

        for op_code in disallowed_ops:
            with pytest.raises(ExprError, match="is not allowed"):
                compile_expr(op_code)

    def test_deeply_nested_ast_resilience(self) -> None:
        """Expressions with deep parenthetical nesting must either compile or raise ExprError."""
        # 100 nested parentheses
        deep_parens = "(" * 100 + "42" + ")" * 100
        expr = compile_expr(deep_parens)
        assert expr.evaluate({}) == 42

        # 300 nested unary minuses
        deep_negations = " - " * 300 + "1"
        expr2 = compile_expr(deep_negations)
        assert expr2.evaluate({}) == 1

        # Excessively deep parentheses (500+) rejected by Python syntax parser as ExprError
        too_deep = "(" * 600 + "1" + ")" * 600
        with pytest.raises(ExprError, match="Expression syntax error"):
            compile_expr(too_deep)


class TestExprRuntimeResilienceAdversarial:
    """Stress testing runtime arithmetic safety, type mismatch wrapping, and short-circuiting."""

    def test_division_by_zero_all_operators(self) -> None:
        """All zero-division variants (/, //, %) must raise ExprError, not unhandled ZeroDivisionError."""
        test_cases = [
            ("10 / 0", {}),
            ("10 // 0", {}),
            ("10 % 0", {}),
            ("x / 0.0", {"x": 10.0}),
            ("x // 0.0", {"x": 10.0}),
            ("x % 0.0", {"x": 10.0}),
            ("x / y", {"x": 10, "y": 0}),
            ("x // y", {"x": 10, "y": 0}),
            ("x % y", {"x": 10, "y": 0}),
            ("10 / False", {}),
            ("10 // False", {}),
            ("10 % False", {}),
        ]

        for code, env in test_cases:
            expr = compile_expr(code)
            with pytest.raises(ExprError, match="Division by zero"):
                expr.evaluate(env)

    def test_type_mismatches_wrapped_in_expr_error(self) -> None:
        """Binary, unary, and comparison type errors must be caught and re-raised as ExprError."""
        type_mismatches = [
            ("10 + 'string'", {}),
            ("'string' + 10", {}),
            ("'string' - 'ing'", {}),
            ("[1, 2] - [1]", {}),
            ("'string' * 'string'", {}),
            ("'string' / 2", {}),
            ("'string' // 2", {}),
            ("'string' % 2", {}),
            ("+'string'", {}),
            ("-'string'", {}),
            ("10 < 'string'", {}),
            ("'string' > 10", {}),
            ("10 in 20", {}),
            ("10 not in 20", {}),
            ("10 in None", {}),
            ("abs('string')", {}),
            ("len(123)", {}),
            ("int('not_a_number')", {}),
            ("round('not_a_number')", {}),
            ("round(1.5, 'two')", {}),
            ("min()", {}),
            ("max()", {}),
        ]

        for code, env in type_mismatches:
            expr = compile_expr(code)
            with pytest.raises(ExprError):
                expr.evaluate(env)

    def test_short_circuiting_logic(self) -> None:
        """and, or, and IfExp must short-circuit, preventing evaluation of error-raising branches."""
        # False and (1 / 0) must return False without evaluating zero division
        assert compile_expr("false and (1 / 0)").evaluate({}) is False

        # True or (1 / 0) must return True without evaluating zero division
        assert compile_expr("true or (1 / 0)").evaluate({}) is True

        # IfExp body / orelse short-circuiting
        assert compile_expr("10 if true else (1 / 0)").evaluate({}) == 10
        assert compile_expr("(1 / 0) if false else 20").evaluate({}) == 20

        # Chained comparisons short-circuiting
        assert compile_expr("1 > 5 and (1 / 0)").evaluate({}) is False

    def test_literal_normalization_preserves_strings(self) -> None:
        """Literals 'true', 'false', 'none' are normalized without mangling string contents or identifiers."""
        # Standalone booleans normalized
        assert compile_expr("true").evaluate({}) is True
        assert compile_expr("false").evaluate({}) is False
        assert compile_expr("none").evaluate({}) is None

        # String literals containing true/false/none must NOT be altered
        assert compile_expr("'true'").evaluate({}) == "true"
        assert compile_expr('"false"').evaluate({}) == "false"
        assert compile_expr("'none'").evaluate({}) == "none"
        assert compile_expr('"It is true that false is none"').evaluate({}) == "It is true that false is none"

        # Variable identifiers containing true/false as substrings must not be replaced
        env = {"not_true": 123, "falsehood": 456}
        assert compile_expr("not_true == 123").evaluate(env) is True
        assert compile_expr("falsehood == 456").evaluate(env) is True

    def test_persistent_attribute_evaluation(self) -> None:
        """persistent.<attr> access handles object attributes, dictionary keys, and missing persistent."""
        class MockPersistent:
            def __init__(self) -> None:
                self.cleared = True
                self.score = 999

        # From object attribute
        env_obj = {"persistent": MockPersistent()}
        assert compile_expr("persistent.cleared").evaluate(env_obj) is True
        assert compile_expr("persistent.score == 999").evaluate(env_obj) is True
        assert compile_expr("persistent.unseen").evaluate(env_obj) is None

        # From dict key
        env_dict = {"persistent": {"cleared": True, "score": 999}}
        assert compile_expr("persistent.cleared").evaluate(env_dict) is True
        assert compile_expr("persistent.unseen").evaluate(env_dict) is None

        # When persistent is None or not provided
        assert compile_expr("persistent.cleared").evaluate({}) is None
        assert compile_expr("persistent.cleared").evaluate({"persistent": None}) is None

    def test_undefined_variable_raises_expr_error(self) -> None:
        """Lookup of an undefined variable in env must raise a clear ExprError."""
        expr = compile_expr("undefined_var + 1")
        with pytest.raises(ExprError, match="Variable 'undefined_var' is not defined"):
            expr.evaluate({})
