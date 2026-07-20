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
    int_fields = {"id"}
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
                for field in int_fields:
                    row[field] = int(row[field])
                for field in float_fields:
                    row[field] = float(row[field])
                songs.append(row)
    except FileNotFoundError:
        # Fail gracefully instead of crashing if the file path is wrong.
        print(f"Could not find song file: {csv_path}")
        return []

    return songs

# Feature weights from the Algorithm Recipe in README.md.
CATEGORICAL_WEIGHTS = {
    "mood": 3.0,
    "genre": 2.0,
}
NUMERICAL_WEIGHTS = {
    "energy": 2.0,
    "acousticness": 1.5,
    "instrumentalness": 1.5,
    "valence": 1.0,
    "danceability": 1.0,
    "tempo_bpm": 0.5,
}

# Tempo is not on a 0-1 scale, so we normalize it using the catalog's range.
TEMPO_MIN = 60.0
TEMPO_MAX = 160.0


def _normalize_tempo(bpm: float) -> float:
    """Scale a BPM value into the 0-1 range, clamped to [0, 1]."""
    scaled = (bpm - TEMPO_MIN) / (TEMPO_MAX - TEMPO_MIN)
    return max(0.0, min(1.0, scaled))  # keep it inside 0-1 even for outliers


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences using the Algorithm Recipe.

    - Categorical features (genre, mood): full weight on an exact match.
    - Numerical features: weight * (1 - |target - value|), so closer is better.

    Only the features the user actually lists in `user_prefs` are scored, so a
    simple profile like {"genre": ..., "mood": ..., "energy": ...} works fine.

    Returns (score, reasons).
    """
    score = 0.0
    reasons: List[str] = []

    # --- Categorical features: fixed bonus for an exact match ---
    for feature, weight in CATEGORICAL_WEIGHTS.items():
        if feature in user_prefs and user_prefs[feature] == song.get(feature):
            score += weight
            reasons.append(f"{feature.capitalize()} match (+{weight:.1f})")

    # --- Numerical features: reward closeness to the user's target ---
    for feature, weight in NUMERICAL_WEIGHTS.items():
        if feature not in user_prefs:
            continue

        target = user_prefs[feature]
        value = song.get(feature)
        if value is None:
            continue

        # Tempo lives on a different scale, so normalize both sides first.
        if feature == "tempo_bpm":
            target = _normalize_tempo(target)
            value = _normalize_tempo(value)

        similarity = 1.0 - abs(target - value)  # 1.0 = identical, 0.0 = far
        points = weight * similarity
        score += points
        reasons.append(f"{feature.capitalize()} similarity (+{points:.2f})")

    return score, reasons

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """
    Scores every song, ranks them, and returns the Top-K recommendations.

    Uses score_song() as the single source of truth for evaluating each song
    (no scoring logic is duplicated here).

    Returns a list of (song, score, explanation) tuples, ordered from best
    match to worst. `explanation` is the scoring reasons joined into a
    readable string.
    """
    # 1. Score every song, keeping the song, its score, and its reasons together.
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        scored.append((song, score, reasons))

    # 2. Rank highest score first; break ties by id so results are stable.
    scored.sort(key=lambda item: (-item[1], item[0].get("id", 0)))

    # 3. Keep the top k and turn each reasons list into a readable explanation.
    top = scored[:k]
    return [(song, score, ", ".join(reasons)) for song, score, reasons in top]
