## Library of Aethon --- prologue
Narrator: The ancient library stands in twilight, its candlelight long extinguished.
- Stone shelves stretch into shadow, bearing volumes whose titles have faded.
/ Yet something stirs within these walls — a presence neither living nor dead.
~ fade_in duration=0.8
~ bg library_interior with crossfade duration=1.0
~ show meris ethereal at center with fade duration=0.6
Meris (solemn): You have returned, seeker. The Library remembers all.
- Even the names it has sworn to forget.
~ show book whispering at right with cut
Meris (urgent): The Grimoire of Vael is awake. It must not leave this place.
? Take the Grimoire and flee (take_book)
? Demand answers from Meris (question_her)
? Search the shelves for a binding ritual (find_ritual)

## The Descent --- take_book
~ bg library_ruins with crossfade duration=1.5
~ hide meris with dissolve duration=0.4
~ hide book with dissolve duration=0.2
Narrator: The moment you clutch the tome, the library shudders.
~ shake intensity=2.5 duration=0.5
~ flash color=#ffffff duration=0.3
Narrator: Stone cracks bloom across the floor like veins of lightning.
Guardian: You have broken the oldest seal!
~ bg endless_stairs with crossfade duration=2.0
Narrator: An endless staircase of floating stone unfolds before you.
~ show guardian stone at left with slide_right duration=0.5
Guardian (grinding): Climb, thief. Each step costs a memory.
>> count_memories

## Counting Memories --- count_memories
Guardian: Count. One... for your mother's voice.
- Two... for your first word.
Narrator: Each step steals something precious.
Guardian: Three... for the face you wore before you were named.
~ fade_out duration=1.0 color=#000000
Narrator: And you remember nothing at all.
<<

## Interrogation --- question_her
~ expr meris angry
Meris (angry): I will not be interrogated by a child of the forgetting!
~ flash color=#ff4500 duration=0.15
~ move meris to center duration=0.3
Meris (shouting): The Grimoire was sealed for a reason!
? Force her to speak (force_speak)
? Lower your voice and apologize (apologize)

## Ritual Search --- find_ritual
~ bg library_ruins with crossfade duration=1.5
Narrator: You comb the shelves, fingers tracing dusty spines until —
~ show ritual_scroll glowing at center with fade duration=0.5
Narrator: A scroll of binding rituals. This could seal the Grimoire without violence.
>> count_memories

## Force Her to Speak --- force_speak
~ bg library_interior with dissolve duration=0.8
Meris (broken): The... the binding circle... it's beneath the third shelf...
Narrator: The cost of force is written in her tear-streaked face.
>> ritual_chamber

## Lower Your Voice --- apologize
~ bg library_interior with dissolve duration=0.8
~ expr meris sad
Meris (softly): Forgive me, seeker. The Library's hunger is not my own.
Narrator: Compassion opens doors that force could never break.
>> ritual_chamber

## The Ritual Chamber --- ritual_chamber
~ bg ritual_chamber with crossfade duration=1.5
~ show meris determined at center with fade duration=0.6
Meris: The circle is drawn. Stand within it.
Narrator: Glyphs flare to life beneath your feet as the Grimoire screams above.
~ flash color=#00ffff duration=0.4
~ fade_out duration=2.0 color=#ffffff
Narrator: When the light fades, the library is still. The Grimoire is sealed.
Narrator: You have restored the forgotten.
