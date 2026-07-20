# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agentic Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

Extend the content-based recommender by adding **five new song attributes** to the
dataset and wiring them into the existing scoring algorithm — without rewriting
the recommender or breaking current behavior.

### Example Prompt(s)

> Review the current implementation of `data/songs.csv` and `src/recommender.py`,
> then extend the recommendation system by adding at least five new song
> attributes and updating the scoring algorithm accordingly. For each new
> feature, decide on an appropriate scoring method and explain why it fits.
> Keep the scoring simple, readable, and consistent with the existing design;
> preserve existing functionality; and modify only `songs.csv`,
> `src/recommender.py`, and `ai_interactions.md`.

### AI-Generated Changes

**Files modified**

- `data/songs.csv` — appended five columns and populated all 36 songs.
- `src/recommender.py` — integrated the five features into scoring.
- `ai_interactions.md` — this log.

**New features added** (all pre-existing columns kept unchanged)

| Feature | Type | Weight | Scoring method & why it fits |
|---|---|---|---|
| `popularity` (0–100) | Numerical | 1.0 | Normalized to 0–1 (like tempo) and scored by **closeness** to the user's target, not "higher is better" — consistent with the system's core idea that a match is *nearness* to preference (some users want hits, others want niche tracks). |
| `release_decade` (1980–2020) | Categorical (ordinal) | 1.0 | **Exact match** = full points; **adjacent decade** (e.g. 2010↔2020) = half. Decades are ordinal, so a neighboring era is a genuine near-miss — the family idea expressed numerically. |
| `mood_tag` (nostalgic/aggressive/euphoric/relaxing) | Categorical | 1.5 | Exact-match bonus via the same generic categorical loop — a finer emotional label than `mood`. |
| `explicit` (yes/no) | Categorical (binary) | 0.5 | Plain **exact-match** bonus; a "family" makes no sense for a boolean. |
| `artist_type` (solo/band) | Categorical (binary) | 0.5 | Plain **exact-match** bonus. |

**How the scoring algorithm changed**

- `load_songs()` now converts `popularity` and `release_decade` to `int`, and
  skips any missing column so older CSVs still load.
- The categorical loop was generalized from a hard-coded genre/mood choice to a
  `FAMILIES_BY_FEATURE` lookup, plus a `_decade_partial()` helper for adjacent-
  decade credit — so all categorical features share one loop.
- The numerical loop gained a `popularity` branch using a new
  `_normalize_popularity()` helper, mirroring the existing tempo normalization.
- New weights were added to `CATEGORICAL_WEIGHTS` / `NUMERICAL_WEIGHTS`; existing
  weights were untouched. The `Song` dataclass gained the five fields with
  defaults so existing tests/callers keep working.

### Manual Verification Notes

**What was checked**

- `python -m pytest tests/` → **2 passed** (existing behavior preserved; new
  `Song` fields have defaults, so the tests that build `Song` without them work).
- `python -m src.main` → loads **36 songs**, no runtime errors across all
  standard and adversarial profiles.
- A targeted check (a profile expressing all five new preferences) confirmed the
  new features enter scoring: for *Night Drive Loop* the score rose **5.80 → 10.00
  (+4.20)**, with visible `mood_tag`, `release_decade`, `explicit`, `artist_type`,
  and `popularity` reasons, and the Top-3 re-ordered toward retro / niche / band
  tracks (*Neon Rain* 10.19 edged out *Night Drive Loop* on closer popularity).

**Corrections/adjustments made after review**

- Added guards in `load_songs()` (`if field in row and row[field] != ""`) so a
  missing new column can't crash loading of an older dataset.
- Chose **closeness** for `popularity` instead of a raw "higher = better" bonus,
  to stay consistent with the README's stated philosophy that nearer-to-target,
  not simply larger, is what wins.

**Confirmation**

The new recommendation logic behaves as expected: the dataset loads correctly,
no runtime errors occur, all five new features participate in scoring, and
recommendation scores/rankings shift appropriately when those attributes are
part of the user profile — while the original features and outputs are preserved.

---

## Design Pattern (SF10)

> Document how AI helped you choose or implement a design pattern.

### Example Prompt(s)

> Review the current implementation of `src/recommender.py` and `src/main.py`,
> then redesign the recommendation system to support multiple scoring modes
> while keeping the code modular and easy to maintain. Before making any code
> changes, analyze the current implementation and recommend a simple design
> pattern that best fits this project (Strategy pattern, a dictionary of scoring
> functions, a function-based dispatcher, or a lightweight class-based
> strategy). Explain why it fits, how it improves readability/extensibility/
> maintainability, and why it beats scattering `if/else` branches through the
> scoring code. Then implement at least two distinct ranking strategies
> (e.g. Genre-First, Mood-First, Energy-Focused) without duplicating scoring
> logic, and let the user pick a mode in `main.py`.

### Chosen Design Pattern

**Pattern: a registry (dictionary) of lightweight `ScoringStrategy` objects — a
data-driven Strategy pattern.**

The decisive observation is that `score_song()` was *already generic*: it does
nothing but loop over two weight dictionaries (`CATEGORICAL_WEIGHTS` and
`NUMERICAL_WEIGHTS`) and apply the same exact/near-match + closeness math to
whatever it finds there. So the *only* difference between "Genre-First" and
"Mood-First" is **the weights**, not the algorithm.

That makes each strategy a pure bundle of weights rather than a new code path:

- `ScoringStrategy` (a frozen dataclass) holds a `name`, a `description`, and
  the two weight dicts.
- `STRATEGIES` is a registry mapping a mode key (`"genre_first"`) to a strategy.
  Each strategy is built as `{**BASE_WEIGHTS, "feature": higher}` so it still
  scores every feature and only *tilts* the ranking toward one priority.
- `score_song(user_prefs, song, strategy=None)` and
  `recommend_songs(..., strategy=None)` resolve the strategy via
  `get_strategy()` and feed its weights into the unchanged loop. `None` falls
  back to `DEFAULT_STRATEGY` (`balanced`), so every existing caller and test
  behaves exactly as before.

**Why this fits / why it beats `if/else`:** the core scoring algorithm is never
touched or duplicated — all modes share one loop, so there is a single source of
truth for the math. Modes become configuration, not code. Adding a fourth or
fifth strategy later means adding one entry to `STRATEGIES`; `main.py` picks it
up automatically because it iterates the registry. Scattering
`if mode == "genre_first"` branches through the scoring loops would instead
duplicate the closeness/family logic per branch, make each mode harder to read,
and force edits to the algorithm every time a mode is added — the opposite of
maintainable.

### AI Contribution

- **Brainstorming designs:** the AI compared the four candidate approaches and
  recommended the data-driven Strategy registry specifically *because* the
  existing `score_song()` was already a generic weight-driven loop — a full
  function-per-strategy or class hierarchy would have re-implemented that loop
  and duplicated logic for no benefit.
- **Implementation ideas:** suggested the frozen `ScoringStrategy` dataclass,
  the `{**BASE, override}` idiom to avoid restating full weight tables, a
  `get_strategy()` resolver that accepts a key / object / `None` and fails
  loudly on typos, and a `DEFAULT_STRATEGY` to preserve backward compatibility.
- **Code organization:** kept `main.py` thin via `resolve_modes()` +
  `run_all_profiles()`, driven entirely by the `STRATEGIES` registry so the CLI
  needs no changes when strategies are added.

### How the pattern appears in the final code

- `ScoringStrategy` dataclass, `STRATEGIES` registry, `DEFAULT_STRATEGY`, and
  `get_strategy()` in `src/recommender.py`.
- `score_song()` / `recommend_songs()` in `src/recommender.py` take a
  `strategy` argument and reuse the same loop for every mode.
- `resolve_modes()` / `run_all_profiles()` in `src/main.py` expose mode
  selection on the command line (`python -m src.main mood_first`, or `all`).

### Manual Verification Notes

**How each scoring mode was tested**

- `python -m pytest tests/` → **2 passed** — the `strategy` argument defaults to
  the balanced profile, so existing behavior is unchanged.
- Ran every mode against all standard + adversarial profiles:
  `python -m src.main`, `genre_first`, `mood_first`, `energy_focused`, and
  `all`. `all` printed **40** profile blocks (10 profiles × 4 modes) with no
  runtime errors; an unknown mode exits cleanly with a helpful message.

**How each strategy changes behavior** (Top 3 for the *High-Energy Pop* profile):

- **Genre-First** — all three picks are `pop` (*Sunrise City*, *Cardio Kings*,
  *Gym Hero*); the strong genre weight clusters the list by genre.
- **Mood-First** — all three share the `happy` mood across *different* genres
  (*Sunrise City* pop, *Rooftop Lights* indie pop, *Sidewalk Groove* funk);
  emotional fit wins over genre.
- **Energy-Focused** — *Cardio Kings* (energetic) rises to #1 ahead of
  *Sunrise City*; ranking follows audio-feature closeness (energy/tempo/
  danceability) rather than categorical labels.

**Corrections/adjustments made after review**

- Threaded `strategy` through *both* the categorical and numerical loops (an
  initial pass updated only the categorical loop) and through `recommend_songs`
  into `score_song`, confirmed via the IDE "unused variable" hints.
- Made `strategy` optional with a `balanced` default so tests and prior callers
  keep working without changes.

**Confirmation**

All modes execute without errors, produce noticeably different rankings, and the
original balanced behavior and outputs are preserved.
