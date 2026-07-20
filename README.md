# 🎵 Music Recommender Simulation

## Project Summary

In this project you will build and explain a small music recommender system.

Your goal is to:

- Represent songs and a user "taste profile" as data
- Design a scoring rule that turns that data into recommendations
- Evaluate what your system gets right and wrong
- Reflect on how this mirrors real world AI recommenders

Replace this paragraph with your own summary of what your version does.

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

**UserProfile** — each user stores the following preferences:

- `favorite_genre` — the user's preferred genre. Compared against each song's `genre`; an exact match boosts the score.
- `favorite_mood` — the user's preferred mood. Compared against each song's `mood`; an exact match boosts the score.
- `target_energy` — the energy level the user wants (0–1). Songs whose `energy` is closest to this value score highest.
- `likes_acoustic` — a true/false flag for whether the user prefers acoustic music. Used to reward songs with high (or low) `acousticness` accordingly.

### The Recommendation Process

When the app runs, the system first **loads the song catalog** from `data/songs.csv`, turning each row into a `Song` object with its features (genre, mood, energy, and so on). It then **reads the user's preference profile** (`UserProfile`), which holds the target genre, mood, energy level, and acoustic preference.

To generate recommendations, the system **loops through every song** and **compares each one against the user's preferences**. Categorical features (genre, mood) earn a fixed bonus when they match exactly, while numerical features (like energy) earn points based on how *close* the song's value is to the user's target — using `1 − |target − value|`, so nearer is always better. Each feature is multiplied by a weight reflecting its importance, and the weighted parts are added together into a single **recommendation score** for that song.

Once every song has a score, the system **ranks them from highest to lowest** and **selects the Top-K** (e.g., the top 5). These best matches are displayed to the user, optionally alongside their score and a short reason explaining why each song was chosen.

### Algorithm Recipe

1. Load the song dataset from `data/songs.csv` into a list of `Song` objects.
2. Load the user's `UserProfile` (preferred genre, mood, target energy, acoustic preference).
3. Loop through every song in the catalog.
4. Compare each song's features against the user's preferences.
5. Score each feature — a fixed bonus for exact categorical matches, and a weighted closeness score (`weight × (1 − |target − value|)`) for numerical features.
6. Sum all weighted feature scores into one final recommendation score for the song.
7. Store the song together with its score (and the reasons it earned points).
8. Sort all scored songs from highest to lowest.
9. Return the Top-K highest-scoring songs as the recommendations.

**Feature weights** (how much each feature can contribute to the score):

| Feature | Type | Weight | Scoring method |
|---|---|---|---|
| Mood | Categorical | 3.0 | Full points on exact match, else 0 |
| Genre | Categorical | 2.0 | Full points on exact match, else 0 |
| Energy | Numerical | 2.0 | `weight × (1 − \|target − value\|)` |
| Acousticness | Numerical | 1.5 | `weight × (1 − \|target − value\|)` |
| Instrumentalness | Numerical | 1.5 | `weight × (1 − \|target − value\|)` |
| Valence | Numerical | 1.0 | `weight × (1 − \|target − value\|)` |
| Danceability | Numerical | 1.0 | `weight × (1 − \|target − value\|)` |
| Tempo (BPM) | Numerical | 0.5 | Normalize to 0–1, then `weight × (1 − \|target − value\|)` |

Mood leads, energy and genre follow, and the lighter audio features refine the ranking so that songs sharing the same genre and mood can still be told apart.

### Potential Biases and Limitations

- **Over-prioritizing categorical matches.** Because genre and mood carry the largest weights, a song with a perfect mood/genre match can outrank a song that actually *feels* closer in energy and tempo. *Impact:* the recommender may favor label matches over true sonic similarity. *Future improvement:* let users adjust the weights, or lower the categorical weights so numerical closeness has more say.
- **Limited diversity.** The system only understands the eight numerical/categorical attributes in the dataset, so its Top-K can fill up with near-identical songs (e.g., five chill lofi tracks). *Impact:* recommendations feel repetitive and discourage discovery. *Future improvement:* add a diversity step that skips a candidate too similar to one already chosen.
- **Cold-start with a simple profile.** The `UserProfile` captures only a handful of preferences and no listening history, so a new or vague profile produces generic results. *Impact:* users with eclectic or undefined taste get poorly personalized picks. *Future improvement:* let the profile learn from songs the user marks as liked, moving toward a richer taste model.
- **Missing context.** The system has no idea what the user is doing — working out, studying, commuting — or the time of day, and it treats preferences as fixed. *Impact:* the "best" song for a moment can be wrong even when the profile is right. *Future improvement:* add a lightweight context input (e.g., an "activity" selector) that shifts the target energy and tempo.

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.main
```

### Running Tests

Run the starter tests with:

```bash
pytest
```

You can add more tests in `tests/test_recommender.py`.

---

## Sample Recommendation Output

The following example shows the recommendation results generated for the default user profile (`genre=pop, mood=happy, energy=0.8`):

```text
Loaded songs: 18

==================================================
             Top 5 Recommended Songs
==================================================

1. Sunrise City - Neon Echo
   Score: 6.96
   Reasons:
   - Mood match (+3.0)
   - Genre match (+2.0)
   - Energy similarity (+1.96)

--------------------------------------------------

2. Sidewalk Groove - The Funk Cadets
   Score: 4.96
   Reasons:
   - Mood match (+3.0)
   - Energy similarity (+1.96)

--------------------------------------------------

3. Rooftop Lights - Indigo Parade
   Score: 4.92
   Reasons:
   - Mood match (+3.0)
   - Energy similarity (+1.92)

--------------------------------------------------

4. Gym Hero - Max Pulse
   Score: 3.74
   Reasons:
   - Genre match (+2.0)
   - Energy similarity (+1.74)

--------------------------------------------------

5. Night Drive Loop - Neon Echo
   Score: 1.90
   Reasons:
   - Energy similarity (+1.90)
```

---

## Experiments You Tried

Use this section to document the experiments you ran. For example:

- What happened when you changed the weight on genre from 2.0 to 0.5
- What happened when you added tempo or valence to the score
- How did your system behave for different types of users

---

## Limitations and Risks

Summarize some limitations of your recommender.

Examples:

- It only works on a tiny catalog
- It does not understand lyrics or language
- It might over favor one genre or mood

You will go deeper on this in your model card.

---

## Reflection

Read and complete `model_card.md`:

[**Model Card**](model_card.md)

Write 1 to 2 paragraphs here about what you learned:

- about how recommenders turn data into predictions
- about where bias or unfairness could show up in systems like this



