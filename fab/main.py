"""Point d'entrée : le bilan quotidien (lancé chaque matin par GitHub Actions).

    python -m fab.main
"""

from __future__ import annotations

import json
from collections import Counter
import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import anthropic

from . import notify
from .analyze import analyze, triage
from .collect import Article, collect_all, filter_recent
from .config import MODEL_PRICES_USD, ROOT, Settings
from .corroborate import corroborate
from .ideas import archive_old, now_iso, process_analysis, recent_ideas_for_prompt
from .report import build_standalone_dashboard
from .selection import merge_triage, select_for_analysis
from .storage import load_json, prune_seen, save_json

log = logging.getLogger("fab")


def today_cost(stats: dict) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(r.get("cout_usd", 0) for r in stats.get("historique", []) if r.get("date", "").startswith(today))


def dashboard_file(settings, ideas, rejected, stats, run_info, day: str) -> tuple[str, bytes] | None:
    """Tableau de bord complet en un fichier HTML, joint au bilan Discord."""
    if not settings.attach_dashboard:
        return None
    try:
        snapshot = {**stats, "historique": [run_info] + stats.get("historique", []), "derniere_execution": run_info["date"],
                    "modele": settings.model}
        ordered = sorted(ideas, key=lambda i: (i.get("statut") == "active", i.get("note_globale", 0)), reverse=True)
        return f"find-a-business-{day}.html", build_standalone_dashboard(ordered, rejected, snapshot)
    except (OSError, ValueError) as exc:
        log.warning("Tableau de bord en pièce jointe impossible : %s", exc)
        return None


def maybe_alert(settings: Settings, stats: dict, message: str) -> None:
    """Prévient sur Discord en cas de panne, au plus une fois toutes les 6 heures."""
    last = stats.get("derniere_alerte")
    if last and datetime.fromisoformat(last) > datetime.now(timezone.utc) - timedelta(hours=6):
        return
    if notify.send_text(settings.discord_webhook_url, f"⚠️ Find-a-Business : {message}"):
        stats["derniere_alerte"] = now_iso()


def run(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    stats = load_json(settings.stats_path, {"historique": []})
    ideas: list[dict] = load_json(settings.ideas_path, [])
    rejected: list[dict] = load_json(settings.rejected_path, [])
    seen: dict[str, str] = prune_seen(load_json(settings.seen_path, {}))

    run_info = {"date": now_iso(), "statut": "ok"}

    # 0. Un seul bilan par jour, à l'heure choisie (heure locale, été comme hiver).
    local_now = datetime.now(ZoneInfo(settings.timezone))
    today_local = local_now.date().isoformat()
    if not (settings.force or settings.dry_run):
        if local_now.hour < settings.report_hour:
            log.info("Pas encore %d h (%s) : rien à faire.", settings.report_hour, settings.timezone)
            return {"statut": "ignoré : trop tôt"}
        if stats.get("dernier_bilan") == today_local:
            log.info("Bilan du %s déjà fait : rien à faire.", today_local)
            return {"statut": "ignoré : bilan déjà fait"}

    # 1. Collecte
    fixture = ROOT / "tests" / "fixtures" / "articles.json"
    if settings.dry_run and fixture.exists():
        # Mode test : articles d'exemple, datés de maintenant pour passer le filtre de fraîcheur.
        articles = [Article(**{**a, "published": now_iso()}) for a in json.loads(fixture.read_text(encoding="utf-8"))]
        report = {"sources_total": 0, "sources_en_echec": 0}
    else:
        sources = load_json(settings.sources_path, {})
        articles, report = collect_all(sources, settings.http_timeout)
    run_info.update(report)
    run_info["articles_collectes"] = len(articles)

    fresh = [a for a in filter_recent(articles, settings.max_article_age_hours) if a.id not in seen]
    run_info["articles_nouveaux"] = len(fresh)
    log.info("%d articles collectés, %d nouveaux", len(articles), len(fresh))

    archived = archive_old(ideas, settings.idea_archive_days)
    run_info["idees_archivees"] = archived

    if len(fresh) < settings.min_new_articles:
        run_info["statut"] = "rien de neuf"
        stats["dernier_bilan"] = today_local
        notify.send_daily_report(
            settings.discord_webhook_url, [], run_info, settings.dashboard_url, test=settings.dry_run,
            attachment=dashboard_file(settings, ideas, rejected, stats, run_info, today_local),
        )
        return _finish(settings, stats, ideas, rejected, seen, run_info)

    if settings.daily_cost_limit_usd > 0 and today_cost(stats) >= settings.daily_cost_limit_usd:
        run_info["statut"] = "plafond quotidien atteint"
        maybe_alert(settings, stats, f"plafond de dépense quotidien ({settings.daily_cost_limit_usd} $) atteint, analyse en pause jusqu'à demain.")
        return _finish(settings, stats, ideas, rejected, seen, run_info)

    # 2. Sélection des sujets les plus prometteurs
    candidates = select_for_analysis(fresh, settings.triage_candidates, max_per_source=40)
    run_info["sujets_candidats"] = len(candidates)
    triage_cost = 0.0
    try:
        tri = triage(settings, candidates)
        tin, tout = MODEL_PRICES_USD.get(settings.triage_model, (0.10, 0.50))
        triage_cost = (tri.input_tokens * tin + tri.output_tokens * tout) / 1_000_000
        refs = tri.refs
    except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as exc:
        # Si le tri échoue, on se rabat sur le classement heuristique : rien n'est perdu.
        log.warning("Tri préalable indisponible (%s), classement heuristique utilisé.", exc)
        refs = [c["ref"] for c in candidates]
    items = merge_triage(candidates, refs, settings.always_keep, settings.max_articles_per_run)
    run_info["sujets_analyses"] = len(items)
    run_info["regions_analysees"] = dict(Counter(it.get("region", "monde") for it in items).most_common())

    # 3. Analyse par Claude
    try:
        result = analyze(settings, items, recent_ideas_for_prompt(ideas))
    except anthropic.AuthenticationError:
        run_info["statut"] = "erreur : clé API Claude invalide"
        maybe_alert(settings, stats, "la clé API Claude est invalide ou absente (secret ANTHROPIC_API_KEY).")
        return _finish(settings, stats, ideas, rejected, seen, run_info, failed=True)
    except anthropic.PermissionDeniedError as exc:
        run_info["statut"] = f"erreur : accès refusé ({exc.message[:120]})"
        maybe_alert(settings, stats, f"accès refusé par l'API Claude : {exc.message[:200]}")
        return _finish(settings, stats, ideas, rejected, seen, run_info, failed=True)
    except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as exc:
        msg = getattr(exc, "message", None) or str(exc)
        if "credit" in msg.lower() or "billing" in msg.lower():
            maybe_alert(settings, stats, "crédit API Claude épuisé : recharge ton compte sur platform.claude.com.")
        run_info["statut"] = f"erreur : {msg[:160]}"
        log.error("Analyse impossible : %s", msg)
        return _finish(settings, stats, ideas, rejected, seen, run_info, failed=True)

    price_in, price_out = settings.price()
    cost = triage_cost + (
        result.input_tokens * price_in + result.cache_read_tokens * price_in * 0.1 + result.output_tokens * price_out
    ) / 1_000_000
    run_info.update(
        modele=result.model,
        tokens_entree=result.input_tokens + result.cache_read_tokens,
        tokens_sortie=result.output_tokens,
        cout_usd=round(cost, 4),
    )

    # 4. Traitement : éthique, déduplication, notes
    new_ideas, newly_rejected, reinforced = process_analysis(result.data, items, ideas, settings.max_budget_eur)
    rejected = (newly_rejected + rejected)[:200]
    run_info.update(idees_nouvelles=len(new_ideas), idees_ecartees=len(newly_rejected), renforcements=reinforced)
    if new_ideas and not settings.dry_run:
        try:
            run_info["sources_confirmation"] = corroborate(new_ideas, settings.http_timeout)
        except Exception as exc:  # la vérification est un bonus : elle ne doit jamais faire échouer le bilan
            log.warning("Recherche de sources supplémentaires impossible : %s", exc)

    # Les articles analysés ne seront plus renvoyés à Claude.
    for it in items:
        for aid in it["ids"]:
            seen[aid] = now_iso()
    # Les articles écartés par le tri sont aussi marqués (sinon le lot grossirait sans fin).
    for a in fresh:
        seen.setdefault(a.id, now_iso())

    # 5. Notification Discord (uniquement si des idées pertinentes sont trouvées)
    to_notify = [i for i in new_ideas if i["note_globale"] >= settings.min_score_notify]
    below = [i for i in new_ideas if i["note_globale"] < settings.min_score_notify]
    run_info["idees_notifiees"] = notify.send_daily_report(
        settings.discord_webhook_url, to_notify, run_info, settings.dashboard_url, test=settings.dry_run,
        attachment=dashboard_file(settings, ideas, rejected, stats, run_info, today_local),
        below=below, threshold=settings.min_score_notify, rejected=newly_rejected,
    )
    stats["dernier_bilan"] = today_local

    return _finish(settings, stats, ideas, rejected, seen, run_info)


def _finish(settings, stats, ideas, rejected, seen, run_info, failed: bool = False) -> dict:
    ideas.sort(key=lambda i: (i.get("statut") == "active", i.get("note_globale", 0)), reverse=True)
    stats.setdefault("historique", []).insert(0, run_info)
    stats["historique"] = stats["historique"][:500]
    stats["derniere_execution"] = run_info["date"]
    stats["cout_aujourdhui_usd"] = round(today_cost(stats), 3)
    stats["modele"] = settings.model
    stats["seuil_notification"] = settings.min_score_notify
    stats["budget_max_eur"] = settings.max_budget_eur

    save_json(settings.ideas_path, ideas)
    save_json(settings.rejected_path, rejected)
    save_json(settings.stats_path, stats)
    if not failed:
        save_json(settings.seen_path, seen)
    log.info("Cycle terminé : %s", json.dumps(run_info, ensure_ascii=False))
    return run_info


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    if not settings.dry_run and not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY manquante : ajoute-la dans les secrets du dépôt GitHub.")
    info = run(settings)
    return 1 if info["statut"].startswith("erreur") else 0


if __name__ == "__main__":
    sys.exit(main())
