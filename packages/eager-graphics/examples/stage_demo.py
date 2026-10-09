"""Demonstration of Eager-Graphics Graphics & Stage Compositor with Eager StoryVM."""

from __future__ import annotations

import json

from eager_runtime import DialogueEvent, EventDispatcher, HookEvent, StoryVM
from eager_script import parse_graph

from eager_graphics import StageCompositor, StageDirector

STORY = """
## Courtyard --- courtyard
~ bg castle_courtyard with crossfade duration=1.0
~ show alice cheerful at left with slide_right duration=0.5
Alice (excited): Look, the castle gates are open!
~ show guard stern at right with fade duration=0.3
Guard: Halt! State your name and business.
Alice (serious): We come seeking audience with the King.
~ move alice to center duration=0.5 easing=ease_in_out_quad
~ hide guard with dissolve duration=0.4
Alice (smiling): He let us through without a fight.
~ shake intensity=1.5 duration=0.3
Alice (panicked): Wait, did you feel that earthquake?!
"""


def main() -> None:
    print("=" * 60)
    print("  Eager-Graphics Graphics & Stage Compositor Demo")
    print("=" * 60)

    # 1. Parse screenplay and initialize Eager VM
    graph = parse_graph(STORY)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    # 2. Setup stage compositor and bind director to dispatcher
    compositor = StageCompositor(virtual_width=1920, virtual_height=1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    beat = 1
    while not vm.is_ended:
        event = vm.step()
        if event is None:
            break

        dispatcher.dispatch(event)

        # Advance animations by simulated time
        compositor.update(dt=0.1)

        print(f"\n--- [Beat {beat}] Event: {event.type} ---")
        if isinstance(event, DialogueEvent):
            print(f"  Dialogue: {event.speaker}: \"{event.text}\"")
            if event.emotion:
                print(f"  (Emotion: {event.emotion})")
        elif isinstance(event, HookEvent):
            print(f"  Hook: ~ {event.hook_name} {event.args}")

        # Render list state
        items = compositor.render_list()
        print(f"  Active Render Elements ({len(items)}):")
        for item in items:
            print(
                f"    • [{item.layer.upper():<10}] asset='{item.asset_id}' "
                f"pos=({item.x:.1f}, {item.y:.1f}) opacity={item.opacity:.2f} "
                f"z_order={item.z_order}"
            )

        beat += 1

    print("\n" + "=" * 60)
    print("Story finished! Snapshotting final visual stage state:")
    saved_state = compositor.save_state()
    print(json.dumps(saved_state, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
