-- Langue choisie par l'utilisateur (fr, en) : sert aux notifications, aux mails et au coach IA en dehors d'une requête de l'interface.
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT CHECK (lang IN ('fr', 'en'));
