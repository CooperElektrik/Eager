# Screenplay Syntax (`.es`)

Eager uses `.es` (Eager-Script) files—plain-text screenplays designed to stay readable while supporting branching, state, and staging.

---

## Scenes

Define a scene with a Markdown-style heading and a unique `scene_id` separated by `---`:

```es
## After the Bell --- prologue
Narrator: The late afternoon chime echoes down the empty corridor.
```

---

## Dialogue & Narration

Write `Speaker: line`, optionally including an expression in parentheses:

```es
Narrator: Golden sunlight slants across the desks.
Hoshiko (smile): Hey! Are you finally done packing up?
- I thought you were about to fall asleep right on your notebook.
/ The sun's already sinking, and almost everyone has headed home.
```

- `-` continues the **same speaker's** dialogue as a new line.
- `/` continues narration/action in the current beat.

---

## Text Formatting & Pacing

Inline tags control text style and pacing:

```es
Guide (smile): Run {b}eager check . --assets{/b} before releasing.
Guide (smile): Look in {i}assets/characters/guide/{/i} for sprites.
```

---

## Choices

### Labeled Choices

Route to another scene by putting its `scene_id` in parentheses:

```es
? Take the coastal train (coastal_train)
? Walk up to the mountain shrine (mountain_shrine)
```

### Inline Choices

Indent blocks directly under a choice without creating a separate scene:

```es
? Announce yourself peacefully (peaceful_entry)
? Draw your sword
    $ gold -= 10
    guard (angry): So that's how it is.
    > combat_start
```

---

## Flow Control (`>`, `>>`, `<<`)

| Syntax | Action | Description |
|--------|--------|-------------|
| `> scene_id` | **Jump** | Transfers execution to `scene_id`. |
| `>> scene_id` | **Call** | Pushes a return frame and runs `scene_id` as a subroutine. |
| `<<` | **Return** | Returns from a `>>` subroutine call. |

```es
## Peaceful Entry --- peaceful_entry
guard: Welcome, traveler.
>> royal_greeting
> finish

## Royal Greeting --- royal_greeting
guard: Present your credentials.
<<
```

---

## Variables, Characters & Conditionals

Declare default variables, character metadata, and conditionals using `@` and `$`:

```es
@default gold = 100
@character guard "Town Guard" #e74c3c

## Courtyard --- courtyard
$ gold -= 10

@if gold >= 50
    guard: You have plenty of coin.
@else
    guard: Better watch your spending.
@endif
```

!!! note "Safe Expressions"
    Conditional and `$` expressions are evaluated using Eager's whitelisted AST compiler—arbitrary Python execution is never allowed.
