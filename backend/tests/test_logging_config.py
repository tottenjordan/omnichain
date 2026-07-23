"""Tests for structured JSON logging with correlation ids."""

import json
import logging

from omnichain.logging_config import configure_logging, correlation_id_var


def test_json_log_includes_correlation_id(capsys):
    configure_logging()
    token = correlation_id_var.set("test-123")
    try:
        logging.getLogger("omnichain.test").info("hello world")
    finally:
        correlation_id_var.reset(token)

    err = capsys.readouterr().err.strip().splitlines()[-1]
    data = json.loads(err)

    assert data["message"] == "hello world"
    assert data["correlation_id"] == "test-123"
    assert data["level"] == "INFO"
    assert data["logger"] == "omnichain.test"


def test_correlation_id_defaults_to_dash(capsys):
    configure_logging()
    logging.getLogger("omnichain.test").warning("no id set")
    err = capsys.readouterr().err.strip().splitlines()[-1]
    data = json.loads(err)
    assert data["correlation_id"] == "-"
    assert data["level"] == "WARNING"
