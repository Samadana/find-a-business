"""Configuration centralisée, lue depuis les variables d'environnement.

Toutes les valeurs ont un défaut raisonnable : seuls ANTHROPIC_API_KEY et
DISCORD_WEBHOOK_URL sont nécessaires en production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Prix publics Anthropic en $ par million de tokens (entrée, sortie).
# Sert uniquement à estimer la dépense et à appliquer le plafond quotidien.
MODEL_PRICES_USD = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.00, 50.00),
}


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value if value else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in ("1", "true", "yes", "oui", "on")


def _default_dashboard_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


@dataclass
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    discord_webhook_url: str = field(default_factory=lambda: os.environ.get("DISCORD_WEBHOOK_URL", ""))
    dashboard_url: str = field(default_factory=lambda: _env("DASHBOARD_URL", _default_dashboard_url()))

    model: str = field(default_factory=lambda: _env("FAB_MODEL", "claude-opus-5-5"))
    # Premier tri bon marché : Haiku lit tous les titres et ne garde que les sujets prometteurs.
    triage_model: str = field(default_factory=lambda: _env("FAB_TRIAGE_MODEL", "claude-haiku-5-5"))
    triage_candidates: int = field(default_factory=lambda: _env_int("FAB_TRIAGE_CANDIDATES", 1500))
    triage_keep: int = field(default_factory=lambda: _env_int("FAB_TRIAGE_KEEP", 120))
    # Sujets les mieux classés par l'heuristique, toujours envoyés à l'analyse finale (filet de sécurité).
    always_keep: int = field(default_factory=lambda: _env_int("FAB_ALWAYS_KEEP", 25))
    effort: str = field(default_factory=lambda: _env("FAB_EFFORT", "high"))

    # Collecte
    max_article_age_hours: int = field(default_factory=lambda: _env_int("FAB_MAX_ARTICLE_AGE_HOURS", 36))
    max_articles_per_run: int = field(default_factory=lambda: _env_int("FAB_MAX_ARTICLES", 150))
    min_new_articles: int = field(default_factory=lambda: _env_int("FAB_MIN_NEW_ARTICLES", 5))
    http_timeout: float = field(default_factory=lambda: _env_float("FAB_HTTP_TIMEOUT", 15.0))

    # Idées
    min_score_notify: float = field(default_factory=lambda: _env_float("FAB_MIN_SCORE_NOTIFY", 6.5))
    max_budget_eur: int = field(default_factory=lambda: _env_int("FAB_MAX_BUDGET_EUR", 5000))
    idea_archive_days: int = field(default_factory=lambda: _env_int("FAB_ARCHIVE_DAYS", 30))

    # Garde-fou de dépense (0 = pas de plafond)
    daily_cost_limit_usd: float = field(default_factory=lambda: _env_float("FAB_DAILY_COST_LIMIT_USD", 2.0))

    dry_run: bool = field(default_factory=lambda: _env_bool("FAB_DRY_RUN", False))

    # Bilan quotidien : heure locale du bilan. GitHub planifie en heure UTC (sans heure d'été),
    # le workflow se déclenche donc à 7 h et 8 h UTC et le programme ne garde que le bon créneau.
    report_hour: int = field(default_factory=lambda: _env_int("FAB_REPORT_HOUR", 9))
    timezone: str = field(default_factory=lambda: _env("FAB_TIMEZONE", "Europe/Paris"))
    # Lancement manuel : ignore l'heure et le « déjà fait aujourd'hui ».
    force: bool = field(default_factory=lambda: _env_bool("FAB_FORCE", False))

    sources_path: Path = ROOT / "config" / "sources.json"
    seen_path: Path = ROOT / "data" / "seen_articles.json"
    ideas_path: Path = ROOT / "docs" / "data" / "ideas.json"
    rejected_path: Path = ROOT / "docs" / "data" / "rejected.json"
    stats_path: Path = ROOT / "docs" / "data" / "stats.json"

    def price(self) -> tuple[float, float]:
        return MODEL_PRICES_USD.get(self.model, MODEL_PRICES_USD["claude-opus-5-5"])
