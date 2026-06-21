"""Re-spawn path resolution: a bare command name must resolve via PATH, not the
CWD (the bug that pointed the daemon at /Users/<you>/bfm)."""
import paths


def test_bare_name_resolves_via_path(tmp_path, monkeypatch):
    binary = tmp_path / "bfm"
    binary.write_text("")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert paths._resolve_executable("bfm") == binary.resolve()


def test_path_with_separator_is_honored(tmp_path):
    binary = tmp_path / "bfm"
    binary.write_text("")
    assert paths._resolve_executable(str(binary)) == binary.resolve()
