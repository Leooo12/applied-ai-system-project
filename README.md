# 🎵 Music Recommender Simulation

## Project Summary

In this project you will build and explain a small music recommender system.

Your goal is to:

- Represent songs and a user "taste profile" as data
- Design a scoring rule that turns that data into recommendations
- Evaluate what your system gets right and wrong
- Reflect on how this mirrors real world AI recommenders

**This version** implements a content-based recommender over a 36-song catalog.
Each song is scored against a user "taste profile" by combining exact/near-match
bonuses for categorical features (genre, mood, and finer attributes) with a
closeness score for numerical audio features (energy, valence, tempo, …). On top
of the core scorer it adds three things: **selectable scoring strategies**
(Balanced, Genre-First, Mood-First, Energy-Focused) that re-weight the features
without duplicating the algorithm; a **diversity pass** that discourages the same
artist or genre from dominating the Top-K; and a **tabular terminal display**
that shows each pick's rank, title, artist, score, and the reasons it was chosen.

---

## How The System Works

### The Recommendation Approach

Real-world music platforms like Spotify and YouTube generate personalized recommendations in two main ways. **Collaborative filtering** looks at the behavior of *other* users — "people who liked what you liked also enjoyed this" — to predict what you might want next. **Content-based filtering**, by contrast, ignores other users entirely and instead looks at the *attributes of the songs themselves* (genre, mood, energy, and so on), recommending music whose characteristics match your stated tastes.

This project implements a **content-based recommendation system**. It does not use any data about other listeners; instead, it compares each song's attributes against a single user's preference profile. This makes the system simple, transparent, and easy to explain — you can always see *why* a song was recommended.

When matching songs to a user, the recommender prioritizes how *close* each song is to the user's preferences. It rewards exact matches on categorical features (like genre and mood) and rewards songs whose numerical values (like energy) are near the user's target — not simply higher or lower. Each feature is weighted by importance, and the songs with the highest total match scores are recommended first.

### Features Used in the Simulation

**Song** — each song stores the following attributes:

- `id` — a unique number identifying the song.
- `title` — the song's name (for display; not used in scoring).
- `artist` — the performer (for display; not used in scoring).
- `genre` — the musical style (e.g., pop, lofi, rock). A categorical feature that gives a strong signal of overall style.
- `mood` — the emotional tone (e.g., chill, happy, intense). A categorical feature and the best single proxy for a song's "vibe."
- `energy` — a 0–1 measure of intensity. Separates calm songs from powerful ones.
- `tempo_bpm` — the speed in beats per minute. Reflects how fast or slow the song feels.
- `valence` — a 0–1 measure of musical positivity (happy vs. sad).
- `danceability` — a 0–1 measure of how suitable the song is for dancing.
- `acousticness` — a 0–1 measure of how acoustic (vs. electronic) the song sounds.
- `instrumentalness` — a 0–1 measure of how likely the song has no vocals (instrumental vs. vocal-driven).
- `popularity` — a 0–100 measure of mainstream reach. Scored by *closeness* to the user's target (some listeners want hits, others want niche tracks), not "higher is better."
- `release_decade` — the era (e.g., 1990, 2010). Categorical but ordinal: an exact decade earns full points and an adjacent decade earns partial credit.
- `mood_tag` — a finer emotional label than `mood` (e.g., nostalgic, aggressive, euphoric, relaxing).
- `explicit` — a yes/no flag; a plain exact-match bonus.
- `artist_type` — solo vs. band; a plain exact-match bonus.

These five extra attributes are optional in scoring: they only contribute when a user profile actually lists a preference for them, so simple profiles still work.

**UserProfile** — each user stores the following preferences:

- `favorite_genre` — the user's preferred genre. Compared against each song's `genre`; an exact match boosts the score.
- `favorite_mood` — the user's preferred mood. Compared against each song's `mood`; an exact match boosts the score.
- `target_energy` — the energy level the user wants (0–1). Songs whose `energy` is closest to this value score highest.
- `likes_acoustic` — a true/false flag for whether the user prefers acoustic music. Used to reward songs with high (or low) `acousticness` accordingly.

### The Recommendation Process

When the app runs, the system first **loads the song catalog** from `data/songs.csv`, turning each row into a `Song` object with its features (genre, mood, energy, and so on). It then **reads the user's preference profile** (`UserProfile`), which holds the target genre, mood, energy level, and acoustic preference.

To generate recommendations, the system **loops through every song** and **compares each one against the user's preferences**. Categorical features (genre, mood) earn a fixed bonus when they match exactly, while numerical features (like energy) earn points based on how *close* the song's value is to the user's target — using `max(0, 1 − |target − value|)`, so nearer is always better and an out-of-range target can never push a feature below 0. Each feature is multiplied by a weight reflecting its importance, and the weighted parts are added together into a single **recommendation score** for that song.

Once every song has a score, the system **ranks them from highest to lowest** and **selects the Top-K** (e.g., the top 5). These best matches are displayed to the user, optionally alongside their score and a short reason explaining why each song was chosen.

### Algorithm Recipe

1. Load the song dataset from `data/songs.csv` into a list of `Song` objects.
2. Load the user's `UserProfile` (preferred genre, mood, target energy, acoustic preference).
3. Loop through every song in the catalog.
4. Compare each song's features against the user's preferences.
5. Score each feature — a bonus for categorical matches (full points on an exact match, half points on a same-family near-match), and a weighted closeness score (`weight × max(0, 1 − |target − value|)`) for numerical features.
6. Sum all weighted feature scores into one final recommendation score for the song.
7. Store the song together with its score (and the reasons it earned points).
8. Sort all scored songs from highest to lowest.
9. Build the Top-K with a diversity-aware pass that penalizes repeated artists (and, more mildly, repeated genres), and return it as the recommendations.

**Feature weights** (how much each feature can contribute to the score):

| Feature | Type | Weight | Scoring method |
|---|---|---|---|
| Mood | Categorical | 2.0 | Full points on exact match, half on a same-family match, else 0 |
| Genre | Categorical | 2.0 | Full points on exact match, half on a same-family match, else 0 |
| Energy | Numerical | 2.0 | `weight × max(0, 1 − \|target − value\|)` |
| Acousticness | Numerical | 1.5 | `weight × max(0, 1 − \|target − value\|)` |
| Instrumentalness | Numerical | 1.5 | `weight × max(0, 1 − \|target − value\|)` |
| Valence | Numerical | 1.0 | `weight × max(0, 1 − \|target − value\|)` |
| Danceability | Numerical | 1.0 | `weight × max(0, 1 − \|target − value\|)` |
| Tempo (BPM) | Numerical | 0.5 | Normalize to 0–1, then `weight × max(0, 1 − \|target − value\|)` |

Mood, genre, and energy now carry equal top weight so no single feature dominates, and the lighter audio features refine the ranking so that songs sharing the same genre and mood can still be told apart.

**Soft categorical matching.** Instead of demanding an exact string match, genres and moods are grouped into coarse families (e.g. `pop`/`indie pop`, `lofi`/`ambient`, `happy`/`energetic`/`confident`). An exact match earns full weight; a same-family near-match earns `PARTIAL_MATCH_FRACTION = 0.5` of the weight, so closely related styles are no longer treated as completely unrelated.

**Numerical closeness in detail.** For every numerical feature the raw closeness `1 − |target − value|` is **clamped to `[0, 1]`** — so a far-off (or out-of-range) value scores 0 instead of going negative — and then raised to `SIMILARITY_SHARPNESS` (now `1.0`, i.e. a straight-line falloff) in `recommender.py`. A linear falloff keeps audio-feature similarity meaningful relative to the categorical bonuses; raising the sharpness above `1.0` makes near-misses lose points faster.

**Diversity-aware ranking.** After scoring, the Top-K is assembled greedily: each pick is chosen by its *raw* score minus a penalty for every already-selected song that repeats one of its attributes. The penalties live in `DIVERSITY_PENALTIES` and are applied per attribute — `artist = 1.0` (the primary target, so one artist can't dominate the list) and `genre = 0.4` (a milder nudge toward stylistic spread). The penalty only affects *selection order*; every song's reported score is still its raw score, and a clearly higher-scoring song still wins despite a repeat. Pass `diversity=False` to `recommend_songs` to recover a plain highest-score-first ranking.

**Selectable scoring strategies.** The scorer is driven entirely by two weight dictionaries, so a "strategy" is just a named bundle of weights fed into the *same* algorithm. The `STRATEGIES` registry in `recommender.py` defines **Balanced** (the default), **Genre-First**, **Mood-First**, and **Energy-Focused**; each re-weights a few features to tilt the ranking without duplicating any scoring logic. Choose one on the command line — `python -m src.main mood_first`, or `python -m src.main all` to run every mode. Adding a new strategy is a single registry entry.

**Readable table output.** `src/main.py` prints each profile's Top-K as an aligned table (rank, title, artist, score, and a wrapped per-feature reasons column). It uses the `tabulate` library when installed and falls back to a built-in ASCII table otherwise, so no dependency is strictly required.

### Potential Biases and Limitations

- **Over-prioritizing categorical matches.** Because genre and mood carry the largest weights, a song with a perfect mood/genre match can outrank a song that actually *feels* closer in energy and tempo. *Impact:* the recommender may favor label matches over true sonic similarity. *Future improvement:* let users adjust the weights, or lower the categorical weights so numerical closeness has more say.
- **Limited diversity.** The system only understands the eight numerical/categorical attributes in the dataset, so its Top-K can fill up with near-identical songs (e.g., five chill lofi tracks). *Impact:* recommendations feel repetitive and discourage discovery. *Future improvement:* add a diversity step that skips a candidate too similar to one already chosen.
- **Cold-start with a simple profile.** The `UserProfile` captures only a handful of preferences and no listening history, so a new or vague profile produces generic results. *Impact:* users with eclectic or undefined taste get poorly personalized picks. *Future improvement:* let the profile learn from songs the user marks as liked, moving toward a richer taste model.
- **Missing context.** The system has no idea what the user is doing — working out, studying, commuting — or the time of day, and it treats preferences as fixed. *Impact:* the "best" song for a moment can be wrong even when the profile is right. *Future improvement:* add a lightweight context input (e.g., an "activity" selector) that shifts the target energy and tempo.

---

## Getting Started

### Setup

These steps take you from a fresh clone to a fully working install.

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/Leooo12/applied-ai-system-project.git
   cd applied-ai-system-project
   ```

2. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

3. Activate it:

   ```bash
   source .venv/bin/activate      # Mac or Linux
   ```

   ```bash
   .venv\Scripts\activate         # Windows
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Set up your environment variables:

   ```bash
   cp .env.example .env
   ```

   Then open `.env` and fill in your real `ANTHROPIC_API_KEY` (get one from
   [console.anthropic.com](https://console.anthropic.com/)). `.env` is
   git-ignored, so your key is never committed.

### Running Tests

Run the full test suite (offline -- every AI-dependent test uses a fake client,
so no API key or network access is required):

```bash
python -m pytest -v
```

### Running the App

Run the classic scoring-strategy evaluation harness:

```bash
python -m src.main
```

Run the interactive natural-language recommender (requires a real
`ANTHROPIC_API_KEY` in `.env`):

```bash
python -m src.main --interactive
```

Run the deterministic reliability evaluation (offline, no API key needed):

```bash
python -m src.evaluator
```

---

## Sample Recommendation Output

The following example shows the recommendation results generated for the
**High-Energy Pop** profile (`genre=pop, mood=happy, energy=0.90`) in the default
**Balanced** scoring mode, as printed by `python -m src.main`:

```text
Loaded songs: 36

============================================================
                  PROFILE: High-Energy Pop
============================================================
+-----+-----------------+-----------------+---------+-----------------------------------+
|   # | Title           | Artist          |   Score | Reasons                           |
+=====+=================+=================+=========+===================================+
|   1 | Sunrise City    | Neon Echo       |   11.07 | - Mood match (+2.0)               |
|     |                 |                 |         | - Genre match (+2.0)              |
|     |                 |                 |         | - Energy similarity (+1.84)       |
|     |                 |                 |         | - Acousticness similarity (+1.38) |
|     |                 |                 |         | - Instrumentalness similarity     |
|     |                 |                 |         |   (+1.46)                         |
|     |                 |                 |         | - Valence similarity (+0.99)      |
|     |                 |                 |         | - Danceability similarity (+0.94) |
|     |                 |                 |         | - Tempo_bpm similarity (+0.46)    |
+-----+-----------------+-----------------+---------+-----------------------------------+
|   2 | Cardio Kings    | Max Pulse       |    10.3 | - Mood related (+1.0)             |
|     |                 |                 |         | - Genre match (+2.0)              |
|     |                 |                 |         | - Energy similarity (+2.00)       |
|     |                 |                 |         |   ...                             |
+-----+-----------------+-----------------+---------+-----------------------------------+
```

The full ranked lists for every standard and adversarial profile are captured
under [Raw Output by Profile](#raw-output-by-profile) below.

---

## System Evaluation

To stress-test the scoring logic, `src/main.py` runs the recommender against a
suite of **standard** and **adversarial** user profiles over the current
36-song catalog. Standard profiles represent realistic listeners; adversarial
profiles are deliberately designed to break assumptions in the scoring formula.
Run them all with `python -m src.main`.

> **Note.** These results reflect the current scoring logic: equal top weights
> for mood, genre, and energy (2.0 each), **soft family matching** (a same-family
> genre/mood earns half credit, shown as `related`), a **linear** closeness
> falloff clamped to `[0, 1]`, and a **diversity-aware** final ranking. Because
> diversity re-ranking can promote a lower-scoring song over a higher one to
> avoid repetition, the displayed order is not always strictly by score.

### Profiles Tested

**Standard**

| Profile | Genre / Mood | Target energy | Intent |
|---|---|---|---|
| High-Energy Pop | pop / happy | 0.90 | Upbeat, danceable, positive |
| Chill Lo-Fi | lofi / chill | 0.35 | Calm, acoustic, instrumental |
| Deep Intense Rock | rock / intense | 0.95 | Loud, fast, aggressive |

**Adversarial**

| Profile | What it probes |
|---|---|
| Conflicting (High Energy + Sad) | Can the score reconcile pulling in opposite directions? |
| All-Maximum Values | Does one extreme feature dominate the ranking? |
| All-Minimum Values | Same, at the bottom of every scale. |
| Uniform / Indifferent (all 0.5) | No categorical prefs; every target neutral. |
| Unsupported Genre + Mood (`k-pop` / `nostalgic`) | Categorical labels that exist for no song. |
| Out-of-Range Targets (`energy=2.0`, `tempo=300`) | Inputs outside the assumed 0–1 range. |
| Extremely Narrow (mood only) | A one-feature profile. |

### Results — do the recommendations make sense?

**Standard profiles all behaved correctly**, each led by an exact genre + mood
match, and — thanks to soft family matching — now backed up by *related* styles
rather than only literal ones:

- *High-Energy Pop* → **Sunrise City** (pop/happy, 11.07), then **Cardio Kings**
  (pop/energetic — a `related` mood) and indie-pop happy tracks.
- *Chill Lo-Fi* → **Library Rain** and **Midnight Coding** (both lofi/chill),
  with ambient and jazz neighbours filling out the list.
- *Deep Intense Rock* → **Storm Runner** (rock/intense), then **Iron Prayer** and
  **Iron Verdict** (metal/intense — a `related` genre).

With mood, genre, and energy now weighted equally (2.0 each), no single feature
dominates the way mood once did. Instead an exact genre+mood match (4.0 combined)
plus close energy reliably floats the intended song to the top.

**How the current logic held up on the edge cases:**

1. **Out-of-range targets are now handled cleanly (previously a bug).** With
   `energy=2.0`, every numerical closeness term clamps to `+0.00` instead of going
   negative, so scores stay positive and the categorical matches still count —
   e.g. **Storm Runner** leads the Out-of-Range profile at 4.46 on its mood+genre
   match alone. No more malformed `(+-…)` strings.

2. **Conflicting preferences still resolve silently toward energy.** The
   High-Energy-Sad profile puts **Gym Hero** (pop/intense) and **Cardio Kings**
   (pop/energetic) on top, while the genuinely sad **Fading Signal** lands last —
   the genre match plus high energy outweigh the low-valence request, and nothing
   flags the contradiction.

3. **Family matching surfaces good neighbours.** *Deep Intense Rock* now pulls in
   two metal tracks as `related` genre matches, and *High-Energy Pop* pulls in an
   `energetic` pop song — both sensible expansions that exact-match scoring used to
   hide.

4. **Diversity re-ranking spreads out the list.** Displayed order is no longer
   strictly by score: in *High-Energy Pop*, **Gym Hero** (9.19) appears above
   **Paper Planes** (9.71) because Paper Planes repeats the indie-pop/happy pattern
   already picked, so the diversity pass demotes it.

5. **Sparse profiles remain weak.** The mood-only profile finds two romantic songs
   tied at 2.00, then pads the list with songs openly labelled *"No strong matches
   for this profile"* (score 0.00). Useful honesty, but still thin results.

### Strengths

- **Related styles now appear.** Soft family matching means a rock fan sees metal,
  and a "happy" fan sees "energetic" pop — richer, less literal results.
- **No near-duplicate pile-ups.** Diversity-aware ranking keeps a single style from
  filling the whole Top-5.
- **Robust to bad input.** Out-of-range and extreme targets clamp to 0 instead of
  producing negative scores or crashes.
- **Transparent.** Every pick still ships with a per-feature reason breakdown,
  including whether a categorical hit was an exact `match` or a `related` one.

### Limitations revealed by the stress test

- **A wrong-mood song can still win on genre + energy.** *Gym Hero* (mood
  "intense") keeps appearing for the Happy-Pop fan because pop + high energy
  outscore its mood miss.
- **Conflicting preferences are resolved silently**, favouring energy over a
  contradictory valence/mood request, with no signal to the user.
- **Sparse or unsupported profiles give thin results** — only audio features drive
  the ranking, and the list is padded with honest-but-weak "no strong match" rows.
- **Displayed order can look non-monotonic.** Because diversity re-ranking reorders
  by a hidden adjusted score, a user reading the printed scores may see a
  higher number below a lower one.

### Suggested improvements

- **Add a combined-fit bonus** so a song matching the *overall* profile (genre +
  mood + energy together) is rewarded over one that wins on genre + energy while
  missing the mood — directly targets the *Gym Hero* case.
- **Flag contradictions** (e.g. high energy + low valence) and either warn or
  down-weight the conflicting term.
- **Be honest about low-confidence profiles** — when a profile is too sparse or
  asks for an absent style, say so and request one more preference instead of
  padding with weak picks.
- **Show the diversity-adjusted score** (or a small "diversified" note) so the
  printed order matches the numbers the user sees.

### Raw Output by Profile

The blocks below are captured verbatim from `python -m src.main` on the current
36-song catalog.

**Standard — High-Energy Pop**

```text
1. Sunrise City - Neon Echo  [pop/happy]
   Score: 11.07
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.84)
   - Acousticness similarity (+1.38)
   - Instrumentalness similarity (+1.46)
   - Valence similarity (+0.99)
   - Danceability similarity (+0.94)
   - Tempo_bpm similarity (+0.46)

2. Cardio Kings - Max Pulse  [pop/energetic]
   Score: 10.30
   - Mood related (+1.0)
   - Genre match (+2.0)
   - Energy similarity (+2.00)
   - Acousticness similarity (+1.44)
   - Instrumentalness similarity (+1.48)
   - Valence similarity (+0.95)
   - Danceability similarity (+0.95)
   - Tempo_bpm similarity (+0.48)

3. Rooftop Lights - Indigo Parade  [indie pop/happy]
   Score: 9.76
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+1.72)
   - Acousticness similarity (+1.12)
   - Instrumentalness similarity (+1.48)
   - Valence similarity (+0.96)
   - Danceability similarity (+0.97)
   - Tempo_bpm similarity (+0.49)

4. Gym Hero - Max Pulse  [pop/intense]
   Score: 9.19
   - Genre match (+2.0)
   - Energy similarity (+1.94)
   - Acousticness similarity (+1.42)
   - Instrumentalness similarity (+1.47)
   - Valence similarity (+0.92)
   - Danceability similarity (+0.97)
   - Tempo_bpm similarity (+0.47)

5. Paper Planes - Indigo Parade  [indie pop/happy]
   Score: 9.71
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+1.64)
   - Acousticness similarity (+1.20)
   - Instrumentalness similarity (+1.50)
   - Valence similarity (+0.94)
   - Danceability similarity (+0.95)
   - Tempo_bpm similarity (+0.48)
```

**Standard — Chill Lo-Fi**

```text
1. Library Rain - Paper Lanterns  [lofi/chill]
   Score: 11.34
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+2.00)
   - Acousticness similarity (+1.48)
   - Instrumentalness similarity (+1.46)
   - Valence similarity (+0.95)
   - Danceability similarity (+0.97)
   - Tempo_bpm similarity (+0.48)

2. Midnight Coding - LoRoom  [lofi/chill]
   Score: 11.05
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.86)
   - Acousticness similarity (+1.29)
   - Instrumentalness similarity (+1.50)
   - Valence similarity (+0.99)
   - Danceability similarity (+0.93)
   - Tempo_bpm similarity (+0.48)

3. Dusk Patrol - Orbit Bloom  [ambient/focused]
   Score: 9.15
   - Mood related (+1.0)
   - Genre related (+1.0)
   - Energy similarity (+1.96)
   - Acousticness similarity (+1.42)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+1.00)
   - Danceability similarity (+0.89)
   - Tempo_bpm similarity (+0.46)

4. Focus Flow - LoRoom  [lofi/focused]
   Score: 10.10
   - Mood related (+1.0)
   - Genre match (+2.0)
   - Energy similarity (+1.90)
   - Acousticness similarity (+1.40)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.96)
   - Danceability similarity (+0.95)
   - Tempo_bpm similarity (+0.47)

5. Coffee Shop Stories - Slow Stereo  [jazz/relaxed]
   Score: 8.08
   - Mood related (+1.0)
   - Energy similarity (+1.96)
   - Acousticness similarity (+1.44)
   - Instrumentalness similarity (+1.43)
   - Valence similarity (+0.84)
   - Danceability similarity (+0.99)
   - Tempo_bpm similarity (+0.42)
```

**Standard — Deep Intense Rock**

```text
1. Storm Runner - Voltline  [rock/intense]
   Score: 11.16
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.92)
   - Acousticness similarity (+1.47)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.92)
   - Danceability similarity (+0.94)
   - Tempo_bpm similarity (+0.49)

2. Iron Prayer - Ash Meridian  [metal/intense]
   Score: 10.23
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+2.00)
   - Acousticness similarity (+1.47)
   - Instrumentalness similarity (+1.47)
   - Valence similarity (+0.90)
   - Danceability similarity (+0.92)
   - Tempo_bpm similarity (+0.48)

3. Iron Verdict - Blacklight Choir  [metal/intense]
   Score: 10.17
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+1.96)
   - Acousticness similarity (+1.44)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.95)
   - Danceability similarity (+0.95)
   - Tempo_bpm similarity (+0.45)

4. Granite Sky - Voltline  [rock/moody]
   Score: 8.46
   - Genre match (+2.0)
   - Energy similarity (+1.46)
   - Acousticness similarity (+1.29)
   - Instrumentalness similarity (+1.50)
   - Valence similarity (+0.90)
   - Danceability similarity (+0.96)
   - Tempo_bpm similarity (+0.35)

5. Gym Hero - Max Pulse  [pop/intense]
   Score: 8.57
   - Mood match (+2.0)
   - Energy similarity (+1.96)
   - Acousticness similarity (+1.46)
   - Instrumentalness similarity (+1.40)
   - Valence similarity (+0.63)
   - Danceability similarity (+0.72)
   - Tempo_bpm similarity (+0.41)
```

**Adversarial — Conflicting (High Energy + Sad)**

```text
1. Gym Hero - Max Pulse  [pop/intense]
   Score: 8.46
   - Genre match (+2.0)
   - Energy similarity (+1.90)
   - Acousticness similarity (+1.42)
   - Instrumentalness similarity (+1.47)
   - Valence similarity (+0.28)
   - Danceability similarity (+0.98)
   - Tempo_bpm similarity (+0.41)

2. Cardio Kings - Max Pulse  [pop/energetic]
   Score: 8.41
   - Genre match (+2.0)
   - Energy similarity (+1.84)
   - Acousticness similarity (+1.44)
   - Instrumentalness similarity (+1.48)
   - Valence similarity (+0.25)
   - Danceability similarity (+1.00)
   - Tempo_bpm similarity (+0.40)

3. Granite Sky - Voltline  [rock/moody]
   Score: 6.79
   - Mood related (+1.0)
   - Energy similarity (+1.40)
   - Acousticness similarity (+1.32)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.55)
   - Danceability similarity (+0.74)
   - Tempo_bpm similarity (+0.35)

4. Sunrise City - Neon Echo  [pop/happy]
   Score: 7.95
   - Genre match (+2.0)
   - Energy similarity (+1.68)
   - Acousticness similarity (+1.38)
   - Instrumentalness similarity (+1.46)
   - Valence similarity (+0.21)
   - Danceability similarity (+0.89)
   - Tempo_bpm similarity (+0.34)

5. Fading Signal - Halcyon Drift  [synthwave/sad]
   Score: 6.51
   - Mood match (+2.0)
   - Energy similarity (+0.92)
   - Acousticness similarity (+1.27)
   - Instrumentalness similarity (+0.60)
   - Valence similarity (+0.77)
   - Danceability similarity (+0.70)
   - Tempo_bpm similarity (+0.25)
```

**Adversarial — All-Maximum Values**

```text
1. Iron Verdict - Blacklight Choir  [metal/intense]
   Score: 7.47
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.94)
   - Acousticness similarity (+0.06)
   - Instrumentalness similarity (+0.08)
   - Valence similarity (+0.35)
   - Danceability similarity (+0.55)
   - Tempo_bpm similarity (+0.50)

2. Iron Prayer - Ash Meridian  [metal/intense]
   Score: 7.40
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.90)
   - Acousticness similarity (+0.09)
   - Instrumentalness similarity (+0.12)
   - Valence similarity (+0.30)
   - Danceability similarity (+0.52)
   - Tempo_bpm similarity (+0.47)

3. Storm Runner - Voltline  [rock/intense]
   Score: 6.65
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+1.82)
   - Acousticness similarity (+0.15)
   - Instrumentalness similarity (+0.08)
   - Valence similarity (+0.48)
   - Danceability similarity (+0.66)
   - Tempo_bpm similarity (+0.46)

4. Neon Overdrive - Pulsewidth  [electronic/energetic]
   Score: 5.01
   - Energy similarity (+1.90)
   - Acousticness similarity (+0.05)
   - Instrumentalness similarity (+1.12)
   - Valence similarity (+0.70)
   - Danceability similarity (+0.90)
   - Tempo_bpm similarity (+0.34)

5. Coffee Shop Stories - Slow Stereo  [jazz/relaxed]
   Score: 4.68
   - Energy similarity (+0.74)
   - Acousticness similarity (+1.33)
   - Instrumentalness similarity (+1.20)
   - Valence similarity (+0.71)
   - Danceability similarity (+0.54)
   - Tempo_bpm similarity (+0.15)
```

**Adversarial — All-Minimum Values**

```text
1. Letters Unsent - Clara Voss  [classical/melancholy]
   Score: 7.61
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.52)
   - Acousticness similarity (+0.08)
   - Instrumentalness similarity (+0.08)
   - Valence similarity (+0.70)
   - Danceability similarity (+0.78)
   - Tempo_bpm similarity (+0.46)

2. Marble Halls - Clara Voss  [classical/melancholy]
   Score: 7.44
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+1.40)
   - Acousticness similarity (+0.10)
   - Instrumentalness similarity (+0.09)
   - Valence similarity (+0.66)
   - Danceability similarity (+0.74)
   - Tempo_bpm similarity (+0.44)

3. Undertow - Mino Grey  [r&b/moody]
   Score: 5.57
   - Mood related (+1.0)
   - Energy similarity (+1.02)
   - Acousticness similarity (+0.90)
   - Instrumentalness similarity (+1.41)
   - Valence similarity (+0.58)
   - Danceability similarity (+0.34)
   - Tempo_bpm similarity (+0.32)

4. Fading Signal - Halcyon Drift  [synthwave/sad]
   Score: 5.19
   - Mood related (+1.0)
   - Energy similarity (+1.12)
   - Acousticness similarity (+1.12)
   - Instrumentalness similarity (+0.52)
   - Valence similarity (+0.72)
   - Danceability similarity (+0.40)
   - Tempo_bpm similarity (+0.30)

5. Paper Boats - Ferns & Foxes  [folk/relaxed]
   Score: 5.10
   - Genre related (+1.0)
   - Energy similarity (+1.24)
   - Acousticness similarity (+0.15)
   - Instrumentalness similarity (+1.35)
   - Valence similarity (+0.48)
   - Danceability similarity (+0.52)
   - Tempo_bpm similarity (+0.36)
```

**Adversarial — Uniform / Indifferent (all 0.5)**

```text
1. Static Bloom - Circuit Fauna  [electronic/chill]
   Score: 6.48
   - Energy similarity (+1.92)
   - Acousticness similarity (+1.05)
   - Instrumentalness similarity (+1.35)
   - Valence similarity (+0.92)
   - Danceability similarity (+0.78)
   - Tempo_bpm similarity (+0.46)

2. Neon Rain - Halcyon Drift  [synthwave/moody]
   Score: 6.48
   - Energy similarity (+1.74)
   - Acousticness similarity (+1.17)
   - Instrumentalness similarity (+1.32)
   - Valence similarity (+0.95)
   - Danceability similarity (+0.82)
   - Tempo_bpm similarity (+0.48)

3. Brass Alley Nights - Brass Cadence  [jazz/confident]
   Score: 6.38
   - Energy similarity (+1.78)
   - Acousticness similarity (+1.42)
   - Instrumentalness similarity (+1.05)
   - Valence similarity (+0.84)
   - Danceability similarity (+0.80)
   - Tempo_bpm similarity (+0.49)

4. Quiet Machines - LoRoom  [lofi/focused]
   Score: 6.31
   - Energy similarity (+1.92)
   - Acousticness similarity (+1.14)
   - Instrumentalness similarity (+1.02)
   - Valence similarity (+0.98)
   - Danceability similarity (+0.88)
   - Tempo_bpm similarity (+0.37)

5. Golden Hour Haze - Sunset Motel  [indie pop/relaxed]
   Score: 6.17
   - Energy similarity (+1.84)
   - Acousticness similarity (+1.41)
   - Instrumentalness similarity (+0.83)
   - Valence similarity (+0.78)
   - Danceability similarity (+0.82)
   - Tempo_bpm similarity (+0.49)
```

**Adversarial — Unsupported Genre + Mood (`k-pop` / `nostalgic`)**

```text
1. Hollow Tide - Amber Sol  [r&b/romantic]
   Score: 7.19
   - Energy similarity (+1.94)
   - Acousticness similarity (+1.41)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.96)
   - Danceability similarity (+0.98)
   - Tempo_bpm similarity (+0.47)

2. Golden Hour Haze - Sunset Motel  [indie pop/relaxed]
   Score: 7.02
   - Energy similarity (+1.96)
   - Acousticness similarity (+1.29)
   - Instrumentalness similarity (+1.42)
   - Valence similarity (+0.88)
   - Danceability similarity (+0.98)
   - Tempo_bpm similarity (+0.48)

3. Granite Sky - Voltline  [rock/moody]
   Score: 6.99
   - Energy similarity (+1.84)
   - Acousticness similarity (+1.38)
   - Instrumentalness similarity (+1.50)
   - Valence similarity (+0.90)
   - Danceability similarity (+0.94)
   - Tempo_bpm similarity (+0.43)

4. Slow Fire - Kayo Vane  [hip-hop/confident]
   Score: 6.89
   - Energy similarity (+1.88)
   - Acousticness similarity (+1.32)
   - Instrumentalness similarity (+1.38)
   - Valence similarity (+1.00)
   - Danceability similarity (+0.88)
   - Tempo_bpm similarity (+0.43)

5. Static Bloom - Circuit Fauna  [electronic/chill]
   Score: 6.38
   - Energy similarity (+1.88)
   - Acousticness similarity (+1.35)
   - Instrumentalness similarity (+0.75)
   - Valence similarity (+0.98)
   - Danceability similarity (+0.98)
   - Tempo_bpm similarity (+0.44)
```

**Adversarial — Out-of-Range Targets (`energy=2.0`, `tempo=300`)**

Every numerical term now clamps to `+0.00` (no negatives, no malformed strings);
only the categorical matches and the in-range tempo term carry the score.

```text
1. Storm Runner - Voltline  [rock/intense]
   Score: 4.46
   - Mood match (+2.0)
   - Genre match (+2.0)
   - Energy similarity (+0.00)
   - Acousticness similarity (+0.00)
   - Instrumentalness similarity (+0.00)
   - Valence similarity (+0.00)
   - Danceability similarity (+0.00)
   - Tempo_bpm similarity (+0.46)

2. Iron Verdict - Blacklight Choir  [metal/intense]
   Score: 3.50
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+0.00)
   - Acousticness similarity (+0.00)
   - Instrumentalness similarity (+0.00)
   - Valence similarity (+0.00)
   - Danceability similarity (+0.00)
   - Tempo_bpm similarity (+0.50)

3. Granite Sky - Voltline  [rock/moody]
   Score: 2.30
   - Genre match (+2.0)
   - Energy similarity (+0.00)
   - Acousticness similarity (+0.00)
   - Instrumentalness similarity (+0.00)
   - Valence similarity (+0.00)
   - Danceability similarity (+0.00)
   - Tempo_bpm similarity (+0.30)

4. Iron Prayer - Ash Meridian  [metal/intense]
   Score: 3.48
   - Mood match (+2.0)
   - Genre related (+1.0)
   - Energy similarity (+0.00)
   - Acousticness similarity (+0.00)
   - Instrumentalness similarity (+0.00)
   - Valence similarity (+0.00)
   - Danceability similarity (+0.00)
   - Tempo_bpm similarity (+0.47)

5. Gym Hero - Max Pulse  [pop/intense]
   Score: 2.36
   - Mood match (+2.0)
   - Energy similarity (+0.00)
   - Acousticness similarity (+0.00)
   - Instrumentalness similarity (+0.00)
   - Valence similarity (+0.00)
   - Danceability similarity (+0.00)
   - Tempo_bpm similarity (+0.36)
```

**Adversarial — Extremely Narrow (mood only)**

```text
1. Velvet Hours - Amber Sol  [r&b/romantic]
   Score: 2.00
   - Mood match (+2.0)

2. Hollow Tide - Amber Sol  [r&b/romantic]
   Score: 2.00
   - Mood match (+2.0)

3. Sunrise City - Neon Echo  [pop/happy]
   Score: 0.00
   - No strong matches for this profile

4. Midnight Coding - LoRoom  [lofi/chill]
   Score: 0.00
   - No strong matches for this profile

5. Storm Runner - Voltline  [rock/intense]
   Score: 0.00
   - No strong matches for this profile
```

---

## Experiments You Tried

### Experiment 1 — Amplify Energy, Reduce Genre

**Hypothesis:** the ranking is dominated by categorical labels; boosting a
numerical feature and shrinking a categorical one should shift results toward
*sonic* similarity rather than genre labels.

**Change (weights only, all other logic untouched):**

| Weight | Default | Experiment |
|---|---|---|
| `energy` | 2.0 | **4.0** (doubled) |
| `genre` | 2.0 | **1.0** (halved) |

*(Both runs used the same numerical closeness with `SIMILARITY_SHARPNESS = 2.0`,
so the weights were the only variable.)*

**What changed:**

- **The head of well-matched lists stayed stable.** Mood (3.0) still anchors the
  top pick for every standard profile — *High-Energy Pop* → Sunrise City,
  *Chill Lo-Fi* → Library Rain, *Deep Intense Rock* → Storm Runner — so the change
  did **not** scramble obvious matches.
- **The tail reshuffled toward energy.** For *Deep Intense Rock*, doubling energy
  pulled **Neon Overdrive** (electronic/energetic, `energy=0.95` = exact target →
  +4.00) into the Top 5, displacing happy-pop tracks that had ranked on label
  proximity alone — arguably a better "intense" companion.
- **Genre became a minor nudge.** With genre at 1.0, the Storm Runner (rock) vs.
  Iron Verdict (metal) ordering was decided by energy closeness rather than the
  genre label, confirming the categorical-dominance hypothesis.
- **High-energy songs rose everywhere.** In *High-Energy Pop*, Storm Runner climbed
  6.28 → 8.24 purely from the doubled energy term, even while losing genre weight.

**Conclusion:** the system is sensitive to energy weighting in the expected
direction. The change is a **different tradeoff, not an objective improvement** —
it favors sonic energy over genre labels. The experimental weights were **reverted
to the defaults** after measuring; the live code uses energy 2.0 / genre 2.0.

### Ideas for further experiments

- **Drop genre weight from 2.0 to 0.5** and measure how far the rankings shift
  toward audio-feature similarity — a stronger version of Experiment 1.
- **Vary the tempo or valence weight** to see how much the finer audio features
  can reorder songs that already share a genre and mood.
- **Compare the four scoring strategies** (Balanced, Genre-First, Mood-First,
  Energy-Focused) on the same profile to quantify how re-weighting alone changes
  who reaches the Top-5.

---

## Limitations and Risks

- **Tiny, uneven catalog.** Only 36 songs, and they are not evenly distributed
  across styles — some genres have four tracks, others two, and "sad" has just
  one. A listener who wants a rare style or mood gets thin, less accurate results
  simply because there is little to choose from.
- **No understanding of lyrics or language.** The system scores only the numeric
  and categorical attributes in the dataset; it has no idea what a song is *about*,
  so whole dimensions of taste (themes, language, storytelling) are invisible.
- **A song can win on the wrong reasons.** Because genre and energy carry heavy
  weight, a song with the right style and energy but the wrong mood (the recurring
  *Gym Hero* case) can outrank a song that fits the overall vibe better.
- **Silent handling of contradictions.** Conflicting requests (very high energy
  *and* a sad mood) are resolved quietly in favor of energy, with no signal to the
  user that the request pulled in opposite directions.
- **Weak results for sparse or unsupported profiles.** A profile with almost no
  information, or one asking for a style the catalog does not contain, still gets a
  full list — sometimes padded with songs openly labelled "no strong match."
- **No personalization over time.** The `UserProfile` is a fixed snapshot with no
  listening history, so the system cannot learn or adapt.

These limitations are explored in more depth in the [model card](model_card.md).

---

## Reflection

Read and complete `model_card.md`:

[**Model Card**](model_card.md)

**How recommenders turn data into predictions.** Building this made it concrete
that a recommender is, at heart, a scoring function: it turns every song and the
user's stated taste into numbers, measures how *close* each song is to what was
asked for, weights those pieces of evidence by importance, and ranks. There is no
"understanding" of music — just arithmetic over features. The most consequential
design choice is not the algorithm but the **weights**: doubling the energy weight
and halving genre visibly reordered the results, which showed how much a
recommender simply reflects whatever its designer chose to reward. The strategy
modes make this explicit — the same songs and the same math produce very different
lists purely because the emphasis changed.

**Where bias or unfairness can show up.** The clearest source here is the data:
a small, uneven catalog means listeners who want under-represented styles get
worse recommendations than fans of common styles — a mirror of how real systems
under-serve niche tastes and can entrench popular content. Feature and weight
choices are a second source: whatever the designer decides "matters" (and what is
left out — lyrics, language, culture, context) quietly shapes who is well served.
A third is the feedback-loop risk that real platforms face: recommending mostly
what is already popular can make popular things more popular still. Even the
diversity penalty I added is a value judgment about what a "good" list looks like.
The lesson is that these systems are never neutral — their fairness depends on the
data they see and the priorities their designers encode.



