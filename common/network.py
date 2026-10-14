"""Réseau local (retours V8-9).

Deux modes, enregistrés dans ``reseau.json`` du dossier de données :

- ``local`` (par défaut) : KIS Kalanso n'est accessible que sur ce poste
  (127.0.0.1). Fermer la fenêtre arrête l'application.
- ``server`` : ce poste devient le serveur de l'école. Les autres ordinateurs,
  tablettes et téléphones du même réseau (Wi-Fi ou câble) ouvrent KIS dans
  leur navigateur à l'adresse http://<adresse de ce poste>:<port>/ ; chacun se
  connecte avec son propre compte et voit ce que son rôle autorise. Fermer la
  fenêtre sur le serveur ne coupe pas l'accès des autres postes.

La base reste unique, sur le serveur : il n'y a rien à synchroniser entre les
postes. Le changement de mode prend effet au prochain démarrage.
"""
import json
import os
import socket
from pathlib import Path

DEFAULT_PORT = 8000
MODES = ("local", "server")
CONFIG_NAME = "reseau.json"


def _data_dir():
    return Path(os.environ.get("KIS_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")


def load_config(data_dir=None):
    path = Path(data_dir or _data_dir()) / CONFIG_NAME
    config = {"mode": "local", "port": DEFAULT_PORT}
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored.get("mode") in MODES:
            config["mode"] = stored["mode"]
        port = int(stored.get("port") or DEFAULT_PORT)
        if 1024 <= port <= 65535:
            config["port"] = port
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return config


def save_config(mode, port=DEFAULT_PORT, data_dir=None):
    if mode not in MODES:
        raise ValueError("Mode réseau inconnu.")
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError("Le port doit être compris entre 1024 et 65535.")
    path = Path(data_dir or _data_dir()) / CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": mode, "port": port}), encoding="utf-8")


def is_server(config=None):
    return (config or load_config())["mode"] == "server"


def bind_host(config=None):
    """Adresse d'écoute du serveur : toutes les interfaces en mode serveur, sinon ce poste seulement."""
    return "0.0.0.0" if is_server(config) else "127.0.0.1"


def lan_addresses():
    """Adresses IPv4 de ce poste sur le réseau local (hors 127.x)."""
    found = []
    try:
        # Aucun paquet n'est envoyé : on demande seulement au système quelle
        # interface servirait à joindre l'extérieur.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            found.append(address)
    except OSError:
        pass
    result = []
    for address in found:
        if address and not address.startswith("127.") and address not in result:
            result.append(address)
    return result


def answers_on(ip, port, timeout=0.8):
    """Vrai si KIS répond à cette adresse depuis ce poste.

    Faux tant que KIS n'a pas été redémarré en mode serveur (il n'écoute alors
    que sur 127.0.0.1). Vrai ici mais injoignable depuis un téléphone : c'est
    le pare-feu de Windows ou le réseau (téléphone sur un autre Wi-Fi, réseau
    « invité » qui isole les appareils…).
    """
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except OSError:
        return False
