# Eager-Runtime

Lightweight, headless narrative runtime, story virtual machine, and session controller for [Eager-Script](https://github.com/CooperElektrik/Eager) screenplays.

`eager-runtime` is completely headless: it contains zero GUI or graphics dependencies and executes story state machines, branching choices, subroutines, saves, rollbacks, and event dispatching. It powers headless automated tests, terminal playthroughs, and GUI frontends (via `eager-graphics`).

---

## Features

- **Headless StoryVM**: Render-agnostic story virtual machine executing beats, choice branching, subroutine call stacks (`>>` and `<<`), and variable mutations.
- **Session Management (`GameSession`)**: High-level coordinator unifying narrative VM state, audio routing, dialogue backlog, player preferences, and persistent unlock variables.
- **Event Dispatching (`EventDispatcher`)**: Event-driven architecture with `run_until_pause()`, cleanly pausing execution at interaction boundaries (`ChoicePromptEvent`, `InputPromptEvent`, and `StoryEndEvent`).
- **Resilient Save Management (`SaveManager`)**: Slot-based persistence with atomic JSON writes, schema migrations, and automatic forensic `.corrupt.bak` backups upon encountering malformed or corrupted save files.
- **Time-Travel Rollback**: Checkpoint-based state rewind restoring story variables, call frames, and dialogue UI states in tandem without reverting global persistent data.
- **Interactive Terminal Player & CLI**: Stream-aware terminal player with readline fallback, command-line inspection, test runners, and developer tooling (`eager` CLI).

---

## Direct Submodule Import Convention

In accordance with Eager monorepo architecture, import core event types directly from `eager_core.events`:

```python
from eager_core.events import DialogueEvent, ChoicePromptEvent, InputPromptEvent
from eager_core.audio import NullAudioBackend
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.saves import SaveManager
```

---

## Quickstart: Headless StoryVM

```python
from eager_core.events import DialogueEvent, ChoicePromptEvent, NarrationEvent
from eager_script import parse_graph
from eager_runtime.runtime import StoryVM

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

# 1. Parse screenplay into a directed scene graph
graph = parse_graph(script)

# 2. Instantiate the headless StoryVM
vm = StoryVM(graph)

# 3. Step beat-by-beat through narrative events
while not vm.is_ended:
    event = vm.step()
    
    if isinstance(event, DialogueEvent):
        print(f"{event.speaker}: {event.text}")
    elif isinstance(event, NarrationEvent):
        print(f"Narrator: {event.text}")
    elif isinstance(event, ChoicePromptEvent):
        for opt in event.options:
            print(f"[{opt.index + 1}] {opt.text}")
        vm.choose(0)  # Select first option
```

---

## Event Dispatcher & Interaction Pausing

`EventDispatcher.run_until_pause()` advances the story until player interaction is required:

```python
from eager_core.events import DialogueEvent, ChoicePromptEvent, InputPromptEvent, StoryEndEvent
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.runtime import StoryVM

dispatcher = EventDispatcher()

# Register event callbacks
@dispatcher.on_event(DialogueEvent)
def handle_dialogue(event: DialogueEvent):
    print(f"{event.speaker}: {event.text}")

@dispatcher.on_hook("play_sfx")
def handle_sfx(clip: str):
    print(f"Playing SFX: {clip}")

vm = StoryVM(graph)

# Runs until ChoicePromptEvent, InputPromptEvent, or StoryEndEvent
pause_event = dispatcher.run_until_pause(vm)

if isinstance(pause_event, ChoicePromptEvent):
    print(f"Awaiting choice among {len(pause_event.options)} options...")
    vm.choose(0)
elif isinstance(pause_event, InputPromptEvent):
    print(f"Awaiting player input for variable '{pause_event.variable}'...")
    vm.set_variable(pause_event.variable, "Player1")
```

---

## Save Management & Fault-Tolerant Backups

`SaveManager` handles slot persistence with automatic corruption resilience:

```python
from pathlib import Path
from eager_runtime.saves import SaveManager
from eager_runtime.session import GameSession

save_mgr = SaveManager(Path("./saves"))

# Save active session to slot 1
save_mgr.save_slot("slot_1", session)

# Load slot; if corrupted or malformed, safe_read_json automatically
# backs up the bad file to slot_1.json.corrupt.bak and returns None
data = save_mgr.load_slot("slot_1")
if data is not None:
    session.restore_from_save(data)
else:
    print("Slot was corrupted; forensic backup created.")

# List valid slots (corrupted slot metadata is safely skipped)
slots = save_mgr.list_slots()
```

---

## Unified Session Management (`GameSession`)

`GameSession` serves as the central runtime controller:

```python
from eager_core.audio import NullAudioBackend
from eager_runtime.session import GameSession

# Create session with headless audio backend
session = GameSession(graph, audio_backend=NullAudioBackend())

# Advance narrative
event = session.advance()

# Submit text for active input prompts
if session.active_input_prompt is not None:
    session.submit_input("Hero")

# Rollback state to prior interaction checkpoint
if session.can_rollback:
    session.rollback()
```

---

## CLI Runner

The `eager` command-line suite provides terminal play, verification, and tooling:

```bash
# Play a story interactively in the terminal
eager play examples/demo_story.es

# Perform an automated headless dry-run
eager test-run examples/demo_story.es

# Inspect scene topology, branching hubs, and terminal scenes
eager inspect examples/demo_story.es

# Run language server protocol in stdio mode
eager lsp --stdio
```

Interactive terminal commands during playback:
- `:save` — Save state to in-memory slot
- `:load` — Restore state from slot
- `:undo` (or `:rollback`) — Rewind to previous interaction beat
- `:vars` — Inspect active state variables
- `:q` — Exit player

---

## Installation

```bash
pip install eager-runtime
```

---

## License

MIT
