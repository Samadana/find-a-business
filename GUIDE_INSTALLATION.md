# Guide d'installation pas à pas

Compte environ 25 minutes. Le bilan tourne sur GitHub (ton ordinateur peut rester éteint) ; seule la petite application de suivi s'installe sur ton PC Windows.

Ce dont tu as besoin à la fin :

| Élément | Où | Coût |
|---|---|---|
| Le dépôt GitHub avec ce code | github.com | gratuit (dépôt **privé**) |
| Une clé API Claude | platform.claude.com | payant à l'usage (voir § Coûts) |
| Un webhook Discord | ton serveur Discord | gratuit |
| L'application de suivi | ton PC Windows | gratuit |

---

## Étape 1 · Le dépôt GitHub (privé)

Le dépôt `Samadana/find-a-business` existe déjà et contient le code. Pour que personne d'autre que toi ne voie les idées, passe-le en privé :

1. Ouvre <https://github.com/Samadana/find-a-business/settings>.
2. Descends tout en bas, jusqu'à la zone rouge **Danger Zone**.
3. **Change visibility** → **Change to private** → confirme.

C'est gratuit : un bilan par jour utilise environ 10 minutes de GitHub Actions par jour, loin de la limite gratuite de 2 000 minutes par mois des dépôts privés.

## Étape 2 · Créer ta clé API Claude

1. Va sur <https://platform.claude.com> (l'ancienne adresse console.anthropic.com y redirige) et crée un compte (e-mail ou Google).
2. Menu **Billing** (Facturation) : ajoute un moyen de paiement et achète des crédits. **Commence par 10 $** : c'est environ une semaine à un mois d'utilisation selon le modèle choisi (voir § Coûts).
   - Recommandé : dans **Billing**, désactive la recharge automatique (*auto-reload*) au début, pour ne jamais dépenser plus que prévu.
   - Dans **Limits**, tu peux aussi fixer une limite de dépense mensuelle.
3. Menu **API Keys** → **Create Key** → nomme-la `find-a-business` → **Create**.
4. **Copie la clé tout de suite** (elle commence par `sk-ant-…`) : elle ne sera plus jamais affichée. Ne la partage avec personne et ne la colle jamais dans un fichier du dépôt.

## Étape 3 · Créer le webhook Discord

1. Dans Discord, crée un serveur si tu n'en as pas (bouton **+** à gauche → *Créer le mien* → *Pour moi et mes amis*).
2. Crée un salon texte, par exemple `#opportunités`.
3. Survole le salon → ⚙️ **Modifier le salon** → **Intégrations** → **Webhooks** → **Nouveau webhook**.
4. Donne-lui un nom (`Find-a-Business`), puis **Copier l'URL du webhook**. Elle ressemble à `https://discord.com/api/webhooks/123…/abc…`.
5. Active les notifications du salon sur ton téléphone (appui long sur le salon → *Paramètres de notification* → *Tous les messages*).

## Étape 4 · Ajouter les secrets dans GitHub

Les secrets sont chiffrés par GitHub : personne ne peut les lire, pas même toi après les avoir enregistrés.

1. Dans ton dépôt : **Settings** → **Secrets and variables** → **Actions**.
2. Onglet **Secrets** → **New repository secret** :
   - Name : `ANTHROPIC_API_KEY` · Secret : ta clé `sk-ant-…` → **Add secret**
3. Encore **New repository secret** :
   - Name : `DISCORD_WEBHOOK_URL` · Secret : l'URL du webhook → **Add secret**

## Étape 5 · L'application sur ton ordinateur (tableau de bord)

L'application affiche toutes les idées en détail et te permet de les piloter : bouton **▶ Lancer un bilan** (bilan complet ou test gratuit), statut de chaque idée (à étudier, en cours, lancée, abandonnée), notes perso, réglages (note minimale, modèle Claude, plafond de dépense) et coûts jour par jour. Elle tourne uniquement sur ton ordinateur et lit ton dépôt privé.

**A. Récupérer l'application**

1. Télécharge `Find-a-Business-App.zip` (fourni avec ce guide), puis clic droit → **Extraire tout…** → choisis par exemple `Documents\Find-a-Business`.
2. Double-clique sur **Lancer Find-a-Business.bat**.
   - Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires** → **Exécuter quand même** (le fichier est un simple script texte, tu peux l'ouvrir avec le Bloc-notes pour le lire).
   - Si Python n'est pas installé, le script te propose de l'installer (tape **O**). C'est l'installateur officiel de Python, via l'outil de Microsoft (`winget`). Ensuite relance le `.bat`.
3. Ton navigateur s'ouvre sur `http://127.0.0.1:8765`. Garde la fenêtre noire ouverte pendant que tu utilises l'application ; ferme-la pour arrêter.

**B. Créer la clé GitHub de l'application (une seule fois)**

1. Ouvre <https://github.com/settings/personal-access-tokens/new>.
2. **Token name** : `find-a-business-app` · **Expiration** : 1 an.
3. **Repository access** : *Only select repositories* → choisis `find-a-business`.
4. **Permissions** → **+ Add permissions** (section *Repositories*) → coche **Actions**, **Contents** et **Variables**. Chacune s'ajoute en *Read-only* : clique sur ce menu et choisis **Read and write**, pour les trois. (*Metadata* passe seul en *Read-only*, c'est normal.) Ne touche à rien d'autre.
5. **Generate token**, copie la clé (`github_pat_…`) et colle-la dans l'écran d'accueil de l'application → **Enregistrer et continuer**.

Cette clé ne donne accès qu'à ce dépôt. Elle est enregistrée uniquement sur ton ordinateur (`%APPDATA%\FindABusiness`). Si un jour elle expire, crée-en une nouvelle et colle-la dans **Réglages → Clé GitHub**.

*Astuce : clic droit sur le `.bat` → **Envoyer vers** → **Bureau (créer un raccourci)** pour le lancer depuis ton bureau.*

## Étape 6 · Premier lancement

1. Onglet **Actions** du dépôt. Si GitHub demande d'activer les workflows, clique sur le bouton vert.
2. Le plus simple : dans l'application, bouton **▶ Lancer un bilan**. (Sinon, sur GitHub : **Bilan quotidien des opportunités** → **Run workflow**.)
3. **Premier essai conseillé : choisis « Test gratuit »** (sur GitHub : coche « Mode test »). Ce mode n'appelle pas Claude et ne coûte rien ; il vérifie que tout est bien branché. Tu dois recevoir sur Discord un message marqué 🧪 **TEST** avec deux idées fictives détaillées. *(Ces idées fictives ne sont pas sauvegardées.)*
4. Relance ensuite en choisissant **Lancer le bilan complet**. L'application affiche « Bilan en cours » ; au bout de 5 à 10 minutes, tu reçois le bilan sur Discord et les idées apparaissent toutes seules dans l'application.
5. **Lancer le bilan du jour** : chaque jour, clique sur **▶ Lancer un bilan** dans l'application, ou sur GitHub : onglet **Actions** → **Bilan quotidien des opportunités** → **Run workflow** (laisse « Mode test » décoché). Le bilan arrive sur Discord en 10 à 20 minutes. Il n'y a plus de lancement automatique : le planning de GitHub sautait trop souvent des déclenchements.

### Ce que contient le bilan Discord

Un message d'en-tête (nombre de sujets analysés, idées trouvées, coût du jour), puis pour chaque idée au-dessus de la note minimale :

- 💡 **Le projet** : note globale, résumé, description détaillée (fonctionnement, parcours client, acquisition, chiffre d'affaires possible), type, budget, délai, fenêtre d'opportunité, pays, cible, modèle de revenus ;
- 📰 **L'événement déclencheur** : ce qui s'est passé, le contexte, pourquoi c'est le bon moment, et les articles sources (liens) ;
- 📊 **Les 8 notes expliquées** : pour chaque note, la valeur et la justification en 2 ou 3 phrases ;
- 🛠️ **Le travail à accomplir** : étapes numérotées avec outils et durées, budget détaillé poste par poste, concurrents, risques et parades, avis global et avis éthique.

✅ Vérification : l'onglet **Coûts** de l'application liste chaque jour de bilan avec son coût.

---

## Réglages optionnels

Le seuil, le modèle et le plafond se règlent dans l'onglet **Réglages** de l'application. Les autres se règlent sur GitHub : **Settings → Secrets and variables → Actions → onglet « Variables » → New repository variable**

| Variable | Défaut | Rôle |
|---|---|---|
| `FAB_MIN_SCORE_NOTIFY` | `6.0` | Note globale minimale pour qu'une idée soit détaillée dans le bilan Discord |
| `FAB_REPORT_HOUR` | `9` | Heure du bilan (heure de Paris) ; pense aussi à adapter la ligne `cron` |
| `FAB_MODEL` | `claude-opus-5-5` | Modèle Claude. `claude-sonnet-5-5` coûte 2× moins, `claude-haiku-5-5` ~40× moins (analyses moins fines) |
| `FAB_EFFORT` | `high` | Profondeur de réflexion : `low`, `medium`, `high` (plus cher, plus fin) |
| `FAB_DAILY_COST_LIMIT_USD` | `2.5` | Plafond de dépense API par jour. Au-delà, l'analyse se met en pause jusqu'au lendemain (et tu es prévenu sur Discord). `0` = pas de plafond |
| `FAB_MAX_ARTICLES` | `240` | Nombre maximum de sujets envoyés à l'analyse finale par passage (tous lots confondus) |
| `FAB_ANALYSIS_BATCHES` | `3` | Nombre de lots (appels successifs) entre lesquels ces sujets sont répartis ; chaque lot mélange toutes les régions |
| `FAB_TRIAGE_MODEL` | `claude-haiku-5-5` | Modèle du premier tri (bon marché) |
| `FAB_ALWAYS_KEEP` | `40` | Sujets les plus repris par les médias, toujours envoyés à l'analyse finale |
| `FAB_MAX_BUDGET_EUR` | `5000` | Budget de lancement maximum d'une idée |
| `FAB_ATTACH_DASHBOARD` | `false` | Joindre en plus un tableau de bord HTML au bilan Discord |
| `FAB_PAGES` | `false` | Tableau de bord en ligne via GitHub Pages (dépôt public uniquement) |

Les sources d'actualité sont dans `config/sources.json` : tu peux ajouter un flux RSS ou un pays Google News en modifiant ce fichier directement sur GitHub (icône crayon).

## Coûts

- **GitHub et Discord : 0 €.**
- **API Claude** : c'est le seul coût, **un passage par jour** en deux temps :

| Étape | Lu par le modèle | Écrit par le modèle | Prix (par million de tokens) | Coût |
|---|---|---|---|---|
| 1. Tri de ~1 500 titres par Claude Haiku | ~68 000 tokens | ~3 000 tokens | 0,10 $ lu / 0,50 $ écrit | ~0,01 $ |
| 2. Analyse approfondie de ~240 sujets par Claude Opus 5.5, en 3 lots de 80 | ~3 × 22 000 tokens | 30 000 à 63 000 tokens (réflexion + idées détaillées) | 4 $ lu / 20 $ écrit | 0,86 à 1,56 $ |
| **Total par jour** | | | | **~1,00 à 1,60 $** |

- Soit environ **30 à 48 $ par mois**, pour 8 à 15 idées par jour. Avec Claude Sonnet 5.5 (à choisir dans **Réglages** de l'application, 2 $ / 10 $) : ~0,50 à 0,80 $ par jour, soit 15 à 24 $ par mois.
- Les idées sont désormais expliquées en détail (contexte, notes justifiées, plan chiffré) : c'est ce qui augmente un peu le coût par rapport à la première version.
- Un « token » vaut environ ¾ de mot. L'essentiel du coût vient de ce que le modèle écrit (sa réflexion et les idées) : l'écriture coûte 5 fois plus cher que la lecture.
- Le plafond `FAB_DAILY_COST_LIMIT_USD` (2,5 $/jour par défaut) bloque tout appel à Claude au-delà, jusqu'au lendemain : avant chaque lot, le bilan vérifie que le coût maximal du lot tient encore sous le plafond. Pour une garantie totale, fixe aussi une limite dans **Limits** sur platform.claude.com et n'achète que 5 ou 10 $ de crédits, sans recharge automatique.
- Le détail réel (tokens et coût de chaque bilan) est visible dans l'onglet **Coûts** de l'application, et par jour et par modèle dans **Usage / Cost** sur platform.claude.com. Ce sont des estimations tant qu'aucun vrai bilan n'a tourné.

**Limite à connaître** : avec un seul passage par jour, le bilan voit ce que les sources affichent au moment où tu le lances. Les flux RSS ne gardent que leurs derniers articles, donc certaines actualités de la nuit peuvent échapper au bilan. GDELT et les recherches Google News couvrent bien les 24 dernières heures et compensent en grande partie.

## En cas de problème

| Symptôme | Solution |
|---|---|
| Message Discord « clé API Claude invalide » | Recrée une clé (étape 2) et remplace le secret `ANTHROPIC_API_KEY` |
| Message « crédit épuisé » | Recharge tes crédits dans **Billing** sur platform.claude.com |
| Aucune notification | Normal si aucune idée ne dépasse la note minimale. Regarde l'application, ou baisse la note minimale dans **Réglages** |
| Le bilan n'arrive pas sur Discord | Vérifie que « Mode test » était décoché au lancement, puis regarde l'exécution dans l'onglet Actions. Si le workflow est grisé : onglet Actions → **Enable workflow** |
| L'application dit « Accès refusé par GitHub » ou « ne permet pas encore de lancer un bilan » | La clé n'a pas les bons droits : sur <https://github.com/settings/personal-access-tokens>, clique sur ta clé → **Edit**, et mets **Actions**, **Contents** et **Variables** en *Read and write* sur `find-a-business` (la clé reste la même, rien à recoller) |
| Le `.bat` se ferme tout de suite | Clic droit → Modifier pour vérifier qu'il est bien dans le dossier extrait (à côté du dossier `app`), puis relance |
| Un passage est en rouge dans Actions | Clique dessus pour voir le journal ; les erreurs sont en français |
