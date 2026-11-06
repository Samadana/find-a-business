# CLAUDE.md : Find-a-Business (le détecteur)

Ce dépôt détecte des idées de business dans l'actualité mondiale. Il les publie dans `docs/data/ideas.json`, lu par le site SeedFox (`Samadana/seedfox`), et envoie un bilan sur Discord. Pour le fonctionnement et le rôle de chaque fichier, voir `README.md`.

## Avec Marty (le propriétaire)

- Réponds en français, de façon concise.
- Ne lance, ne publie et ne fusionne rien sans son feu vert explicite. Une PR n'est fusionnée que sur sa demande, une fois la CI verte.
- **Ne lance jamais le bilan payant `veille.yml` à la main.** Cloud Scheduler `seedfox-detecteur` le déclenche chaque jour à 7 h 30 ; un lancement en plus coûte en double. Le mode test (`dry_run`) est gratuit.
- Ne demande jamais de secret (clé Anthropic, webhook Discord) et n'en écris aucun dans le code, le chat ou les logs. Ils vivent dans les secrets GitHub.

## Commandes

```bash
pip install -r requirements-dev.txt
python -m pytest -q                 # c'est aussi la CI (tests.yml)
FAB_DRY_RUN=1 python -m fab.main    # passage de démonstration, sans appel à Claude
```

## Règles métier (à respecter dans la consigne et les filtres)

- Les idées couvrent tous les types de business (web, local, import, production, événementiel…), dans le monde entier, avec le pays visé.
- Le champ `realisable_en_ligne` est obligatoire.
- Les idées sont rédigées en anglais ; SeedFox les traduit.
- Une personne seule, 60 jours pour une idée numérique, 90 jours sinon.
- **Budget :**
  - Le développement est fait avec une IA de développement : compte l'abonnement à l'IA, jamais un freelance ou une agence.
  - `strip_dev_costs` (`fab/ideas.py`) retire les coûts de développement, sauf les lignes d'abonnement à une IA (`AI_TOOL_RE`).
  - Il n'y a pas de budget maximum : `FAB_MAX_BUDGET_EUR` vaut 0, ce qui veut dire « sans limite ».
- **Sources :** au plus 30 % par région dans la sélection finale. GDELT est abandonné, car il est bloqué depuis les serveurs de GitHub.
- **Suivi :** les statuts et notes de Marty (`data/suivi.json`) ne doivent jamais influencer les idées suivantes.

## Pièges

- Avant de changer le format d'une idée (champs, noms, types), vérifie que SeedFox le lit encore : voir `DetectorIdea` et `IdeaImporter` dans le dépôt `seedfox`.
- Les fichiers `data/` et `docs/data/` sont écrits par le workflow. Ne les modifie pas à la main dans une PR.
- Le coût par jour est plafonné par `FAB_DAILY_COST_LIMIT_USD`. Les prix des modèles sont dans `MODEL_PRICES_USD` (`fab/config.py`).
