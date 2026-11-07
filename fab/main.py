"""Point d'entrée : le bilan quotidien (lancé chaque matin par GitHub Actions).

    python -m fab.main
"""

from __future__ import annotations

import json
from collections import Counter
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import anthropic

from . import notify
from .analyze import SYSTEM_PROMPT, analyze, build_user_message, triage
from .collect import Article, collect_all, filter_recent
from .config import MODEL_PRICES_USD, ROOT, Settings
from .corroborate import corroborate
from .ideas import archive_old, now_iso, process_analysis, recent_ideas_for_prompt, rescore
from .report import build_standalone_dashboard
from .selection import merge_triage, select_for_analysis, split_batches
from .storage import load_json, prune_seen, save_json

log = logging.getLogger("fab")

# Analyse en lots : sortie maximale d'un lot et échéance après laquelle aucun nouveau lot ne démarre
# (le workflow est coupé à 50 min ; s'il coupait, rien ne serait sauvegardé).
BATCH_MAX_TOKENS = 32000
BATCH_DEADLINE_S = 25 * 60
clock = time.monotonic  # remplacée dans les tests


def batch_max_cost(settings: Settings, items: list[dict], existing: list[dict], max_tokens: int = BATCH_MAX_TOKENS) -> float:
    """Coût maximal d'un lot : entrée estimée (prudemment, 3 caractères par token) + sortie maximale."""
    price_in, price_out = settings.price()
    est_in = len(SYSTEM_PROMPT + build_user_message(items, existing)) / 3
    return (est_in * price_in + max_tokens * price_out) / 1_000_000


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


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
    started = clock()
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
    # Recalcul gratuit (sans Claude) des notes globales des idées actives si la formule a changé.
    run_info["idees_renotees"] = rescore(ideas)

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
    # Mode test : un seul lot (la réponse simulée renverrait sinon les mêmes idées à chaque lot).
    batches = split_batches(items, 1 if settings.dry_run else settings.analysis_batches)

    # 3. Analyse par Claude, lot après lot. Chaque lot voit les idées des lots précédents (ajoutées à `ideas`).
    price_in, price_out = settings.price()
    spent = triage_cost
    tokens_in = tokens_out = reinforced = 0
    new_ideas: list[dict] = []
    newly_rejected: list[dict] = []
    analysed: list[dict] = []
    lots: list[dict] = []
    stop = ""  # raison de l'arrêt des lots restants
    fatal: tuple[str, str] | None = None  # (statut, alerte) : clé invalide, accès refusé, crédit épuisé
    last_error = ""
    model = ""
    for batch in batches:
        lot = {"sujets": len(batch), "idees": 0, "cout_usd": 0.0, "statut": "non analysé"}
        lots.append(lot)
        if stop:
            lot["statut"] = f"non analysé ({stop})"
            continue
        existing = recent_ideas_for_prompt(ideas)
        if clock() - started > BATCH_DEADLINE_S:
            stop = "échéance"
        elif not settings.dry_run and settings.daily_cost_limit_usd > 0 and (
            today_cost(stats) + spent + batch_max_cost(settings, batch, existing) > settings.daily_cost_limit_usd
        ):
            stop = "plafond"
        if stop:
            log.warning("Lots restants non analysés : %s.", stop)
            lot["statut"] = f"non analysé ({stop})"
            continue
        try:
            result = analyze(settings, batch, existing, max_tokens=BATCH_MAX_TOKENS)
        except anthropic.AuthenticationError:
            fatal = ("erreur : clé API Claude invalide", "la clé API Claude est invalide ou absente (secret ANTHROPIC_API_KEY).")
        except anthropic.PermissionDeniedError as exc:
            fatal = (f"erreur : accès refusé ({exc.message[:120]})", f"accès refusé par l'API Claude : {exc.message[:200]}")
        except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as exc:
            msg = getattr(exc, "message", None) or str(exc)
            log.error("Analyse d'un lot impossible : %s", msg)
            last_error = msg
            if "credit" in msg.lower() or "billing" in msg.lower():
                fatal = (f"erreur : {msg[:160]}", "crédit API Claude épuisé : recharge ton compte sur platform.claude.com.")
            else:
                lot["statut"] = f"échec : {msg[:120]}"
                continue
        if fatal:
            stop = "arrêt"
            lot["statut"] = fatal[0].replace("erreur", "échec", 1)
            continue

        cost = (result.input_tokens * price_in + result.cache_read_tokens * price_in * 0.1
                + result.output_tokens * price_out) / 1_000_000
        spent += cost
        tokens_in += result.input_tokens + result.cache_read_tokens
        tokens_out += result.output_tokens
        model = result.model
        # 4. Traitement : éthique, déduplication, notes
        batch_new, batch_rejected, batch_reinforced = process_analysis(result.data, batch, ideas, settings.max_budget_eur)
        new_ideas += batch_new
        newly_rejected += batch_rejected
        reinforced += batch_reinforced
        analysed += batch
        lot.update(idees=len(batch_new), cout_usd=round(cost, 4), statut="ok")

    run_info["lots"] = lots
    run_info["sujets_analyses"] = len(analysed)
    run_info["regions_analysees"] = dict(Counter(it.get("region", "monde") for it in analysed).most_common())
    run_info["cout_usd"] = round(spent, 4)
    if fatal:
        maybe_alert(settings, stats, fatal[1])
    failed_lots = sum(1 for lot in lots if lot["statut"] != "ok")
    if not analysed:
        if fatal:
            run_info["statut"] = fatal[0]
        elif stop == "plafond" and not last_error:
            run_info["statut"] = "plafond quotidien atteint"
            maybe_alert(settings, stats, f"plafond de dépense quotidien ({settings.daily_cost_limit_usd} $) atteint, analyse en pause jusqu'à demain.")
            return _finish(settings, stats, ideas, rejected, seen, run_info)
        else:
            reason = last_error or (f"aucun lot analysé ({stop})" if stop else "aucun sujet à analyser")
            run_info["statut"] = f"erreur : {reason[:160]}"
        return _finish(settings, stats, ideas, rejected, seen, run_info, failed=True)
    if failed_lots:
        run_info["statut"] = f"partiel : {_plural(failed_lots, 'lot')} sur {len(lots)} en échec ou non analysé{'s' if failed_lots > 1 else ''}"

    run_info.update(modele=model, tokens_entree=tokens_in, tokens_sortie=tokens_out)
    rejected = (newly_rejected + rejected)[:200]
    run_info.update(idees_nouvelles=len(new_ideas), idees_ecartees=len(newly_rejected), renforcements=reinforced)
    if new_ideas and not settings.dry_run:
        try:
            run_info["sources_confirmation"] = corroborate(new_ideas, settings.http_timeout)
        except Exception as exc:  # la vérification est un bonus : elle ne doit jamais faire échouer le bilan
            log.warning("Recherche de sources supplémentaires impossible : %s", exc)

    # Les articles analysés ne seront plus renvoyés à Claude. Ceux des lots non analysés restent libres :
    # ils pourront revenir le lendemain s'ils sont encore assez récents.
    skipped = {aid for batch, lot in zip(batches, lots) if lot["statut"] != "ok" for it in batch for aid in it["ids"]}
    for it in analysed:
        for aid in it["ids"]:
            seen[aid] = now_iso()
    # Les articles écartés par le tri sont aussi marqués (sinon le lot grossirait sans fin).
    for a in fresh:
        if a.id not in skipped:
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
