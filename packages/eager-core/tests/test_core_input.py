from eager_core.input import InputAction, Keymap


def test_input_action_values():
    assert InputAction.ADVANCE == "advance"
    assert InputAction.ROLLBACK == "rollback"
    assert InputAction.CHOOSE == "choose"


def test_keymap_mapping():
    keymap = Keymap()
    assert keymap.map_key("space") == InputAction.ADVANCE
    assert keymap.map_key("SPACE") == InputAction.ADVANCE
    assert keymap.map_key("pageup") == InputAction.ROLLBACK
    assert keymap.map_key("nonexistent") is None


def test_keymap_custom_binding():
    keymap = Keymap()
    keymap.bind("x", InputAction.ADVANCE)
    assert keymap.map_key("x") == InputAction.ADVANCE
    keymap.unbind("x")
    assert keymap.map_key("x") is None
