# Règles du moteur de plan

> Version 0 du 07/10/2026. Les références ont été vérifiées sur les **résumés** (pas les textes complets) :
> voir [references.md](references.md) et [references-2.md](references-2.md), et la base structurée `data/evidence/`.
> Quand la preuve est faible, c'est écrit : le choix est alors une pratique de terrain prudente, pas un résultat établi.
> Une relecture humaine complète reste à faire (voir les tickets du dépôt).

## Principes

1. Le moteur est **déterministe** : mêmes faits, même plan. Le LLM ne change ni volumes ni intensités.
2. **Prudence par défaut** : en cas de doute (donnée manquante, blessure, signal d'alerte), on réduit.
3. Chaque règle a un **identifiant**, une **valeur**, un **niveau de preuve** (A solide, B modéré, C pratique)
   et un **effet** vérifiable par test. Chaque séance du plan cite les règles appliquées.
4. Tout paramètre est **réglable par l'utilisateur** dans une plage de sécurité, jamais en dehors.

## Entrées utilisées (faits du profil)

Objectifs et échéances (`project.goals`), niveau et performances (`bench.*`), historique et blessures
(`history.*`), disponibilité (`constraints.*`), jours préférés et bloqués (`multisport.*`), matériel,
charge récente (séances réalisées, Garmin), check-in du matin, poids. Une donnée absente rend la règle
concernée **conservatrice** (niveau débutant, volume bas).

## A. Sécurité (priorité absolue)

| Id | Règle | Effet |
|---|---|---|
| S1 | Signal d'alerte à l'effort (douleur thoracique, malaise, palpitations, essoufflement inhabituel) déclaré et non discuté avec un médecin | Aucun plan d'intensité ; message de renvoi vers un médecin |
| S2 | Blessure active déclarée (menu ou douleur décrite dans un retour de séance) | Exercices et gestes concernés exclus ; progression gelée sur la zone ; si la zone porte la course (genou, cheville, hanche, tibia, tendon d'Achille, mollet, pied, ischio-jambiers) : volume, sortie longue et intensité de course gelés ; message si la douleur persiste |
| S3 | Objectif de perte de poids irréaliste (> 1 % du poids par semaine) ou poids cible hors plage saine | Objectif plafonné, explication affichée |
| S4 | Antécédent de trouble alimentaire, grossesse ou post-partum déclaré | Pas de déficit calorique proposé ; renvoi vers un professionnel |
| S5 | Plancher calorique | Jamais sous le métabolisme de base estimé |
| S6 | Mineur | Pas de plan de perte de poids |

Preuve : C (principe de précaution). Ces règles ne sont pas désactivables.

## B. Charge et progression générales

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| G1 | Montée de charge progressive : volume hebdomadaire d'endurance relevé de 5 à 10 % par semaine au plus, jamais deux semaines de forte hausse de suite | 10 % max | C. La « règle des 10 % » n'est pas démontrée (Buist 2008, novices : pas de différence de blessures) : on s'en sert comme **plafond**, pas comme cible |
| G2 | Cycle de 3 semaines de montée puis 1 semaine allégée (volume −30 à −40 %, intensité conservée) | 3+1 | C. Pas d'essai solide sur la décharge ; adopté pour la récupération perçue. Cycle 2+1 si âge > 45 ans, reprise après arrêt ou check-ins dégradés |
| G3 | Reprise après arrêt long : volume de départ = 50 % du volume d'avant arrêt (≤ 4 semaines d'arrêt) ou 30 % (plus long), avec montée en 4 à 6 semaines | 50 % / 30 % | C |
| G4 | Le ratio charge aiguë/chronique n'est utilisé que comme **signal d'alerte souple** (> 1,5 sur la charge d'endurance), jamais comme cible | 1,5 | B contre : fortement critiqué (Impellizzeri 2020) |
| G5 | Au plus 1 séance « clé » (intense ou longue) isolée par 48 h ; au moins 1 jour de repos complet par semaine | | C |
| G7 | Périodisation : la position dans le bloc 3+1 est enregistrée dans chaque séance (`details.cycle`) et reprise à chaque génération du plan (jamais de retour à zéro sans demande). Phases selon les semaines avant l'objectif : base (> 12 ou sans objectif), développement (5 à 12), pic de forme (2 à 4 : volume maximal, spécificité), affûtage (1), semaine de l'objectif (0) ; l'affûtage remplace la semaine allégée | | C. Périodisation par blocs : consensus de pratique, preuves directes limitées ; le pic et l'affûtage s'appuient sur C6 |
| G6 | Jours bloqués et durées maximales de l'utilisateur toujours respectés | | A (contrainte) |

## C. Course à pied et trail

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| C1 | Distribution d'intensité : ≈ 80 % du temps en facile (zones 1-2), ≈ 20 % en intensité ; au plus 2 séances de qualité par semaine (1 si volume < 3 séances) | 80/20 | B (Seiler & Kjerland 2006 ; Stöggl & Sperlich 2014 ; débat polarisé/pyramidal, Treff 2019) |
| C2 | Une sortie longue par semaine, ≤ 30 % du volume hebdomadaire de course et ≤ 2 h 30 sauf préparation d'ultra | 30 % | C |
| C3 | Zones de fréquence cardiaque calculées sur la FC max déclarée ou mesurée ; à défaut, allures dérivées du meilleur 10 km (récent) | | B |
| C4 | Trail : dénivelé hebdomadaire monté de 10 % max par semaine, en partant du dénivelé réel récent ; sortie longue avec dénivelé proche de celui de l'objectif en fin de préparation (≥ 60 % de son D+, ≥ 70 % de sa durée) | | C |
| C5 | Descentes : travail excentrique introduit progressivement (5 à 10 min par séance, +5 min par semaine) pour limiter les courbatures et le risque tendineux | | B (Vernillo et al. 2017 : charge musculaire excentrique élevée en descente) |
| C6 | Avant l'objectif : affûtage de 7 à 14 jours (volume −40 à −60 %, intensité maintenue) | | B (affûtage : méta-analyses Bosquet 2007 en endurance) |
| C7 | Bâtons, ravitaillement, test du matériel : séances d'essai planifiées avant l'objectif si déclaré « jamais testé » | | C |
| C9 | Objectif de course à moins de 12 semaines : la sortie longue est guidée par l'objectif. Départ = plus longue sortie récente mesurée (au moins 30 min), +10 min par semaine jusqu'à environ 75 % de la durée estimée de l'objectif (au plus 2 h 30), allégée de 25 % en semaine de décharge, 55 % du pic à l'affûtage ; 2 footings de 25 min ; dénivelé de la sortie longue jusqu'à 80 % de celui de l'objectif. Dépasse volontairement le plafond de 10 % de G1 quand la base aérobie vient d'autres sports : à lever si une douleur est déclarée | | C. Pratique d'entraînement ; la progression de la sortie longue est un repère, pas une loi (voir G1 sur la règle des 10 %) |
| C8 | Objectif trail > 50 km : au moins 2 sorties longues de plus de 3 h avant l'affûtage ; jamais plus d'une sortie très longue par 10 jours | | C |
| C10 | Niveau actuel sur la distance d'un objectif de performance : équivalence entre distances t₂ = t₁ × (d₂ / d₁)^1,06 appliquée aux records 5 km, 10 km, semi (le niveau « actuel » prime sur le record) ; on garde l'équivalent le plus lent, par prudence | exposant 1,06 | C. Formule empirique de Riegel : elle surestime les performances sur les distances plus longues que le record de départ et quand le volume est faible |
| C11 | Trajectoire vers un objectif de performance daté (course de 3 km à un semi, temps visé) : phases remontées depuis la date : affûtage (1 semaine), bloc spécifique (8 semaines : 1 000 m à l'allure de l'objectif, au plus 6), bloc seuil (12 semaines : répétitions de 8 min à allure seuil, au plus 4), base avant ; un événement à moins de 12 semaines prime (C9). Allures projetées linéairement du niveau actuel vers le temps visé, jamais plus rapides que lui. Test chronométré (5 km, ou 3 km pour un objectif court) tous les 3 mois ; gain mensuel > 0,8 % jugé ambitieux, > 1,5 % très ambitieux ; un ultra ne se place pas dans les 20 semaines qui précèdent l'objectif ni dans les 3 qui suivent | 1 + 8 + 12 semaines | C. Périodisation classique (base, développement, spécifique, affûtage) ; les seuils de gain mensuel sont des repères de pratique, pas une loi |
| C12 | Volume hebdomadaire de course visé tant que l'objectif de performance est lointain, d'après le temps équivalent au 10 km : ≤ 35 min : 65 km ; ≤ 40 min : 50 km ; ≤ 45 min : 40 km ; ≤ 50 min : 32 km ; ≤ 60 min : 25 km ; au-delà : 20 km. La montée de G1 s'arrête à ce plafond au lieu de continuer sans limite | voir règle | C. Repères de pratique, à ajuster selon le temps disponible et la tolérance : pas une loi |

## D. Musculation

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| M1 | Volume cible pour l'hypertrophie : 10 à 20 séries dures par groupe musculaire et par semaine, réparties sur 2 séances au moins | 10-20 | A-B (Schoenfeld et al. 2017 ; relation dose-réponse) |
| M2 | **Sèche** : conserver l'intensité (charges lourdes, 5-12 répétitions près de l'échec, 1-3 répétitions en réserve) et un volume d'**entretien** (≈ 1/3 à 1/2 du volume de croissance suffit à conserver le muscle) ; le surplus de volume va au haut du corps si c'est l'objectif | | B (Bickel 2011 ; Spiering et al. 2021) |
| M3 | Protéines : 1,6 à 2,2 g/kg/jour, jusqu'à 2,4 en déficit | 1,6-2,4 | A (Morton et al. 2018 ; Helms et al. 2014 pour la sèche) |
| M4 | Rythme de perte : 0,5 à 1 % du poids par semaine ; plus lent si on cherche à garder la performance de course | 0,5-1 % | B (Garthe et al. 2011 : 0,7 %/sem. conserve mieux la masse maigre que 1,4 %) |
| M5 | Progression : double progression (monter les répétitions dans une fourchette, puis la charge de 2,5 à 5 %) ; si deux séances de suite sous la fourchette, charge −5 à −10 % | | B |
| M8 | Surcharge progressive entre blocs : dans un bloc, +1 série sur les mouvements clés et RIR décroissant ; le bloc suivant démarre une série plus haut (mouvements clés) et une répétition de qualité de plus ; les charges suivent la double progression (M5) d'après la dernière performance enregistrée | | B-C (Schoenfeld 2017 pour le volume ; progression par blocs : pratique) |
| M9 | Séance hybride hebdomadaire (CrossFit/Hyrox déclaré) : un conditionnement par semaine à la place de la 3e séance de musculation (échauffement, force/technique, WOD, retour au calme) ; jamais la veille ni le lendemain de la sortie longue, ni le jour d'une autre séance clé ; durée du WOD qui monte d'un bloc à l'autre, allégée en semaine de décharge ; en entretien (course à moins de 8 semaines, affûtage) la séance disparaît | | C. Pratique du CrossFit ; la séparation des séances est la règle I1 (interférence faible sur la force maximale selon Schumann 2022, mais à ne pas ignorer, Wilson 2012) |
| M6 | Priorité haut du corps déclarée : 60 % du volume hebdomadaire en haut du corps ; jambes à volume d'entretien tant qu'un objectif de course est dans les 8 semaines | | C |
| M7 | Exercices choisis dans la bibliothèque selon le matériel disponible, les blessures actives et le niveau ; au plus 6 à 8 exercices par séance | | C |
| M11 | Fourchettes de répétitions : l'hypertrophie se développe sur une large plage (environ 5 à 30 répétitions) tant que les séries sont proches de l'échec ; on alourdit donc les fourchettes d'une semaine à l'autre du bloc (par exemple 8-10, puis 6-8, puis 5-6 sur le mouvement principal) pour progresser en charge. **La supériorité d'une « vague » de répétitions sur une fourchette fixe n'est pas démontrée** : c'est un choix de pratique pour la progression et la variété | 5 à 30 reps près de l'échec | B pour la plage de répétitions ; C pour la variation par semaine |
| M12 | Proximité de l'échec : RIR 2-3 en début de bloc, 1-2 ensuite, jamais à l'échec sur les mouvements polyarticulaires lourds (squat, soulevé) ; dernière série des isolations jusqu'à 0-1 répétition en réserve, plus sûr et efficace sur les exercices simples. Le RIR est un outil imparfait, d'autant plus fiable que la série est proche de l'échec | RIR 0-3 | B (Zourdos 2016 pour le RIR) ; B-C pour la proximité de l'échec |
| M13 | Supersets (biceps/triceps, antagonistes) : proposés pour gagner du temps, sans bénéfice d'hypertrophie démontré par rapport à des séries séparées | | B (gain de temps) |

## E. Interférence muscu et endurance (multisport)

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| I1 | Séances de jambes lourdes et séances d'endurance intenses séparées de 6 h au moins, idéalement de jours différents | 6 h | B (Wilson et al. 2012 ; Schumann et al. 2022 : interférence faible sur l'hypertrophie, plus nette sur la force et la puissance des jambes, plus marquée avec la course) |
| I2 | Jamais de jambes lourdes la veille d'une séance clé de course (qualité ou sortie longue) ni dans les 48 h avant un objectif | | C |
| I3 | Course facile et musculation du haut du corps peuvent être le même jour | | C |
| I4 | La musculation de jambes en préparation de course vise la force (3-6 répétitions, 2-3 séries) plutôt que l'épuisement | | B (Blagrove et al. 2018 : la force améliore l'économie de course et la performance) |
| I5 | Jambes lourdes déclarées après la musculation (`multisport.leg_fatigue_after_strength` = souvent) : volume de jambes réduit d'un tiers et séances de jambes déplacées loin des séances clés | | C |
| I6 | Hyrox / CrossFit : séances à contenu déclaré, comptées dans la charge globale ; au plus 1 séance mixte intense par semaine en période de préparation de trail | | C |

## F. Récupération sans mesure de nuit

Le check-in du matin (≈ 15 s : sommeil ressenti, courbatures, énergie, douleurs) est le signal principal.
Les mesures subjectives réagissent bien à la charge d'entraînement, au moins autant que les mesures
objectives (Saw et al. 2016, B).

| Id | Règle | Effet |
|---|---|---|
| R1 | Check-in dégradé un jour | Séance du jour réduite (volume −30 %) ou remplacée par du facile |
| R2 | Check-in dégradé 3 jours sur 7 | Semaine allégée déclenchée ; question de clarification (sommeil, stress, douleur) |
| R3 | Douleur localisée déclarée | Règle S2 |
| R4 | Le check-in ne peut **qu'alléger** un jour, jamais l'alourdir | |
| R5 | FC de repos de jour et charge Garmin utilisées comme signaux secondaires | Alerte douce, jamais décisive seule |

## G. Alimentation (cibles et suggestions)

Cibles calculées : métabolisme de base (Mifflin-St Jeor), dépense selon la charge réelle du jour, déficit
ou surplus selon l'objectif (M4, surplus de 0,25 à 0,5 %/semaine pour une prise), protéines (M3), glucides
modulés par la charge (plus autour des sorties longues et séances intenses), lipides ≥ 0,6 g/kg. Le LLM ne
fait que **proposer des idées de repas** compatibles avec ces cibles, les allergies et le régime. Pas de
journal alimentaire. Preuve : A-B pour les ordres de grandeur, C pour la modulation par la charge.

## G bis. Nutrition : cibles, suivi du poids, estimation des repas

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| N1 | Cible d'énergie = dépense estimée (Mifflin-St Jeor × niveau d'activité hors séances + séances planifiées) moins un déficit ; jamais sous le métabolisme de base estimé ni sous un plancher (1 500 kcal hommes, 1 200 femmes) | plancher = max(BMR, plancher) | B (Mifflin 1990 ; estimations à ±10 %) |
| N2 | Protéines : 2,0 g/kg/jour en perte de poids avec musculation (plage 1,8 à 2,4), réparties sur 3 à 5 prises | 2,0 g/kg | A-B (Morton 2018 ; Helms 2014, exprimé par kg de masse maigre) |
| N3 | Lipides au moins 0,8 g/kg ; glucides pour le reste ; ±120 kcal de glucides selon que la journée contient une séance de 45 min ou plus, la moyenne reste inchangée | 0,8 g/kg | C |
| N4 | Rythme de perte 0,5 % du poids par semaine à moins de 12 semaines d'un objectif sportif, 0,75 % sinon ; sous 0,25 % pendant 3 semaines avec 14 jours renseignés : −100 à −150 kcal ; au-delà de 1 % : +150 kcal | 0,5 à 0,75 % | B (Garthe 2011 ; Helms 2014) |
| N5 | Le poids se suit par moyenne glissante sur 7 jours, au moins deux pesées par semaine, jamais d'après le chiffre d'un jour (eau, sel, digestion) | 7 j | C |
| N6 | Les estimations de repas par texte ou photo sont des ordres de grandeur (fourchette, confiance) : on suit les moyennes hebdomadaires, jamais un repas isolé ; aucun jugement moral | sous-estimation fréquente | B |
| N7 | Pas de déficit pour un mineur, en cas de grossesse ou post-partum, ni d'antécédent de trouble alimentaire déclaré : renvoi vers un professionnel | | C |
| N8 | Qualité : 25 à 30 g de fibres, des légumes à chaque repas, produits ultra-transformés et alcool limités | | B |

## H. Vérifications automatiques (tests)

- Aucun plan ne dépasse G1, G5, C2, C8 ni ne viole S1 à S6 (tests par propriétés sur des profils aléatoires).
- Jamais de jambes lourdes la veille d'une séance clé (I2) ; 6 h minimum entre jambes lourdes et intensité (I1).
- Toute séance cite au moins une règle ; un plan sans données suffisantes est plus prudent qu'un plan complet.
- Les profils de référence (dont un profil de sèche, haut du corps, trail) produisent un plan lisible
  et conforme, relu par un humain.

## Décisions retenues (07/10/2026, par l'auteur, selon les meilleures recommandations disponibles)

1. **Décharge** : 3+1 par défaut ; 2+1 si âge > 45 ans, reprise après arrêt ou check-ins dégradés (G2).
2. **Sèche et course** : déficit plafonné à 0,5 % du poids par semaine dès qu'un objectif de course est à moins de 12 semaines, jusqu'à 1 % sinon (M4).
3. **Priorité** : à moins de 8 semaines d'un objectif de course, la course l'emporte ; la musculation passe en entretien, haut du corps conservé (M6, I2).
4. **Zones** : calculées sur la FC max si elle est connue, sinon sur l'allure du meilleur 10 km récent ; les deux sont affichées quand elles divergent (C3).
5. **Messages de prudence** : discrets par défaut (une ligne sur la séance concernée) ; systématiques et visibles pour les règles de sécurité S1 à S6.

## Objectifs vivants

Les objectifs ne sont pas figés par le questionnaire : l'utilisateur peut **ajouter, modifier, terminer ou
abandonner un objectif à tout moment** (table `goals`, source de vérité). Tout changement déclenche le
recalcul du plan à partir de la semaine suivante ; la semaine en cours n'est jamais bouleversée sans accord.
Un objectif terminé ou abandonné reste dans l'historique (mémoire du coach).
Priorité entre objectifs : le principal l'emporte ; deux objectifs « événement » à moins de 6 semaines l'un de
l'autre sont signalés comme un conflit à arbitrer avec l'utilisateur.

## Références

Vérifiées le 08/10/2026 par recherche (voir [references.md](references.md), avec liens, limites et verdict par étude). Des valeurs de règles
restent à réexaminer d'après cette vérification : C1 (Seiler et Treff : descriptifs, pas des arbitrages), C5 (progression de 5 à 10 min : pratique de terrain),
C6 (Bosquet : −41 à −60 % sur 2 semaines), M1 (10 à 20 séries : preuve modérée), M3 (2,4 g/kg en sèche : Helms, en g/kg de masse maigre), I1 (Schumann : interférence faible sur la force maximale).

Seiler & Kjerland 2006 ; Stöggl & Sperlich 2014 ; Treff et al. 2019 ; Wilson et al. 2012 (J Strength Cond Res) ;
Schumann et al. 2022 (Sports Med) ; Blagrove et al. 2018 (Sports Med) ; Schoenfeld et al. 2017 (J Sports Sci) ;
Morton et al. 2018 (BJSM) ; Helms et al. 2014 (J Int Soc Sports Nutr) ; Garthe et al. 2011 (Int J Sport Nutr
Exerc Metab) ; Bickel et al. 2011 (Med Sci Sports Exerc) ; Spiering et al. 2021 (J Strength Cond Res) ; Vernillo et al.
2017 (Sports Med) ; Bosquet et al. 2007 (Med Sci Sports Exerc) ; Buist et al. 2008 (Am J Sports Med) ;
Impellizzeri et al. 2020 (Int J Sports Physiol Perform) ; Saw et al. 2016 (Br J Sports Med).

## Notes de vérification des sources (08/10/2026)

Issues des bases `data/evidence/*.yaml` (60 publications relues sur leurs résumés PubMed/Europe PMC, textes complets non relus) et de `references-2.md`.

- **C1** : deux revues récentes ne montrent pas de supériorité nette de la méthode polarisée sur la performance chronométrée ; Seiler 2006 est descriptif. La règle 80/20 reste un repère de pratique.
- **C6** : la baisse de volume étayée est de −40 à −60 % sur 2 semaines (Bosquet 2007 ; Wang 2023). Le moteur applique −40 %.
- **I1** : pas d'interférence démontrée sur la force maximale ni l'hypertrophie (Schumann 2022), seulement sur la force explosive.
- **G2** : un seul essai sur la semaine allégée, et il teste un arrêt total, pas une baisse de volume : bénéfice non démontré, règle de pratique.
- **M2** : la référence « Bickel 2011 » n'a pas été retrouvée ; l'entretien du muscle à volume réduit s'appuie sur Spiering 2021 (revue narrative).
- **M11** (répétitions) : la périodisation ne montre pas d'avantage sur l'hypertrophie (Moesgaard 2022, Grgic 2017) ; la variation par semaine reste un choix de pratique.
- **M12** (proximité de l'échec) : les études divergent (Refalo 2023, Robinson 2024) ; le RIR sous-estime d'environ une répétition (Halperin 2022).
- **M13** (supersets) : séances plus courtes, hypertrophie similaire (Zhang 2025). La référence « Weakley 2021 » citée de mémoire n'existe pas.
- **N1** : Mifflin-St Jeor est exacte à ±10 % pour moins de la moitié des sportifs récréatifs (ten Haaf 2014) : traiter la cible comme un point de départ à ajuster sur la tendance de poids. Le repère de 7 700 kcal/kg n'est valable qu'à court terme (Hall 2008).
- **N2** : en déficit avec musculation, les consensus vont jusqu'à 2,3-3,1 g/kg de masse maigre (Helms 2014, ISSN) ; 2,0 g/kg de poids total reste dans la plage prudente.
- **N5** : aucune étude ne valide la moyenne glissante sur 7 jours ni le seuil de deux pesées par semaine ; le poids fluctue d'environ 0,35 % d'un jour à l'autre (Turicchi 2020) : règle de pratique.
- **N6** : l'estimation de calories sur photo ou description sous-estime de façon systématique ; la fourchette « ±20 à 30 % » n'est pas démontrée.
- **N3, N7, N8** : non vérifiées.
