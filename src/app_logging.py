"""
Structured logging for VibeMatch AI.

Every significant step emits a single JSON line via `log_event()`, e.g.

    {"event": "recommendation_completed", "parser_confidence": 0.82,
     "candidate_count": 5, "strategy": "balanced", "verification_passed": true,
     "repair_attempted": false, "fallback_used": false}

Structured events are easy to grep, parse, and aggregate -- far more useful than
free-form strings.

Safety is built in:
* Fields whose name looks like a secret (api_key, token, password, ...) are
  replaced with "[REDACTED]".
* Any value containing an API-key-shaped token (e.g. `sk-...` or `AIzaSy...`) is scrubbed, so a
  secret can't leak through an exception message.
* We log lengths/counts rather than raw user text, to avoid storing unnecessary
  personal information.

The log level is user-controllable via the `VIBEMATCH_LOG_LEVEL` environment
variable (or the `level` argument to `configure_logging`).
"""

import json
import logging
import os
import re

LOG_LEVEL_ENV_VAR = "VIBEMATCH_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"

# Field names that must never have their value logged.
_SENSITIVE_KEY_SUBSTRINGS = (
    "api_key", "apikey", "secret", "token", "password", "passwd",
    "authorization", "auth_token", "env",
)

# Values shaped like common provider keys get scrubbed even inside prose (for
# example, if an exception message happens to include one).
_TOKEN_PATTERN = re.compile(r"\b(?:sk-|AIzaSy)[A-Za-z0-9\-_]{6,}\b")

REDACTED = "[REDACTED]"


def configure_logging(level=None) -> logging.Logger:
    """
    Set up logging once, honoring `VIBEMATCH_LOG_LEVEL` (or an explicit `level`).

    Returns the root "vibematch" logger. Called from the app entry point -- not at
    import time -- so importing this module has no side effects.
    """
    resolved = level or os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LEVEL)
    logging.basicConfig(level=resolved, format="%(message)s")
    return logging.getLogger("vibematch")


def get_logger(name: str = "vibematch") -> logging.Logger:
    """Return a named logger under the `vibematch` namespace."""
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> dict:
    """
    Emit one structured event as a JSON line, after redacting anything sensitive.

    Returns the (sanitized) payload dict -- handy for tests and callers that want
    to inspect what was logged.
    """
    payload = {"event": event}
    payload.update(_sanitize(fields))
    logger.log(level, json.dumps(payload, default=str))
    return payload


def safe_error_message(exc: Exception) -> str:
    """Build an understandable, secret-free message for an exception."""
    return _scrub_value(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _sanitize(fields: dict) -> dict:
    clean = {}
    for key, value in fields.items():
        if any(marker in key.lower() for marker in _SENSITIVE_KEY_SUBSTRINGS):
            clean[key] = REDACTED
        else:
            clean[key] = _scrub_value(value)
    return clean


def _scrub_value(value):
    """Redact key-shaped tokens inside string values; pass other types through."""
    if isinstance(value, str):
        return _TOKEN_PATTERN.sub(REDACTED, value)
    return value
