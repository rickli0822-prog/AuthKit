import json

from authkit import settings


def test_load_settings_defaults_when_json_is_not_object(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    path = settings.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    assert settings.load_settings() == {"locale": settings.DEFAULT_LOCALE}


def test_config_dir_falls_back_to_home_when_userprofile_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(settings.Path, "home", lambda: tmp_path)

    assert settings.config_dir() == tmp_path / ".authkit"


def test_load_settings_defaults_invalid_locale(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    path = settings.config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"locale": "bad", "theme": "light"}), encoding="utf-8")

    loaded = settings.load_settings()

    assert loaded["locale"] == settings.DEFAULT_LOCALE
    assert loaded["theme"] == "light"


def test_save_settings_writes_complete_json_with_fsync(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    fsync_calls = []
    monkeypatch.setattr(settings.os, "fsync", lambda fileno: fsync_calls.append(fileno))

    settings.save_settings({"locale": "en"})

    assert settings.load_settings()["locale"] == "en"
    assert len(fsync_calls) == 1
    assert not list(settings.config_dir().glob(".*.tmp"))


def test_save_settings_keeps_existing_file_when_temp_open_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    settings.save_settings({"locale": "zh"})
    target = settings.config_path()
    real_open = type(target).open

    def fail_open(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise OSError("disk full")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.open", fail_open)

    try:
        settings.save_settings({"locale": "en"})
    except OSError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("expected temp write failure")

    assert json.loads(target.read_text(encoding="utf-8"))["locale"] == "zh"
    assert not list(settings.config_dir().glob(".*.tmp"))
