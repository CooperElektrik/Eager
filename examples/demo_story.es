## After the Bell --- prologue
Narrator: The late afternoon chime echoes down the empty second-floor corridor.
- Golden sunlight slants across rows of polished wooden desks, stretching long shadows toward the back chalkboard.
/ For a few moments, the classroom is completely still.
~ fade_in duration=0.8
~ bg classroom_day with crossfade duration=1.0
~ show hoshiko smile at center with fade duration=0.6
Hoshiko (smile): Hey! Are you finally done packing up your bag?
- I thought you were about to fall asleep right on your notebook.
/ The sun's already sinking, and almost everyone has headed home.
Hoshiko (smile): So... got any plans for the rest of the evening?
? Take the coastal train towards the beach (coastal_train)
? Walk up the stone path to the mountain shrine (mountain_shrine)
? Stroll through the shopping street for some snacks (town_stroll)

## Coastal Railway --- coastal_train
~ bg train_day with crossfade duration=1.2
~ move hoshiko to center_left duration=0.5
Narrator: The rhythmic clatter of wheels on iron reverberates through the quiet train car.
Hoshiko (smile): I love taking this line when the day cools down.
- Look out the window — you can see the coastline already!
~ bg train_beach with crossfade duration=1.5
Narrator: The train emerges from the cliffside cut, revealing the vast expanse of blue water glistening under the sky.
~ expr hoshiko surprised
Hoshiko (surprised): Whoa, look at the tide today! It's completely crystal clear!
~ move hoshiko to center duration=0.4
~ expr hoshiko embarrassed
Hoshiko (embarrassed): To tell you the truth... I actually brought my swimsuit in my bag, just in case we took this detour.
Narrator: She unzips her school satchel just enough to reveal a peek of turquoise fabric.
~ flash color=#ffffff duration=0.2
Hoshiko (flustered): D-don't look at me like that! It's summer, so being prepared is just smart!
>> sunset_promise
~ bg train_evening with crossfade duration=1.2
~ expr hoshiko smile
Hoshiko (smile): Thanks for taking the long route with me today.
- Watching the sunset over the water never gets old.
Narrator: The evening train glides forward as the horizon melts into shades of amber and indigo.
Narrator: Some journeys are made unforgettable simply by who sits beside you.

## Mountain Shrine --- mountain_shrine
~ bg temple_day with crossfade duration=1.2
Narrator: Ancient cedar branches sway gently above the worn mossy stairs leading to the shrine grounds.
Hoshiko (smile): Phew! Those stairs never get any easier no matter how many times we climb them.
- My legs feel practically made of jelly right now.
~ expr hoshiko upset
Hoshiko (upset): And you didn't even break a sweat! How is that fair at all?
? Offer to carry her school bag (carry_bag)
? Tease her about skipping gym class (tease_gym)

## A Helping Hand --- carry_bag
~ expr hoshiko embarrassed
Hoshiko (embarrassed): W-wait, really? You'll carry it for me?
~ move hoshiko to center duration=0.3
Hoshiko (smile): You're way too nice sometimes... okay, deal! Here you go.
Narrator: She hands over her bag with a relieved sigh and a grateful smile.
> shrine_twilight

## Friendly Teasing --- tease_gym
~ expr hoshiko upset
Hoshiko (upset): Hey! I tried my best in badminton yesterday, for your information!
- The shuttlecock had a mind of its own, okay?
~ expr hoshiko smile
Hoshiko (smile): Fine, fine, I forgive you. Let's make our wish before it gets dark.
> shrine_twilight

## Shrine at Dusk --- shrine_twilight
~ bg temple_night with crossfade duration=1.5
Narrator: Dusk settles softly over the cedar grove, and ancient stone lanterns cast warm glows along the cobblestones.
Hoshiko (smile): They say if you make a wish here at twilight, it's bound to come true.
>> sunset_promise
~ expr hoshiko smile
Hoshiko (smile): May tomorrow be just as bright as today.
Narrator: You clap twice together in front of the offering box, the sound drifting into the tranquil mountain night.

## Town Stroll --- town_stroll
~ bg street_day with crossfade duration=1.0
Narrator: The shopping arcade bustles with lively conversation, bicycle bells, and the tempting aroma of freshly baked goods.
Hoshiko (smile): Ooh, the bakery on the corner smells amazing! Let's grab some melon pan!
Narrator: Without warning, the sky darkens overhead as distant thunder rumbles across the valley.
~ shake intensity=2.0 duration=0.4
~ flash color=#e0f7fa duration=0.25
~ bg street_rain with crossfade duration=0.8
Narrator: Fat raindrops suddenly pelt the warm pavement in a sudden summer shower.
~ expr hoshiko surprised
Hoshiko (surprised): Kya! Rain?! But the morning forecast said zero percent!
~ move hoshiko to left duration=0.3
Hoshiko (upset): My uniform is going to get completely drenched!
~ bg busstop_rain with crossfade duration=0.6
~ move hoshiko to center duration=0.3
Narrator: You grab Hoshiko's hand and pull her under the narrow canopy of a nearby bus shelter.
Hoshiko (embarrassed): Whew... that was close! Thanks for pulling me in.
- Though... we're standing pretty close together under here, aren't we?
>> sunset_promise
~ bg street_night with crossfade duration=1.5
Narrator: As suddenly as it arrived, the summer cloudburst drifts away, revealing a pristine canopy of shimmering stars.
~ expr hoshiko smile
Hoshiko (smile): Look at that... the sky cleared up completely.
Hoshiko (smile): Getting caught in the rain wasn't so bad after all.
Narrator: Side by side under the starlit sky, you walk the glistening street back home.

## A Quiet Promise --- sunset_promise
Narrator: For a lingering moment, time slows to a quiet breath.
Hoshiko (smile): You know... afternoons like this make me really happy that we're friends.
- Promise me we'll hang out again soon, okay?
Narrator: A gentle nod and a smile are all the answer she needs.
<<
