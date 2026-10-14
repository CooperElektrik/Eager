## Welcome --- welcome

Narrator: Welcome to your new visual novel powered by Eager!
- You can customize this scene in main.es, or add new scripts in this directory.

~ fade_in duration=0.6
~ bg classroom with crossfade duration=0.8
~ show guide smile at center with fade duration=0.5

Guide (smile): Hi there! I'm your project guide.
- Everything is set up and ready to run.
/ You can configure window settings in game.toml, drop new art into the assets folder, and write scenes right here.

~ expr guide surprised
Guide (surprised): What kind of story are you going to create?

? Tell me more about the engine features (features)
? I'm ready to write my own story! (start)

## Engine Features --- features

~ expr guide smile
~ move guide center_left duration=0.4

Guide (smile): Eager gives you a distraction-free screenplay language, time-travel rollback, multiple rendering backends, and full asset validation!
- Try pressing Page Up or Rollback in the game to rewind time.
- Or run {b}eager check . --assets{/b} in your terminal to verify everything before releasing.

> wrap_up

## Ready to Start --- start

~ expr guide smile
~ move guide center_right duration=0.4

Guide (smile): Awesome! Open up {b}main.es{/b} in your favorite editor and start bringing your characters to life.
- You can replace my sprite in {i}assets/characters/guide/{/i} whenever you're ready.

> wrap_up

## Wrap Up --- wrap_up

~ move guide center duration=0.4
Guide (smile): Have fun creating, and welcome aboard!
Narrator: The journey begins.
