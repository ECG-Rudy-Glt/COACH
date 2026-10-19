"""Valeurs canoniques et libellés français des filtres."""

MUSCLE_FR = {
    "abdominals": "Abdominaux", "abductors": "Abducteurs", "adductors": "Adducteurs",
    "biceps": "Biceps", "calves": "Mollets", "chest": "Pectoraux", "forearms": "Avant-bras",
    "glutes": "Fessiers", "hamstrings": "Ischio-jambiers", "lats": "Grand dorsal",
    "lower back": "Bas du dos", "middle back": "Milieu du dos", "neck": "Nuque",
    "quadriceps": "Quadriceps", "shoulders": "Épaules", "traps": "Trapèzes", "triceps": "Triceps",
}
EQUIPMENT_FR = {
    "barbell": "Barre", "dumbbell": "Haltères", "kettlebell": "Kettlebell", "cable": "Poulie",
    "machine": "Machine", "bands": "Élastiques", "bench": "Banc", "pull-up bar": "Barre de traction",
    "exercise ball": "Swiss ball", "medicine ball": "Médecine ball", "foam roll": "Rouleau",
    "ez bar": "Barre EZ", "mat": "Tapis", "bodyweight": "Poids du corps", "other": "Autre",
    "sled": "Traîneau", "rower": "Rameur", "skierg": "SkiErg", "sandbag": "Sac de sable",
}
KIND_FR = {
    "strength": "Force", "stretching": "Étirements", "cardio": "Cardio", "plyometrics": "Pliométrie",
    "olympic": "Haltérophilie", "strongman": "Strongman", "powerlifting": "Force athlétique",
    "mobility": "Mobilité et gainage", "pilates": "Pilates", "hyrox": "Hyrox", "trail": "Trail",
    "other": "Autre",
}

# --- correspondances sources -> valeurs canoniques ---
WGER_MUSCLE = {
    "shoulders": "shoulders", "biceps": "biceps", "hamstrings": "hamstrings", "calves": "calves",
    "glutes": "glutes", "lats": "lats", "chest": "chest", "quads": "quadriceps", "abs": "abdominals",
    "triceps": "triceps", "brachialis": "biceps", "obliquus externus abdominis": "abdominals",
    "serratus anterior": "chest", "soleus": "calves", "trapezius": "traps",
}
WGER_EQUIPMENT = {
    "barbell": "barbell", "bench": "bench", "cable machine": "cable", "dumbbell": "dumbbell",
    "gym mat": "mat", "incline bench": "bench", "kettlebell": "kettlebell", "pull-up bar": "pull-up bar",
    "resistance band": "bands", "sz-bar": "ez bar", "swiss ball": "exercise ball",
    "none (bodyweight exercise)": "bodyweight",
}
FREE_EQUIPMENT = {
    "body only": "bodyweight", "kettlebells": "kettlebell", "e-z curl bar": "ez bar",
    "foam roll": "foam roll", "exercise ball": "exercise ball", "medicine ball": "medicine ball",
    "bands": "bands", "barbell": "barbell", "dumbbell": "dumbbell", "cable": "cable",
    "machine": "machine", "other": "other",
}
FREE_KIND = {
    "strength": "strength", "stretching": "stretching", "plyometrics": "plyometrics",
    "powerlifting": "powerlifting", "olympic weightlifting": "olympic", "strongman": "strongman",
    "cardio": "cardio",
}
