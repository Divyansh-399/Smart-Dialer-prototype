"""Lock-protected source of truth for the single-process prototype."""

from threading import RLock
import sqlite3

from .models import Agent, AgentState, CallRecord, CallState, Lead


class InMemoryRepository:
    """The lock models a DB transaction: reserve agent and borrower together or neither."""
    def __init__(self, agents: list[Agent], leads: list[Lead] | None = None) -> None:
        self.lock = RLock()
        self.agents = {agent.id: agent for agent in agents}
        self.leads = {lead.id: lead for lead in leads or []}
        self.calls: dict[str, CallRecord] = {}

    def add_leads(self, leads: list[Lead]) -> None:
        with self.lock:
            self.leads.update({lead.id: lead for lead in leads})

    def available_agents(self) -> int:
        with self.lock:
            return sum(agent.state == AgentState.AVAILABLE for agent in self.agents.values())

    def reserve(self, lead_id: str, call: CallRecord, turn: int = 0, lookahead_turns: int = 0) -> bool:
        """Atomic compare-and-set reservation, safe when two workers race."""
        with self.lock:
            lead = self.leads[lead_id]
            if lead.reserved_call_id:
                return False
            agent = next((a for a in self.agents.values() if a.state == AgentState.AVAILABLE), None)
            future = False
            if agent is None and lookahead_turns:
                agent = next((a for a in self.agents.values()
                              if a.state == AgentState.CONNECTED and not a.future_call_id
                              and a.release_turn <= turn + lookahead_turns), None)
                future = agent is not None
            if not agent:
                return False
            lead.reserved_call_id = call.id
            if future:
                agent.future_call_id = call.id
            else:
                agent.reserved_call_id = call.id
                agent.state = AgentState.RESERVED
            call.agent_id, call.state = agent.id, CallState.RESERVED
            call.history.append(CallState.RESERVED.value)
            self.calls[call.id] = call
            return True

    def release(self, call: CallRecord) -> None:
        with self.lock:
            lead = self.leads[call.lead_id]
            agent = self.agents[call.agent_id] if call.agent_id else None
            if lead.reserved_call_id == call.id:
                lead.reserved_call_id = None
            if agent and agent.reserved_call_id == call.id:
                agent.reserved_call_id = None
                if agent.future_call_id:
                    agent.reserved_call_id, agent.future_call_id = agent.future_call_id, None
                    agent.state = AgentState.RESERVED
                elif agent.state not in {AgentState.OFFLINE, AgentState.PAUSED}:
                    agent.state = AgentState.AVAILABLE
            elif agent and agent.future_call_id == call.id:
                agent.future_call_id = None

    def mark_agent_offline(self, agent_id: str) -> None:
        with self.lock:
            self.agents[agent_id].state = AgentState.OFFLINE


class SqliteReservationStore:
    """Small durable equivalent of ``reserve`` for multi-process deployments.

    SQLite's BEGIN IMMEDIATE gives one writer the reservation transaction. PostgreSQL
    would use the same conditional writes with row locks / SKIP LOCKED at scale.
    """
    def __init__(self, path: str) -> None:
        self.path = path
        connection = self._connect()
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, state TEXT NOT NULL, call_id TEXT);
                CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, call_id TEXT);
            """)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)

    def seed(self, agent_ids: list[str], lead_ids: list[str]) -> None:
        connection = self._connect()
        try:
            connection.executemany("INSERT OR IGNORE INTO agents VALUES (?, 'available', NULL)", ((item,) for item in agent_ids))
            connection.executemany("INSERT OR IGNORE INTO leads VALUES (?, NULL)", ((item,) for item in lead_ids))
        finally:
            connection.close()

    def reserve_pair(self, lead_id: str, call_id: str) -> str | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("UPDATE leads SET call_id=? WHERE id=? AND call_id IS NULL", (call_id, lead_id)).rowcount != 1:
                connection.execute("ROLLBACK")
                return None
            agent = connection.execute("SELECT id FROM agents WHERE state='available' AND call_id IS NULL LIMIT 1").fetchone()
            if not agent:
                connection.execute("ROLLBACK")
                return None
            agent_id = agent[0]
            connection.execute("UPDATE agents SET state='reserved', call_id=? WHERE id=?", (call_id, agent_id))
            connection.execute("COMMIT")
            return agent_id
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
