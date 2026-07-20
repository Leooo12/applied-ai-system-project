import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    instrumentalness: float = 0.0
    # --- New attributes (all optional so existing callers/tests still work) ---
    popularity: int = 50          # 0-100 mainstream reach
    release_decade: int = 2010    # e.g. 1980, 1990, 2000, 2010, 2020
    mood_tag: str = ""            # detailed mood: nostalgic/aggressive/euphoric/relaxing
    explicit: str = "no"          # "yes" / "no"
    artist_type: str = "band"     # "solo" / "band"

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        """Initialize the recommender with a catalog of songs."""
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return the top-k recommended songs for a user."""
        # TODO: Implement recommendation logic
        return self.songs[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return a human-readable reason why a song was recommended."""
        # TODO: Implement explanation logic
        return "Explanation placeholder"

def load_songs(csv_path: str) -> List[Dict]:
    """
    Loads songs from a CSV file into a list of dictionaries.

    Numeric columns are converted to int/float so they can be used
    directly in math later; all other columns stay as strings.
    Required by src/main.py
    """
    # Columns that must be numbers (everything else stays a string).
    # popularity and release_decade are whole numbers; the rest are 0-1 floats.
    int_fields = {"id", "popularity", "release_decade"}
    float_fields = {
        "energy", "tempo_bpm", "valence",
        "danceability", "acousticness", "instrumentalness",
    }

    songs: List[Dict] = []

    try:
        # newline="" is the recommended way to open files for the csv module.
        with open(csv_path, newline="", encoding="utf-8") as f:
            # DictReader uses the header row as keys for each song dict.
            reader = csv.DictReader(f)
            for row in reader:
                # Convert each numeric field from string to its proper type.
                # Skip any field a given CSV happens not to have so older
                # datasets (without the new columns) still load cleanly.
                for field in int_fields:
                    if field in row and row[field] != "":
                        row[field] = int(row[field])
                for field in float_fields:
                    if field in row and row[field] != "":
                        row[field] = float(row[field])
                songs.append(row)
    except FileNotFoundError:
        # Fail gracefully instead of crashing if the file path is wrong.
        print(f"Could not find song file: {csv_path}")
        return []

    return songs

# Feature weights from the Algorithm Recipe in README.md.
#
# Improvement #1 (rebalanced weights): mood was previously 3.0 -- the single
# largest weight in the system -- which let one exact mood-string match outrank
# a song that fit far better on energy + valence + danceability combined. Mood
# now sits at parity with genre and energy (2.0) so no single categorical
# feature dominates the ranking.
#
# --- New features (see NEW-FEATURE notes below) ---
# * mood_tag  : a finer-grained emotional label than `mood`. Categorical, so it
#               fits the same exact/same-family bonus the other categoricals use.
# * explicit  : a yes/no flag. Binary, so a plain exact-match bonus is the
#               natural fit (a "family" concept makes no sense for a boolean).
# * artist_type: solo vs band. Also binary categorical -> exact-match bonus.
CATEGORICAL_WEIGHTS = {
    "mood": 2.0,
    "genre": 2.0,
    "mood_tag": 1.5,        # NEW-FEATURE: detailed mood tag
    "release_decade": 1.0,  # NEW-FEATURE: era; exact + adjacent-decade partial
    "explicit": 0.5,        # NEW-FEATURE: yes/no flag
    "artist_type": 0.5,     # NEW-FEATURE: solo/band
}
NUMERICAL_WEIGHTS = {
    "energy": 2.0,
    "acousticness": 1.5,
    "instrumentalness": 1.5,
    "valence": 1.0,
    "danceability": 1.0,
    "popularity": 1.0,      # NEW-FEATURE: 0-100 mainstream reach (closeness-scored)
    "tempo_bpm": 0.5,
}

# --- Scoring strategies (Strategy pattern, data-driven) ---------------------
#
# score_song() is already a *generic* loop over two weight dictionaries, so the
# only thing that distinguishes one ranking philosophy from another is the
# weights themselves -- not the algorithm. A "strategy" is therefore just a
# named bundle of weights, and every mode reuses the exact same scoring loop.
#
# This is preferable to sprinkling `if mode == ...` branches through the scoring
# code: the core algorithm stays untouched, each mode is pure configuration, and
# adding a new mode later means adding ONE entry to the STRATEGIES registry
# below -- no edits to score_song()/recommend_songs() at all.


@dataclass(frozen=True)
class ScoringStrategy:
    """
    A named ranking philosophy: a bundle of categorical + numerical weights
    plugged into the shared score_song() loop. No scoring logic lives here --
    only the emphasis (which features matter most) differs between strategies.
    """
    name: str
    description: str
    categorical_weights: Dict[str, float]
    numerical_weights: Dict[str, float]


# Each strategy starts from the balanced base weights above and overrides only
# the features it wants to emphasize (via {**BASE, "feature": higher}). Sharing
# the base means every mode still scores every feature -- it just tilts the
# ranking toward a different priority.
STRATEGIES: Dict[str, ScoringStrategy] = {
    "balanced": ScoringStrategy(
        name="Balanced",
        description="Default weighting -- no single feature dominates.",
        categorical_weights=CATEGORICAL_WEIGHTS,
        numerical_weights=NUMERICAL_WEIGHTS,
    ),
    "genre_first": ScoringStrategy(
        name="Genre-First",
        description="Strongly prioritizes matching the user's favorite genre.",
        categorical_weights={**CATEGORICAL_WEIGHTS, "genre": 5.0, "mood": 1.0},
        numerical_weights=NUMERICAL_WEIGHTS,
    ),
    "mood_first": ScoringStrategy(
        name="Mood-First",
        description="Prioritizes emotional fit (mood + detailed mood_tag).",
        categorical_weights={
            **CATEGORICAL_WEIGHTS, "mood": 5.0, "mood_tag": 3.0, "genre": 1.0,
        },
        numerical_weights={**NUMERICAL_WEIGHTS, "valence": 2.5},
    ),
    "energy_focused": ScoringStrategy(
        name="Energy-Focused",
        description="Ranks by how closely a song's energy/tempo/danceability "
                    "match the target, downplaying categorical labels.",
        categorical_weights={**CATEGORICAL_WEIGHTS, "genre": 1.0, "mood": 1.0},
        numerical_weights={
            **NUMERICAL_WEIGHTS,
            "energy": 5.0, "tempo_bpm": 2.5, "danceability": 2.5,
        },
    ),
}

# The strategy used when a caller does not specify one, so existing callers and
# tests keep their original behavior unchanged.
DEFAULT_STRATEGY = STRATEGIES["balanced"]


def get_strategy(mode) -> ScoringStrategy:
    """
    Resolve a strategy from a mode key, a ScoringStrategy, or None.

    Accepts a registry key ("genre_first"), an already-built ScoringStrategy,
    or None (-> DEFAULT_STRATEGY). Raises a clear error for unknown keys so a
    typo fails loudly instead of silently falling back.
    """
    if mode is None:
        return DEFAULT_STRATEGY
    if isinstance(mode, ScoringStrategy):
        return mode
    try:
        return STRATEGIES[mode]
    except KeyError:
        valid = ", ".join(STRATEGIES)
        raise ValueError(f"Unknown scoring mode {mode!r}. Choose one of: {valid}")

# Tempo is not on a 0-1 scale, so we normalize it using the catalog's range.
TEMPO_MIN = 60.0
TEMPO_MAX = 160.0

# Popularity is a 0-100 value; normalize it into 0-1 like tempo so it plugs
# straight into the existing closeness formula.
# NEW-FEATURE (popularity): scored by *closeness* to the user's target rather
# than "higher is better", to stay consistent with the system's core idea that
# a good match is one near the user's preference -- some users want mainstream
# hits, others deliberately want niche tracks.
POPULARITY_MIN = 0.0
POPULARITY_MAX = 100.0

# --- Improvement #3 (softer numerical similarity) ---
# A value > 1 makes near-misses fall off faster than a straight line, but it
# also shrinks every numerical contribution, which *strengthens* the dominance
# of the flat categorical bonuses and pushes the ranking toward exact-match
# filter bubbles. Lowering it back to 1.0 (linear) keeps audio-feature
# closeness meaningful, so sonically-similar songs can still compete with
# same-mood/same-genre songs. Raise it above 1.0 to sharpen the falloff again.
SIMILARITY_SHARPNESS = 1.0

# --- Improvement #2 (soft categorical matching) ---
# Exact string equality treats "happy" vs "energetic" or "pop" vs "indie pop"
# as completely unrelated (score 0), even though they are near-identical. We
# group genres and moods into coarse families and award partial credit when the
# user's preference and a song share a family but not the exact label. Anything
# not listed simply has no family and only ever earns points on an exact match.
PARTIAL_MATCH_FRACTION = 0.5  # fraction of full weight for a same-family match

GENRE_FAMILIES = {
    "pop": "pop", "indie pop": "pop",
    "electronic": "electronic", "synthwave": "electronic",
    "lofi": "chill", "ambient": "chill",
    "rock": "rock", "metal": "rock",
    "hip-hop": "urban", "r&b": "urban", "funk": "urban",
    "jazz": "acoustic", "folk": "acoustic", "classical": "acoustic",
}

MOOD_FAMILIES = {
    "happy": "positive", "energetic": "positive", "confident": "positive",
    "chill": "calm", "relaxed": "calm", "focused": "calm",
    "sad": "melancholic", "melancholy": "melancholic", "moody": "melancholic",
    "intense": "intense",
    "romantic": "romantic",
}

# Which family map (if any) each categorical feature uses. Features not listed
# here -- explicit, artist_type -- have no family, so they only ever earn points
# on an exact match. This mapping lets score_song() stay a single generic loop
# instead of hard-coding one family map per feature.
FAMILIES_BY_FEATURE = {
    "genre": GENRE_FAMILIES,
    "mood": MOOD_FAMILIES,
}

# --- Improvement #5 (diversity-aware re-ranking) ---
# After scoring, greedily build the Top-K but penalize each candidate for every
# already-selected song that repeats one of its attributes. This breaks up
# "all songs by one artist" / "all one genre" filter bubbles WITHOUT changing
# any song's raw score -- the penalty only affects *selection order*.
#
# The penalty is applied per attribute so different repeats can be discouraged
# to different degrees. Artist is the primary target (a strong penalty), because
# a Top-K dominated by one artist is the least useful; genre repetition gets a
# smaller penalty so the list still spans styles without over-scattering.
#
# It stays MODERATE on purpose: a candidate only loses `penalty * (# earlier
# picks sharing that attribute)`, so a song whose raw score is clearly higher
# still wins even if its artist/genre already appeared. Add or remove a key to
# change which repeats are discouraged; set a value to 0 (or empty the dict) to
# disable that penalty.
DIVERSITY_PENALTIES = {
    "artist": 1.0,   # primary: strongly discourage repeating the same artist
    "genre": 0.4,    # secondary: mildly discourage repeating the same genre
}


def _normalize_tempo(bpm: float) -> float:
    """Scale a BPM value into the 0-1 range, clamped to [0, 1]."""
    scaled = (bpm - TEMPO_MIN) / (TEMPO_MAX - TEMPO_MIN)
    return max(0.0, min(1.0, scaled))  # keep it inside 0-1 even for outliers


def _normalize_popularity(pop: float) -> float:
    """Scale a 0-100 popularity value into the 0-1 range, clamped to [0, 1]."""
    scaled = (pop - POPULARITY_MIN) / (POPULARITY_MAX - POPULARITY_MIN)
    return max(0.0, min(1.0, scaled))


def _decade_partial(user_decade, song_decade) -> bool:
    """
    True when two decades are adjacent (e.g. 2010 vs 2020) but not equal.

    NEW-FEATURE (release_decade): decades are *ordinal*, not just labels, so an
    adjacent decade is a near-miss deserving partial credit -- the same idea as
    the genre/mood families, expressed numerically instead of via a lookup.
    """
    try:
        return abs(int(user_decade) - int(song_decade)) == 10
    except (TypeError, ValueError):
        return False


def score_song(
    user_prefs: Dict, song: Dict, strategy=None
) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences using the Algorithm Recipe.

    - Categorical features (genre, mood): full weight on an exact match.
    - Numerical features: weight * (1 - |target - value|), so closer is better.

    Only the features the user actually lists in `user_prefs` are scored, so a
    simple profile like {"genre": ..., "mood": ..., "energy": ...} works fine.

    `strategy` selects which weight profile to use (a registry key, a
    ScoringStrategy, or None for the balanced default). The algorithm is
    identical across strategies -- only the weights change.

    Returns (score, reasons).
    """
    strategy = get_strategy(strategy)
    categorical_weights = strategy.categorical_weights
    numerical_weights = strategy.numerical_weights

    score = 0.0
    reasons: List[str] = []

    # --- Categorical features: full bonus for an exact match, partial for a
    #     same-family near-match (improvement #2) ---
    for feature, weight in categorical_weights.items():
        if feature not in user_prefs:
            continue

        user_value = user_prefs[feature]
        song_value = song.get(feature)
        families = FAMILIES_BY_FEATURE.get(feature, {})

        # A "near match" is either a same-family label (genre/mood) or, for
        # release_decade, an adjacent decade. Features with neither (explicit,
        # artist_type) can only ever score on an exact match.
        same_family = (
            families.get(user_value) is not None
            and families.get(user_value) == families.get(song_value)
        )
        near_match = same_family or (
            feature == "release_decade" and _decade_partial(user_value, song_value)
        )

        if user_value == song_value:
            score += weight
            reasons.append(f"{feature.capitalize()} match (+{weight:.1f})")
        elif near_match:
            # Near-match (e.g. pop/indie pop, happy/energetic, 2010/2020):
            # partial credit.
            points = weight * PARTIAL_MATCH_FRACTION
            score += points
            reasons.append(f"{feature.capitalize()} related (+{points:.1f})")

    # --- Numerical features: reward closeness to the user's target ---
    for feature, weight in numerical_weights.items():
        if feature not in user_prefs:
            continue

        target = user_prefs[feature]
        value = song.get(feature)
        if value is None:
            continue

        # Tempo and popularity live on different scales, so normalize both
        # sides into 0-1 before measuring closeness.
        if feature == "tempo_bpm":
            target = _normalize_tempo(target)
            value = _normalize_tempo(value)
        elif feature == "popularity":
            target = _normalize_popularity(target)
            value = _normalize_popularity(value)

        # Clamp closeness to [0, 1] so a far (or out-of-range) value scores 0
        # rather than going negative, then sharpen it so near-misses fall off
        # faster (see SIMILARITY_SHARPNESS).
        closeness = max(0.0, 1.0 - abs(target - value))  # 1.0 = identical, 0.0 = far
        similarity = closeness ** SIMILARITY_SHARPNESS
        points = weight * similarity
        score += points
        reasons.append(f"{feature.capitalize()} similarity (+{points:.2f})")

    return score, reasons

def recommend_songs(
    user_prefs: Dict,
    songs: List[Dict],
    k: int = 5,
    diversity: bool = True,
    strategy=None,
) -> List[Tuple[Dict, float, str]]:
    """
    Scores every song, ranks them, and returns the Top-K recommendations.

    Uses score_song() as the single source of truth for evaluating each song
    (no scoring logic is duplicated here). `strategy` (a registry key, a
    ScoringStrategy, or None for the balanced default) selects which weight
    profile score_song() applies -- the ranking algorithm is unchanged.

    When `diversity` is True (improvement #5), the Top-K is built with a
    diversity-aware greedy pass that penalizes candidates sharing a genre or
    mood with songs already picked, so the list spans more styles instead of
    collapsing onto one cluster. The penalty only affects *selection order* --
    each song's reported score is still its raw score. Pass diversity=False to
    recover a plain highest-score-first ranking.

    Returns a list of (song, score, explanation) tuples, ordered from best
    match to worst. `explanation` is the scoring reasons joined into a
    readable string.
    """
    # 1. Score every song, keeping the song, its score, and its reasons together.
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song, strategy=strategy)
        scored.append((song, score, reasons))

    # 2. Rank highest score first; break ties by id so results are stable.
    scored.sort(key=lambda item: (-item[1], item[0].get("id", 0)))

    if not diversity or not any(p > 0 for p in DIVERSITY_PENALTIES.values()):
        top = scored[:k]
    else:
        top = _select_diverse(scored, k)

    # 3. Turn each reasons list into a readable explanation.
    return [(song, score, ", ".join(reasons)) for song, score, reasons in top]


def _select_diverse(
    scored: List[Tuple[Dict, float, List[str]]], k: int
) -> List[Tuple[Dict, float, List[str]]]:
    """
    Greedily pick k songs, each time choosing the candidate with the best
    *diversity-adjusted* score: the raw score minus, for each attribute in
    DIVERSITY_PENALTIES, that attribute's penalty times how many already-selected
    songs share its value. Artist repeats are penalized most, genre repeats less.
    `scored` must already be sorted best-first so ties fall back to the original
    (score, id) order. Only selection order is affected -- raw scores are kept.
    """
    remaining = list(scored)
    selected: List[Tuple[Dict, float, List[str]]] = []

    # counts[feature][value] = how many already-selected songs have that value.
    counts: Dict[str, Dict[str, int]] = {feature: {} for feature in DIVERSITY_PENALTIES}

    while remaining and len(selected) < k:
        best_index = 0
        best_adjusted = None
        for index, (song, score, _reasons) in enumerate(remaining):
            # Sum the penalty across every tracked attribute this candidate
            # repeats among the already-selected songs.
            penalty = sum(
                weight * counts[feature].get(song.get(feature), 0)
                for feature, weight in DIVERSITY_PENALTIES.items()
            )
            adjusted = score - penalty
            # Strictly-greater keeps the earlier (higher raw score) song on ties.
            if best_adjusted is None or adjusted > best_adjusted:
                best_adjusted = adjusted
                best_index = index

        song, score, reasons = remaining.pop(best_index)
        selected.append((song, score, reasons))
        # Record this pick's attribute values so later candidates get penalized.
        for feature in DIVERSITY_PENALTIES:
            value = song.get(feature)
            counts[feature][value] = counts[feature].get(value, 0) + 1

    return selected
