# eager

Unified visual novel engine package (`import eager`).

## Layers

- `eager.core` — dependency-free primitives, events, saves, state, assets, i18n
- `eager.script` — dependency-free screenplay parser, AST, expressions, scene graph, validator, project config
- `eager.vm` — headless `StoryVM` and catalog tools
- `eager.stage` — `StageCompositor`, `StageDirector`, particles
- `eager.ui` — `UIOverlay`, `ScreenManager`, `BasePlayer`, `PILPlayer`, `PygletPlayer`, `TerminalPlayer`
- `eager.session` — `GameSession` orchestrator
- `eager.backends` — `NullRenderer`, `PILRenderer`, `PygletRenderer`, `NullAudioBackend`, `MiniaudioAudioBackend`, `PygletAudioBackend`
- `eager.cli` — unified `eager` CLI
