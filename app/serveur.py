"""Find-a-Business — application locale.

Lance un petit serveur sur ton ordinateur (http://127.0.0.1:8765) et ouvre ton navigateur.
Les données viennent de ton dépôt GitHub privé, via une clé d'accès limitée à ce dépôt.
Aucune dépendance : uniquement la bibliothèque standard de Python.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
STATIC = APP_DIR / "static"
CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "FindABusiness"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_FILE = CONFIG_DIR / "derniere_copie.json"
DEFAULT_REPO = "Samadana/find-a-business"
API = "https://api.github.com"

STATUTS = ["nouvelle", "a_etudier", "en_cours", "lancee", "abandonnee"]
SETTINGS = {
    "FAB_MIN_SCORE_NOTIFY": "6.5",
    "FAB_MODEL": "claude-opus-5-5",
    "FAB_DAILY_COST_LIMIT_USD": "2",
}
ALLOWED_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")


class GitHub:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo

    def request(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        url = path if path.startswith("http") else f"{API}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github.raw+json" if raw else "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "find-a-business-app")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read() or b"{}").get("message", "")
            except json.JSONDecodeError:
                msg = ""
            raise GitHubError(exc.code, msg or exc.reason) from None
        except urllib.error.URLError as exc:
            raise GitHubError(0, f"connexion impossible ({exc.reason})") from None
        if raw:
            return content
        return json.loads(content) if content else {}

    # --- fichiers du dépôt
    def read_json(self, path: str, default):
        try:
            return json.loads(self.request("GET", f"/repos/{self.repo}/contents/{path}", raw=True))
        except GitHubError as exc:
            if exc.status == 404:
                return default
            raise

    def update_json(self, path: str, mutate, message: str):
        """Lecture + modification + écriture, avec nouvel essai si le bilan a écrit entre-temps."""
        for _ in range(4):
            try:
                meta = self.request("GET", f"/repos/{self.repo}/contents/{path}")
                sha = meta["sha"]
                current = json.loads(base64.b64decode(meta["content"]))
            except GitHubError as exc:
                if exc.status != 404:
                    raise
                sha, current = None, {}
            new = mutate(current)
            body = {
                "message": message,
                "content": base64.b64encode(json.dumps(new, ensure_ascii=False, indent=1).encode()).decode(),
            }
            if sha:
                body["sha"] = sha
            try:
                self.request("PUT", f"/repos/{self.repo}/contents/{path}", body)
                return new
            except GitHubError as exc:
                if exc.status not in (409, 422):
                    raise
                time.sleep(1)
        raise GitHubError(409, "le fichier a changé pendant l'enregistrement, réessaie")

    # --- variables GitHub Actions (réglages)
    def get_variables(self) -> dict:
        out, page = {}, 1
        while True:
            res = self.request("GET", f"/repos/{self.repo}/actions/variables?per_page=30&page={page}")
            for v in res.get("variables", []):
                out[v["name"]] = v["value"]
            if len(res.get("variables", [])) < 30:
                return out
            page += 1

    def set_variable(self, name: str, value: str) -> None:
        try:
            self.request("PATCH", f"/repos/{self.repo}/actions/variables/{name}", {"name": name, "value": value})
        except GitHubError as exc:
            if exc.status != 404:
                raise
            self.request("POST", f"/repos/{self.repo}/actions/variables", {"name": name, "value": value})


def github() -> GitHub:
    cfg = load_config()
    if not cfg.get("token"):
        raise GitHubError(401, "application non configurée")
    return GitHub(cfg["token"], cfg.get("repo") or DEFAULT_REPO)


def fetch_all() -> dict:
    gh = github()
    data = {
        "ideas": gh.read_json("docs/data/ideas.json", []),
        "rejected": gh.read_json("docs/data/rejected.json", []),
        "stats": gh.read_json("docs/data/stats.json", {}),
        "suivi": gh.read_json("data/suivi.json", {}),
        "repo": gh.repo,
    }
    try:
        variables = gh.get_variables()
        data["variables_ok"] = True
    except GitHubError:
        variables, data["variables_ok"] = {}, False
    data["settings"] = {k: variables.get(k, v) for k, v in SETTINGS.items()}
    data["auto"] = variables.get("FAB_AUTO", "false") == "true"
    data["recupere_le"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return data


def validate_settings(values: dict) -> dict:
    out = {}
    if "FAB_MIN_SCORE_NOTIFY" in values:
        v = float(values["FAB_MIN_SCORE_NOTIFY"])
        if not 0 <= v <= 10:
            raise ValueError("Le seuil doit être entre 0 et 10.")
        out["FAB_MIN_SCORE_NOTIFY"] = f"{v:g}"
    if "FAB_MODEL" in values:
        if values["FAB_MODEL"] not in ALLOWED_MODELS:
            raise ValueError("Modèle inconnu.")
        out["FAB_MODEL"] = values["FAB_MODEL"]
    if "FAB_DAILY_COST_LIMIT_USD" in values:
        v = float(values["FAB_DAILY_COST_LIMIT_USD"])
        if not 0 <= v <= 100:
            raise ValueError("Le plafond doit être entre 0 et 100 $.")
        out["FAB_DAILY_COST_LIMIT_USD"] = f"{v:g}"
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "FindABusiness/1.0"

    def log_message(self, fmt, *args):  # journal silencieux
        pass

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def _local_host(self) -> bool:
        # Protection : l'application ne répond qu'aux adresses locales (évite qu'un site web s'y connecte).
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def _same_origin(self) -> bool:
        # Protection : seules les pages de l'application elle-même peuvent modifier les données.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        json_body = (self.headers.get("Content-Type") or "").startswith("application/json")
        return self._local_host() and json_body and (origin is None or origin == f"http://{host}")

    def do_GET(self):
        if not self._local_host():
            return self._json(403, {"erreur": "adresse refusée"})
        if self.path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/config":
            cfg = load_config()
            self._json(200, {"configured": bool(cfg.get("token")), "repo": cfg.get("repo") or DEFAULT_REPO})
        elif self.path == "/api/data":
            try:
                self._json(200, fetch_all())
            except GitHubError as exc:
                cached = None
                try:
                    cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
                self._json(200 if cached else 502, {"erreur": str(exc), "status": exc.status, "copie": cached})
        else:
            self._json(404, {"erreur": "introuvable"})

    def do_POST(self):
        if not self._same_origin():
            return self._json(403, {"erreur": "origine refusée"})
        try:
            body = self._body()
            if self.path == "/api/config":
                token = str(body.get("token", "")).strip()
                repo = str(body.get("repo") or DEFAULT_REPO).strip()
                gh = GitHub(token, repo)
                gh.request("GET", f"/repos/{repo}")  # vérifie la clé et l'accès au dépôt
                save_config({"token": token, "repo": repo})
                return self._json(200, {"ok": True})
            if self.path == "/api/suivi":
                idea_id = str(body["id"])
                statut = body.get("statut", "nouvelle")
                if statut not in STATUTS:
                    raise ValueError("Statut inconnu.")
                note = str(body.get("note", ""))[:5000]

                def mutate(current):
                    current[idea_id] = {"statut": statut, "note": note, "maj": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    return current

                suivi = github().update_json("data/suivi.json", mutate, f"Suivi : {idea_id} → {statut}")
                return self._json(200, {"ok": True, "suivi": suivi})
            if self.path == "/api/settings":
                gh = github()
                for name, value in validate_settings(body).items():
                    gh.set_variable(name, value)
                return self._json(200, {"ok": True})
            if self.path == "/api/auto":
                github().set_variable("FAB_AUTO", "true" if body.get("enabled") else "false")
                return self._json(200, {"ok": True})
            return self._json(404, {"erreur": "introuvable"})
        except GitHubError as exc:
            return self._json(502, {"erreur": explain(exc), "status": exc.status})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._json(400, {"erreur": str(exc)})


def explain(exc: GitHubError) -> str:
    if exc.status == 401:
        return "Clé GitHub invalide ou expirée : recrée-la (onglet Réglages)."
    if exc.status in (403, 404):
        return ("Accès refusé par GitHub : vérifie que la clé donne accès au dépôt "
                "avec les droits Contents et Variables en lecture et écriture.")
    return f"GitHub : {exc}"


def free_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 0


def already_running(port: int = 8765) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=2) as resp:
            return resp.headers.get("Server", "").startswith("FindABusiness")
    except (OSError, urllib.error.URLError):
        return False


def main() -> None:
    if already_running():
        print("Find-a-Business est déjà ouvert : j'ouvre simplement le navigateur.")
        if "--no-browser" not in sys.argv:
            webbrowser.open("http://127.0.0.1:8765/")
        return
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print("Find-a-Business est lancé :", url)
    print("Garde cette fenêtre ouverte. Ferme-la pour arrêter l'application.")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
