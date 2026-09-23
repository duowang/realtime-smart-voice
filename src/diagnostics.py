"""Keep diagnostics useful without persisting conversation content by default."""

import os
import re
from logging.handlers import RotatingFileHandler

CONTENT_EVENTS = {
    "USER_TRANSCRIPT",
    "ASSISTANT_RESPONSE",
    "FUNCTION_CALL",
    "MUSIC_FUNCTION_CALL",
    "MUSIC_SEARCH",
    "MUSIC_PLAYBACK",
    "CONVERSATION_END_DETECTED",
}
KEY_PATTERN = re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}")


def safe_text(value: object, *, secret: str = "", multiline: bool = False) -> str:
    """Remove terminal controls and redact the configured/OpenAI-shaped key."""
    text = str(value)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = KEY_PATTERN.sub("[REDACTED]", text)
    return "".join(c for c in text if c.isprintable() or (multiline and c in "\n\t"))


def log_message(kind: str, message: str, *, include_content: bool = False, secret: str = "") -> str:
    if kind in CONTENT_EVENTS and not include_content:
        return "[content omitted]"
    return safe_text(message, secret=secret)[:2000]


class PrivateRotatingFileHandler(RotatingFileHandler):
    """Keep new and existing log files owner-only, including after rotation."""

    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)
            return os.fdopen(fd, "a", encoding=self.encoding, errors=self.errors)
        except BaseException:
            os.close(fd)
            raise
