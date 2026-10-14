"""Réseau local (V8-9) : mode « ce poste » ou « serveur de l'école »."""
import pytest

from administration.models import Role
from common import network


def test_config_defaults_and_roundtrip(tmp_path):
    assert network.load_config(tmp_path) == {"mode": "local", "port": 8000}
    assert network.bind_host(network.load_config(tmp_path)) == "127.0.0.1"
    network.save_config("server", 8080, data_dir=tmp_path)
    config = network.load_config(tmp_path)
    assert config == {"mode": "server", "port": 8080} and network.bind_host(config) == "0.0.0.0"
    with pytest.raises(ValueError):
        network.save_config("server", 80, data_dir=tmp_path)
    (tmp_path / "reseau.json").write_text("{abîmé", encoding="utf-8")
    assert network.load_config(tmp_path)["mode"] == "local"            # fichier illisible : mode sûr


def test_launcher_reads_network_mode(tmp_path, monkeypatch):
    import launcher
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    network.save_config("server", 8123, data_dir=tmp_path)
    launcher.configure_network()
    try:
        assert (launcher.BIND_HOST, launcher.PORT, launcher.SERVER_MODE) == ("0.0.0.0", 8123, True)
        assert launcher.APP_URL == "http://127.0.0.1:8123/"               # la fenêtre du serveur reste en local
    finally:
        network.save_config("local", 8000, data_dir=tmp_path)
        launcher.configure_network()
    assert (launcher.BIND_HOST, launcher.SERVER_MODE) == ("127.0.0.1", False)


def test_settings_page(client, login, school, tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(network, "lan_addresses", lambda: ["192.168.1.20"])
    login(Role.ADMIN)
    page = client.get("/reseau/").content.decode()
    assert "Serveur de l'école" in page and "192.168.1.20" not in page        # adresse affichée en mode serveur seulement
    client.post("/reseau/", {"mode": "server", "port": "8000"})
    assert network.load_config(tmp_path)["mode"] == "server"
    page = client.get("/reseau/").content.decode()
    assert "http://192.168.1.20:8000/" in page and "<svg" in page
    r = client.get("/reseau/raccourci/?ip=192.168.1.20")
    assert r.content.decode() == "[InternetShortcut]\r\nURL=http://192.168.1.20:8000/\r\n"
    assert client.get("/reseau/raccourci/?ip=10.0.0.1").status_code == 400
    client.logout()
    login(Role.SECRETARY, username="secretaire")
    assert client.get("/reseau/").status_code in (302, 403)


def test_settings_page_says_when_kis_must_be_restarted(client, login, school, tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    network.save_config("server", 8000, data_dir=tmp_path)
    monkeypatch.setattr(network, "lan_addresses", lambda: ["192.168.1.101"])
    login(Role.ADMIN)
    monkeypatch.setattr(network, "answers_on", lambda ip, port, timeout=0.8: False)
    assert "fermez complètement KIS Kalanso" in client.get("/reseau/").content.decode()
    monkeypatch.setattr(network, "answers_on", lambda ip, port, timeout=0.8: True)
    page = client.get("/reseau/").content.decode()
    assert "KIS répond à cette adresse" in page and "même Wi-Fi" in page


def test_answers_on_detects_a_listening_port():
    import socket
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert network.answers_on("127.0.0.1", port)
    finally:
        server.close()
    assert not network.answers_on("127.0.0.1", port)
