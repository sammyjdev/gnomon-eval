from gnomon.config.env import expand_env


def test_expands_simple_var(monkeypatch):
    monkeypatch.setenv("MY_URL", "http://box:11434")
    assert expand_env({"base_url": "${MY_URL}"}) == {"base_url": "http://box:11434"}


def test_missing_var_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("MY_URL", raising=False)
    assert expand_env("${MY_URL:-http://localhost:11434}") == "http://localhost:11434"


def test_set_var_wins_over_default(monkeypatch):
    monkeypatch.setenv("MY_URL", "http://box:11434")
    assert expand_env("${MY_URL:-http://localhost:11434}") == "http://box:11434"


def test_missing_var_without_default_stays_literal(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    assert expand_env("${NOPE}") == "${NOPE}"


def test_plain_strings_untouched():
    assert expand_env("llama3.1:8b") == "llama3.1:8b"
    assert expand_env("http://localhost:8765/v1") == "http://localhost:8765/v1"


def test_recurses_dicts_and_lists(monkeypatch):
    monkeypatch.setenv("H", "example.com")
    data = {"judge": {"base_url": "${H}"}, "hosts": ["${H}", "static"], "seed": 42}
    assert expand_env(data) == {
        "judge": {"base_url": "example.com"},
        "hosts": ["example.com", "static"],
        "seed": 42,
    }
