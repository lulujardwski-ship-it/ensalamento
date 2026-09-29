"""Repositório transacional de documento único, com revisão otimista.

PostgreSQL usa SELECT FOR UPDATE; SQLite local usa BEGIN IMMEDIATE. O formato
prioriza uma demonstração auditável. A granularidade do bloqueio é global,
portanto a evolução para muitos administradores exige tabelas normalizadas.
"""
import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


ENTITIES = ("periods", "campuses", "buildings", "resources", "courses", "subjects",
            "rooms", "users", "classes", "meetings")


def empty_state():
    return {**{name: [] for name in ENTITIES}, "allocations": [], "versions": [],
            "active_versions": {}, "audit": [], "identities": [],
            "settings": {"timezone": "America/Sao_Paulo",
                         "weights": {"capacity": 40, "building": 20,
                                     "resources": 25, "stability": 15}},
            "schema_version": 1, "demo_data": False}


class StaleRevision(Exception):
    pass


class Store:
    def __init__(self, url):
        self.postgres = url.startswith(("postgres://", "postgresql://"))
        self.url = url
        self.table = "ensalamento.application_state" if self.postgres else "application_state"
        if not self.postgres:
            self.path = url.removeprefix("sqlite:///")
            if self.path == ":memory:":
                raise ValueError("Use arquivo SQLite temporário; conexões são transacionais por operação.")
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self):
        if self.postgres:
            import psycopg
            connection = psycopg.connect(self.url, connect_timeout=10)
        else:
            connection = sqlite3.connect(self.path, timeout=15)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.connection() as conn:
            value_type = "JSONB" if self.postgres else "TEXT"
            if self.postgres:
                # Workers e réplicas podem iniciar juntos. IF NOT EXISTS não
                # serializa DDL nem REVOKE; o bloqueio dura até o commit.
                conn.execute("SELECT pg_advisory_xact_lock(184337, 1)")
                # Fora de public: nunca adicionar este schema aos exposed schemas do Supabase.
                conn.execute("CREATE SCHEMA IF NOT EXISTS ensalamento")
                conn.execute("REVOKE ALL ON SCHEMA ensalamento FROM PUBLIC")
            conn.execute(f"CREATE TABLE IF NOT EXISTS {self.table} (id INTEGER PRIMARY KEY CHECK(id=1), revision BIGINT NOT NULL, document {value_type} NOT NULL)")
            payload = json.dumps(empty_state())
            if self.postgres:
                conn.execute(f"INSERT INTO {self.table}(id,revision,document) VALUES(1,0,%s::jsonb) ON CONFLICT(id) DO NOTHING", (payload,))
            else:
                conn.execute("INSERT OR IGNORE INTO application_state(id,revision,document) VALUES(1,0,?)", (payload,))

    def _read(self, conn, lock=False):
        suffix = " FOR UPDATE" if self.postgres and lock else ""
        row = conn.execute(f"SELECT revision, document FROM {self.table} WHERE id=1" + suffix).fetchone()
        return int(row[0]), json.loads(row[1]) if isinstance(row[1], str) else row[1]

    def read(self):
        with self.connection() as conn:
            return self._read(conn)

    def update(self, revision, change):
        """Apply change under a lock. Exceptions roll back all changes."""
        with self.connection() as conn:
            if not self.postgres:
                conn.execute("BEGIN IMMEDIATE")
            current, state = self._read(conn, lock=True)
            if revision is not None and (isinstance(revision, bool) or revision != current):
                raise StaleRevision("Os dados foram alterados por outra operação. Atualize a tela e tente novamente.")
            result = change(state)
            payload = json.dumps(state, ensure_ascii=False, allow_nan=False)
            if self.postgres:
                conn.execute(f"UPDATE {self.table} SET revision=%s, document=%s::jsonb WHERE id=1", (current + 1, payload))
            else:
                conn.execute("UPDATE application_state SET revision=?, document=? WHERE id=1", (current + 1, payload))
            return current + 1, copy.deepcopy(result)
