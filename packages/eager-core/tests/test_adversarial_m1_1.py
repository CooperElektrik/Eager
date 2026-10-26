"""Adversarial stress harness for eager-core foundation primitives (M1 Challenger 1).

Probes Vec2 arithmetic with extremes and non-numerics, Color.from_hex and Color.from_dict
fuzzing, and TextReveal typewriter pacing with rapid ticks, multiple fast tags, and negative times.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from eager_core.exceptions import ColorParseError
from eager_core.text import TextReveal, parse_text_tags
from eager_core.types import Color, Vec2


class TestVec2Adversarial:
    """Stress testing Vec2 arithmetic safety, immutability, and coercions."""

    def test_vec2_arithmetic_extremes(self) -> None:
        """Vec2 must handle zero, negative, extreme magnitudes, and inf/nan without crashing."""
        extremes = [
            0.0,
            -0.0,
            1.0,
            -1.0,
            1e-300,
            1e308,
            -1e308,
            float("inf"),
            float("-inf"),
            float("nan"),
        ]

        for x in extremes:
            for y in extremes:
                v = Vec2(x, y)
                neg_v = -v
                if not math.isnan(x):
                    assert neg_v.x == -x
                if not math.isnan(y):
                    assert neg_v.y == -y

                # Addition with Vec2
                v2 = v + Vec2(1.0, -1.0)
                assert isinstance(v2, Vec2)

                # Subtraction with Vec2
                v3 = v - Vec2(1.0, -1.0)
                assert isinstance(v3, Vec2)

                # Scalar multiplication (both orders)
                v_mul = v * 2.0
                v_rmul = 2.0 * v
                assert isinstance(v_mul, Vec2)
                assert isinstance(v_rmul, Vec2)

                # Lerp towards origin
                v_lerp = v.lerp(Vec2(0.0, 0.0), 0.5)
                assert isinstance(v_lerp, Vec2)

                # Serialization
                t = v.to_tuple()
                d = v.to_dict()
                assert len(t) == 2
                assert "x" in d and "y" in d

    def test_vec2_division_by_zero(self) -> None:
        """Vec2 division by integer 0, float 0.0, -0.0, or False must raise ZeroDivisionError."""
        v = Vec2(10.0, 20.0)

        for zero_val in (0, 0.0, -0.0, False):
            with pytest.raises(ZeroDivisionError, match="Cannot divide Vec2 by zero"):
                _ = v / zero_val

        # Non-zero division must succeed
        v_div = v / 2.0
        assert v_div == Vec2(5.0, 10.0)

        # Division by extreme scalar
        v_tiny = v / 1e300
        assert isinstance(v_tiny, Vec2)

    def test_vec2_incompatible_operands_rejection(self) -> None:
        """Vec2 arithmetic methods must return NotImplemented (causing TypeError) on non-numeric operands."""
        v = Vec2(5.0, 10.0)
        incompatible_operands: list[Any] = [
            "string",
            None,
            object(),
            [1.0],  # list len != 2
            [1.0, 2.0, 3.0],  # list len != 2
            (1.0,),  # tuple len != 2
            (1.0, 2.0, 3.0),  # tuple len != 2
            ("a", "b"),  # tuple of non-numeric
            (1.0, "bad"),  # tuple with invalid element
            {"x": 1.0, "y": 2.0},  # dict operand
            lambda: None,
        ]

        for bad in incompatible_operands:
            # Addition
            with pytest.raises(TypeError):
                _ = v + bad
            with pytest.raises(TypeError):
                _ = bad + v

            # Subtraction
            with pytest.raises(TypeError):
                _ = v - bad
            with pytest.raises(TypeError):
                _ = bad - v

            # Multiplication
            with pytest.raises(TypeError):
                _ = v * bad
            with pytest.raises(TypeError):
                _ = bad * v

            # Division
            with pytest.raises(TypeError):
                _ = v / bad

    def test_vec2_from_dict_fuzzing(self) -> None:
        """Vec2.from_dict must validate input types and structures rigorously."""
        # Valid cases
        assert Vec2.from_dict({"x": 10, "y": 20}) == Vec2(10.0, 20.0)
        assert Vec2.from_dict({"x": "1.5", "y": "-2.5"}) == Vec2(1.5, -2.5)
        # Extra keys tolerated
        assert Vec2.from_dict({"x": 1.0, "y": 2.0, "z": 3.0}) == Vec2(1.0, 2.0)

        # Non-mapping input raises TypeError
        for non_map in (None, 123, "string", [1, 2], (1, 2)):
            with pytest.raises(TypeError, match="expects a Mapping"):
                Vec2.from_dict(non_map)  # pyright: ignore[reportArgumentType]

        # Missing required keys raises KeyError
        for bad_keys in ({}, {"x": 1.0}, {"y": 2.0}, {"a": 1, "b": 2}):
            with pytest.raises(KeyError, match="requires 'x' and 'y' keys"):
                Vec2.from_dict(bad_keys)

        # Non-numeric coordinate types raise TypeError
        for bad_vals in (
            {"x": None, "y": 1.0},
            {"x": 1.0, "y": None},
            {"x": [1.0], "y": 2.0},
            {"x": 1.0, "y": {"nested": 2}},
        ):
            with pytest.raises(TypeError, match="must be numbers or numeric strings"):
                Vec2.from_dict(bad_vals)

        # Unparseable strings raise ValueError
        with pytest.raises(ValueError, match="could not be converted to float"):
            Vec2.from_dict({"x": "not_a_number", "y": 1.0})

    def test_vec2_geometry_invariants(self) -> None:
        """Verify Euclidean distance invariants and lerp stability."""
        a = Vec2(0.0, 0.0)
        b = Vec2(3.0, 4.0)
        c = Vec2(6.0, 0.0)

        assert math.isclose(a.distance_to(b), 5.0)
        # Triangle inequality: d(a, c) <= d(a, b) + d(b, c)
        assert a.distance_to(c) <= a.distance_to(b) + b.distance_to(c)

        # Distance to self is 0.0
        assert b.distance_to(b) == 0.0

        # Extreme magnitude distance avoids intermediate float overflow
        large1 = Vec2(1e300, 0.0)
        large2 = Vec2(-1e300, 0.0)
        assert not math.isinf(large1.distance_to(large2))


class TestColorAdversarial:
    """Stress testing Color parsing, clamping, and hex/dict deserialization."""

    def test_color_from_hex_valid_and_whitespace(self) -> None:
        """Color.from_hex handles all standard hex formats with leading/trailing whitespace and case."""
        cases = [
            ("white", Color(1.0, 1.0, 1.0, 1.0)),
            ("  BLACK  ", Color(0.0, 0.0, 0.0, 1.0)),
            ("Red", Color(1.0, 0.0, 0.0, 1.0)),
            ("TRANSPARENT", Color(0.0, 0.0, 0.0, 0.0)),
            ("#fff", Color(1.0, 1.0, 1.0, 1.0)),
            ("fff", Color(1.0, 1.0, 1.0, 1.0)),
            ("#0000", Color(0.0, 0.0, 0.0, 0.0)),
            ("ffff", Color(1.0, 1.0, 1.0, 1.0)),
            ("#ffffff", Color(1.0, 1.0, 1.0, 1.0)),
            ("123456", Color(0x12 / 255.0, 0x34 / 255.0, 0x56 / 255.0, 1.0)),
            ("#12345678", Color(0x12 / 255.0, 0x34 / 255.0, 0x56 / 255.0, 0x78 / 255.0)),
            ("AABBCCDD", Color(0xAA / 255.0, 0xBB / 255.0, 0xCC / 255.0, 0xDD / 255.0)),
        ]
        for hex_str, expected in cases:
            res = Color.from_hex(hex_str)
            assert math.isclose(res.r, expected.r, abs_tol=1e-3)
            assert math.isclose(res.g, expected.g, abs_tol=1e-3)
            assert math.isclose(res.b, expected.b, abs_tol=1e-3)
            assert math.isclose(res.a, expected.a, abs_tol=1e-3)

    def test_color_from_hex_malformed_fuzzing(self) -> None:
        """Color.from_hex must raise ColorParseError on every malformed, out-of-spec, or non-hex string."""
        malformed_strings = [
            "",
            "   ",
            "#",
            "##",
            "###",
            "##fff",
            "#0",  # len 1
            "#00",  # len 2
            "#12345",  # len 5
            "12345",  # len 5
            "#1234567",  # len 7
            "1234567",  # len 7
            "#123456789",  # len 9
            "1234567890",  # len 10
            "#xyz",
            "#ghijkl",
            "#12345g",
            "rgba(1, 2, 3, 4)",
            "hsl(0, 100%, 50%)",
            "\0",
            "\n\r\t",
            "none",
            "null",
            "undefined",
            "purple",  # not in named list
            "orange",  # not in named list
        ]

        for bad_hex in malformed_strings:
            with pytest.raises(ColorParseError, match="Invalid hex color string"):
                Color.from_hex(bad_hex)

    def test_color_from_dict_fuzzing(self) -> None:
        """Color.from_dict must validate types, missing keys, and clamp float channels."""
        # Valid dict with default alpha
        c1 = Color.from_dict({"r": 0.2, "g": 0.4, "b": 0.6})
        assert (c1.r, c1.g, c1.b, c1.a) == (0.2, 0.4, 0.6, 1.0)

        # Clamping out-of-range floats to [0.0, 1.0]
        c2 = Color.from_dict({"r": -100.0, "g": 200.0, "b": 10.0, "a": -5.0})
        assert (c2.r, c2.g, c2.b, c2.a) == (0.0, 1.0, 1.0, 0.0)

        # Numeric strings coercion and clamping
        c3 = Color.from_dict({"r": "1.5", "g": "-0.5", "b": "0.5", "a": "1.0"})
        assert (c3.r, c3.g, c3.b, c3.a) == (1.0, 0.0, 0.5, 1.0)

        # Non-mapping rejection
        for non_map in (None, 123, "bad", [1, 2, 3]):
            with pytest.raises(TypeError, match="expects a Mapping"):
                Color.from_dict(non_map)  # pyright: ignore[reportArgumentType]

        # Missing required keys
        for bad_dict in ({}, {"r": 1.0}, {"g": 1.0}, {"b": 1.0}, {"r": 1.0, "g": 1.0}):
            with pytest.raises(KeyError, match="missing required keys"):
                Color.from_dict(bad_dict)

        # Non-numeric channel types
        for bad_channel in (
            {"r": None, "g": 1.0, "b": 1.0},
            {"r": 1.0, "g": [0.5], "b": 1.0},
            {"r": 1.0, "g": 1.0, "b": {}},
            {"r": 1.0, "g": 1.0, "b": 1.0, "a": None},
        ):
            with pytest.raises(TypeError, match="must be numbers or numeric strings"):
                Color.from_dict(bad_channel)

        # Non-numeric strings in channels raise ColorParseError
        for bad_str in (
            {"r": "invalid", "g": 1.0, "b": 1.0},
            {"r": 1.0, "g": "not_a_num", "b": 1.0},
            {"r": 1.0, "g": 1.0, "b": "bad"},
            {"r": 1.0, "g": 1.0, "b": 1.0, "a": "bad_alpha"},
        ):
            with pytest.raises(ColorParseError, match="could not be converted to float"):
                Color.from_dict(bad_str)

    def test_color_lerp_and_bounds_invariants(self) -> None:
        """Color lerp and with_alpha strictly clamp resulting components to [0.0, 1.0]."""
        c1 = Color(0.0, 0.0, 0.0, 0.0)
        c2 = Color(1.0, 1.0, 1.0, 1.0)

        # Over-extrapolated lerp factors (t > 1.0 and t < 0.0) must clamp cleanly
        lerp_high = c1.lerp(c2, 5.0)
        assert lerp_high == Color(1.0, 1.0, 1.0, 1.0)

        lerp_low = c1.lerp(c2, -5.0)
        assert lerp_low == Color(0.0, 0.0, 0.0, 0.0)

        # with_alpha bounds clamping
        assert Color(1.0, 1.0, 1.0).with_alpha(10.0).a == 1.0
        assert Color(1.0, 1.0, 1.0).with_alpha(-10.0).a == 0.0

        # to_rgba_bytes roundtripping
        rgba_bytes = Color(0.5, 0.5, 0.5, 0.5).to_rgba_bytes()
        assert rgba_bytes == (128, 128, 128, 128)


class TestTextRevealAdversarial:
    """Stress testing TextReveal typewriter pacing, fast tags, micro-ticks, and edge cases."""

    def test_rapid_delta_time_ticks(self) -> None:
        """10,000 rapid micro-ticks must cleanly reveal text without drift beyond total_chars."""
        plain = "Rapid tick stress test: verifying typewriter accumulator stability."
        fmt = parse_text_tags(plain)
        tr = TextReveal(fmt, chars_per_second=100.0)

        # 10,000 ticks of dt = 0.0001 (total elapsed = 1.0s, revealing 100 characters max)
        for _ in range(10_000):
            tr.update(0.0001)

        assert tr.is_complete
        assert tr.visible_chars == float(len(plain))
        assert tr.current_visible_plain_text == plain

    def test_multiple_fast_tags(self) -> None:
        """Multiple {fast} tags in text must set fast_index to the latest tag offset."""
        text = "Intro {fast}middle section {fast}final animated segment."
        fmt = parse_text_tags(text)

        # Tag 1 at char 6 ('Intro ')
        # Tag 2 at char 21 ('Intro middle section ')
        expected_fast_index = 21
        assert fmt.fast_index == expected_fast_index
        assert fmt.plain_text == "Intro middle section final animated segment."

        tr = TextReveal(fmt, chars_per_second=20.0)
        assert tr.visible_chars == float(expected_fast_index)
        assert tr.current_visible_plain_text == "Intro middle section "
        assert not tr.is_complete

        # Updating advances from the fast_index position
        tr.update(0.1)  # 0.1 * 20 = 2 chars
        assert tr.visible_chars == 23.0
        assert tr.current_visible_plain_text == "Intro middle section fi"

    def test_fast_tag_bypasses_prior_pauses_retains_subsequent(self) -> None:
        """TextReveal must bypass pause markers before fast_index but pause at subsequent markers."""
        text = "Start {w=2.0}middle {fast}resumed {w=1.5}end."
        fmt = parse_text_tags(text)
        assert len(fmt.pauses) == 2
        # Pause 0 at char 6 ('Start ')
        # Fast tag at char 13 ('Start middle ')
        # Pause 1 at char 21 ('Start middle resumed ')
        assert fmt.fast_index == 13

        tr = TextReveal(fmt, chars_per_second=50.0)
        assert tr.visible_chars == 13.0
        # The pause at char 6 is bypassed
        assert tr._current_pause_idx == 1

        # Advance towards subsequent pause
        tr.update(0.1)  # 0.1 * 50 = 5 chars -> next_visible = 18 < 21
        assert tr.visible_chars == 18.0
        assert tr._pause_timer == 0.0

        # Advance past char 21 -> hits pause
        tr.update(0.1)  # next_visible = 23 >= 21
        assert tr.visible_chars == 21.0
        assert tr._pause_timer == 1.5

    def test_long_text_and_many_pauses_scaling(self) -> None:
        """TextReveal must scale efficiently on 20,000+ characters with 200 pause markers."""
        repeated_chunk = "Typewriter block segment. {w=0.01} "
        long_script = repeated_chunk * 200
        fmt = parse_text_tags(long_script)
        assert len(fmt.pauses) == 200

        tr = TextReveal(fmt, chars_per_second=5000.0)
        steps = 0
        while not tr.is_complete and steps < 50_000:
            tr.update(0.01)
            steps += 1

        assert tr.is_complete
        assert tr.visible_chars == float(len(fmt.plain_text))
        assert tr.current_visible_plain_text == fmt.plain_text

    def test_negative_dt_edge_case_observation(self) -> None:
        """EMPIRICAL FINDING: Negative dt causes visible_chars to decrement below 0.

        In TextReveal.update(dt), chars_to_reveal is dt * chars_per_second, which is negative
        when dt < 0. Without a max(0.0, ...) clamp on next_visible or current_visible_plain_text,
        Python's negative string slice plain_text[:int(visible_chars)] slices from the end of the
        string instead of yielding an empty string.
        """
        fmt = parse_text_tags("Hello world, this is a test string.")
        tr = TextReveal(fmt, chars_per_second=50.0)
        assert tr.visible_chars == 0.0
        assert tr.current_visible_plain_text == ""

        # Applying negative delta time
        tr.update(-0.1)
        # visible_chars becomes -5.0
        assert tr.visible_chars == -5.0

        # String slicing with negative index: text[:-5] returns text omitting the last 5 chars!
        # This confirms the empirical failure mode under adversarial negative dt.
        observed_text = tr.current_visible_plain_text
        assert observed_text == "Hello world, this is a test st"

    def test_complete_immediately_and_zero_chars_per_second(self) -> None:
        """complete_immediately and chars_per_second <= 0 must immediately complete."""
        fmt = parse_text_tags("Testing immediate completion with {w=5.0} pause tags.")
        tr = TextReveal(fmt, chars_per_second=10.0)
        assert not tr.is_complete

        tr.complete_immediately()
        assert tr.is_complete
        assert tr.visible_chars == float(len(fmt.plain_text))
        assert tr.current_visible_plain_text == fmt.plain_text

        # chars_per_second <= 0 initializes as complete
        tr_instant = TextReveal(fmt, chars_per_second=0.0)
        assert tr_instant.is_complete
        assert tr_instant.visible_chars == float(len(fmt.plain_text))
