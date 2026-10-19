# Mémoire et historique pour le LLM

> Décision du 06/10/2026 (à valider avant la Phase 4).

## Besoin
Le coach LLM doit connaître **tout l'historique** de la personne (parcours long terme, performances
passées et actuelles, réponses, séances, bilans précédents, échanges) et le relire à la demande.

## Choix : pas de base NoSQL séparée
Le modèle de faits est déjà documentaire : `facts.value` est du **JSONB** (listes, objets imbriqués,
parcours, performances). Postgres permet d'interroger ces documents (index GIN, opérateurs JSON) tout
en gardant transactions, sauvegarde unique (pg_dump + PBS) et une seule base à exploiter. Une base
NoSQL de plus (MongoDB, etc.) doublerait la sauvegarde et la sécurité des données de santé sans
fonction que JSONB ne couvre pas ici.

## Ce qui est ajouté
1. **Table `coach_memory`** : bilans hebdomadaires, résumés de conversation, décisions du plan
   (JSONB + texte, date, sujets). Rien n'est supprimé, seulement résumé.
2. **Table `llm_calls`** : prompt, réponse brute, validation, coût (traçabilité).
3. **Aucun accès direct à la base par le LLM.** Il reçoit :
   - un **instantané du profil** compact (faits courants + performances) construit par le serveur ;
   - des **outils en lecture seule**, validés côté serveur : `get_history(domain, depuis)`,
     `get_performance(exercice)`, `get_sessions(du, au)`, `get_past_reviews(n)` ;
   - les **derniers résumés** de mémoire.
4. **Compactage** : les longues périodes sont résumées par le LLM (résumé stocké, source conservée)
   pour tenir dans le contexte.
5. **Recherche sémantique (option)** : extension `pgvector` dans le même Postgres si la recherche par
   mots-clés ne suffit pas.
6. **Vie privée** : identifiants anonymisés dans les prompts ; pas de nom ni d'adresse envoyés.
