"""Interactive Visual Novel window player powered by Eager-Graphics and PIL."""

from __future__ import annotations

import sys

import pyglet
from eager_runtime import EventDispatcher, StoryVM
from eager_script import parse_graph

from eager_graphics import StageCompositor, StageDirector
from eager_graphics.renderers.pil import PILPlayer

STORY = """
## Courtyard --- courtyard
~ bg castle_courtyard with crossfade duration=1.0
~ show alice cheerful at left with slide_right duration=0.6
Alice (excited): Welcome to the Citadel of Aethelgard!
~ show guard stern at right with fade duration=0.4
Guard: Halt! State your identity and purpose at once.
Alice (serious): We are royal emissaries bearing the seal.
~ move alice to center duration=0.6 easing=ease_in_out_quad
Guard: Very well. You may proceed, but choose your destination wisely.
~ hide guard with dissolve duration=0.4
? Enter the Great Hall of the King (hall)
? Investigate the Whispering Woods (woods)

## Great Hall --- hall
~ bg hall_interior with crossfade duration=1.0
~ show alice smiling at center with fade duration=0.4
Alice (smiling): The throne room is breathtaking!
~ shake intensity=2.0 duration=0.4
Alice (panicked): By the gods! The ceiling is crumbling!
Narrator: The royal adventure has only just begun...

## Whispering Woods --- woods
~ bg dark_woods with crossfade duration=1.0
~ show alice worried at center with fade duration=0.4
Alice (worried): The shadows in these woods move on their own...
Narrator: A chill wind blows through the ancient trees...
"""


def main() -> None:
    headless = "--headless" in sys.argv or "--test" in sys.argv

    # 1. Parse screenplay script into SceneGraph
    graph = parse_graph(STORY)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    # 2. Setup Stage Compositor and Director
    compositor = StageCompositor(virtual_width=1920, virtual_height=1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    # 3. Create interactive PIL Player
    player = PILPlayer(
        vm=vm,
        compositor=compositor,
        director=director,
        dispatcher=dispatcher,
        width=1280,
        height=720,
        title="Eager-Graphics Visual Novel Demo (PIL)",
        visible=not headless,
    )

    if headless:
        print("Running in headless test mode...")
        # Step through and simulate
        while not player.is_finished:
            if player.active_choice_prompt is not None:
                player.make_choice(0)
            else:
                player.advance_story()
            player.on_draw()
        player.close()
        print("Headless playthrough completed successfully!")
    else:
        print("Starting Eager-Graphics PIL Player...")
        print("Controls: Click / Space / Enter = Advance | 1-9 = Choices | Backspace = Undo | Esc/Q = Quit")
        pyglet.app.run()


if __name__ == "__main__":
    main()
