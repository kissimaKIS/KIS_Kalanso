import sys

import launcher


def test_no_app_browser_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert launcher.find_app_browser() is None


def test_app_window_uses_app_mode(monkeypatch, tmp_path):
    calls = {}

    class FakeProcess:
        def wait(self):
            return 0

    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(launcher, "find_app_browser", lambda: "msedge.exe")
    monkeypatch.setattr(launcher, "browser_profile_dir", lambda: tmp_path)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args: calls.setdefault("args", args) and FakeProcess())
    monkeypatch.setattr(launcher.os, "_exit", lambda code: calls.setdefault("exit", code))
    launcher.open_app_window()
    assert f"--app={launcher.APP_URL}" in calls["args"]
    assert "exit" not in calls  # fermeture immédiate : le serveur n'est pas coupé


def test_missing_std_streams_are_redirected_to_log(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    launcher._ensure_std_streams()
    sys.stdout.write("Operations to perform:\n")
    assert sys.stdout is sys.stderr
    sys.stdout.flush()
    assert "Operations to perform" in (tmp_path / "kis_kalanso.log").read_text(encoding="utf-8")


def test_migrations_are_skipped_only_when_database_is_up_to_date(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "db.sqlite3"
    assert launcher.migrations_needed(db)  # base absente
    names = sorted(launcher._app_migration_names())
    assert names, "les migrations de l'application doivent être trouvées sur le disque"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
        connection.executemany("INSERT INTO django_migrations VALUES (?, ?)", names[:-1])
    launcher.remember_migrations(db)
    assert launcher.migrations_needed(db)  # une migration manque
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO django_migrations VALUES (?, ?)", names[-1])
    assert not launcher.migrations_needed(db)
    (tmp_path / ".kis_migrations").write_text("django=0.0;count=1", encoding="utf-8")
    assert launcher.migrations_needed(db)  # autre version de Django : on migre


def test_second_instance_cannot_take_the_lock(tmp_path):
    first = launcher.acquire_single_instance(tmp_path)
    assert first not in (None, True)
    assert launcher.acquire_single_instance(tmp_path) is None
    first.close()
    again = launcher.acquire_single_instance(tmp_path)
    assert again not in (None, True)
    again.close()


def test_second_instance_only_opens_the_window(monkeypatch, tmp_path, settings):
    settings.KIS_DATA_DIR = tmp_path
    held = launcher.acquire_single_instance(tmp_path)
    calls = []
    monkeypatch.setattr(launcher, "open_app_window", lambda: calls.append("window"))
    monkeypatch.setattr(launcher, "execute_from_command_line", lambda argv: calls.append("migrate"))
    monkeypatch.setattr(launcher, "serve", lambda: calls.append("serve"))
    launcher.main()
    assert calls == ["window"]  # ni migration ni second serveur
    held.close()
