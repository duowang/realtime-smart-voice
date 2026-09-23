import logging
from pathlib import Path

from diagnostics import CONTENT_EVENTS, PrivateRotatingFileHandler, log_message, safe_text


def test_conversation_and_tool_content_are_omitted_by_default():
    for kind in CONTENT_EVENTS:
        assert log_message(kind, "private shopping list") == "[content omitted]"
        assert (
            log_message(kind, "private shopping list", include_content=True)
            == "private shopping list"
        )


def test_keys_and_terminal_controls_are_removed_even_when_content_logging_is_enabled():
    key = "sk-proj-" + "a" * 30
    text = f"\x1b]52;c;clipboard\x07\n{key}\rsecret-test-key\x9b31m\u202esecret"
    result = log_message("USER_TRANSCRIPT", text, include_content=True, secret="secret-test-key")
    assert key not in result and "secret-test-key" not in result
    assert result.count("[REDACTED]") == 2
    assert all(c.isprintable() for c in result)
    assert safe_text("你好\nhello\x1b", multiline=True) == "你好\nhello"


def test_private_log_permissions_survive_rotation(tmp_path):
    path = tmp_path / "assistant.log"
    path.write_text("old log\n")
    path.chmod(0o644)
    handler = PrivateRotatingFileHandler(path, maxBytes=30, backupCount=2, encoding="utf-8")
    try:
        assert path.stat().st_mode & 0o777 == 0o600
        for _ in range(4):
            handler.emit(
                logging.LogRecord("test", logging.INFO, "", 0, "bounded message", (), None)
            )
        assert Path(str(path) + ".1").exists()
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
    finally:
        handler.close()
