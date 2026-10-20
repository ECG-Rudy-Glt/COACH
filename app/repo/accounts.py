"""Comptes et sessions de connexion : version mémoire et version Postgres du domaine (mêlées dans MemoryRepo / PostgresRepo par héritage)."""
from datetime import UTC, datetime
from typing import Any


class AccountsMemory:
    def _acct(self) -> dict[int, dict[str, Any]]:
        if not hasattr(self, "_accounts"):
            self._accounts: dict[int, dict[str, Any]] = {}
            self._sessions: dict[str, tuple[int, datetime]] = {}
        return self._accounts

    def create_account(self, name: str, email: str, password_hash: str) -> int:
        uid = self.create_user(name)
        self._acct()[uid] = {"email": email, "password_hash": password_hash}
        return uid

    def get_account(self, email: str) -> dict[str, Any] | None:
        for uid, a in self._acct().items():
            if a["email"] == email:
                return {"id": uid, "name": self._users[uid], "password_hash": a["password_hash"]}
        return None

    def has_accounts(self) -> bool:
        return bool(self._acct())

    def list_legacy_users(self) -> list[dict[str, Any]]:
        return [{"id": u, "name": n, "answers": len(self._facts[u])}
                for u, n in self._users.items() if u not in self._acct()]

    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool:
        if user_id not in self._users or user_id in self._acct():
            return False
        self._users[user_id] = name
        self._acct()[user_id] = {"email": email, "password_hash": password_hash}
        return True

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self._acct()
        self._sessions[token_hash] = (user_id, expires_at)

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        self._acct()
        row = self._sessions.get(token_hash)
        if not row or row[1] < datetime.now(UTC):
            return None
        uid = row[0]
        return {"id": uid, "name": self._users[uid], "email": self._accounts[uid]["email"]}

    def delete_session(self, token_hash: str) -> None:
        self._acct()
        self._sessions.pop(token_hash, None)

    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None:
        self._acct()[user_id]["password_hash"] = password_hash
        self._sessions = {t: v for t, v in self._sessions.items() if v[0] != user_id or t == keep_session}


class AccountsPostgres:
    def create_account(self, name: str, email: str, password_hash: str) -> int:
        with self._conn() as c:
            row = c.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                            (name, email, password_hash)).fetchone()
            return row["id"]

    def get_account(self, email: str) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute("SELECT id, name, password_hash FROM users WHERE email = %s", (email,)).fetchone()

    def has_accounts(self) -> bool:
        with self._conn() as c:
            return bool(c.execute("SELECT EXISTS (SELECT 1 FROM users WHERE email IS NOT NULL) AS x").fetchone()["x"])

    def list_legacy_users(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            return c.execute(
                "SELECT u.id, u.name, (SELECT count(*) FROM facts f WHERE f.user_id = u.id) AS answers "
                "FROM users u WHERE u.email IS NULL ORDER BY u.id").fetchall()

    def adopt_legacy_user(self, user_id: int, name: str, email: str, password_hash: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE users SET name = %s, email = %s, password_hash = %s "
                            "WHERE id = %s AND email IS NULL", (name, email, password_hash, user_id))
            return cur.rowcount == 1

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < now()")
            c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                      (token_hash, user_id, expires_at))

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        with self._conn() as c:
            return c.execute(
                "SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > now()", (token_hash,)).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def set_password(self, user_id: int, password_hash: str, keep_session: str | None) -> None:
        """Change le mot de passe et ferme les autres sessions de l'utilisateur."""
        with self._conn() as c:
            c.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            c.execute("DELETE FROM sessions WHERE user_id = %s AND token_hash IS DISTINCT FROM %s",
                      (user_id, keep_session))
