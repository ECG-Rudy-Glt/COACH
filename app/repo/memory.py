"""Stockage en mémoire (développement, démonstration, tests) : le noyau (utilisateurs, faits) et les domaines assemblés."""


from app.questionnaire.models import Fact
from app.repo.accounts import AccountsMemory
from app.repo.chat import ChatMemory
from app.repo.coach import CoachMemory
from app.repo.exercises import ExercisesMemory
from app.repo.garmin import GarminMemory
from app.repo.goals import GoalsMemory
from app.repo.nutrition import NutritionMemory
from app.repo.plan import PlanMemory


class MemoryRepo(AccountsMemory, ExercisesMemory, GoalsMemory, PlanMemory, GarminMemory, CoachMemory, ChatMemory, NutritionMemory):
    name = "memory"

    def __init__(self) -> None:
        self._users: dict[int, str] = {}
        self._facts: dict[int, list[Fact]] = {}

    def create_user(self, name: str) -> int:
        uid = len(self._users) + 1
        self._users[uid] = name
        self._facts[uid] = []
        return uid

    def user_exists(self, user_id: int) -> bool:
        return user_id in self._users

    def add_facts(self, user_id: int, facts: list[Fact]) -> None:
        self._facts[user_id].extend(facts)

    def list_facts(self, user_id: int) -> list[Fact]:
        return list(self._facts[user_id])
