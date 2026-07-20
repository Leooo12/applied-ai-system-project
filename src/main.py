"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

try:
    # Works when run from the project root: python -m src.main
    from src.recommender import load_songs, recommend_songs
except ModuleNotFoundError:
    # Works when run from inside the src/ folder: python main.py
    from recommender import load_songs, recommend_songs


def main() -> None:
    songs = load_songs("data/songs.csv")
    print(f"Loaded songs: {len(songs)}")

    # Starter example profile
    user_prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}

    k = 5
    recommendations = recommend_songs(user_prefs, songs, k=k)

    # --- Header ---
    line = "=" * 50
    print()
    print(line)
    print(f"Top {len(recommendations)} Recommended Songs".center(50))
    print(line)
    print()

    # --- One block per recommended song ---
    for position, (song, score, explanation) in enumerate(recommendations, start=1):
        print(f"{position}. {song['title']} - {song['artist']}")
        print(f"   Score: {score:.2f}")
        print("   Reasons:")

        # The explanation is reasons joined by ", "; split it back into a list.
        reasons = explanation.split(", ") if explanation else []
        if reasons:
            for reason in reasons:
                print(f"   - {reason}")
        else:
            print("   - No strong matches for this profile")

        # Separator between songs (a blank line is enough after the last one).
        print()
        if position < len(recommendations):
            print("-" * 50)
            print()


if __name__ == "__main__":
    main()
