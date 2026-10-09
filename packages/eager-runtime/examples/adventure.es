## The Ancient Gate --- gate
Narrator: Heavy iron chains creak as the fortress gate stands before you.
- Moss clings to the damp weathered stone.
/ A cold wind blows from the mountain pass.
~ play_sfx wind_gust.ogg

Guard (stern): Who approaches the Citadel uninvited?
Alice (calm): {voice:alice_greeting.ogg} We seek shelter from the coming storm.

? Offer a silver coin as passage fee (bribe)
? State your noble quest truthfully (truth)
? Draw your weapons and force entry (combat)

## Peaceful Passage --- bribe
~ play_sfx coin_clink.ogg
Guard: A sensible traveler. You may enter the outer courtyard.
>> courtyard_intro
> sanctuary

## The Citadel Courtyard --- courtyard_intro
Narrator: You step through into the torchlit courtyard.
Guard: Keep to the main hall and avoid the catacombs.
<<

## Noble Quest --- truth
Guard: The Citadel welcomes brave souls in troubled times.
>> courtyard_intro
> sanctuary

## Citadel Gate Combat --- combat
Guard (furious): Treason! Guards, to arms!
~ screen_shake intensity=1.0
~ play_sfx swords_clashing.ogg
Narrator: You battle your way past the gatekeepers into the sanctuary.
> sanctuary

## The Sanctuary --- sanctuary
Narrator: The sanctuary doors close behind you. Safe for now.
Alice (smiling): That was quite the entrance.
