# 💡 Find-a-Business

Veille automatique de l'actualité mondiale qui détecte des **opportunités de business web rapides à lancer** (site, e-commerce, SaaS) déclenchées par un événement : un conflit, une pénurie, une nouvelle loi, la fermeture d'un grand service, une tendance virale…

- **Toutes les 3 heures**, gratuitement, via GitHub Actions (fréquence réglable).
- **Monde entier, toutes langues** : ~30 médias internationaux, Google News de 31 pays dans leur langue, recherches ciblées, et GDELT (presse de plus de 60 langues).
- **Analyse en deux temps** : Claude Haiku (très bon marché) lit tous les titres et écarte le bruit évident, puis Claude Opus analyse en détail les ~60 sujets retenus. Les 15 sujets les plus repris par les médias passent toujours, même si le tri les écarte.
- **Analyse par Claude** : chaque idée reçoit une note globale et 8 notes détaillées, un budget (jusqu'à 5 000 €), un délai de lancement et un plan d'action.
- **Filtre éthique** : les idées qui exploitent la détresse des victimes (prix abusifs, fausses cagnottes, désinformation…) sont écartées et listées à part, pour transparence.
- **Déduplication** : une idée déjà proposée n'est jamais renvoyée ; si de nouvelles actualités la confirment, elle gagne des « signaux » et un petit bonus de note.
- **Discord** : un message seulement quand une nouvelle idée pertinente est trouvée.
- **Tableau de bord** (GitHub Pages) : filtres, tri par note, favoris, plan d'action à cocher.

👉 **Mise en route : [GUIDE_INSTALLATION.md](GUIDE_INSTALLATION.md)**

## Les notes (0 à 10, toujours « 10 = favorable »)

| Note | Signification de 10 | Poids dans la note globale |
|---|---|---|
| Potentiel | marché et revenus importants | 22 % |
| Fiabilité | événement confirmé, demande évidente | 16 % |
| Durabilité | le besoin restera après l'actualité | 14 % |
| Risque | très faible risque juridique / financier / de réputation | 12 % |
| Coût | presque gratuit (0 = 5 000 €) | 10 % |
| Travail | lançable en un week-end | 10 % |
| Concurrence | quasiment aucun concurrent | 10 % |
| Urgence | à lancer dans les jours qui viennent | 6 % |

Les poids se modifient dans `fab/ideas.py` (`WEIGHTS`).

## Fonctionnement

```
config/sources.json ──► collecte (RSS, Google News, GDELT)
                         │  articles déjà vus ignorés (data/seen_articles.json)
                         ▼
                    regroupement des articles d'un même sujet,
                    priorité aux sujets repris par plusieurs médias
                    et contenant des mots déclencheurs
                         │
                         ▼
                    Claude Haiku : premier tri (≈600 sujets → ~50)
                    + les 15 meilleurs sujets heuristiques toujours gardés
                         │
                         ▼
                    Claude Opus : idées + notes + plan + avis éthique
                         │
                         ▼
          filtre éthique, budget, sources vérifiables, déduplication
                         │
             ┌───────────┴────────────┐
             ▼                        ▼
   docs/data/*.json            Discord (si note ≥ seuil)
   = tableau de bord
```

| Fichier | Rôle |
|---|---|
| `fab/collect.py` | Téléchargement et nettoyage des actualités |
| `fab/selection.py` | Regroupement et choix des sujets envoyés à Claude |
| `fab/analyze.py` | Consigne donnée à Claude et format de réponse |
| `fab/ideas.py` | Notes, filtre éthique, déduplication, archivage (30 jours sans nouvelle) |
| `fab/notify.py` | Messages Discord |
| `fab/main.py` | Enchaînement d'un passage complet |
| `docs/index.html` | Tableau de bord |
| `.github/workflows/veille.yml` | Planification toutes les 3 h + publication du tableau de bord |

## Lancer en local (facultatif)

```bash
pip install -r requirements-dev.txt
python -m pytest -q                 # tests
FAB_DRY_RUN=1 python -m fab.main    # passage de démonstration, sans appel à Claude
ANTHROPIC_API_KEY=sk-ant-... DISCORD_WEBHOOK_URL=https://... python -m fab.main
```
