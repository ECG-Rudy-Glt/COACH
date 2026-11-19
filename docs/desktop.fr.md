# Application de bureau COACH (Windows et Linux)

Un seul installateur, rien d'autre à installer. L'application de bureau embarque le serveur COACH et une base locale, s'ouvre dans sa propre fenêtre et garde tout sur votre ordinateur. English: [desktop.md](desktop.md).

> Pas un dispositif médical ni un conseil diététique, comme le reste de COACH : voir [DISCLAIMER.md](../DISCLAIMER.md).

## Ce que vous obtenez (et ce que vous n'obtenez pas)

- Une fenêtre de bureau classique. Derrière, un serveur COACH démarre sur `127.0.0.1` uniquement (jamais joignable depuis le réseau, sur un port libre choisi au hasard) et s'arrête quand vous fermez la fenêtre.
- Vos comptes, plans et journaux sont dans un fichier SQLite local. Aucun compte sur un site, aucune télémétrie.
- Le coach IA est **facultatif**. Sans lui, COACH construit quand même votre plan et vos objectifs nutritionnels (ils ne viennent jamais d'une IA de toute façon). Détails dans [le guide de la clé IA](#guide-de-la-clé-ia).
- Non inclus : accès depuis le téléphone (utilisez l'[installation Docker](../README.md#quick-start-5-minutes-docker)), notifications push du navigateur, mises à jour automatiques. Voir [Limites connues](#limites-connues).

## 1. Télécharger

Ouvrez la [page des Releases](https://github.com/ECG-Rudy-Glt/COACH/releases) et choisissez la version dont l'étiquette commence par `desktop-v`.

| Système | Fichier à télécharger |
|---|---|
| Windows 10/11 | `COACH_<version>_x64-setup.exe` (conseillé) ou `COACH_<version>_x64_fr-FR.msi` |
| Linux (distribution récente) | `COACH_<version>_amd64.AppImage` |
| Debian / Ubuntu | `COACH_<version>_amd64.deb` |
| macOS, Apple Silicon (M1 et suivants) | `COACH_<version>_aarch64.dmg` |
| macOS, Intel | `COACH_<version>_x64.dmg` |

Téléchargez aussi `SHA256SUMS.txt` depuis la même release.

## 2. Vérifier le téléchargement (SHA-256)

Les installateurs sont construits par GitHub Actions à partir de ce dépôt. `SHA256SUMS.txt` permet de vérifier que votre fichier est bien celui qui a été construit, ni corrompu ni remplacé.

```sh
# Linux (dans le dossier de téléchargement)
sha256sum -c SHA256SUMS.txt --ignore-missing
```

```powershell
# Windows (PowerShell) : la valeur doit être identique à la ligne de SHA256SUMS.txt
Get-FileHash .\COACH_0.1.0_x64-setup.exe -Algorithm SHA256
```

Si les valeurs diffèrent, ne lancez pas le fichier et téléchargez-le de nouveau.

## 3. Installer

### Windows et l'avertissement SmartScreen

Les installateurs ne sont **pas signés** (un certificat de signature est payant). Windows SmartScreen affiche donc « Windows a protégé votre PC / éditeur inconnu ». Ce n'est pas une détection de virus. Après avoir vérifié la somme SHA-256 : cliquez sur **Informations complémentaires**, puis **Exécuter quand même**.

Lancez le `-setup.exe` (installation pour votre seul utilisateur, sans droits d'administrateur) ou le `.msi`. Démarrez **COACH** depuis le menu Démarrer.

### Linux

```sh
chmod +x COACH_*.AppImage && ./COACH_*.AppImage     # AppImage (Ubuntu 22.04+ : installez libfuse2 s'il refuse de démarrer)
sudo apt install ./COACH_*_amd64.deb               # Debian / Ubuntu
```

### macOS et Gatekeeper

Le `.dmg` n'est **ni signé ni notarisé par Apple** (à notre connaissance le programme de signature d'Apple n'est pas gratuit ; nous n'avons pas vérifié ses conditions actuelles) : macOS bloque donc le premier lancement (« ne peut pas être ouvert car le développeur ne peut pas être vérifié », ou, sur Apple Silicon, parfois « est endommagé »). Vérifiez d'abord la somme SHA-256, glissez COACH dans Applications, puis :

- essayez de l'ouvrir une fois, puis allez dans *Réglages Système > Confidentialité et sécurité* et cliquez sur **Ouvrir quand même** à côté du message COACH (macOS 15 et suivants) ; sur un macOS plus ancien, clic droit sur l'application puis **Ouvrir** ; ou
- dans un terminal : `xattr -dr com.apple.quarantine /Applications/COACH.app`.

Nous n'avons pas de Mac pour tester : les installateurs macOS sont construits par la CI mais l'interface n'a jamais été lancée sur macOS par les mainteneurs. La clé IA va dans le Trousseau d'accès macOS (il peut demander votre mot de passe de session).

### Trousseau Linux

La clé IA est rangée dans le trousseau de votre bureau (GNOME Keyring ou KWallet, présents sur la plupart des bureaux). Sans trousseau, vous pouvez utiliser COACH sans IA ou avec Ollama.

## 4. Premier lancement, pas à pas

1. **Écran d'assistant.** COACH demande quel assistant IA utiliser. Dans le doute, choisissez **Aucun** : vous pourrez changer à tout moment dans **COACH > Réglages**. Cliquez sur **Démarrer COACH**.
2. **Attente.** Le premier démarrage prend quelques secondes (le serveur se lance et crée sa base).
3. **Créez votre compte.** Le premier compte est le propriétaire ; c'est local, rien n'est envoyé. Choisissez un mot de passe d'au moins 10 caractères et conservez-le : il n'y a pas de serveur d'e-mail pour envoyer un lien de réinitialisation. L'inscription se ferme ensuite (personne d'autre ne peut créer de compte via l'application).
4. **Répondez aux questions essentielles** (voir [Ce qu'il reste à remplir](#ce-quil-reste-à-remplir)).

<img src="img/home-light.png" width="240" alt="Écran d'accueil de COACH">

## Guide de la clé IA

Les faits ci-dessous ont été lus sur les pages officielles des fournisseurs le **19/11/2026** ; les prix et les menus changent, vérifiez la page liée avant de payer. Ce que nous n'avons pas pu vérifier est dit explicitement.

### À quoi sert la clé

Le coach IA rédige des explications, répond à vos questions dans le chat, propose de petits ajustements bornés de votre semaine (le serveur les vérifie avec les règles), estime un repas à partir d'une photo et pose les questions manquantes à l'accueil. Il ne produit jamais les chiffres de votre plan ni de vos objectifs nutritionnels.

### Faut-il en avoir une ?

Non. Tout ce qui est marqué « facultatif » fonctionne sans, et COACH indique quand une fonction IA est désactivée. Ajoutez une clé quand vous voulez le chat, le bilan hebdomadaire ou l'estimation d'un repas sur photo.

### Ce qui quitte votre ordinateur

Seulement si vous choisissez un fournisseur dans le cloud : les questions et le contexte de la fonction IA utilisée (vos données et votre entraînement récent, jamais votre nom ni votre e-mail, voir [docs/prompts.md](prompts.md)) partent chez ce fournisseur. Avec **Ollama** (modèle local) ou **Aucun**, rien ne quitte l'ordinateur pour l'IA.

### Où la clé est rangée

Dans le trousseau de votre système (Gestionnaire d'identifiants Windows, Trousseau d'accès macOS, GNOME Keyring / KWallet). Jamais dans un fichier de l'application, jamais dans les journaux, jamais réaffichée après l'enregistrement. Le serveur ne la reçoit que sous forme de variable d'environnement, à son démarrage.

### Un abonnement ChatGPT ou Claude n'est pas une clé d'API

Il faut un compte développeur **API** avec facturation chez le fournisseur. Les abonnements des applications de chat ne peuvent pas être utilisés par une application.

### Créer une clé, fournisseur par fournisseur

L'assistant a un bouton **Créer une clé chez ce fournisseur** qui ouvre la bonne page dans votre navigateur. Ne partagez jamais une clé et ne la collez jamais dans une issue.

**Anthropic (Claude)** : [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys).
1. Connectez-vous sur [platform.claude.com](https://platform.claude.com/) (créez un compte au besoin) et ouvrez la page API keys.
2. **Create key**, donnez un nom, choisissez une expiration et le compte lié (vous).
3. La Console affiche la clé complète (elle commence par `sk-ant-`) **une seule fois** : copiez-la.
4. Plafond : votre **limite de dépense** mensuelle est dans [Settings > Spend limits](https://platform.claude.com/settings/spend-limits) ; vous pouvez demander un palier supérieur sur la page Rate limits.
5. Non vérifié : les étapes exactes pour ajouter du crédit ou un moyen de paiement (les pages lues ne les décrivent pas).
- Prix par million de jetons (entrée / sortie), [page des tarifs](https://platform.claude.com/docs/en/about-claude/pricing) : Claude Sonnet 5.5 2 $ / 10 $ (défaut de COACH), Haiku 4.5 1 $ / 5 $, Opus 5.5 4 $ / 20 $. Les lectures du cache de prompt sont facturées 0,05 x le prix d'entrée sur Sonnet 5.5 (écritures du cache : 1,25 x).
- Sources : [Get your Claude API key](https://platform.claude.com/docs/en/get-api-key), [API overview](https://platform.claude.com/docs/en/api/overview).

**OpenAI** : [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
1. Connectez-vous, ouvrez la page API keys et créez une clé secrète ; rangez-la en lieu sûr.
2. Facturation : [platform.openai.com/account/billing/overview](https://platform.openai.com/account/billing/overview). Le guide de démarrage dit que la première requête de test est gratuite et recommande d'ajouter des crédits ensuite ; il n'indique aucun minimum.
3. Plafond : OpenAI documente deux contrôles, une **alerte de dépense** (elle prévient seulement, le trafic continue) et une **limite de dépense stricte** (les requêtes renvoient alors l'erreur 429). Les paliers d'usage sont dans [Settings > Organization > Limits](https://platform.openai.com/settings/organization/limits). Non vérifié : le chemin de menu exact de la limite stricte (la page renvoie vers un guide « spend limits » séparé).
- Prix par million de jetons (entrée / sortie), [page des tarifs](https://developers.openai.com/api/docs/pricing) : gpt-4o 2,50 $ / 10 $ (défaut de COACH), gpt-4o-mini 0,15 $ / 0,60 $, gpt-4.1 2 $ / 8 $, gpt-4.1-mini 0,40 $ / 1,60 $.
- Sources : [quickstart](https://developers.openai.com/api/docs/quickstart), [rate limits](https://developers.openai.com/api/docs/guides/rate-limits).

**Google Gemini** : [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
1. Connectez-vous avec un compte Google et acceptez les conditions : AI Studio crée un projet Google Cloud par défaut et une clé pour les nouveaux utilisateurs. Les utilisateurs Google Cloud existants importent d'abord leur projet (Dashboard > Projects > Import projects), puis créent une clé dans la page API Keys.
2. Un niveau gratuit existe (limites strictes ; les projets importés peuvent demander une vérification). Pour le niveau payant, vous activez la facturation dans Google Cloud.
3. Plafond : Google conseille des **alertes de facturation** dans la console Google Cloud. Nous n'avons trouvé aucun plafond strict dans la page lue : une alerte prévient, elle n'arrête pas la dépense.
- Prix par million de jetons, niveau payant, [page des tarifs](https://aistudio.google.com/docs/pricing) : gemini-2.5-flash 0,30 $ en entrée / 2,50 $ en sortie (défaut de COACH), gemini-2.5-pro 1,25 $ / 10 $ pour les prompts jusqu'à 200 000 jetons.
- **À savoir** : cette page indique que les deux modèles 2.5 sont dépréciés et redirigés vers d'autres modèles, facturés à leurs tarifs, à partir du 1er décembre 2026. Après cette date, indiquez dans COACH (champ « Modèle ») le modèle actuel que vous voulez.
- Source : [page des clés API](https://aistudio.google.com/docs/api-key).

**Mistral AI** : [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys).
1. Il faut un compte sur un forfait avec accès API et un moyen de paiement (Admin > Billing, « Set up billing »).
2. Page API Keys > **New key**, nommez-la, fixez une expiration, choisissez la portée des connecteurs (**Shared connectors only** suffit), créez, puis copiez la clé : elle n'apparaît qu'une fois.
3. Plafond : Admin Panel > Subscriptions and Billing > votre espace de travail > fixez un **budget mensuel en USD**. Au-delà, les requêtes renvoient 429 jusqu'au cycle de facturation suivant.
- Prix : Mistral Large 0,50 $ par million de jetons en entrée et 1,50 $ en sortie, d'après [mistral.ai/pricing](https://mistral.ai/pricing). Non vérifié : Mistral Small (non listé sur cette page).
- Sources : [démarrage : clé API](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key), [espaces de travail et limites](https://docs.mistral.ai/getting-started/quickstarts/admin/manage-workspaces).

**OpenRouter** : [openrouter.ai/keys](https://openrouter.ai/keys).
1. Créez une clé : donnez-lui un nom et choisissez une **limite de crédit** (ou aucune). La documentation d'OpenRouter recommande vivement une limite sur chaque clé ; elle peut se réinitialiser chaque jour, semaine ou mois. Une fois la limite atteinte, les requêtes de la clé sont rejetées.
2. Non vérifié : comment acheter des crédits et les frais d'OpenRouter (absents de la page lue). Le prix dépend du modèle choisi : consultez openrouter.ai.
3. Dans COACH, saisissez un nom de modèle du catalogue OpenRouter, ou laissez vide pour le choix automatique.
- Source : [documentation d'authentification](https://openrouter.ai/docs/api-reference/authentication).

**Ollama (local, sans clé)** : [ollama.com/download](https://ollama.com/download).
1. Installez Ollama, puis dans un terminal téléchargez un modèle : `ollama pull qwen2.5:7b` (celui que COACH suggère ; tout modèle proposé par Ollama convient).
2. Laissez Ollama lancé. Dans COACH, choisissez **Ollama** ; l'adresse `http://127.0.0.1:11434/v1` est celle, compatible OpenAI, du serveur local (Ollama ignore la clé d'API en local).
3. Gratuit, mais il faut un ordinateur capable de faire tourner le modèle, et les réponses sont plus lentes et moins précises que celles des gros modèles du cloud. Le modèle suggéré ne lit pas les photos de repas et l'appel d'outils varie selon le modèle : non vérifié pour chaque modèle.
- Source : [compatibilité OpenAI d'Ollama](https://docs.ollama.com/api/openai-compatibility).

Dans COACH : **COACH > Réglages**, choisissez le fournisseur, collez la clé (le champ est masqué), indiquez au besoin un modèle (vide = celui que COACH recommande), réglez le budget, **Enregistrer et redémarrer**.

### Plafonner la dépense, deux fois

1. **Chez le fournisseur** (le vrai garde-fou) : limite mensuelle ou crédit prépayé, comme ci-dessus. Les fournisseurs diffèrent : certains s'arrêtent à la limite, d'autres préviennent seulement.
2. **Dans COACH** : le budget mensuel (par défaut **5 EUR**). Quand l'estimation de COACH l'atteint, les appels IA sont refusés jusqu'au mois suivant ; le reste continue de fonctionner. *Profil > Préférences > Coût de l'IA ce mois-ci* affiche l'estimation ; elle est calculée avec les tarifs publics, la facture du fournisseur fait foi.

### Coût typique, avec le calcul

Mesuré sur les vrais prompts (un compte de démonstration de la suite de tests) : le bilan hebdomadaire envoie un message système d'environ 38 600 caractères (règles et sources) et le chat d'environ 41 900 caractères, plus un court contexte. Les plafonds de réponse du code sont de 1 400 jetons (bilan) et 700 (chat). Les jetons sont **estimés** à 3,5 caractères par jeton (nous n'avons pas pu lancer le tokeniseur de chaque fournisseur : comptez +/- 20 %).

Scénario, une personne, une semaine : **1 bilan hebdomadaire + 10 messages de chat** dans une même séance. Hypothèses : bilan = 11 000 jetons système + 2 000 de contexte + 1 000 en sortie ; chat = 12 000 jetons système + 1 500 (message et historique) + 400 en sortie par message.

Avec le Claude Sonnet 5.5 par défaut (2 $ en entrée / 10 $ en sortie par million de jetons ; écriture du cache 1,25 x, lecture 0,05 x, comme COACH les compte) :

- Bilan : 11 000 x 2,5 + 2 000 x 2 + 1 000 x 10 = 41 500 -> **0,042 $**
- Chat : le premier message écrit le cache (12 000 x 2,5 = 30 000), les 9 autres le lisent (9 x 12 000 x 0,10 = 10 800), plus 10 x 1 500 x 2 = 30 000 de contexte et 10 x 400 x 10 = 40 000 de sortie -> 110 800 -> **0,111 $**
- Semaine : 0,152 $ ; mois (52/12 semaines) : **environ 0,66 $, soit à peu près 0,59 EUR** (au taux prudent de COACH, 0,90 EUR pour 1 USD).

Même scénario, autres modèles (sans remise de cache, ce qui surestime si le fournisseur met en cache automatiquement) :

| Modèle | Environ par mois |
|---|---|
| Claude Haiku 4.5 (1 $ / 5 $) | 0,32 EUR |
| GPT-4o (2,50 $ / 10 $) | 1,64 EUR |
| GPT-4.1 mini (0,40 $ / 1,60 $) | 0,26 EUR |
| Gemini 2.5 Flash (0,30 $ / 2,50 $) | 0,22 EUR |
| Mistral Large (0,50 $ / 1,50 $) | 0,32 EUR |
| Ollama (local) | 0 |

Un usage léger reste donc très en dessous du budget par défaut de 5 EUR. Non inclus et non mesuré : le chat peut appeler des outils de recherche dans l'historique (tours de modèle supplémentaires, qui peuvent presque doubler le coût du chat), les estimations de repas sur photo (modèle économique, jetons d'image non vérifiés), les questions d'accueil et un usage plus intensif. Le compteur de l'application donne le chiffre réel.

### Si l'IA répond « non configurée »

- Ouvrez **COACH > Réglages** et vérifiez qu'un fournisseur autre que **Aucun** est choisi et qu'une clé est enregistrée (« Une clé est déjà enregistrée » s'affiche).
- Collez de nouveau la clé (sans espace ni retour à la ligne) ; une clé d'un autre fournisseur est refusée par celui-ci.
- Vérifiez la facturation / le crédit sur le site du fournisseur, et que le budget mensuel de COACH n'est pas épuisé.
- Ollama : vérifiez qu'il tourne (`ollama list`) et que le nom du modèle correspond.
- Linux : si l'enregistrement de la clé échoue, installez et déverrouillez un trousseau (GNOME Keyring ou KWallet), ou utilisez Ollama / Aucun.

## Ce qu'il reste à remplir

Rien n'est obligatoire hormis votre compte et l'avis de santé. Dans l'ordre :

1. **Compte local** : identifiant de type e-mail et mot de passe (gardés sur cet ordinateur uniquement).
2. **Questions essentielles** (13 écrans au plus) : sports, objectifs, âge, sexe, taille, poids, avis de santé et signaux d'alerte, jours d'entraînement, durée des séances, blessures, volume de course et niveau en force. Pourquoi : le moteur de règles en a besoin pour dimensionner un plan en sécurité. Vous pouvez tout passer sauf l'avis de santé ; une réponse passée rend le plan plus prudent ou plus générique.
3. **Questions de suivi du coach** (avec une IA seulement) : quelques questions manquantes au plus, chacune avec sa raison. Sans IA, COACH pose lui-même celles qui restent obligatoires.
4. **Objectifs** : une échéance datée ou un objectif général. Un objectif daté donne ses phases au plan.
5. **Générer le plan** : depuis l'accueil. Le premier plan sort des règles, avec les identifiants de règles cités sur chaque séance.
6. **Nutrition et poids** : saisissez votre poids régulièrement et, si vous le souhaitez, vos repas (code-barres et texte ; l'estimation sur photo demande une IA capable de lire les images). Les objectifs et le suivi de la tendance de poids sont calculés par des règles.
7. **Montre Garmin (facultatif)** : Profil, puis Garmin. Saisissez une fois vos identifiants Garmin Connect : seuls des jetons chiffrés sont conservés (la clé de chiffrement est dans votre trousseau). Pour une autre marque, importez des fichiers FIT/TCX/GPX ([docs/activity-import.md](activity-import.md)). La bibliothèque Garmin n'est pas officielle, à vos risques.
8. **Langue et thème** : dans le Profil (langue de l'application, du coach et des e-mails ; thèmes clair, sombre et éco).
9. **Rappels (facultatif)** : dans **COACH > Réglages > Rappels par ntfy ou e-mail**, indiquez l'adresse d'un serveur [ntfy](https://ntfy.sh) et son jeton d'accès (COACH n'envoie sur ntfy qu'avec un jeton), et/ou un serveur SMTP (hôte, port, utilisateur, mot de passe, expéditeur). Mots de passe et jetons vont dans le trousseau du système. Cochez *Envoyer automatiquement* et choisissez une heure pour le point quotidien et le résumé hebdomadaire. Ensuite chaque personne choisit son sujet ntfy ou active l'e-mail dans *Profil > Notifications* et peut envoyer un test. Les notifications push du navigateur et les fenêtres de notification du bureau ne sont pas proposées (voir [Limites connues](#limites-connues)).

<img src="img/plan-light.png" width="240" alt="Plan de la semaine">

## Où sont vos données

| Quoi | Windows | Linux / macOS |
|---|---|---|
| Dossier de données | `%APPDATA%\io.github.ecgrudyglt.coach` | `~/.local/share/io.github.ecgrudyglt.coach` (macOS : `~/Library/Application Support/io.github.ecgrudyglt.coach`) |

Dedans : `coach.db` (tout : comptes, plans, journaux), `media/` (photos, images d'exercices en cache), `settings.json` (fournisseur, modèle, budget : pas de clé), `logs/sidecar.log` (journal du serveur, remplacé à chaque démarrage). Ouvrez-le depuis **COACH > Ouvrir le dossier de données**. La clé IA et la clé de chiffrement Garmin sont dans le trousseau de l'OS (service `COACH`).

## Sauvegarder et restaurer

- **Sauvegarder** : **COACH > Sauvegarder mes données…** enregistre une archive datée `coach-backup-AAAA-MM-JJ.zip` contenant une copie cohérente de la base (`coach.db`, faite avec la fonction de sauvegarde de SQLite, sûre pendant que COACH tourne) et le dossier `media/` (photos). Gardez-la aussi ailleurs que sur cet ordinateur. Votre clé IA, votre jeton ntfy et votre mot de passe SMTP n'y sont pas (ni dans aucun fichier) : vous les ressaisissez après une réinstallation.
- **Restaurer** : 1. fermez COACH ; 2. dans le dossier de données, mettez de côté `coach.db` (et `coach.db-wal` / `coach.db-shm` s'ils existent) et `media/` ; 3. décompressez votre archive dans le dossier de données (vous obtenez `coach.db` et `media/`) ; 4. relancez COACH. Sur un autre ordinateur, les jetons Garmin ne se déchiffreront pas (leur clé reste dans l'ancien trousseau) : reconnectez Garmin.

## Mettre à jour

**COACH > Rechercher une mise à jour…** interroge l'API publique de GitHub (une requête anonyme, sans compte, rien sur vous n'est envoyé) pour trouver la dernière release `desktop-v*` publiée, la compare à votre version et, si elle est plus récente, propose d'ouvrir la page de téléchargement dans votre navigateur. Téléchargez ensuite, vérifiez la somme SHA-256 et installez par-dessus l'ancienne version (fermez COACH avant). Vos données et réglages restent ; les migrations de base s'exécutent au démarrage suivant. Faites d'abord une sauvegarde. Il n'y a **pas de mise à jour automatique** : elle demande une clé de signature que le mainteneur n'a pas mise en place.

## Désinstaller

- Windows : *Paramètres > Applications > COACH > Désinstaller*.
- Linux : supprimez l'AppImage, ou `sudo apt remove coach`.
- macOS : glissez COACH depuis Applications vers la Corbeille.

Le dossier de données n'est **pas** supprimé (une réinstallation retrouve tout). Pour tout effacer : supprimez le dossier de données et retirez les entrées `COACH` du trousseau (Windows : Gestionnaire d'identifiants, Informations d'identification Windows ; macOS : Trousseau d'accès ; Linux : « Mots de passe et clés » ou KWalletManager).

## Limites connues

| Limite | État |
|---|---|
| Installateurs non signés | **Subsiste.** La signature demande un certificat payant ; voir [SmartScreen](#windows-et-lavertissement-smartscreen) et [macOS](#macos-et-gatekeeper). Une piste gratuite pour l'open source (SignPath Foundation) est notée dans [desktop/README.md](../desktop/README.md) mais n'a pas été demandée. |
| Mise à jour automatique | **Subsiste** (elle demande une clé de signature). Remplacée par l'entrée de menu *Rechercher une mise à jour…* qui ouvre la page de téléchargement. |
| Notifications push du navigateur et fenêtres de notification du bureau | **Subsiste.** Le push web exige un service de push lié à une origine web, ce que l'adresse locale embarquée ne peut pas enregistrer ; l'application n'a pas de pont vers les notifications natives. ntfy (sur votre téléphone) et l'e-mail fonctionnent à la place. |
| Sauvegarde des photos | **Corrigé** : l'archive inclut `media/`. |
| macOS | **Ajouté**, non signé, interface jamais lancée par les mainteneurs sur un Mac. |
| Interface Windows et macOS | Construites par la CI mais **non lancées** par les mainteneurs. La partie serveur a été testée de bout en bout sous Linux. |
| Accès depuis le téléphone | Impossible avec l'application de bureau (local uniquement) ; utilisez l'installation Docker. |

## Dépannage

| Symptôme | Que faire |
|---|---|
| « COACH n'a pas pu démarrer » | Lisez `logs/sidecar.log` dans le dossier de données ; cliquez sur **Réessayer**. Un antivirus peut bloquer le premier démarrage du serveur embarqué : autorisez COACH. |
| Premier démarrage très lent | Normal pendant quelques secondes (le serveur se décompresse). Plus d'une minute : voyez le journal. |
| Rien ne s'ouvre, fenêtre blanche | Fermez-la depuis la zone de notification / le gestionnaire de tâches ; relancez. Une seule instance de COACH peut tourner. |
| Linux : l'AppImage ne démarre pas | Installez `libfuse2`, ou utilisez le `.deb`. |
| Linux : la clé ne s'enregistre pas | Installez et déverrouillez GNOME Keyring ou KWallet, ou choisissez Ollama / Aucun. |
| Windows : « Windows a protégé votre PC » | Voir [SmartScreen](#windows-et-lavertissement-smartscreen). |
| macOS : « ne peut pas être ouvert » / « est endommagé » | Voir [Gatekeeper](#macos-et-gatekeeper). |
| Clé IA oubliée | Elle ne peut pas être relue, par conception : créez-en une nouvelle chez le fournisseur et collez-la dans les Réglages. |

Bogues et questions : [issues](https://github.com/ECG-Rudy-Glt/COACH/issues). N'y collez jamais vos clés, votre base ni des données de santé. Pour construire les installateurs vous-même, voir [desktop/README.md](../desktop/README.md).
