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
charge récente (séances réalisées, Garmin), check-in du matin, poids ; pour l'hybride : années de CrossFit et mouvements maîtrisés (`hybrid.crossfit_*`), expérience, catégorie et stations faibles Hyrox (`hybrid.hyrox_*`), lieu d'entraînement (`hybrid.access`). Une donnée absente rend la règle
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
| S7 | Blessure décrite en texte libre (« autre », détail, anglais ou français, accents, pluriels : « Genoux », « knee pain », « tendinite d'Achille ») : le texte est ramené aux zones connues de S2 ; « aucune », « none », « pas de blessure » ne sont pas des blessures. Un texte qui ne cite aucune zone connue n'est jamais ignoré en silence | Zone reconnue : S2 s'applique ; texte non reconnu : aucun exercice exclu automatiquement, message dans les notes et les conseils (mouvements sans douleur, professionnel de santé si elle persiste) ; une valeur illisible ne lève jamais d'erreur |
| S8 | Entrée absurde ou incohérente (0 ou plus de 7 jours, durée nulle, négative ou illisible, record 10 km impossible, échéance passée, deux objectifs le même jour) | Jamais d'erreur : 0 jour = aucun plan et le dit ; 1 jour = 2 ; plus de 6 = 6 (G5) ; durée ramenée à 20-600 min ou à la valeur par défaut ; échéance passée ignorée ; objectif le plus prioritaire retenu sans dépendre de l'ordre de saisie ; chaque correction est affichée avec le plan |

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
| G8 | Reprise sans historique fiable : sans course depuis 4 semaines ou plus (`running.weeks_since_last_run`), le volume des 8 dernières semaines saisi ou le volume par défaut (12 km) date d'avant l'arrêt : G3 s'applique à lui (50 % jusqu'à 4 semaines d'arrêt, 30 % au-delà). La montée suit G3 (+15 % par semaine au plus, G3 prime sur G1 pendant la reprise) et ne dépasse pas le volume d'avant l'arrêt avant la fin de la reprise ; G1 reprend ensuite | 50 % / 30 % ; +15 % | C. Prolonge G3 ; mêmes limites de preuve |
| G9 | Une séance voulue qui ne trouve aucun jour compatible (jours bloqués, espacement de 48 h de G5, I1, I2, M14) n'est jamais retirée en silence : ordre de sacrifice (sortie longue, qualité, jambes, haut du corps, conditionnement hybride), séance retirée ou remplacée dite dans les notes de la semaine ; moins de 3 séances possibles : message dans les conseils | | C. Aucune contrainte nouvelle : G5 et G6 restent inchangées, seule l'information change |
| G10 | Génération en cours de semaine : seuls les jours à partir d'aujourd'hui sont planifiés, la semaine entamée n'est jamais remplacée ; si plus rien ne reste à planifier cette semaine (jours passés ou bloqués) ou le week-end, la génération prépare la semaine suivante ; un plan vide donne la raison exacte (signal d'alerte, 0 jour, jours bloqués, sport absent) | | C |
| G11 | G1 porte sur le volume réellement planifié : quand les jours et les durées ne permettent pas d'atteindre le volume visé d'une semaine, la suivante repart du volume réellement planifié (+8 % ; +15 % en reprise, G8), l'allègement (G2) et l'affûtage (C6) aussi | 8 % | C. Complète G1 |
| G12 | Durées maximales (G6) : une course est plafonnée à la durée du jour (semaine ou week-end) ; une séance de musculation, estimée à 35 min + 6 min par exercice, tient dans la durée saisie à 10 % près (accessoires retirés d'abord, puis gainage, jamais sous 2 exercices) ; une séance qui ne tient pas du tout (conditionnement, musculation) saute et le dit | 10 % | C. Estimation de durée, pas une mesure |

## C. Course à pied et trail

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| C1 | Distribution d'intensité : ≈ 80 % du temps en facile (zones 1-2), ≈ 20 % en intensité ; au plus 2 séances de qualité par semaine (1 si volume < 3 séances) | 80/20 | B (Seiler & Kjerland 2006 ; Stöggl & Sperlich 2014 ; débat polarisé/pyramidal, Treff 2019) |
| C2 | Une sortie longue par semaine, ≤ 30 % du volume hebdomadaire de course et ≤ 2 h 30 sauf préparation d'ultra | 30 % | C |
| C3 | Zones de fréquence cardiaque calculées sur la FC max déclarée ou mesurée ; à défaut, allures dérivées du meilleur 10 km (récent) | | B |
| C4 | Trail : dénivelé hebdomadaire monté de 10 % max par semaine, en partant du dénivelé réel récent ; sortie longue avec dénivelé proche de celui de l'objectif en fin de préparation (≥ 60 % de son D+, ≥ 70 % de sa durée) | | C |
| C5 | Descentes : travail excentrique introduit progressivement (5 à 10 min par séance, +5 min par semaine) pour limiter les courbatures et le risque tendineux | | B (Vernillo et al. 2017 : charge musculaire excentrique élevée en descente) |
| C6 | Avant l'objectif : affûtage de 7 à 14 jours (volume −40 à −60 %, intensité maintenue) ; le jour de l'événement est la séance (rien d'autre), la veille 30 min de course au plus sans jambes ni intensité, pas de course les 2 jours suivants | | B (affûtage : méta-analyses Bosquet 2007 en endurance) |
| C7 | Bâtons, ravitaillement, test du matériel : séances d'essai planifiées avant l'objectif si déclaré « jamais testé » | | C |
| C9 | Objectif de course à moins de 12 semaines : la sortie longue est guidée par l'objectif. Départ = plus longue sortie récente mesurée (au moins 30 min), +10 min par semaine jusqu'à environ 75 % de la durée estimée de l'objectif (au plus 2 h 30), allégée de 25 % en semaine de décharge, 55 % du pic à l'affûtage ; 2 footings de 25 min ; dénivelé de la sortie longue jusqu'à 80 % de celui de l'objectif. Dépasse volontairement le plafond de 10 % de G1 quand la base aérobie vient d'autres sports : à lever si une douleur est déclarée | | C. Pratique d'entraînement ; la progression de la sortie longue est un repère, pas une loi (voir G1 sur la règle des 10 %) |
| C8 | Objectif trail > 50 km : au moins 2 sorties longues de plus de 3 h avant l'affûtage ; jamais plus d'une sortie très longue par 10 jours | | C |
| C10 | Niveau actuel sur la distance d'un objectif de performance : équivalence entre distances t₂ = t₁ × (d₂ / d₁)^1,06 appliquée aux records 5 km, 10 km, semi (le niveau « actuel » prime sur le record) ; on garde l'équivalent le plus lent, par prudence | exposant 1,06 | C. Formule empirique de Riegel : elle surestime les performances sur les distances plus longues que le record de départ et quand le volume est faible |
| C13 | Un record n'est pas un niveau actuel : quand C10 ne s'appuie que sur un record (aucun temps « actuel » renseigné), l'écran et le coach l'indiquent comme point de départ, probablement plus rapide que le niveau du moment, et invitent à saisir un temps récent | | C (pratique) |
| C14 | Niveau actuel de course estimé sur les huit dernières semaines, par priorité : temps « actuel » saisi (C10) > meilleur effort récent de la montre > record seul (C13). Effort = sortie de course (route, piste, trail à moins de 15 m de dénivelé positif par km) d'au moins 3 km et d'une distance comprise entre 1/3 et 2 fois celle de l'objectif, convertie par Riegel (C10). Avec la FC moyenne et la FC max (déclarée, sinon observée) : ≥ 85 % = effort soutenu, **estimation** (la plus lente des tranches de distance, jamais plus lente que la meilleure borne) ; < 75 % = footing, écarté. Sans FC ou entre les deux : la sortie ne prouve qu'une **borne** (« au moins aussi rapide que », majorant du temps). Source, distance, temps et date sont affichés ; l'API de trajectoire expose `level.source_kind` (saisi | garmin | record) et `level.bound` | 8 semaines, ≥ 3 km, 85 % / 75 % FC max | C. Riegel (1981) ; calibré jusqu'au semi, pas au-delà (Vickers & Vertosick 2016, BMC Sports Sci Med Rehabil 8:26, résumé lu). Seuils de FC et fenêtre : repères de pratique, non validés |
| C15 | Niveau actuel de force estimé : pour les exercices de référence du moteur (développé couché, développé militaire, rowing barre, squat, presse), meilleur e1RM d'Epley (charge × (1 + répétitions / 30)) sur les séances faites des 12 dernières semaines, séries chargées de 1 à 10 répétitions seulement (au-delà, ignorées). Affiché « estimé » avec sa date sous le niveau de la page Mes performances, sans jamais remplacer la saisie « actuel » ; à défaut de saisie, il sert de base à la charge de départ conseillée avant le record (× 0,9) | 12 semaines, 1 à 10 reps | C. Formule d'Epley (1985), estimation et non mesure ; l'erreur croît avec le nombre de répétitions et la fatigue. Formule non vérifiée dans une source ouverte lors de cette révision |
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
| M9 | Séance hybride hebdomadaire (CrossFit déclaré avec course ou musculation ; pour Hyrox avec course voir I7 ; sans course : M10 et M18) : un conditionnement par semaine à la place de la 3e séance de musculation (échauffement, force/technique, WOD, retour au calme) ; jamais la veille ni le lendemain de la sortie longue, ni le jour d'une autre séance clé ; durée du WOD qui monte d'un bloc à l'autre, allégée en semaine de décharge ; en entretien (course à moins de 8 semaines, affûtage) la séance disparaît | | C. Pratique du CrossFit ; la séparation des séances est la règle I1 (interférence faible sur la force maximale selon Schumann 2022, mais à ne pas ignorer, Wilson 2012) |
| M10 | Programmation CrossFit dédiée (CrossFit déclaré sans course) : un microcycle de 2 à 6 séances selon les jours disponibles, aux qualités distinctes — 2 j : force bas du corps + metcon ; 3 j : + gymnastique et force du haut du corps ; 4 j : + capacité aérobie ; 5 j : + force haut du corps et haltérophilie technique ; 6 j : + 2e metcon de capacité (remplacé par de la prévention en semaine allégée ou avec une blessure déclarée) | 2-6 | C. Pratique de terrain. Les revues du CrossFit (Claudino 2018) trouvent peu d'études de haut niveau : aucune preuve qu'un fractionnement soit meilleur qu'un autre. Feito 2018 définit l'entraînement fonctionnel à haute intensité ; Villarroel López 2025 (revue exploratoire) lui attribue des gains d'aptitude aérobie et de force |
| M14 | Alternance dur/facile : jamais deux séances dures (force lourde, metcon, séance de qualité, course compromise) sur des jours qui se touchent quand elles sollicitent les mêmes groupes (bas du corps, haut du corps, corps entier) ; au moins un jour de repos complet ; en semaine allégée tout devient modéré. Si aucune disposition ne respecte la règle, la dernière séance du microcycle saute | | C. Prolonge G5 (48 h entre séances clés) ; aucune étude ne compare des agencements de semaine |
| M15 | Metcons et mise à l'échelle : un format différent chaque semaine du bloc (AMRAP, For Time 21-15-9 ou tours chronométrés, EMOM, intervalles 3 min / 2 min) ; durée de 12 min qui monte de 2 min par bloc jusqu'à 18 ; effort ≤ 8 sur 10 ; débutant : 0,75 × la durée et 0,7 × les répétitions, avancé 1,2 ×, mouvements régressés (tractions → rowing aux anneaux, toes-to-bar → relevés de genoux) ; semaine allégée : AMRAP de 8 min à 6 sur 10. Niveau d'après les années de CrossFit et l'expérience Hyrox si renseignées, sinon le niveau de musculation | 12-18 min | C. Le format change la charge : à travail égal, un For Time de 12 min donne une FC de 171 bpm contre 153 pour un EMOM de 20 min (Smith 2024, 12 sujets) |
| M16 | Force, haltérophilie et gymnastique du CrossFit : mouvement principal à 3-6 séries de 3 à 5 répétitions avec 3, puis 2, puis 1 répétition en réserve (jamais à l'échec sur squat et soulevé, M12), 4 en réserve en semaine allégée ; le bloc suivant démarre une série plus haut (M8) ; haltérophilie en séries de 2 à charge légère (6 sur 10 au plus), arrêt dès que la technique se dégrade ; gymnastique stricte avant les versions avec élan, avec une régression par mouvement ; mouvements liés à une blessure déclarée remplacés (S2) ; poussée et tirage équilibrés | | C. Les blessures du CrossFit touchent surtout l'épaule (26 %), le rachis (24 %) et le genou (18 %) (Rodríguez 2022, études de qualité limitée) ; alterner charges prescrites et allégées est associé à plus de blessures (Mehrab 2023, preuve limitée) : la charge reste choisie par répétitions en réserve, pas par pourcentage |
| M17 | Capacité aérobie : une séance par semaine à partir de 4 jours (rameur, vélo, SkiErg ou course facile), en zone 2 (60 à 75 % de la FC max, ou allure de conversation) ; 30 min au départ, +8 % par semaine (G1) jusqu'à 60 min, ×0,65 en semaine allégée (G2) ; sans course si une zone de course est blessée | 30-60 min | B pour l'endurance (distribution d'intensité, Seiler 2010 : surtout descriptif), C pour son usage chez le pratiquant de CrossFit |
| M18 | Programmation Hyrox dédiée (Hyrox déclaré sans course) : les 8 km de course font environ la moitié du temps d'une épreuve, la semaine est donc bâtie autour de la course et des stations — 2 j : stations + qualité de course ; 3 j : + footing, la séance hybride alternant stations et course compromise d'une semaine à l'autre ; 4 j : stations et course compromise chaque semaine ; 5 j : + haut du corps (force de soutien, jambes non épuisées par la musculation) ; 6 j : + aérobie sans impact. Volume de course porté par G1, G2, G3 ; séance de qualité = intervalles de 1 km à l'allure Hyrox ou seuil (à partir de 75 min de course par semaine et de la 2e semaine) ; la course des séances hybrides compte dans le volume | 2-6 | B-C. Course ≈ 50 % du temps de l'épreuve et composante la plus liée à la performance (Rappelt 2026 ; Brandt 2025 : 51 min de course sur 86,5) ; aucun essai d'un programme d'entraînement Hyrox : l'agencement est une pratique de terrain |
| M19 | Stations et charges : charges de course officielles par catégorie (Open ou Pro, hommes ou femmes ; Doubles et Relais suivent Open) — traîneau poussé 152 / 102 / 202 / 152 kg, tiré 103 / 78 / 153 / 103 kg (traîneau compris), farmers 2 × 24 / 16 / 32 / 24 kg, sac 20 / 10 / 30 / 20 kg, wall balls 6 / 4 / 9 / 6 kg (hommes Open, femmes Open, hommes Pro, femmes Pro). L'entraînement part d'une part de ces charges (0,60 débutant, 0,80 intermédiaire, 0,95 avancé, 1,00 expert), monte de 0,05 par bloc, suit la rampe du bloc (0,90, 0,95, 1,00) et ne dépasse jamais le standard ; les stations jugées faibles passent en premier ; sans traîneau (salle perso, aucun lieu fixe) la poussée devient des fentes lestées | | C. Charges relevées sur le site officiel de l'épreuve (https://hyrox.com/the-fitness-race/, 21/10/2026) ; Fernández-Navarrete 2026 donne les temps de référence par catégorie (186 411 résultats), pas des charges d'entraînement |
| M20 | Course compromise (station puis course) : 3 à 5 répétitions dans le bloc, +1 par bloc (2 au plus), 1 de moins pour un débutant, 3 en semaine allégée et 2 en affûtage ; chaque répétition = une station à la moitié de la distance et à 85 % de la charge d'entraînement, puis 1 km à l'allure Hyrox (≈ allure du 10 km × 1,10), la première 10 s/km plus lente ; zone de course blessée : le kilomètre devient du rameur ou du vélo (S2) ; jamais deux jours durs de suite (M14) | 3-8 | C. En épreuve, la vitesse baisse de 16,1 à 13,6 km/h entre le 1er et le 8e kilomètre, à environ 84 % du seuil (Gutiérrez-Hellín 2026, 24 hommes Pro) : partir sous contrôle ; le genou et la jambe concentrent les blessures Hyrox (Chittenden 2026). Aucune étude ne compare des méthodes de travail de la course compromise : lacune |
| M21 | Objectif Hyrox daté (titre contenant « Hyrox ») : les 8 km sont dans l'épreuve et non un objectif de course (pas de C9, ni de priorité de la course) ; demi-simulation (4 × 1 km + station) 5 semaines avant (6 si la décharge tombe là), simulation complète (8 × 1 km + 8 stations) 3 semaines avant (4 si la décharge tombe là), une seule simulation complète par préparation, abandonnée ou réduite si sa course dépasse la moitié du volume de course ou la durée permise (G1, G6) ; affûtage de 2 semaines (C6), séances raccourcies, semaine de l'épreuve réduite à footings et activation ; la veille ni jambes lourdes ni séance dure, rien de dur les 2 jours suivants. Sans objectif : une demi-simulation à la 3e semaine d'un bloc sur deux | | C. Aucune étude sur la fréquence des simulations ni sur la durée de l'affûtage propre à l'Hyrox : lacune ; C6 pour l'affûtage |
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
| I7 | Course + Hyrox ou CrossFit : la course garde sa sortie longue et sa séance de qualité (G5, I2) ; au plus une séance hybride dure par semaine (Hyrox : stations et course compromise en alternance, simulations aux semaines de M21 ; CrossFit : metcon + force de M9, plus une séance de gymnastique modérée seulement si la musculation n'est pas déclarée et à partir de 4 jours), jamais à moins de 48 h de la sortie longue, de la qualité ou des jambes lourdes ; la course d'une séance hybride (compromise, simulation) est retranchée du volume de course de la semaine (G1) ; la simulation complète tient lieu de sortie longue de sa semaine ; si aucun jour ne respecte ces 48 h, la séance hybride saute plutôt que de heurter une séance de course ou de jambes ; à moins de 8 semaines d'un objectif de course, la course l'emporte : CrossFit disparaît (M9), Hyrox se réduit à une séance de stations légère | | C. Sortie longue + qualité + séance hybride remplissent les trois jours durs que G5 permet ; interférence faible sur la force maximale (Schumann 2022), plus nette sur la force explosive (Wilson 2012) |

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
| N6 | Les estimations de repas par texte ou photo sont des ordres de grandeur (fourchette, confiance) : on suit les moyennes hebdomadaires, jamais un repas isolé ; aucun jugement moral | sous-estimation fréquente : l'estimateur est invité à retenir la fourchette haute; un poids indiqué est multiplié par la densité du plat cuit | B |
| N7 | Pas de déficit pour un mineur, en cas de grossesse ou post-partum, ni d'antécédent de trouble alimentaire déclaré : renvoi vers un professionnel | | C |
| N8 | Qualité : 25 à 30 g de fibres, des légumes à chaque repas, produits ultra-transformés et alcool limités | | B |
| N9 | Quand la confiance d'une estimation de repas n'est pas élevée, l'estimateur peut poser 1 à 2 questions courtes (quantité, graisse de cuisson, sauce, boisson) : l'estimation est refaite avec les réponses, on peut toujours passer ; le serveur borne le nombre, la longueur et ne repose aucune question après des réponses | 2 questions au plus | C |
| N10 | Une valeur déclarée prime sur une valeur devinée : code-barres Open Food Facts (pour 100 g × quantité saisie) puis correction de l'utilisateur ; les corrections récentes et les repas identiques servent d'exemples aux estimations suivantes du même utilisateur (sans identité) ; le chiffre principal affiché est la moyenne des jours estimés de la semaine | 4 exemples au plus, 90 jours | C |

## G ter. Statistiques : écran de suivi des données

| Id | Règle | Valeur | Preuve |
|---|---|---|---|
| ST1 | Chaque chiffre de l'écran Statistiques vient des données stockées et d'un calcul déterministe du moteur, jamais d'un LLM ; une donnée absente est affichée comme absente (ni 0, ni valeur interpolée) ; une estimation est marquée « ≈ » ; chaque graphique a une alternative texte (tableau) | | C |
| ST2 | Repas : la moyenne de la semaine ne porte que sur les jours ayant au moins un repas estimé (un jour sans estimation n'est pas un zéro) ; la cible n'est affichée que si la taille, l'année de naissance et un poids sont connus ; l'écart à la cible est présenté sans jugement (voir N6) | 7 jours | C |
| ST3 | Poids : la courbe montre les pesées et leur moyenne glissante sur 7 jours (N5) ; le rythme hebdomadaire n'est affiché que lorsque le moteur dispose de 3 pesées sur au moins 7 jours | 7 j | C |
| ST4 | Pas : relevés de la montre par jour ; la journée en cours est incomplète et n'entre pas dans la moyenne ; un total à 0 (montre non portée) n'est pas enregistré | 7 jours | C |
| ST5 | Activité récente : une séance reliée à la montre n'est comptée qu'une fois (via l'activité) ; l'allure n'est calculée que pour une course d'au moins 1 km | 14 jours | C |
| ST6 | Records de course (5 km, 10 km) : trois sources affichées séparément, jamais fusionnées ni extrapolées : record déclaré, meilleure allure mesurée sur une sortie d'au moins cette distance, dernière estimation de la montre | 5 km, 10 km | C |
| ST7 | Charges : l'e1RM (Epley, charge × (1 + répétitions / 30)) n'est calculé que pour une série chargée de 1 à 10 répétitions et marqué « ≈ » ; sans charge, la courbe suit le meilleur nombre de répétitions ; un point par jour, seulement les séances faites ; une charge illisible écarte la série | 1 à 10 reps, 16 semaines | C (formule d'estimation, pas une mesure) |
| ST8 | Trajectoire : affichée seulement avec un objectif de performance actif et daté ; phases, jalons et volume viennent de C10 à C12 sans recalcul ; la ligne de repère est une interpolation, pas une prévision ; les points mesurés sont les estimations de la montre (converties par Riegel, C10) | | C |
| ST9 | Volume hebdomadaire : semaines du lundi au dimanche, la semaine en cours est signalée incomplète ; kilomètres de course seulement quand la montre les mesure ; une séance reliée à la montre n'est comptée qu'une fois ; repère de volume visé = C12 | 12 semaines | C |
| ST10 | Allure par sortie : points non reliés (une sortie facile et une séance de vitesse ne sont pas comparables) ; comparaison 28 jours contre 28 jours précédents seulement avec 3 sorties d'au moins 3 km de chaque côté, allure globale (temps total / distance totale) | 28 j | C |
| ST11 | Semaine « tenue » : au moins 75 % des séances prévues par le moteur sont faites ; une séance passée volontairement sort du calcul, une séance passée sans retour compte comme non faite ; la semaine en cours peut être tenue mais n'est jamais jugée non tenue | 75 % (repère de pratique) | C |
| ST12 | Série = semaines tenues consécutives ; une semaine sans séance prévue ne casse ni ne prolonge la série ; seule une semaine terminée non tenue la remet à zéro, la meilleure série sur un an reste affichée ; pas de badge | 52 semaines | C |
| ST13 | La régularité est désactivable dans le profil (préférence `ui.stats_regularity`, activée par défaut) : désactivée, rien n'est calculé ni affiché ; aucune notification, relance ni message du coach ne s'appuie sur les séries ; formulation sans culpabilisation | | C |
| ST14 | Araignée de forme : seuls des axes qu'une donnée stockée mesure sont tracés (volume, régularité, endurance, force) ; la vitesse et la récupération n'ont pas de mesure validée et ne sont pas tracées (l'écran le dit) ; aucun score global ; un axe sans donnée suffisante n'est pas tracé et en donne la raison ; le polygone n'est tracé qu'à partir de 3 axes mesurés, sinon les axes sont affichés en texte | 3 axes minimum | C |
| ST15 | Échelle de l'araignée : chaque axe est un pourcentage de TA propre référence (objectif du plan, temps visé, meilleure période précédente), arrondi et plafonné à 100 ; aucune comparaison avec d'autres personnes ni table de seuils ; la définition, la source, la période, la référence et la valeur brute sont affichées en texte à côté du pourcentage, qui ne vit jamais seul | 0 à 100 % de la référence | C |
| ST16 | Axe volume : moyenne des 4 dernières semaines terminées (la semaine en cours est exclue), en km de course si la personne a couru au moins 4 des 16 dernières semaines, sinon en minutes d'activité ; référence = repère de volume du plan (C12) en km quand un objectif de performance existe, sinon la meilleure semaine des 12 semaines précédant la période (au moins 3 semaines non vides, sinon axe non tracé) | 4 semaines ; référence sur 12 semaines | C |
| ST17 | Axe régularité : séances faites / séances prévues par le moteur sur les 12 dernières semaines terminées (séances passées volontairement hors calcul, semaine en cours exclue, comme ST11) ; au moins 8 séances prévues réparties sur 4 semaines, sinon axe non tracé ; régularité masquée dans le profil (ST13) : rien n'est calculé | 12 semaines | C |
| ST18 | Axe endurance : meilleur effort de course des 8 dernières semaines mesuré par la montre (C14), converti en temps équivalent par Riegel (C10) sur la distance de l'objectif de performance, sinon sur 10 km ; référence = temps visé, sinon la meilleure estimation obtenue par les fenêtres de 8 semaines qui se terminent 9 à 20 semaines avant (aucune sinon : axe non tracé) ; pourcentage = temps de référence / temps équivalent ; les temps saisis et les records ne servent pas ; sans FC l'estimation n'est qu'une borne et est signalée comme telle | 8 semaines ; Riegel 1,06 | C |
| ST19 | Axe force : e1RM d'Epley (ST7, C15) le plus haut des 12 dernières semaines par exercice de référence, face au plus haut des 12 semaines précédentes ; pourcentage = moyenne des exercices présents dans les deux périodes, au moins 2 exercices, sinon axe non tracé ; les séries au-delà de 10 répétitions ne comptent pas | 12 semaines ; 2 exercices minimum | C |
| ST20 | Comparaison « il y a 4 semaines » : mêmes règles, fenêtres décalées de 4 semaines ; la forme passée n'est tracée que si chaque axe dessiné a une valeur à cette date (sinon les écarts sont donnés en texte, axe par axe) ; l'écart est en points de pourcentage, calculé par le moteur, sans jugement | 4 semaines | C |

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

## Hyrox et CrossFit : sources et lacunes (21/10/2026)

Sources lues (résumés PubMed) : Rappelt 2026, Gutiérrez-Hellín 2026, Chittenden 2026, Fernández-Navarrete 2026, Brandt 2025, Villarroel López 2025 (Hyrox et entraînement fonctionnel) ;
Rodríguez 2022, Mehrab 2023, Claudino 2018, Smith 2024, Feito 2018 (CrossFit) ; Ramos-Campo 2025 (musculation et endurance). Voir `data/evidence/endurance.yaml` (HYB-004 à HYB-014).

Ce que la littérature ne dit pas, et que ces règles tranchent par pratique de terrain (niveau C) : aucun essai d'un programme d'entraînement Hyrox ou CrossFit complet ;
rien sur la répartition hebdomadaire des séances (M10, M18) ; rien sur l'entraînement de la course compromise (M20) ni sur la fréquence des simulations (M21) ;
aucune étude des progressions de gymnastique et de leurs régressions (M16) ; les charges d'entraînement par niveau (M19) sont un choix prudent, pas un résultat.
Les charges de course viennent du règlement publié par l'organisateur et peuvent changer d'une saison à l'autre : à revérifier à chaque saison.

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
- **N9, N10** : règles de conception sans étude propre ; les valeurs d'Open Food Facts sont déclarées par des contributeurs et peuvent être fausses ou périmées : la correction de l'utilisateur prime.
- **N3, N7, N8** : non vérifiées.
