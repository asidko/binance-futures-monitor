"""config.load() materializes a complete config from the template on first run,
so no command (however the user installed) lands on a missing/empty file."""
import config
import paths


def test_load_creates_populated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(paths, "CONFIG_FILE", tmp_path / "config.toml")

    config.load()

    text = (tmp_path / "config.toml").read_text()
    assert "default_provider" in text
    assert "[telegram]" in text
