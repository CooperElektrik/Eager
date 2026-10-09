# Eager

Lightweight, headless narrative runtime and state machine for [Eager-S](https://github.com/CooperElektrik/Eager-S) screenplays.

Eager is a render-agnostic story virtual machine (VM). It handles execution flow, choice branching, subroutine call stacks (`>>` and `<<`), engine hooks (`~`), save/load snapshots, and time-travel rollbacks.

## Features

- **Headless Runtime**: Render-agnostic story VM designed to drive any frontend (Terminal, Pygame, Godot, Web).
- **Deterministic State & Save/Load**: Serializable snapshot model for instant JSON save states.
- **Time-Travel Rollback**: Effortless step-by-step history rewind.
- **Engine Hooks**: Typed dispatcher connecting screenplay `~` markup to arbitrary game callbacks.
- **Subroutines**: Call-stack execution for reusable narrative sequences (`>>` and `<<`).
- **Interactive CLI Player**: Built-in terminal player for testing and playing stories.

## Installation

```bash
pip install eager-runtime
```

## Quickstart

```python
import eager_script
from eager_runtime import StoryVM, DialogueEvent, ChoicePromptEvent

script = """
## Courtyard --- courtyard
Guard: Who goes there? State your business.
? Announce yourself peacefully (peace)
? Draw your sword (fight)

## Peace --- peace
Guard: Welcome traveler. Enter freely.

## Fight --- fight
Guard (angry): You will regret this!
"""

# 1. Parse screenplay into a scene graph
graph = eager_script.parse_graph(script)

# 2. Initialize the virtual machine
vm = StoryVM(graph)

# 3. Advance through beats
while not vm.is_ended:
    event = vm.step()
    
    if isinstance(event, DialogueEvent):
        print(f"{event.speaker}: {event.text}")
    elif isinstance(event, ChoicePromptEvent):
        for opt in event.options:
            print(f"[{opt.index + 1}] {opt.text}")
        vm.choose(0)  # Choose first branch
```

## Event & Hook Dispatcher

```python
from eager_runtime import EventDispatcher, StoryVM, DialogueEvent

dispatcher = EventDispatcher()

# Register custom game callbacks for script hooks (~ play_sfx thunder.ogg)
@dispatcher.on_hook("play_sfx")
def handle_sfx(clip: str):
    print(f"Playing sound: {clip}")

# Register listeners for specific narrative events
@dispatcher.on_event(DialogueEvent)
def handle_dialogue(event: DialogueEvent):
    print(f"{event.speaker}: {event.text}")

vm = StoryVM(graph)
dispatcher.run_until_pause(vm)
```

## Save, Load & Rollback

```python
# Create an immutable snapshot
snapshot = vm.save()
json_data = snapshot.to_json(indent=2)

# Restore state at any time
vm.load(snapshot)

# Rewind history (undo last choice or beat)
if vm.can_rollback:
    vm.rollback()
```

## CLI Usage

Eager comes with a built-in command-line tool for inspecting and testing screenplays:

```bash
# Play a screenplay interactively in the terminal
eager play adventure.es

# Inspect screenplay scene topology, hubs, dead-ends
eager inspect adventure.es

# Perform an automated headless dry-run
eager test-run adventure.es
```

During interactive terminal play, the following built-in commands are available:
- `:save` — Save current state to in-memory slot
- `:load` — Restore state from slot
- `:undo` (or `:rollback`) — Rewind to previous beat or choice
- `:vars` — Inspect narrative state variables
- `:q` — Quit playthrough

## License

MIT
