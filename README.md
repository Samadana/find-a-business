# 💡 Find-a-Business

Veille automatique de l'actualité mondiale qui détecte des **opportunités de business rapides à lancer**, en ligne (site, e-commerce, SaaS) ou sur place (commerce, service local, import, restauration…), déclenchées par un événement : un conflit, une pénurie, une nouvelle loi, la fermeture d'un grand service, une tendance virale…

- **Un bilan par jour, lancé à la main** depuis l'application (bouton « Lancer un bilan ») ou l'onglet Actions de GitHub. Le planning automatique de GitHub a été retiré : il sautait trop de déclenchements.
- **Monde entier, toutes langues** : ~70 médias de tous les continents (Afrique, Asie, Amérique latine, Moyen-Orient, Océanie…), Google News de 31 pays dans leur langue, Google Trends de 24 pays, 17 recherches ciblées en 12 langues, Product Hunt, journaux officiels (UE, États-Unis) et GDELT quand il répond. La sélection alterne les régions : aucune ne dépasse 30 % des sujets analysés.
- **Idées sourcées** : chaque idée reprend tous les médias qui couvrent l'événement, puis une recherche gratuite ajoute jusqu'à 5 médias qui le confirment.
- **Analyse en deux temps** : Claude Haiku (très bon marché) lit tous les titres et écarte le bruit évident, puis Claude Opus analyse en profondeur (réflexion poussée) jusqu'à 240 sujets retenus, en 3 lots de 80 qui mélangent toutes les régions. Les 40 sujets les plus repris par les médias passent toujours, même si le tri les écarte.
- **Analyse par Claude** : chaque idée reçoit une note globale et 8 notes détaillées, un budget (sans plafond ; l'abonnement à l'IA de développement y figure, jamais de développeur freelance), un délai de lancement et un plan d'action.
- **Filtre éthique** : les idées qui exploitent la détresse des victimes (prix abusifs, fausses cagnottes, désinformation…) sont écartées et listées à part, pour transparence.
- **Déduplication** : une idée déjà proposée n'est jamais renvoyée ; si de nouvelles actualités la confirment, elle gagne des « signaux » et un petit bonus de note.
- **Discord** : un bilan chaque matin. Chaque idée est détaillée en 4 cartes : le projet, l'événement déclencheur et son contexte, les 8 notes expliquées, le travail à accomplir (étapes, budget poste par poste, concurrents, risques).
- **Application locale (Windows)** : un double-clic sur `Lancer Find-a-Business.bat` ouvre le tableau de bord dans le navigateur. Bouton pour lancer un bilan à la demande, statut et notes perso pour chaque idée, réglages (note minimale, modèle, plafond de dépense), coûts jour par jour.

👉 **Mise en route : [GUIDE_INSTALLATION.md](GUIDE_INSTALLATION.md)**

## Les notes (0 à 10, toujours « 10 = favorable »)

| Note | Signification de 10 | Poids dans la note globale |
|---|---|---|
| Potentiel | 20 000 € ou plus par mois après 12 mois | 24 % |
| Urgence + durabilité (« timing ») | fenêtre de quelques jours / besoin permanent | 20 % |
| Fiabilité | fait officiel, plusieurs médias, demande déjà visible | 14 % |
| Coût | presque gratuit (5 = 5 000 €, 0 = 100 000 €) | 11 % |
| Risque | rien de notable (mise perdue < 500 €) | 11 % |
| Concurrence | aucun acteur | 10 % |
| Travail | lançable en un week-end | 10 % |

Urgence et durabilité s'opposent presque toujours : elles comptent ensemble pour 20 % sous forme de « timing »
= 0,7 × la meilleure des deux + 0,3 × l'autre. Une idée urgente ou durable n'est donc pas pénalisée.
Bonus : + 0,1 par actualité supplémentaire qui confirme l'idée (au plus + 0,5).
Les repères chiffrés de chaque note sont dans la consigne (`fab/analyze.py`). Les poids se modifient dans `fab/ideas.py`
(`WEIGHTS` et `TIMING_WEIGHT`). Quand la formule change, le bilan suivant recalcule la note globale des idées actives.

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
                    Claude Haiku : premier tri (≈1 500 sujets → ~200)
                    + les 40 meilleurs sujets heuristiques toujours gardés
                         │
                         ▼
                    Claude Opus, en 3 lots : idées + notes + plan + avis éthique
                    (≈1,00 à 1,60 $ par jour, plafond 2,50 $)
                         │
                         ▼
          filtre éthique, budget, sources vérifiables, déduplication
                         │
             ┌───────────┴────────────┐
             ▼                        ▼
   docs/data/*.json            Discord : bilan du matin détaillé
   (lu par l'application)
```

| Fichier | Rôle |
|---|---|
| `fab/collect.py` | Téléchargement et nettoyage des actualités |
| `fab/selection.py` | Regroupement et choix des sujets envoyés à Claude |
| `fab/analyze.py` | Consigne donnée à Claude et format de réponse |
| `fab/ideas.py` | Notes, filtre éthique, déduplication, archivage (30 jours sans nouvelle) |
| `fab/notify.py` | Messages Discord |
| `fab/main.py` | Enchaînement d'un passage complet |
| `app/serveur.py`, `app/static/index.html` | Application locale (tableau de bord et pilotage) |
| `Lancer Find-a-Business.bat` | Lancement de l'application en double-clic (installe Python si besoin) |
| `docs/index.html`, `fab/report.py` | Ancien tableau de bord HTML (facultatif) |
| `.github/workflows/veille.yml` | Bilan lancé à la main (bouton de l'application ou Actions → Run workflow) |
| `data/suivi.json` | Statuts et notes perso saisis dans l'application |

## Lancer en local (facultatif)

```bash
pip install -r requirements-dev.txt
python -m pytest -q                 # tests
FAB_DRY_RUN=1 python -m fab.main    # passage de démonstration, sans appel à Claude
ANTHROPIC_API_KEY=sk-ant-... DISCORD_WEBHOOK_URL=https://... python -m fab.main
```
