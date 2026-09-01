"""Lock-protected source of truth for the single-process prototype."""

from threading import RLock

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

    def reserve(self, lead_id: str, call: CallRecord) -> bool:
        """Atomic compare-and-set reservation, safe when two workers race."""
        with self.lock:
            lead = self.leads[lead_id]
            if lead.reserved_call_id:
                return False
            agent = next((a for a in self.agents.values() if a.state == AgentState.AVAILABLE), None)
            if not agent:
                return False
            lead.reserved_call_id = call.id
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
                if agent.state not in {AgentState.OFFLINE, AgentState.PAUSED}:
                    agent.state = AgentState.AVAILABLE

    def mark_agent_offline(self, agent_id: str) -> None:
        with self.lock:
            self.agents[agent_id].state = AgentState.OFFLINE
