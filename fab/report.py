"""Tableau de bord autonome : un seul fichier HTML avec les données intégrées.

Il est joint au bilan Discord, ce qui permet de garder le dépôt privé
(GitHub Pages n'est gratuit que pour les dépôts publics).
"""

from __future__ import annotations

import json

from .config import ROOT

MARKER = "<script>\nconst LABELS"


def build_standalone_dashboard(ideas: list[dict], rejected: list[dict], stats: dict) -> bytes:
    template = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    data = json.dumps({"ideas": ideas, "rejected": rejected, "stats": stats}, ensure_ascii=False)
    data = data.replace("</", "<\\/")  # empêche de fermer la balise <script> depuis les données
    inject = f"<script>window.FAB_DATA = {data};</script>\n"
    if MARKER not in template:
        raise ValueError("Modèle de tableau de bord inattendu")
    return template.replace(MARKER, inject + MARKER, 1).encode("utf-8")
