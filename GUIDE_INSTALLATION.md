# Guide d'installation pas à pas

Compte environ 20 minutes. Tu n'as rien à installer sur ton ordinateur : tout se fait depuis ton navigateur.

Ce dont tu as besoin à la fin :

| Élément | Où | Coût |
|---|---|---|
| Le dépôt GitHub avec ce code | github.com | gratuit (dépôt **public**) |
| Une clé API Claude | platform.claude.com | payant à l'usage (voir § Coûts) |
| Un webhook Discord | ton serveur Discord | gratuit |

---

## Étape 1 · Le dépôt GitHub

1. Va sur <https://github.com/new>.
2. Nom du dépôt : `find-a-business` (ou ce que tu veux).
3. Choisis **Public** : GitHub Actions et GitHub Pages sont alors gratuits et illimités pour ce projet.
   *(En privé, GitHub Pages demande un abonnement payant.)*
4. Ne coche rien d'autre, clique sur **Create repository**.
5. Le code y est envoyé (par Claude, ou par toi via **Add file → Upload files** en glissant le contenu du dossier).

> Le dépôt public rend visibles les idées détectées. Si tu veux les garder pour toi, dis-le : on peut passer en dépôt privé + tableau de bord hébergé ailleurs gratuitement (Cloudflare Pages par exemple).

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

Les secrets sont chiffrés par GitHub : personne ne peut les lire, même dans un dépôt public.

1. Dans ton dépôt : **Settings** → **Secrets and variables** → **Actions**.
2. Onglet **Secrets** → **New repository secret** :
   - Name : `ANTHROPIC_API_KEY` · Secret : ta clé `sk-ant-…` → **Add secret**
3. Encore **New repository secret** :
   - Name : `DISCORD_WEBHOOK_URL` · Secret : l'URL du webhook → **Add secret**

## Étape 5 · Activer le tableau de bord (GitHub Pages)

1. **Settings** → **Pages**.
2. Sous **Build and deployment** → **Source**, choisis **GitHub Actions**.
3. C'est tout : le tableau de bord sera publié à chaque passage, à l'adresse `https://TON-PSEUDO.github.io/find-a-business/`.

## Étape 6 · Premier lancement

1. Onglet **Actions** du dépôt. Si GitHub demande d'activer les workflows, clique sur le bouton vert.
2. Clique sur **Bilan quotidien des opportunités** → **Run workflow**.
3. **Premier essai conseillé : coche « Mode test »** → **Run workflow**. Ce mode n'appelle pas Claude et ne coûte rien ; il vérifie que tout est bien branché et publie un tableau de bord d'exemple. Tu dois recevoir sur Discord un message marqué 🧪 **TEST** : le webhook fonctionne. *(Ces idées fictives ne sont pas sauvegardées.)*
4. Relance ensuite **sans** cocher le mode test. Au bout de 3 à 8 minutes :
   - le tableau de bord affiche les premières idées ;
   - tu reçois le bilan sur Discord : le détail des idées qui dépassent 6,5/10 (réglable), ou un court message s'il n'y en a pas.
5. **Activer le bilan automatique de 9 h** (désactivé par défaut) : ouvre le fichier `.github/workflows/veille.yml` sur GitHub → icône crayon ✏️ → supprime le `#` au début des deux lignes `# schedule:` et `#   - cron: …` (garde l'alignement : `schedule:` sous `on:` avec 2 espaces, `- cron` avec 4) → **Commit changes**.
   Ensuite, le bilan arrive seul **chaque matin vers 9 h** (heure de Paris, été comme hiver ; GitHub peut le décaler de quelques minutes), sans que ton ordinateur soit allumé. Tu peux aussi lancer un bilan à tout moment avec **Run workflow**. Pour l'arrêter : onglet **Actions** → **Bilan quotidien des opportunités** → **⋯** → **Disable workflow**.

✅ Vérification : l'onglet **Activité** du tableau de bord liste chaque passage avec son statut et son coût.

---

## Réglages optionnels

**Settings → Secrets and variables → Actions → onglet « Variables » → New repository variable**

| Variable | Défaut | Rôle |
|---|---|---|
| `FAB_MIN_SCORE_NOTIFY` | `6.5` | Note globale minimale pour qu'une idée soit détaillée dans le bilan Discord |
| `FAB_REPORT_HOUR` | `9` | Heure du bilan (heure de Paris) ; pense aussi à adapter la ligne `cron` |
| `FAB_MODEL` | `claude-opus-5-5` | Modèle Claude. `claude-sonnet-5-5` coûte 2× moins, `claude-haiku-5-5` ~40× moins (analyses moins fines) |
| `FAB_EFFORT` | `high` | Profondeur de réflexion : `low`, `medium`, `high` (plus cher, plus fin) |
| `FAB_DAILY_COST_LIMIT_USD` | `2` | Plafond de dépense API par jour. Au-delà, l'analyse se met en pause jusqu'au lendemain (et tu es prévenu sur Discord). `0` = pas de plafond |
| `FAB_MAX_ARTICLES` | `150` | Nombre maximum de sujets envoyés à l'analyse finale par passage |
| `FAB_TRIAGE_MODEL` | `claude-haiku-5-5` | Modèle du premier tri (bon marché) |
| `FAB_ALWAYS_KEEP` | `25` | Sujets les plus repris par les médias, toujours envoyés à l'analyse finale |
| `FAB_MAX_BUDGET_EUR` | `5000` | Budget de lancement maximum d'une idée |
| `DASHBOARD_URL` | auto | Adresse du tableau de bord si tu utilises un domaine personnalisé |

Les sources d'actualité sont dans `config/sources.json` : tu peux ajouter un flux RSS ou un pays Google News en modifiant ce fichier directement sur GitHub (icône crayon).

## Coûts

- **GitHub et Discord : 0 €.**
- **API Claude** : c'est le seul coût, **un passage par jour** en deux temps :

| Étape | Lu par le modèle | Écrit par le modèle | Prix (par million de tokens) | Coût |
|---|---|---|---|---|
| 1. Tri de ~1 500 titres par Claude Haiku | ~68 000 tokens | ~3 000 tokens | 0,10 $ lu / 0,50 $ écrit | ~0,01 $ |
| 2. Analyse approfondie de ~150 sujets par Claude Opus 5.5 | ~19 000 tokens | 10 000 à 20 000 tokens (réflexion + idées) | 4 $ lu / 20 $ écrit | 0,28 à 0,48 $ |
| **Total par jour** | | | | **~0,30 à 0,50 $** |

- Soit environ **9 à 15 $ par mois**. Avec Claude Sonnet 5.5 pour l'analyse (`FAB_MODEL = claude-sonnet-5-5`, 2 $ / 10 $) : ~0,15 à 0,25 $ par jour, soit 5 à 8 $ par mois.
- Un « token » vaut environ ¾ de mot. L'essentiel du coût vient de ce que le modèle écrit (sa réflexion et les idées) : l'écriture coûte 5 fois plus cher que la lecture.
- Le plafond `FAB_DAILY_COST_LIMIT_USD` (2 $/jour par défaut) bloque tout appel à Claude au-delà, jusqu'au lendemain. Pour une garantie totale, fixe aussi une limite dans **Limits** sur platform.claude.com et n'achète que 5 ou 10 $ de crédits, sans recharge automatique.
- Le détail réel (tokens et coût de chaque bilan) est visible dans l'onglet **Activité** du tableau de bord, et par jour et par modèle dans **Usage / Cost** sur platform.claude.com. Ce sont des estimations tant qu'aucun vrai bilan n'a tourné.

**Limite à connaître** : avec un seul passage par jour, le bilan voit ce que les sources affichent à 9 h. Les flux RSS ne gardent que leurs derniers articles, donc certaines actualités de la nuit peuvent échapper au bilan. GDELT et les recherches Google News couvrent bien les 24 dernières heures et compensent en grande partie.

## En cas de problème

| Symptôme | Solution |
|---|---|
| Message Discord « clé API Claude invalide » | Recrée une clé (étape 2) et remplace le secret `ANTHROPIC_API_KEY` |
| Message « crédit épuisé » | Recharge tes crédits dans **Billing** sur platform.claude.com |
| Le tableau de bord affiche une erreur 404 | Vérifie l'étape 5 (Source = GitHub Actions) puis relance le workflow |
| Aucune notification | Normal si aucune idée ne dépasse la note minimale. Regarde le tableau de bord, ou baisse `FAB_MIN_SCORE_NOTIFY` |
| Le workflow ne se lance plus tout seul | GitHub met en pause les tâches planifiées d'un dépôt inactif depuis 60 jours ; ici chaque passage enregistre ses résultats, donc ça ne devrait pas arriver. Sinon : onglet Actions → **Enable workflow** |
| Un passage est en rouge dans Actions | Clique dessus pour voir le journal ; les erreurs sont en français |
