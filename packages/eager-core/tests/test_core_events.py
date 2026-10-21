from eager_core.events import (
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)


def test_events_to_dict():
    enter = SceneEnterEvent("intro", "Introduction", 1)
    assert enter.type == "scene_enter"
    assert enter.to_dict()["scene_id"] == "intro"

    diag = DialogueEvent("Alice", "Hello world!", "voice1", "happy", 2)
    assert diag.type == "dialogue"
    assert diag.to_dict()["speaker"] == "Alice"

    narr = NarrationEvent("A quiet night.", 3)
    assert narr.type == "narration"

    opt1 = ChoiceOption(0, "Go left", "left_path", 10)
    opt2 = ChoiceOption(1, "Go right", "right_path", 11)
    choice = ChoicePromptEvent(options=(opt1, opt2), line_number=9)
    assert choice.type == "choice_prompt"
    opts = choice.to_dict()["options"]
    assert isinstance(opts, list)
    assert len(opts) == 2

    exit_ev = SceneExitEvent("intro", "jump", "next", 12)
    assert exit_ev.type == "scene_exit"

    end = StoryEndEvent("next", "completed")
    assert end.type == "story_end"


def test_choice_option_dict_roundtrip():
    opt = ChoiceOption(0, "Proceed", "start", 1, condition="visited('room')", enabled=True)
    d = opt.to_dict()
    assert d["index"] == 0
    assert d["text"] == "Proceed"
    assert d["condition"] == "visited('room')"

    reconstructed = ChoiceOption.from_dict(d)
    assert reconstructed.index == opt.index
    assert reconstructed.text == opt.text
    assert reconstructed.target == opt.target
    assert reconstructed.condition == opt.condition
