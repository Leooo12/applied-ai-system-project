"""
Command line runner + evaluation harness for the Music Recommender Simulation.

Running this file (`python -m src.main`) stress-tests the recommender against a
suite of user preference profiles:

  * Standard profiles  - realistic tastes we expect the system to handle well.
  * Adversarial profiles - edge cases designed to expose weaknesses in the
                           scoring logic (conflicting prefs, extreme values,
                           unsupported genres/moods, out-of-range inputs, ...).

For every profile it prints the Top 5 recommendations with score and reasons.

Choose a scoring mode on the command line (defaults to "balanced"):

    python -m src.main                 # balanced
    python -m src.main mood_first      # emphasize emotional fit
    python -m src.main all             # run every mode back-to-back

Valid modes are whatever is registered in recommender.STRATEGIES, so adding a
new strategy there automatically makes it selectable here -- no edits needed.
"""

import sys
import textwrap

# Prefer the `tabulate` library for a polished table, but fall back to a
# stdlib-only ASCII renderer if it isn't installed -- so the program runs
# everywhere with no required dependency. To get the nicer output, install it:
#     pip install tabulate
try:
    from tabulate import tabulate as _tabulate
except ModuleNotFoundError:
    _tabulate = None

try:
    # Works when run from the project root: python -m src.main
    from src.recommender import load_songs, recommend_songs, STRATEGIES
    from src.app_logging import configure_logging, get_logger, log_event
except ModuleNotFoundError:
    # Works when run from inside the src/ folder: python main.py
    from recommender import load_songs, recommend_songs, STRATEGIES
    from app_logging import configure_logging, get_logger, log_event


# ---------------------------------------------------------------------------
# 1. Standard user profiles - realistic tastes with a value for every feature.
# ---------------------------------------------------------------------------
STANDARD_PROFILES = {
    "High-Energy Pop": {
        "genre": "pop", "mood": "happy",
        "energy": 0.90, "tempo_bpm": 125, "valence": 0.85,
        "danceability": 0.85, "acousticness": 0.10, "instrumentalness": 0.05,
    },
    "Chill Lo-Fi": {
        "genre": "lofi", "mood": "chill",
        "energy": 0.35, "tempo_bpm": 75, "valence": 0.55,
        "danceability": 0.55, "acousticness": 0.85, "instrumentalness": 0.85,
    },
    "Deep Intense Rock": {
        "genre": "rock", "mood": "intense",
        "energy": 0.95, "tempo_bpm": 150, "valence": 0.40,
        "danceability": 0.60, "acousticness": 0.08, "instrumentalness": 0.10,
    },
}


# ---------------------------------------------------------------------------
# 2. Adversarial / edge-case profiles - each paired with what it probes.
# ---------------------------------------------------------------------------
ADVERSARIAL_PROFILES = {
    # Conflicting signals: wants maximum energy but a sad, low-valence vibe.
    "Conflicting (High Energy + Sad)": {
        "genre": "pop", "mood": "sad",
        "energy": 0.98, "tempo_bpm": 150, "valence": 0.05,
        "danceability": 0.90, "acousticness": 0.10, "instrumentalness": 0.05,
    },
    # Everything pinned to the maximum - tests whether the max song dominates.
    "All-Maximum Values": {
        "genre": "metal", "mood": "intense",
        "energy": 1.0, "tempo_bpm": 160, "valence": 1.0,
        "danceability": 1.0, "acousticness": 1.0, "instrumentalness": 1.0,
    },
    # Everything pinned to the minimum.
    "All-Minimum Values": {
        "genre": "classical", "mood": "melancholy",
        "energy": 0.0, "tempo_bpm": 60, "valence": 0.0,
        "danceability": 0.0, "acousticness": 0.0, "instrumentalness": 0.0,
    },
    # Perfectly neutral - every numeric target at 0.5, no categorical prefs.
    "Uniform / Indifferent (all 0.5)": {
        "energy": 0.5, "tempo_bpm": 110, "valence": 0.5,
        "danceability": 0.5, "acousticness": 0.5, "instrumentalness": 0.5,
    },
    # Genre and mood that do not exist in the catalog.
    "Unsupported Genre + Mood": {
        "genre": "k-pop", "mood": "nostalgic",
        "energy": 0.60, "tempo_bpm": 105, "valence": 0.60,
        "danceability": 0.70, "acousticness": 0.30, "instrumentalness": 0.10,
    },
    # Out-of-range targets (>1). Exposes the negative-score bug in closeness.
    "Out-of-Range Targets (energy=2.0)": {
        "genre": "rock", "mood": "intense",
        "energy": 2.0, "tempo_bpm": 300, "valence": 2.0,
        "danceability": 2.0, "acousticness": 2.0, "instrumentalness": 2.0,
    },
    # Extremely narrow: only a single, rare categorical preference.
    "Extremely Narrow (mood only)": {
        "mood": "romantic",
    },
}


# Column headers and the width (in characters) the Reasons text wraps at, so
# long explanations stay inside a readable column instead of running off-screen.
TABLE_HEADERS = ["#", "Title", "Artist", "Score", "Reasons"]
REASONS_WRAP_WIDTH = 34


def _format_reasons(explanation: str) -> str:
    """
    Turn the comma-joined reasons string into wrapped, bulleted lines that fit
    the Reasons column. Returns a placeholder when a song matched nothing.
    """
    reasons = [r for r in explanation.split(", ") if r] if explanation else []
    if not reasons:
        return "No strong matches"
    # One bullet per reason, each wrapped so long reasons don't overflow.
    lines = []
    for reason in reasons:
        wrapped = textwrap.wrap(reason, width=REASONS_WRAP_WIDTH - 2) or [""]
        lines.append("- " + wrapped[0])
        lines.extend("  " + cont for cont in wrapped[1:])
    return "\n".join(lines)


def _build_rows(recommendations):
    """Build the [rank, title, artist, score, reasons] rows for the table."""
    rows = []
    for position, (song, score, explanation) in enumerate(recommendations, start=1):
        rows.append([
            position,
            song["title"],
            song["artist"],
            f"{score:.2f}",              # round score to 2 decimals
            _format_reasons(explanation),
        ])
    return rows


def _render_ascii_table(headers, rows) -> str:
    """
    Stdlib fallback: render a neatly aligned ASCII table that supports
    multi-line cells (used for the wrapped Reasons column). Used when the
    `tabulate` library isn't installed.
    """
    # Split every cell into its lines so multi-line Reasons align row-by-row.
    grid = [[str(cell).split("\n") for cell in row] for row in rows]

    # Column width = widest line across the header and every row in that column.
    widths = []
    for col in range(len(headers)):
        cell_lines = [line for row in grid for line in row[col]]
        widths.append(max([len(headers[col])] + [len(l) for l in cell_lines]))

    def fmt_line(cells):
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    out = [sep, fmt_line(headers), sep]
    for row in grid:
        height = max(len(cell) for cell in row)  # tallest cell drives row height
        for line_no in range(height):
            cells = [cell[line_no] if line_no < len(cell) else "" for cell in row]
            out.append(fmt_line(cells))
        out.append(sep)
    return "\n".join(out)


def print_recommendations(title: str, recommendations) -> None:
    """Pretty-print one profile's Top-K recommendations as a table."""
    line = "=" * 60
    print()
    print(line)
    print(f"PROFILE: {title}".center(60))
    print(line)

    if not recommendations:
        print("  (no recommendations)")
        return

    rows = _build_rows(recommendations)
    if _tabulate is not None:
        # `grid` format draws borders and honors the newlines in wrapped cells.
        print(_tabulate(rows, headers=TABLE_HEADERS, tablefmt="grid"))
    else:
        print(_render_ascii_table(TABLE_HEADERS, rows))


def run_all_profiles(songs, mode: str) -> None:
    """Run every standard + adversarial profile under a single scoring mode."""
    strategy = STRATEGIES[mode]
    banner = f"SCORING MODE: {strategy.name} -- {strategy.description}"
    print("\n" + "@" * 60)
    print(banner)
    print("@" * 60)

    print("\n" + "#" * 60)
    print("#  STANDARD PROFILES".ljust(59) + "#")
    print("#" * 60)
    for name, prefs in STANDARD_PROFILES.items():
        print_recommendations(name, recommend_songs(prefs, songs, k=5, strategy=mode))

    print("\n" + "#" * 60)
    print("#  ADVERSARIAL / EDGE-CASE PROFILES".ljust(59) + "#")
    print("#" * 60)
    for name, prefs in ADVERSARIAL_PROFILES.items():
        print_recommendations(name, recommend_songs(prefs, songs, k=5, strategy=mode))


def resolve_modes(argv) -> list:
    """
    Turn the command-line argument into the list of modes to run.

    No argument -> ["balanced"]; "all" -> every registered mode; otherwise the
    single requested mode (validated against the STRATEGIES registry).
    """
    requested = argv[1] if len(argv) > 1 else "balanced"
    if requested == "all":
        return list(STRATEGIES)
    if requested not in STRATEGIES:
        valid = ", ".join(list(STRATEGIES) + ["all"])
        print(f"Unknown mode {requested!r}. Choose one of: {valid}")
        sys.exit(1)
    return [requested]


# ---------------------------------------------------------------------------
# Interactive natural-language mode (python -m src.main --interactive)
# ---------------------------------------------------------------------------
QUIT_WORDS = {"quit", "exit", "q"}


def _make_recommend_fn(strategy):
    """Bind a scoring strategy into the recommender call the orchestrator makes."""
    from src.recommender import recommend_songs

    def _fn(prefs, songs, k=5):
        return recommend_songs(prefs, songs, k=k, strategy=strategy)

    return _fn


def _display_context(ctx, out) -> None:
    """Pretty-print one RecommendationContext to the user."""
    # Blocked requests: show the friendly guardrail messages and stop.
    if not ctx.allowed:
        out("\nI couldn't process that request:")
        for message in ctx.errors:
            out(f"  - {message}")
        return

    out("\n" + "-" * 60)
    out("Interpreted preferences:")
    if ctx.parsed_preferences:
        for key, value in ctx.parsed_preferences.items():
            out(f"  {key}: {value}")
    else:
        out("  (none specified)")

    out(f"\nConfidence: {ctx.confidence:.2f}")

    explanation = ctx.explanation or {}
    out("\nSummary:")
    out(f"  {explanation.get('summary', '(no summary)')}")

    out("\nRecommended songs:")
    ai_by_title = {
        e.get("title"): e.get("explanation")
        for e in explanation.get("song_explanations", [])
    }
    for i, rec in enumerate(ctx.recommendations, start=1):
        out(f"  {i}. {rec['title']} - {rec['artist']}  (score {rec['score']:.2f})")
        out(f"       reasons: {rec['reasons']}")
        note = ai_by_title.get(rec["title"])
        if note:
            out(f"       why it fits: {note}")

    if not ctx.recommendations:
        out("  (no songs matched closely enough)")

    # How the explanation was produced.
    method_label = {
        "generated": "AI explanation (verified against the retrieved songs)",
        "repaired": "AI explanation (repaired once, then verified)",
        "fallback": "Deterministic fallback (AI answer could not be verified)",
    }.get(ctx.explanation_method, "unknown")
    out(f"\nExplanation source: {method_label}")

    warnings = explanation.get("warnings") or ctx.warnings
    if warnings:
        out("\nWarnings:")
        for warning in warnings:
            out(f"  - {warning}")
    out("-" * 60)


def run_interactive(ai_client=None, input_fn=input, output_fn=print) -> None:
    """
    Run the interactive natural-language recommender loop.

    `ai_client`, `input_fn`, and `output_fn` are injectable so this can be driven
    by tests without a real network, keyboard, or terminal.
    """
    # Imported lazily so the classic evaluation harness (python main.py) doesn't
    # require the full AI stack.
    from src.ai_client import AIClientError, AnthropicAIClient, MissingAPIKeyError
    from src.orchestrator import VibeMatchOrchestrator, CatalogNotFoundError
    from src.preference_parser import PreferenceParseError
    from src.recommender import STRATEGIES

    # Build the production AI client unless one was injected (tests inject a fake).
    if ai_client is None:
        try:
            ai_client = AnthropicAIClient()
        except MissingAPIKeyError:
            output_fn(
                "\nVibeMatch needs an Anthropic API key to run in interactive mode.\n"
                "Set it up like this:\n"
                "  1. Copy the template:   cp .env.example .env\n"
                "  2. Put your real key in .env under ANTHROPIC_API_KEY\n"
                "  3. Load it into your shell:  export ANTHROPIC_API_KEY=...\n"
                "Then run:  python -m src.main --interactive\n"
            )
            return

    output_fn("VibeMatch AI - describe the music you want.")
    output_fn(f"Scoring strategies: {', '.join(STRATEGIES)} (default: balanced).")
    output_fn("Type 'quit' at any prompt to exit.\n")

    while True:
        try:
            request = input_fn("Your music request: ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn("\nGoodbye!")
            return

        if request.lower() in QUIT_WORDS:
            output_fn("Goodbye!")
            return
        if not request:
            continue

        try:
            strategy = input_fn("Scoring strategy [balanced]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            output_fn("\nGoodbye!")
            return
        if strategy in QUIT_WORDS:
            output_fn("Goodbye!")
            return
        if not strategy:
            strategy = "balanced"
        if strategy not in STRATEGIES:
            output_fn(f"Unknown strategy {strategy!r}; using 'balanced'.")
            strategy = "balanced"

        orchestrator = VibeMatchOrchestrator(
            ai_client,
            recommend_fn=_make_recommend_fn(strategy),
            strategy=strategy,
        )

        # Turn expected failures into friendly messages -- never raw tracebacks.
        try:
            ctx = orchestrator.recommend_and_explain(request)
        except CatalogNotFoundError:
            output_fn("Setup problem: the song catalog (data/songs.csv) is missing.\n")
            continue
        except PreferenceParseError:
            output_fn("I couldn't understand that request. Please try rephrasing it.\n")
            continue
        except AIClientError as exc:
            output_fn(f"The AI service is unavailable right now ({exc}). Please try again.\n")
            continue

        _display_context(ctx, output_fn)
        output_fn("")


def _wants_interactive(argv) -> bool:
    return any(arg in ("--interactive", "-i") for arg in argv[1:])


def main() -> None:
    # Set up structured logging. The level is user-controllable via the
    # VIBEMATCH_LOG_LEVEL environment variable (defaults to INFO).
    configure_logging()
    logger = get_logger("vibematch.main")

    # Interactive natural-language mode.
    if _wants_interactive(sys.argv):
        log_event(logger, "interactive_session_started")
        run_interactive()
        return

    # Classic evaluation harness (preserved unchanged).
    songs = load_songs("data/songs.csv")
    print(f"Loaded songs: {len(songs)}")
    log_event(logger, "songs_loaded", song_count=len(songs))

    modes = resolve_modes(sys.argv)
    for mode in modes:
        log_event(logger, "evaluation_started", strategy=mode)
        run_all_profiles(songs, mode)
    log_event(logger, "evaluation_completed", strategies_run=len(modes))


if __name__ == "__main__":
    main()
