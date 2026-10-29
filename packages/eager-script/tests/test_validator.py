"""Tests for eager_script validator: structural link and syntax validation."""

from eager_script import parse, validate

SAMPLE_SCRIPT = """
## The Clearing --- clearing_label

# This is an ambient comment
Alice: {voice:alice_01.ogg} Welcome to the ancient ruins!
- Look at those carved pillars.
/ Be careful where you step.

The wind howls through the stone.
A cold chill runs down your spine.

~ inspect_pillars

? Examine the glowing runes (runes)
? Turn back towards town (exit)

## Ancient Runes --- runes
The runes shimmer with blue light.
>> secret_subroutine
> clearing_label

## Subroutine --- secret_subroutine
Alice: A hidden compartment opened!
<<

## Town Exit --- exit
You head back to town.
"""


def test_valid_script_passes_validation() -> None:
    items = parse(SAMPLE_SCRIPT)
    result = validate(items)
    assert result.is_valid
    assert len(result.errors) == 0


def test_duplicate_label_error() -> None:
    script = """
    ## Scene One --- scene1
    Alice: Hello
    ## Scene One Again --- scene1
    Alice: Bye
    """
    items = parse(script)
    result = validate(items)
    assert not result.is_valid
    assert any("Duplicate label" in err.message for err in result.errors)


def test_undefined_target_error() -> None:
    script = """
    ## Start --- start
    > nonexistent_target
    ? Option (missing_label)
    """
    items = parse(script)
    result = validate(items)
    assert not result.is_valid
    assert len(result.errors) == 2
    assert any("nonexistent_target" in err.message for err in result.errors)
    assert any("missing_label" in err.message for err in result.errors)


def test_unreturned_call_warning() -> None:
    script = """
    ## Start --- start
    >> my_subroutine
    ## Sub --- my_subroutine
    Alice: Done.
    """
    items = parse(script)
    result = validate(items)
    assert result.is_valid  # Warnings do not invalidate
    assert len(result.warnings) == 1
    assert "Subroutine call" in result.warnings[0].message


def test_cyclical_traversal_warning() -> None:
    # 2-node unconditional loop
    script = """
    ## Intro --- intro
    Alice: Hello
    > tiny_slug

    ## Tiny Slug --- tiny_slug
    Alice: World
    > intro
    """
    items = parse(script)
    result = validate(items)
    assert result.is_valid
    cycle_warnings = [w for w in result.warnings if "Cyclical traversal detected" in w.message]
    assert len(cycle_warnings) == 1
    assert "intro -> tiny_slug -> intro" in cycle_warnings[0].message
    assert cycle_warnings[0].level == "warning"

    # Self-loop
    script_self = """
    ## Intro --- intro
    Alice: Hello
    > intro
    """
    items_self = parse(script_self)
    result_self = validate(items_self)
    cycle_self = [w for w in result_self.warnings if "Cyclical traversal detected" in w.message]
    assert len(cycle_self) == 1
    assert "intro -> intro" in cycle_self[0].message


def test_branching_loop_with_choices_not_flagged() -> None:
    # Game hub looping back via player choices should not be flagged as unconditional cycle
    script = """
    ## Town Square --- town
    Alice: What do you want to do?
    ? Enter tavern (tavern)
    ? Depart town (leave)

    ## Tavern --- tavern
    Bartender: Welcome to the tavern!
    > town

    ## Departure --- leave
    You walk away into the sunset.
    """
    items = parse(script)
    result = validate(items)
    assert result.is_valid
    cycle_warnings = [w for w in result.warnings if "Cyclical traversal detected" in w.message]
    assert len(cycle_warnings) == 0


def test_unreachable_statements_within_scene() -> None:
    # Code after jump
    script_jump = """
    ## Start --- start
    Alice: Hello
    > finish
    Bob: This is unreachable!

    ## Finish --- finish
    Alice: Done.
    """
    result = validate(parse(script_jump))
    unreachable = [
        w for w in result.warnings if "Unreachable code: statement after jump" in w.message
    ]
    assert len(unreachable) == 1

    # Code after return
    script_ret = """
    ## Sub --- sub
    Alice: Inside subroutine
    <<
    Bob: This is unreachable after return!
    """
    result_ret = validate(parse(script_ret))
    unreachable_ret = [
        w
        for w in result_ret.warnings
        if "Unreachable code: statement after return" in w.message
    ]
    assert len(unreachable_ret) == 1

    # Code after choice menu
    script_choice = """
    ## Choices --- choices
    ? Option 1 (finish)
    ? Option 2 (finish)
    Alice: This is unreachable after choice menu!

    ## Finish --- finish
    """
    result_choice = validate(parse(script_choice))
    unreachable_choice = [
        w
        for w in result_choice.warnings
        if "Unreachable code: statement after choice menu" in w.message
    ]
    assert len(unreachable_choice) == 1


def test_unreachable_scene_cluster() -> None:
    # Scenes referencing each other but disconnected from script entry point
    script = """
    ## Main --- main
    Alice: Welcome to main story
    > finish

    ## Finish --- finish
    Alice: Goodbye

    ## Island A --- island_a
    Alice: Secret island A
    > island_b

    ## Island B --- island_b
    Alice: Secret island B
    > island_a
    """
    result = validate(parse(script))
    unreachable_scenes = [
        w for w in result.warnings if "unreachable from the script entry point" in w.message
    ]
    assert len(unreachable_scenes) == 2
    warned_labels = {w.message for w in unreachable_scenes}
    assert any("island_a" in msg for msg in warned_labels)
    assert any("island_b" in msg for msg in warned_labels)


def test_if_branches_do_not_falsely_trigger_unreachable_or_cycle_warnings() -> None:
    script = """
    ## Main --- main
    @if cond == 1
        > target_a
    @elif cond == 2
        > target_b
    @else
        > target_c
    @end
    Alice: After if block
    > finish

    ## Target A --- target_a
    Alice: At target A
    > main

    ## Target B --- target_b
    Alice: At target B
    > finish

    ## Target C --- target_c
    Alice: At target C
    > finish

    ## Finish --- finish
    Alice: All done
    """
    result = validate(parse(script))
    unreachable_warnings = [
        w for w in result.warnings if "Unreachable code" in w.message
    ]
    assert unreachable_warnings == []

    unreachable_scene_warnings = [
        w for w in result.warnings if "unreachable from the script entry point" in w.message
    ]
    assert unreachable_scene_warnings == []

    cycle_warnings = [
        w for w in result.warnings if "Infinite loop detected" in w.message
    ]
    assert cycle_warnings == []

