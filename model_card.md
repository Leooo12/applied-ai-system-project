# 🎧 Model Card: VibeMatch AI

## System Name

**VibeMatch AI**, built on top of the original **VibeMatch 1.0** deterministic
scoring engine (Module 3, the *Music Recommender Simulation*). "VibeMatch"
because it matches songs to the "vibe" a listener describes — style, mood, and
energy — and "AI" marks the addition of natural-language understanding and
AI-generated explanations on top of the unchanged scoring core.

---

## Intended Use

**Goal / task.** A listener describes the music they want in plain English
(e.g. *"calm instrumental music for late-night coding"*). VibeMatch AI
interprets that request, retrieves the five best-matching songs from its
library using a transparent scoring formula, and returns an AI-written
explanation of *why* each pick was chosen — checked against the retrieved data
before it's shown to anyone.

**What it's designed for.**
- Learning how a natural-language front end can sit on top of a deterministic
  recommender without weakening its guarantees.
- Classroom exploration and experimentation, not production use with real
  users.
- Demonstrating retrieval-augmented generation, guardrails, and automated
  verification in a small, fully inspectable system.

## Inappropriate Uses

- A real, user-facing music app or anything people depend on for a live
  service.
- Judging songs, artists, or genres as objectively "good" or "bad."
- Any decision about a real person — the system only compares song attributes
  to a stated preference; it has no concept of a person.
- Any task outside music recommendation. The system's guardrails explicitly
  refuse off-topic requests (see Misuse Prevention and Guardrails below).

**Assumptions the system makes:** the listener can describe a style, mood,
energy level, or activity in a sentence; those traits are enough to describe
taste for the purposes of this demo; every song is fairly described by the
attributes in `data/songs.csv`.

---

## How the System Works

Think of it as two layers working together, not one AI system:

1. **Understand.** An AI model reads the free-text request and converts it
   into structured preferences (genre, mood, energy, tempo, etc.) — nothing
   more. It never sees the song catalog and never picks songs.
2. **Retrieve and rank.** The structured preferences are scored against every
   song in `data/songs.csv` using the original weighted scoring formula: a
   fixed bonus for a categorical match (genre, mood) or a same-family near
   match, and `weight × (1 − |target − value|)` for numerical closeness on
   audio features. The five highest-scoring songs win, after a diversity pass
   that discourages one artist or genre from dominating the list.
3. **Explain.** An AI model writes a short explanation of *only* the five
   retrieved songs, using their real attributes, scores, and reasons as its
   only evidence.
4. **Verify.** Before anything is shown to the user, an independent checker
   confirms every song title, artist, and attribute claim in the explanation
   matches the retrieved data. A failed check triggers exactly one AI repair
   attempt; if that also fails, the system falls back to an explanation built
   directly from the scores and reasons, with no further AI involvement.

The scoring formula itself, including its four selectable strategies
(Balanced, Genre-First, Mood-First, Energy-Focused) and its diversity-aware
ranking pass, is unchanged from the original Module 3 project.

---

## Data Source

The library is a small, made-up list of songs in `data/songs.csv`. Nothing
here is real streaming data.

- **Size:** 36 songs.
- **Features per song:** title and artist (shown, not scored), plus genre,
  mood, energy, valence, danceability, acousticness, instrumentalness, tempo,
  popularity, release decade, a finer mood tag, explicit flag, and solo/band
  artist type.
- **Styles:** 14 genres (pop, indie pop, lofi, ambient, rock, metal, hip-hop,
  r&b, funk, jazz, folk, classical, electronic, synthwave).
- **Moods:** 11 moods (happy, relaxed, chill, moody, intense, confident,
  focused, romantic, melancholy, energetic, sad).
- **What's missing:** the dataset is small and uneven — some styles have four
  songs, others just two, and "sad" has only one. It has no lyrics, no
  language, and no real-world listening data. Whole parts of real musical
  taste simply aren't represented.

## AI Components

These are the parts of the system that call a language model:

- **`src/preference_parser.py`** — converts the natural-language request into
  structured preferences (JSON). This is the *only* place the system asks the
  AI to understand language.
- **`src/explanation_generator.py`** — writes a short explanation of the
  retrieved songs, grounded strictly in the evidence it's given.
- **The repair attempt** inside `src/orchestrator.py` — a second, corrective
  call to the same explanation generator, given the specific reasons the first
  explanation failed verification.

The AI never ranks, scores, or selects songs. Its role is limited to language
understanding and narration of results a deterministic process already
produced.

## Deterministic Components

These parts of the system contain no AI call and produce the same output
every time given the same input:

- **`src/recommender.py`** — the original scoring and ranking engine; the sole
  authority on which songs are recommended and in what order.
- **`src/guardrails.py`** — checks raw requests and parsed preferences for
  safety, topicality, and internal consistency.
- **`src/verifier.py`** — checks a generated explanation against the retrieved
  song data.
- **`src/app_logging.py`** — structured JSON logging with secret redaction.
- **`src/evaluator.py`** — the reliability evaluation harness.
- **`src/orchestrator.py`**'s control flow — the sequencing of guardrail →
  parse → retrieve → generate → verify → repair/fallback is plain,
  deterministic Python, even though some of the steps it calls are AI-powered.

---

## Limitations and Biases

**What are the limitations or biases in the system?**

Inherited from the original scoring engine:
- **Uneven, tiny catalog.** 36 songs, unevenly spread across genres and moods,
  means a listener who wants a rare style or mood gets thinner, less confident
  results simply because there is little to choose from.
- **A song can win on the wrong reasons.** A song matching genre and energy
  can outrank one that fits the overall vibe better if its mood doesn't match
  — there is no bonus for matching everything at once. (This behavior is
  visible directly in the running system: a request for happy, high-energy
  pop can surface a pop song whose labeled mood is not "happy" but whose genre
  and energy match strongly enough to place it in the Top 5.)
- **No understanding of lyrics, language, or cultural context** — only the
  numeric and categorical attributes in the dataset.
- **Silent handling of contradictions.** A request for very high energy and a
  calm/sad mood doesn't get rejected — the system still returns results and
  only *warns* about the conflict rather than resolving it for the user.

New in the AI layer:
- **Guardrail topicality and prompt-injection detection is keyword-based**,
  not a trained classifier. It reliably catches the phrasings tested in this
  project's evaluation suite, but an unusually worded legitimate request could
  be misjudged, and a sufficiently different injection phrasing could
  potentially slip through.
- **The verifier's genre/mood conflict check is a text heuristic** (word-
  boundary matching against a known vocabulary), not semantic understanding.
  It catches direct contradictions but can miss a paraphrased mismatch.
- **A vague request produces thin, honest — but still weak — results.** When
  almost nothing is specified, every retrieved song can score 0.00 with the
  explicit reason "no strong matching features." The system is honest about
  this rather than hiding it, but it does not yet ask a clarifying follow-up
  question; it proceeds with a warning instead.

---

## Potential Misuse

**Could the AI be misused, and how is misuse prevented?**

Yes — the two realistic misuse patterns for a system like this are (1) using
the natural-language interface to make the AI do something other than
recommend music (a general-purpose chatbot jailbreak), and (2) trying to get
the AI to reveal secrets or internal configuration (prompt injection /
credential extraction).

Both are addressed by `src/guardrails.py`, running on the raw request *before*
it ever reaches the AI model:

- Off-topic requests (anything not recognizably about music, mood, genre, or
  a listening activity) are refused with a fixed, non-committal message.
- Requests containing injection or extraction phrases — including
  *"ignore all previous instructions"*, *"reveal your API key"*, and
  *"delete project files"* — are refused outright.

This is not theoretical: the reliability evaluation suite includes exactly
this case (test case TC09, "Prompt-injection attempt") and running
`python -m src.evaluator` confirms it is blocked before any AI call is made —
the guardrail result is `blocked (input guardrail)` and the request never
reaches the parser or the model.

Separately, `src/app_logging.py` redacts any field whose name looks like a
secret (`api_key`, `token`, `password`, ...) and scrubs key-shaped values
(e.g. `sk-...`) out of log text and exception messages, so even an
unanticipated code path cannot leak a credential through the logs.

## Misuse Prevention and Guardrails

| Guardrail | Where | What it does |
|---|---|---|
| Empty / whitespace-only input | `Guardrails.check_input` | Blocked, with a clarification message |
| Excessively long input | `Guardrails.check_input` | Blocked above a configurable character limit |
| Off-topic request | `Guardrails.check_input` | Blocked unless the text is recognizably music-related |
| Prompt injection / secret extraction | `Guardrails.check_input` | Blocked before the AI is ever called |
| Out-of-range numeric preference | `Guardrails.check_preferences` | Hard error — processing stops |
| Unsupported genre/mood | `Guardrails.check_preferences` | Warning only — processing continues |
| Conflicting preferences (e.g. high energy + calm mood) | `Guardrails.check_preferences` | Warning only — never silently changed |
| Unsupported/invented content in the AI's explanation | `src/verifier.py` | One repair attempt, then a deterministic (no-AI) fallback |

---

## Reliability Testing Method

Reliability was tested two ways:

1. **95 automated unit and integration tests** (`python -m pytest -v`), all
   running offline against a deterministic `FakeAIClient` — no network access
   or API cost. These cover the scoring engine, the AI client abstraction, the
   preference parser, the guardrails, the orchestrator's retrieval and
   agentic verify/repair/fallback logic, the explanation generator, the
   verifier, structured logging, and the interactive CLI.
2. **A 12-case reliability evaluation** (`python -m src.evaluator`), which
   runs the same `VibeMatchOrchestrator` used by the real application against
   a fixed set of scripted scenarios — a clear request, a calm instrumental
   request, an intense workout request, conflicting preferences, an
   unsupported genre, a vague request, empty input, excessively long input, a
   prompt-injection attempt, malformed AI JSON, an invented song in a
   generated answer, and an unavailable AI service — and grades each one
   against its expected behavior. The pass count is computed from the actual
   graded results every run, not hardcoded.

## Reliability Testing Results

```
python -m pytest -v
```
**95 of 95 tests passed.**

```
python -m src.evaluator
```
**12 of 12 reliability cases passed.**

The invented-song case (TC11) is the most direct proof of the verification
layer working: with the AI's output forced to fabricate a song, the actual
recorded result was `verification_result: "attempt 1: failed; attempt 2:
failed"`, `repair_attempted: true`, `fallback_used: true`, and the case still
passed — meaning the system correctly detected the fabrication twice, tried
one repair, and then served the user a fully deterministic answer instead of
an unverified one. Full per-case detail is in
`evaluation/evaluation_results.md` and `evaluation/evaluation_results.json`.

## Reliability Testing Surprises

**What was surprising during reliability testing?**

The invented-song test case (TC11) did not behave the way it was first
designed. My initial version fed a fake AI reply naming a song that was never
retrieved ("Totally Made Up Song") straight into the real
`ExplanationGenerator`, expecting the verifier to catch it and trigger a
repair and fallback. Instead, the test passed with `explanation_method:
"generated"` and no repair or fallback at all.

The reason was surprising: `ExplanationGenerator.generate()` already builds
its output by iterating the *retrieved* songs and only attaching AI text
where a title matches one of them. An invented title is silently discarded by
that loop before the verifier ever sees it — a genuine, independently useful
safety property I had built earlier (Step 7) without realizing it would make
this particular test case pass for the wrong reason. The test wasn't actually
exercising the verifier's defense at all; it was exercising the generator's
defense instead, and happened to get the "right" answer regardless.

I caught this by inspecting the actual recorded output
(`explanation_method`, `repair_attempted`, `fallback_used`) rather than
trusting the green checkmark, exactly the failure mode this whole project is
designed to guard against. The fix was to inject a stub explanation generator
for this one case that deliberately bypasses the generator's own filtering
(mirroring the pattern already used in `tests/test_orchestrator.py`), so the
test genuinely proves the verifier's *independent* defense works even if the
generator's filtering ever failed on its own. The corrected version is what
runs today and produces the `attempt 1: failed; attempt 2: failed` /
`fallback_used: true` result cited above.

---

## How I Collaborated With AI

Every step of VibeMatch AI was built incrementally with an AI coding
assistant, one scoped step at a time: for each step, the assistant was told
exactly which files to create or modify and which files to leave untouched,
asked to run the resulting tests and the actual commands (not just describe
what they *should* do), and required to report real terminal output before
moving on. Before any implementation step, the assistant first reviewed the
existing code and explained, in plain language, how it currently worked and
what looked wrong — this surfaced real issues before they were built on top
of (see the Design Pattern collaboration in `ai_interactions.md` for an
earlier example of this same review-first approach in the original project).
At the end of every step, the assistant was asked to explain the changes
file-by-file for a beginner audience and to show exact, real command output
rather than a summary — which is what makes the Reliability Testing Surprise
above something I could actually catch and fix, instead of something that
quietly shipped.

## One Helpful AI Suggestion

When the original project needed to support multiple scoring strategies
(Balanced, Genre-First, Mood-First, Energy-Focused) without duplicating the
scoring algorithm, the AI assistant was asked to recommend a design pattern
before writing any code. Its suggestion — recorded in `ai_interactions.md`
under "Design Pattern (SF10)" — was a data-driven Strategy pattern: a registry
of `ScoringStrategy` objects that are pure bundles of weights, all fed into
the *same* unchanged `score_song()` loop, rather than a new code path per
mode. This was genuinely helpful because it meant `score_song()` never had to
be touched or duplicated to add a new strategy, and it was verified
concretely: all existing tests kept passing with the `strategy` parameter
defaulting to `None`/balanced, and running every mode against the standard
and adversarial profiles showed each strategy producing a distinctly
different, sensible ranking (Genre-First clustering by genre, Mood-First
clustering by mood across different genres, Energy-Focused reordering by
audio-feature closeness) — with no duplicated scoring logic anywhere in the
codebase.

## One Flawed or Incorrect AI Suggestion

The evaluator test case for "invented song in generated answer" (TC11, see
Reliability Testing Surprises above) is a concrete example of an AI-authored
artifact — in this case, a test I (as the AI assistant) wrote — that was
incorrect and passed for the wrong reason on the first attempt. I designed a
test intended to prove that the verifier rejects an AI hallucination and
triggers repair-then-fallback, but the way I wired the fake AI reply into the
real `ExplanationGenerator` meant the hallucinated title was filtered out
before the verifier ever ran, so the test passed without exercising the
behavior it claimed to test. This is functionally the same class of mistake
called out in the original project's own limitations: **a test that passes
does not by itself prove the intended logic ran** — the same lesson as the
starter `Recommender.recommend()` stub, whose tests passed while it simply
returned `self.songs[:k]` (the input order) instead of using any real
scoring, until that was found during a code review and fixed to delegate to
the real `recommend_songs()` engine. In both cases, the fix required actually
running the code and inspecting the real output, not trusting that a passing
test meant the described behavior was in effect.

---

## Human Responsibilities

Using this system responsibly means:

- Treating every AI-generated explanation as advisory text describing an
  already-computed, auditable score — not as an independent recommendation
  authority.
- Not deploying this system for real users or real decisions; it is a
  learning project over a synthetic, 36-song catalog.
- Reviewing the reliability evaluation results (`evaluation/`) and the test
  suite before trusting any change to the guardrails, verifier, or scoring
  weights.
- Keeping the `GEMINI_API_KEY` out of version control (`.env` is
  git-ignored) and never adding it to a prompt, log statement, or committed
  file.
- Verifying claims about the system's behavior by running the actual code
  (`python -m pytest -v`, `python -m src.evaluator`) rather than relying on
  documentation or a prior description of it.

---

## Reflection

The biggest lesson from this project is the same one carried over from the
original scoring engine, now applied one layer up: the "smartest"-looking
part of a system is rarely where the real guarantees live. In the original
recommender, the weights decided everything. In VibeMatch AI, the AI produces
the most human-sounding output, but it is deliberately the least trusted
component in the pipeline — confined to language understanding and narration,
never ranking, and never allowed to ship unverified text. Building the
verifier and the repair/fallback loop made this concrete: writing a system
that catches its own AI component's mistakes turned out to require more
careful engineering than writing the AI-calling code itself. The invented-song
test surprise reinforced the project's central discipline — a passing test or
a plausible-looking explanation is not evidence of correctness by itself; only
running the real code and inspecting the real output is.

## Future Improvements

1. **Reward the whole vibe, not just parts.** Add a bonus when a song fits
   style, mood, *and* energy together, so a song right on genre and energy
   but wrong on mood doesn't outrank one that fits the whole picture.
2. **Ask, don't just warn.** When confidence is low or a request is too
   vague, ask the user a specific follow-up question instead of proceeding
   with a warning attached to a weak result.
3. **Grow and even out the library.** A bigger, more balanced catalog across
   genres and moods would make results more accurate for listeners with rarer
   tastes, not just fans of the common styles.
4. **Move guardrail and conflict detection beyond keyword heuristics.** A
   lightweight trained classifier for topicality/injection detection, and a
   more semantic check for genre/mood conflicts in the verifier, would close
   the gaps described in Limitations and Biases above.
5. **Add a real, network-gated integration test** against the live Gemini
   API for a small sample of requests, to validate prompt quality that the
   offline `FakeAIClient` test suite cannot cover on its own.
