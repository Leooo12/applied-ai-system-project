# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name

**VibeMatch 1.0**

It's called VibeMatch because it tries to match songs to the "vibe" you describe —
your favorite style, mood, and energy level.

---

## 2. Intended Use

### Goal / Task

You describe the music you're in the mood for. VibeMatch picks the five songs
from its library that best fit. For each pick it also shows *why* it was chosen.

It guesses fit from the song's own traits — its style, mood, and sound. It does
not use other people's listening history.

### What it's designed for

- Learning how a simple recommender turns data into suggestions.
- Classroom exploration and experiments, not real users.
- Small, clear demos where you can see the reason behind every pick.

### What it should NOT be used for

- A real music app or anything people depend on.
- Judging songs, artists, or genres as "good" or "bad."
- Any real decision about a person. It only compares song traits.

### Assumptions it makes

- The user can name a style, a mood, and an energy level.
- Those few traits are enough to describe someone's taste for now.
- Every song is fairly described by the numbers in the dataset.

---

## 3. How the Model Works

Think of it like a points contest. Every song earns points for how well it fits
what you asked for. The songs with the most points win.

**What it looks at.** Each song has a style (genre), a mood, and a set of "sound"
numbers: energy, how positive it feels, how danceable it is, how acoustic it is,
how instrumental it is, and its speed (tempo).

**What you tell it.** You give a favorite style, a favorite mood, and target
numbers like how much energy you want.

**How points are earned.** A song gets a big bonus if its style or mood matches
yours. For the number traits, a song scores higher the closer it is to your
target — so if you want high energy, songs near that energy score best. Style,
mood, and energy count the most; the other sound traits act as tie-breakers.

**Changes from the starter version.** The starter only gave points on an exact
style or mood match. We made four upgrades:

1. **Fairer balance.** Mood used to outweigh everything. Now style, mood, and
   energy count the same, so no single trait can take over.
2. **"Close enough" matches.** Related styles now earn partial points — a rock
   fan can see metal, a "happy" fan can see "energetic." Before, these counted
   as total misses.
3. **No broken scores.** Impossible requests (like energy above the normal range)
   no longer produce negative points. They just earn zero and move on.
4. **More variety.** The final list avoids stacking songs by the same artist (and,
   more gently, the same genre), so you get a bit of range instead of clones.
5. **Selectable "modes."** You can switch how the model weighs things — Balanced,
   Genre-First, Mood-First, or Energy-Focused — so the same library can be sorted
   by different priorities without changing the underlying math.

The model can also read a few extra song details when a listener asks for them
(how mainstream a song is, its era, a finer mood label, whether it's explicit, and
solo vs. band), but everyday profiles don't need to set these.

---

## 4. Data

The library is a small, made-up list of songs in a spreadsheet
(`data/songs.csv`). Nothing here is real streaming data.

**Size.** 36 songs.

**Features per song.** Each song has a title and artist (shown, not scored),
plus eight traits the model uses: style, mood, energy, positivity, danceability,
acousticness, how instrumental it is, and tempo.

**Styles.** 14 genres, including pop, indie pop, lofi, ambient, rock, metal,
hip-hop, r&b, funk, jazz, folk, classical, electronic, and synthwave.

**Moods.** 11 moods, such as happy, relaxed, chill, moody, intense, confident,
focused, romantic, melancholy, energetic, and sad.

**What we changed.** We doubled the catalog from 18 songs to 36 so related styles
would have company (for example, more than one rock or metal track to compare).

**What's missing.** The dataset is tiny and uneven — some styles have four songs,
others just two, and "sad" has only one. It has no lyrics, no language, no release
year, and no artist popularity. So whole parts of real musical taste simply aren't
represented.

---

## 5. Strengths

**It works well for clear tastes.** When someone names a real style and mood, the
top picks are spot on. A pop fan gets *Sunrise City*; a lo-fi fan gets *Library
Rain*; a rock fan gets *Storm Runner*. These matched our gut feeling every time.

**It finds close cousins.** Because related styles now count, the rock fan also
sees metal and the "happy" fan sees "energetic" pop. The lists feel fuller and
less robotic.

**It explains itself.** Every pick comes with a short reason, like "mood match"
or "energy similarity." You can always see why a song made the list.

**It stays calm under weird input.** Strange or impossible requests don't crash it
or produce nonsense scores. It just ignores what it can't use.

**It mixes things up.** The final five aren't five clones of the same song, so
there's a little variety to explore.

---

## 6. Observed Behavior / Biases

**Pattern: a song can win on the wrong reasons.** The clearest example is *Gym
Hero*. Its mood is "intense," but it keeps showing up for someone who asked for
"happy pop." It gets in because it's the right style (pop) and has the right
energy. Those two wins outweigh its wrong mood. So a song can ride in on style and
energy even when the feeling is off.

**Bias: the library is small and uneven.** There are only 36 songs, and they're
not spread evenly. Some styles have four songs, others just two. "Sad" has only
one song. So a listener who wants a rare style or mood gets thin, less accurate
results simply because there isn't much to choose from.

**Limitation: it can't tell real conflicts apart.** If someone asks for opposite
things — very high energy but a sad mood — the model quietly picks energy and
never mentions the clash. It always gives an answer, even when the request doesn't
really make sense.

**Limitation: blank profiles get weak guesses.** If a listener gives almost no
information, the model still fills a list, sometimes with songs it openly labels
"no strong match." It would be more honest to ask for one more preference.

---

## 7. Evaluation

### How We Tested It

We tried the recommender on three everyday listeners and several deliberately
tricky "trap" listeners, using a library of 36 songs.

The three everyday listeners were:

- **Upbeat Pop fan** — wants happy, high-energy, danceable pop.
- **Calm Lo-Fi listener** — wants quiet, acoustic, instrumental study music.
- **Intense Rock fan** — wants loud, fast, aggressive rock.

The trap listeners were designed to confuse the system on purpose: someone who
asks for opposite things at once (very high energy *and* a sad mood), someone who
turns every dial to its maximum, someone who leaves all preferences blank, and
someone who asks for a style the library doesn't contain.

### What the Results Looked Like

For all three everyday listeners, the top picks were exactly what you'd hope for.
The Pop fan's #1 was *Sunrise City* (a happy pop song); the Lo-Fi listener's top
two were *Library Rain* and *Midnight Coding* (both calm lo-fi tracks); and the
Rock fan's #1 was *Storm Runner* (an intense rock song). Nothing wildly out of
place showed up at the top of any of these lists.

A pleasant surprise was that the system now understands *related* styles, not
just exact ones. The Rock fan's list included metal songs like *Iron Prayer* and
*Iron Verdict* right below the rock pick, and the Pop fan's list included an
"energetic" pop song, *Cardio Kings*, even though the fan asked for "happy." The
system treats these neighbors as partial matches instead of ignoring them, which
makes the recommendations feel more natural and varied. The results also avoid
piling up near-identical songs, so a lo-fi list will still mix in an ambient or
jazz track rather than five clones of the same style.

### Comparing the Listeners

**Pop fan vs. Lo-Fi listener.** These two lists share almost no songs. The Pop
fan gets bright, danceable, vocal tracks; the Lo-Fi listener gets slow, acoustic,
mostly instrumental ones. This makes sense: the two listeners asked for opposite
energy levels and opposite "sounds," so the system correctly sends them in
different directions.

**Pop fan vs. Rock fan.** Both want high energy, so at first glance they seem
similar — but the results still diverge because they asked for different styles
and moods. The Pop fan's picks are happy and pop-flavored; the Rock fan's are
intense and guitar-driven. The shared craving for energy explains why a couple of
high-energy songs (like *Gym Hero*) appear on *both* lists, while the mood and
style differences keep the overall lists distinct.

**Lo-Fi listener vs. Rock fan.** This is the sharpest contrast of all — calm and
quiet versus loud and aggressive. As expected, the two lists have essentially
nothing in common, which is the clearest sign the system is responding to the
listener's stated taste rather than just recommending popular songs to everyone.

### Explaining the Surprises in Plain Language

**Why does "Gym Hero" keep showing up for a Happy Pop fan?** *Gym Hero* is a pop
song, but its mood is labelled "intense," not "happy." It still sneaks onto the
Pop fan's list because it wins points two ways: it's the right *genre* (pop) and
its *energy* is almost exactly what the fan wanted. Those two wins are enough to
outweigh the fact that its mood is wrong. In short, a song can ride in on genre
and energy even when its mood doesn't fit.

**Which preferences mattered most?** Genre, mood, and energy did the heavy
lifting. A song that matched the listener's genre and mood almost always landed
near the top, and energy usually decided the order among the remaining songs.
The quieter details (like danceability or tempo) mostly acted as tie-breakers.

**What this tells us about how the recommender works.** It's essentially a
"find songs most like what you described" engine. It leans hardest on the big,
obvious traits — style, mood, and energy — and uses the finer audio details to
sort near-ties. That makes its choices easy to understand and explain, but it
also means a strong match on one big trait (like energy) can occasionally pull in
a song that doesn't quite fit the overall vibe.

### Key Observations

**What worked well.**

- The everyday listeners all got sensible, on-taste top picks.
- Related styles now appear (metal for a rock fan, "energetic" for a "happy" fan),
  so results feel richer instead of rigidly literal.
- Lists no longer fill up with near-duplicate songs.
- The "trap" listener who asked for impossible values no longer breaks the
  system — it simply gives those unusable requests no credit and moves on.

**What still has limits.**

- A song can still be recommended on the strength of one trait (genre + energy)
  even when its mood is a poor fit — the *Gym Hero* case.
- A listener who gives almost no information (only a mood, or a style we don't
  carry) gets weak results, sometimes padded with songs the system openly admits
  are "no strong match."

**Ideas for improvement.**

- Give a small bonus when a song matches the *overall* combination of traits, so
  a song that's right on genre and energy but wrong on mood doesn't outrank a
  song that fits the whole picture.
- When a listener gives very little to go on, say so honestly and ask for one more
  preference rather than filling the list with weak guesses.

---

## 8. Future Work

If I kept building this, I'd try three things:

1. **Reward the whole vibe, not just parts.** Give a bonus when a song fits style,
   mood, *and* energy together. This would stop songs like *Gym Hero* from winning
   on style and energy while getting the mood wrong.

2. **Be honest when unsure.** When someone gives too little to go on, or asks for
   a style we don't have, say so and ask for one more detail instead of padding the
   list with weak picks.

3. **Grow and even out the library.** Add more songs and make sure every style and
   mood has a fair number. A bigger, more balanced catalog would make the picks
   more accurate for everyone, not just fans of the common styles.

---

## 9. Personal Reflection

**My biggest learning moment.** It was seeing that the "smartest" part of a
recommender is really just the weights. When I doubled energy and halved genre,
the whole list changed. I realized these systems aren't magic — they reflect
whatever the designer decided to reward.

**How AI tools helped, and when I checked them.** AI tools helped me move fast:
building test profiles, running experiments, and writing clear explanations. But I
had to double-check them. For example, after the scoring logic changed, the docs
still described the old formula and old results. The numbers only became right
after I re-ran the program and compared. The lesson: trust the actual output, not
a description of it.

**What surprised me.** How much a simple points system can "feel" like a real
recommendation. There's no AI brain inside — just adding up how close each song is
to what you asked for. Yet the top picks feel personal, and the little "why" notes
make it feel like the app understands you. That's mostly good design and clear
explanations, not deep intelligence.

**What I'd try next.** I'd reward the overall vibe instead of single traits, add
an "activity" option (like study or workout) that shifts the targets, and grow the
song library so rarer tastes get good picks too.
