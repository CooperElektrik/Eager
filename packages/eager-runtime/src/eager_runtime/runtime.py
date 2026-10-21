"""Core virtual machine for executing Eager-Script narrative scene graphs."""

from __future__ import annotations

import copy
import logging
import random
import re
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


def _to_nested_tuple(obj: Any) -> Any:
    """Recursively convert lists and tuples to tuples for random.setstate compatibility."""
    if isinstance(obj, (list, tuple)):
        return tuple(_to_nested_tuple(x) for x in obj)
    return obj

from eager_core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_core.i18n import TranslationManager
from eager_script import (
    ParsedAppend,
    ParsedCall,
    ParsedChoiceSet,
    ParsedCondJump,
    ParsedDefault,
    ParsedDialogue,
    ParsedFreshBox,
    ParsedHook,
    ParsedJump,
    ParsedLocalJump,
    ParsedNarration,
    ParsedReturn,
    ParsedSet,
)
from eager_script.expr import ExprError, compile_expr
from eager_script.hooks import parse_hook_args

from eager_runtime.i18n import compute_beat_id, get_beat_occurrence, strip_explicit_id
from eager_runtime.state import CallFrame, HistoryManager, StorySnapshot

if TYPE_CHECKING:
    from eager_script.graph import SceneGraph


class StoryRuntimeError(Exception):
    """Raised when an illegal operation or invalid state occurs during story execution."""


_INTERPOLATION_PATTERN = re.compile(r"\[\[|\]\]|\[([a-zA-Z_][a-zA-Z0-9_\.]*)\]")


class StoryVM:
    """Headless story virtual machine executing an Eager-Script SceneGraph."""

    def __init__(
        self,
        graph: SceneGraph,
        *,
        initial_state: StorySnapshot | None = None,
        max_history: int = 500,
        rng_seed: int | None = None,
        translation_manager: TranslationManager | None = None,
        enable_history: bool = True,
    ) -> None:
        self._graph = graph
        self._history: HistoryManager | None = (
            HistoryManager(max_history=max_history) if enable_history else None
        )
        self._translation_manager: TranslationManager = translation_manager or TranslationManager()

        self._current_scene_id: str | None = None
        self._beat_index: int = 0
        self._call_stack: list[CallFrame] = []
        self._variables: dict[str, Any] = {}
        self._visited_scenes: set[str] = set()

        self._rng = random.Random(rng_seed)

        self._pending_choice: ChoicePromptEvent | None = None
        self._pending_input: InputPromptEvent | None = None
        self._is_ended: bool = False
        self._just_entered_scene: bool = False
        self._next_transition_target: str | None = None

        # Initialize defaults from graph
        self._apply_graph_defaults()

        if initial_state is not None:
            self.load(initial_state)
        elif self._graph.entry:
            self._enter_scene(self._graph.entry)

    @property
    def translation_manager(self) -> TranslationManager:
        """The active translation manager."""
        return self._translation_manager

    @translation_manager.setter
    def translation_manager(self, mgr: TranslationManager) -> None:
        self._translation_manager = mgr

    def set_locale(self, locale: str) -> None:
        """Set the active translation locale."""
        self._translation_manager.set_locale(locale)

    def _translate(self, key: str | None, default: str) -> str:
        """Translate key if catalog present and key non-null, else default."""
        if key is not None and self._translation_manager is not None:
            return self._translation_manager.translate(key, default)
        return default

    def _translate_beat(
        self, key: str | None, default: str
    ) -> tuple[str, str | None]:
        """Translate by content-addressed ID."""
        clean_default = strip_explicit_id(default)
        if self._translation_manager is not None and key is not None:
            val = self._translation_manager.translate(key, clean_default)
            if val != clean_default:
                return val, key
        return clean_default, key

    def _translate_speaker(self, speaker: str) -> str:
        """Translate speaker name if catalog present, else default."""
        if self._translation_manager is not None:
            return self._translation_manager.translate_speaker(speaker)
        return speaker

    def _apply_graph_defaults(self) -> None:
        """Evaluate graph defaults if not already set."""
        if self._graph.defaults:
            for d in self._graph.defaults:
                if isinstance(d, ParsedDefault) and d.name not in self._variables:
                    val = self._evaluate_expr(d.expr_src)
                    self._variables[d.name] = val

    def _get_eval_env(self) -> dict[str, Any]:
        """Build evaluation environment for expression evaluation."""
        env = dict(self._variables)
        env["visited"] = lambda scene_id: scene_id in self._visited_scenes
        env["seen"] = lambda scene_id: scene_id in self._visited_scenes
        env["random"] = lambda a=0, b=1: self._rng.randint(a, b) if isinstance(a, int) and isinstance(b, int) else self._rng.uniform(a, b)
        env["chance"] = lambda p: self._rng.random() < (p / 100.0 if p > 1 else p)
        return env

    def _evaluate_expr(self, expr_src: str) -> Any:
        """Safely evaluate an expression string in current VM environment."""
        compiled = compile_expr(expr_src)
        return compiled.evaluate(self._get_eval_env())

    def _interpolate(self, text: str) -> str:
        """Perform [var_name] text interpolation with [[ literal escape."""
        if not text or "[" not in text:
            return text

        def repl(match: re.Match[str]) -> str:
            full = match.group(0)
            if full == "[[":
                return "["
            if full == "]]":
                return "]"
            var_name = match.group(1)
            if var_name.startswith("_"):
                return f"[{var_name}]"
            # Evaluate var_name or attribute path in variables
            if "." in var_name:
                parts = var_name.split(".")
                if any(p.startswith("_") for p in parts):
                    return f"[{var_name}]"
                if parts[0] not in self._variables:
                    return f"[{var_name}]"
                curr: Any = self._variables.get(parts[0])
                for p in parts[1:]:
                    if isinstance(curr, dict):
                        curr = curr.get(p)
                    elif hasattr(curr, p):
                        curr = getattr(curr, p)
                    else:
                        return f"[{var_name}]"
                return str(curr) if curr is not None else ""
            if var_name in self._variables:
                return str(self._variables[var_name])
            return f"[{var_name}]"

        return _INTERPOLATION_PATTERN.sub(repl, text)

    def interpolate(self, text: str) -> str:
        """Perform [var_name] text interpolation with [[ literal escape."""
        return self._interpolate(text)

    @property
    def graph(self) -> SceneGraph:
        """The underlying scene graph being executed."""
        return self._graph

    @graph.setter
    def graph(self, new_graph: SceneGraph) -> None:
        self._graph = new_graph

    @property
    def current_scene_id(self) -> str | None:
        """ID of the current active scene, or None if story hasn't started or ended."""
        return self._current_scene_id

    @current_scene_id.setter
    def current_scene_id(self, scene_id: str | None) -> None:
        self._current_scene_id = scene_id

    @property
    def beat_index(self) -> int:
        """Index of the next beat to execute in the current scene."""
        return self._beat_index

    @beat_index.setter
    def beat_index(self, index: int) -> None:
        self._beat_index = max(0, index)

    def hot_reload(self, new_graph: SceneGraph) -> bool:
        """Hot-swap the underlying scene graph and reconcile execution state.

        1. Capture current state: current_scene_id, beat_index, variables.
        2. Swap self._graph reference.
        3. Reconcile state:
           - If current_scene_id exists, cap beat_index to len(new_scene.body) - 1.
           - If scene was deleted, gracefully jump to entry node if available,
             or clear current scene.
        """
        cur_scene = self._current_scene_id
        b_idx = self._beat_index
        self._graph = new_graph

        if cur_scene is not None and cur_scene in new_graph.nodes:
            new_scene = new_graph.nodes[cur_scene]
            if new_scene.body:
                self._beat_index = max(0, min(b_idx, len(new_scene.body) - 1))
            else:
                self._beat_index = 0
            return True
        else:
            if new_graph.entry and new_graph.entry in new_graph.nodes:
                self._enter_scene(new_graph.entry)
                return True
            else:
                self._current_scene_id = None
                self._beat_index = 0
                return False

    @property
    def is_ended(self) -> bool:
        """True if the story has concluded (reached a terminal node or completed)."""
        return self._is_ended

    @property
    def pending_choice(self) -> ChoicePromptEvent | None:
        """Active choice prompt waiting for player selection, if any."""
        return self._pending_choice

    @property
    def pending_input(self) -> InputPromptEvent | None:
        """Active input prompt waiting for player input, if any."""
        return self._pending_input

    @property
    def variables(self) -> dict[str, Any]:
        """Mutable narrative state variables."""
        return self._variables

    @property
    def visited_scenes(self) -> set[str]:
        """Set of all scene IDs visited during this playthrough."""
        return set(self._visited_scenes)

    @property
    def history_enabled(self) -> bool:
        """True if internal beat-level history recording is enabled."""
        return self._history is not None

    def enable_history(self, max_history: int = 500) -> None:
        """Enable internal beat-level history recording."""
        self._history = HistoryManager(max_history=max_history)

    def disable_history(self) -> None:
        """Disable internal beat-level history recording."""
        self._history = None

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one step in history available to rewind."""
        return self._history.can_rollback if self._history is not None else False

    def set_variable(self, name: str, value: Any) -> None:
        """Set a story variable value."""
        self._variables[name] = value
        if self._pending_input is not None and self._pending_input.var_name == name:
            self._pending_input = None

    def submit_input(self, value: str) -> None:
        """Submit user input for the active input prompt."""
        if self._pending_input is None:
            msg = "No input prompt currently active."
            raise StoryRuntimeError(msg)
        self.set_variable(self._pending_input.var_name, value)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Retrieve a story variable value."""
        return self._variables.get(name, default)

    def _build_choice_prompt(
        self,
        item: ParsedChoiceSet,
        beat_index: int | None = None,
    ) -> ChoicePromptEvent:
        """Construct ChoicePromptEvent from ParsedChoiceSet node, evaluating conditions."""
        options: list[ChoiceOption] = []
        b_idx = beat_index if beat_index is not None else self._beat_index
        cid = None
        if self._current_scene_id is not None and self._graph is not None:
            node = self._graph.nodes.get(self._current_scene_id)
            occ = get_beat_occurrence(node.body, b_idx) if node else 1
            cid = compute_beat_id(self._current_scene_id, item, occurrence=occ)

        for i, opt in enumerate(item.options):
            enabled = True
            if opt.condition:
                try:
                    enabled = bool(self._evaluate_expr(opt.condition))
                except ExprError as exc:
                    logger.warning(
                        "ExprError evaluating choice condition '%s' at line %d: %s",
                        opt.condition,
                        opt.line_number,
                        exc,
                    )
                    enabled = False
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error evaluating choice condition '%s' at line %d: %s",
                        opt.condition,
                        opt.line_number,
                        exc,
                    )
                    enabled = False
            opt_cid = f"{cid}.choice_{i}" if cid else None
            raw_text, used_opt_id = self._translate_beat(opt_cid, opt.text)
            options.append(
                ChoiceOption(
                    index=i,
                    text=self._interpolate(raw_text),
                    target=opt.target,
                    line_number=opt.line_number,
                    condition=opt.condition,
                    enabled=enabled,
                    beat_id=used_opt_id,
                )
            )
        return ChoicePromptEvent(
            options=tuple(options),
            line_number=item.line_number,
            beat_id=cid,
        )

    def save(self) -> StorySnapshot:
        """Create an immutable, serializable snapshot of the current VM state."""
        pending_beat: int | None = None
        if self._pending_choice is not None and self._beat_index > 0:
            pending_beat = self._beat_index - 1

        pending_input_b: int | None = None
        if self._pending_input is not None and self._beat_index > 0:
            pending_input_b = self._beat_index - 1

        # Filter out persistent object from per-save variables (persistent state is saved independently)
        vars_to_save = {k: copy.deepcopy(v) for k, v in self._variables.items() if k != "persistent"}

        return StorySnapshot(
            current_scene=self._current_scene_id,
            beat_index=self._beat_index,
            call_stack=tuple(self._call_stack),
            variables=vars_to_save,
            visited_scenes=tuple(self._visited_scenes),
            pending_choice_beat=pending_beat,
            pending_input_beat=pending_input_b,
            next_transition_target=self._next_transition_target,
            just_entered_scene=self._just_entered_scene,
            is_ended=self._is_ended,
            rng_state=list(self._rng.getstate()),
        )

    def load(self, snapshot: StorySnapshot) -> None:
        """Restore VM state exactly from a StorySnapshot."""
        if snapshot.current_scene and snapshot.current_scene not in self._graph.nodes:
            msg = f"Cannot restore snapshot: scene '{snapshot.current_scene}' not in SceneGraph."
            raise StoryRuntimeError(msg)

        self._current_scene_id = snapshot.current_scene
        self._beat_index = snapshot.beat_index
        self._call_stack = list(snapshot.call_stack)
        persistent_obj = self._variables.get("persistent")
        self._variables = copy.deepcopy(snapshot.variables)
        if persistent_obj is not None:
            self._variables["persistent"] = persistent_obj
        self._visited_scenes = set(snapshot.visited_scenes)

        if snapshot.rng_state is not None:
            try:
                self._rng.setstate(_to_nested_tuple(snapshot.rng_state))
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to restore PRNG state: %s", exc)

        self._pending_choice = None
        self._pending_input = None
        self._next_transition_target = snapshot.next_transition_target
        self._just_entered_scene = snapshot.just_entered_scene
        self._is_ended = False

        # If saved while waiting on a choice prompt, re-materialize the ChoicePromptEvent
        if snapshot.pending_choice_beat is not None and self._current_scene_id is not None:
            scene = self._graph.nodes.get(self._current_scene_id)
            if scene and 0 <= snapshot.pending_choice_beat < len(scene.body):
                item = scene.body[snapshot.pending_choice_beat]
                if isinstance(item, ParsedChoiceSet):
                    self._pending_choice = self._build_choice_prompt(item, snapshot.pending_choice_beat)

        # If saved while waiting on an input prompt, re-materialize the InputPromptEvent
        if snapshot.pending_input_beat is not None and self._current_scene_id is not None:
            scene = self._graph.nodes.get(self._current_scene_id)
            if scene and 0 <= snapshot.pending_input_beat < len(scene.body):
                item = scene.body[snapshot.pending_input_beat]
                if isinstance(item, ParsedHook):
                    interp_hook = self._interpolate(item.hook_name)
                    parts = interp_hook.split(None, 1)
                    hook_name = parts[0] if parts else ""
                    args = parts[1] if len(parts) > 1 else ""
                    if hook_name == "input":
                        parsed_hook = parse_hook_args(args)
                        pos = parsed_hook.positional
                        var_name = pos[0] if pos else "player_input"
                        default_text = parsed_hook.kwargs.get("default", "")
                        if "prompt" in parsed_hook.kwargs:
                            prompt_text = parsed_hook.kwargs["prompt"]
                        elif len(pos) == 3 and not default_text:
                            prompt_text = pos[1]
                            default_text = pos[2]
                        elif len(pos) == 2:
                            prompt_text = pos[1]
                        elif len(pos) > 3 and not default_text:
                            prompt_text = " ".join(pos[1:])
                        else:
                            prompt_text = "Enter input:"
                        occ = get_beat_occurrence(scene.body, snapshot.pending_input_beat)
                        cid = compute_beat_id(self._current_scene_id, item, occurrence=occ)
                        input_cid = f"{cid}.input" if cid else None
                        raw_prompt, _ = self._translate_beat(input_cid, prompt_text)
                        self._pending_input = InputPromptEvent(
                            var_name=var_name,
                            prompt=self._interpolate(raw_prompt),
                            default=self._interpolate(default_text),
                            line_number=item.line_number,
                            beat_id=input_cid,
                        )

    def rollback(self) -> bool:
        """Rewind VM state to the previous recorded beat in history.

        Returns True if rollback was successful, or False if no history exists.
        """
        if self._history is None:
            return False
        snapshot = self._history.pop()
        if snapshot is None:
            return False

        self.load(snapshot)
        return True

    def jump(self, scene_id: str) -> None:
        """Jump execution immediately to a target scene."""
        if scene_id not in self._graph.nodes:
            msg = f"Cannot jump to unknown scene '{scene_id}'"
            raise StoryRuntimeError(msg)

        target_node = self._graph.nodes.get(scene_id)
        if target_node is not None and not target_node.is_anonymous:
            while self._call_stack and self._call_stack[-1].kind == "inline":
                self._call_stack.pop()

        self._pending_choice = None
        self._pending_input = None
        self._enter_scene(scene_id)

    def call(self, scene_id: str) -> None:
        """Call a subroutine scene, pushing current position onto the call stack."""
        if scene_id not in self._graph.nodes:
            msg = f"Cannot call unknown subroutine scene '{scene_id}'"
            raise StoryRuntimeError(msg)

        if self._current_scene_id is not None:
            self._call_stack.append(CallFrame(self._current_scene_id, self._beat_index))

        self._pending_choice = None
        self._pending_input = None
        self._enter_scene(scene_id)

    def choose(self, choice: int | str) -> None:
        """Select an option from the active choice prompt and branch to target scene."""
        if self._pending_choice is None:
            msg = "No choice prompt currently active to choose from."
            raise StoryRuntimeError(msg)

        target: str | None = None
        if isinstance(choice, int):
            if 0 <= choice < len(self._pending_choice.options):
                opt = self._pending_choice.options[choice]
                if not opt.enabled:
                    msg = f"Cannot select disabled choice index {choice} ('{opt.text}')"
                    raise StoryRuntimeError(msg)
                target = opt.target
            else:
                msg = f"Choice index {choice} out of range (0..{len(self._pending_choice.options) - 1})"
                raise StoryRuntimeError(msg)
        else:
            # Match by target ID or text
            for opt in self._pending_choice.options:
                if opt.target == choice or opt.text == choice:
                    if not opt.enabled:
                        msg = f"Cannot select disabled choice '{choice}'"
                        raise StoryRuntimeError(msg)
                    target = opt.target
                    break
            if target is None:
                msg = f"Choice target '{choice}' not found among active choices."
                raise StoryRuntimeError(msg)

        if target is None:
            msg = f"Choice '{choice}' has no valid target scene."
            raise StoryRuntimeError(msg)

        self._pending_choice = None
        self._pending_input = None

        # Inline choice blocks are lowered into anonymous scenes.  Branching into one
        # should resume the enclosing scene once the block finishes, so push a return
        # frame pointing at the beat right after the choice prompt.
        target_node = self._graph.nodes.get(target)
        if (
            target is not None
            and target_node is not None
            and target_node.is_anonymous
            and self._current_scene_id is not None
        ):
            self._call_stack.append(CallFrame(self._current_scene_id, self._beat_index, "inline"))
        else:
            while self._call_stack and self._call_stack[-1].kind == "inline":
                self._call_stack.pop()

        self.jump(target)

    def _enter_scene(self, scene_id: str) -> None:
        """Prepare internal state for entering a new scene node."""
        self._current_scene_id = scene_id
        self._beat_index = 0
        self._visited_scenes.add(scene_id)
        self._just_entered_scene = True
        self._next_transition_target = None

    def step(self) -> StoryEvent | None:
        """Advance story execution by one discrete beat.

        Returns a StoryEvent, or None if the story has concluded.
        """
        if self._is_ended:
            return None

        # 1. Handle pending choice or input pause
        if self._pending_choice is not None:
            return self._pending_choice
        if self._pending_input is not None:
            return self._pending_input

        # 2. Handle delayed scene transition from previous exit beat
        if self._next_transition_target is not None:
            target = self._next_transition_target
            self._next_transition_target = None
            self._enter_scene(target)

        # 3. Handle initial or empty graph
        if self._current_scene_id is None:
            self._is_ended = True
            return StoryEndEvent(scene_id=None, reason="no_entry")

        scene = self._graph.nodes.get(self._current_scene_id)
        if scene is None:
            self._is_ended = True
            return StoryEndEvent(scene_id=self._current_scene_id, reason="dead_end")

        # 4. Handle scene entry event
        if self._just_entered_scene:
            self._just_entered_scene = False
            if self._history is not None:
                self._history.push(self.save())
            return SceneEnterEvent(
                scene_id=scene.id,
                display_name=scene.display_name,
                line_number=scene.line_number,
            )

        # 5. Process next beat inside scene body
        while self._beat_index < len(scene.body):
            item = scene.body[self._beat_index]

            # Handle internal flow control statements silently without pushing history or pausing
            if isinstance(item, ParsedSet):
                val = self._evaluate_expr(item.expr_src)
                target = item.target
                if item.op == "=":
                    self._variables[target] = val
                elif item.op == "+=":
                    self._variables[target] = self._variables.get(target, 0) + val
                elif item.op == "-=":
                    self._variables[target] = self._variables.get(target, 0) - val
                elif item.op == "*=":
                    self._variables[target] = self._variables.get(target, 1) * val
                elif item.op == "/=":
                    self._variables[target] = self._variables.get(target, 1) / val
                elif item.op == "%=":
                    self._variables[target] = self._variables.get(target, 1) % val
                self._beat_index += 1
                continue

            if isinstance(item, ParsedCondJump):
                cond_val = bool(self._evaluate_expr(item.condition))
                if not cond_val:
                    # Condition false -> jump to target_index
                    self._beat_index = item.target_index
                else:
                    self._beat_index += 1
                continue

            if isinstance(item, ParsedLocalJump):
                self._beat_index = item.target_index
                continue

            # Record state snapshot before consuming narrative beat
            if self._history is not None:
                self._history.push(self.save())
            current_beat_idx = self._beat_index
            self._beat_index += 1
            occ = get_beat_occurrence(scene.body, current_beat_idx)
            cid = compute_beat_id(self._current_scene_id, item, occurrence=occ)
            beat_id = cid

            if isinstance(item, ParsedDialogue):
                raw_speaker = self._translate_speaker(item.speaker)
                interp_speaker = self._interpolate(raw_speaker)
                # If speaker matches a character ID, we could map name if needed, but interpolate handles [var]
                if self._graph.characters:
                    cid_match = interp_speaker if interp_speaker in self._graph.characters else interp_speaker.lower()
                    if cid_match in self._graph.characters:
                        interp_speaker = self._graph.characters[cid_match].get("name", interp_speaker)
                raw_text, _ = self._translate_beat(cid, item.text)
                return DialogueEvent(
                    speaker=interp_speaker,
                    text=self._interpolate(raw_text),
                    voice=item.voice,
                    emotion=item.emotion,
                    line_number=item.line_number,
                    beat_id=beat_id,
                )

            if isinstance(item, ParsedNarration):
                raw_text, _ = self._translate_beat(cid, item.text)
                return NarrationEvent(
                    text=self._interpolate(raw_text),
                    line_number=item.line_number,
                    beat_id=beat_id,
                )

            if isinstance(item, ParsedAppend):
                raw_text, _ = self._translate_beat(cid, item.text)
                return AppendEvent(
                    text=self._interpolate(raw_text),
                    line_number=item.line_number,
                    beat_id=beat_id,
                )

            if isinstance(item, ParsedFreshBox):
                raw_text, _ = self._translate_beat(cid, item.text)
                return FreshBoxEvent(
                    text=self._interpolate(raw_text),
                    line_number=item.line_number,
                    beat_id=beat_id,
                )

            if isinstance(item, ParsedHook):
                interp_hook = self._interpolate(item.hook_name)
                parts = interp_hook.split(None, 1)
                hook_name = parts[0] if parts else ""
                args = parts[1] if len(parts) > 1 else ""
                if hook_name == "input":
                    # ~ input var_name [default=val] Prompt text
                    parsed_hook = parse_hook_args(args)
                    pos = parsed_hook.positional
                    var_name = pos[0] if pos else "player_input"
                    default_text = parsed_hook.kwargs.get("default", "")
                    if "prompt" in parsed_hook.kwargs:
                        prompt_text = parsed_hook.kwargs["prompt"]
                    elif len(pos) == 3 and not default_text:
                        prompt_text = pos[1]
                        default_text = pos[2]
                    elif len(pos) == 2:
                        prompt_text = pos[1]
                    elif len(pos) > 3 and not default_text:
                        prompt_text = " ".join(pos[1:])
                    else:
                        prompt_text = "Enter input:"
                    input_cid = f"{cid}.input" if cid else None
                    raw_prompt, _ = self._translate_beat(input_cid, prompt_text)
                    input_prompt = InputPromptEvent(
                        var_name=var_name,
                        prompt=self._interpolate(raw_prompt),
                        default=self._interpolate(default_text),
                        line_number=item.line_number,
                        beat_id=input_cid,
                    )
                    self._pending_input = input_prompt
                    return input_prompt
                return HookEvent(
                    hook_name=hook_name,
                    args=args,
                    line_number=item.line_number,
                )


            if isinstance(item, ParsedChoiceSet):
                prompt = self._build_choice_prompt(item, current_beat_idx)
                self._pending_choice = prompt
                return prompt

            if isinstance(item, ParsedJump):
                # An unconditional jump out of an anonymous inline block abandons the
                # block's pending return to the enclosing scene.
                if scene.is_anonymous:
                    while self._call_stack and self._call_stack[-1].kind == "inline":
                        self._call_stack.pop()
                self._next_transition_target = item.target
                return SceneExitEvent(
                    scene_id=scene.id,
                    transition_kind="jump",
                    target=item.target,
                    line_number=item.line_number,
                )

            if isinstance(item, ParsedCall):
                # Push return frame
                self._call_stack.append(CallFrame(scene.id, self._beat_index))
                self._next_transition_target = item.target
                return SceneExitEvent(
                    scene_id=scene.id,
                    transition_kind="call",
                    target=item.target,
                    line_number=item.line_number,
                )

            if isinstance(item, ParsedReturn):
                if self._call_stack:
                    frame = self._call_stack.pop()
                    self._current_scene_id = frame.scene_id
                    self._beat_index = frame.beat_index
                    return SceneExitEvent(
                        scene_id=scene.id,
                        transition_kind="return",
                        target=frame.scene_id,
                        line_number=item.line_number,
                    )
                # Return from main level
                self._is_ended = True
                return StoryEndEvent(scene_id=scene.id, reason="completed")

        # 6. Scene body exhausted
        if self._call_stack:
            frame = self._call_stack.pop()
            self._current_scene_id = frame.scene_id
            self._beat_index = frame.beat_index
            return SceneExitEvent(
                scene_id=scene.id,
                transition_kind="return",
                target=frame.scene_id,
                line_number=scene.line_number,
            )

        self._is_ended = True
        return StoryEndEvent(scene_id=scene.id, reason="terminal")
