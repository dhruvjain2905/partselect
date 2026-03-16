"""
Assembles the LangGraph state machine and compiles it with a MemorySaver
so conversation state (model number, appliance type, etc.) persists
across turns in the same session.

Graph topology:

  START
    │
    ▼
  guardrail ──(out of scope / greeting)──► END
    │
    │ (in scope)
    ▼
  context
    │
    ▼
  agent ◄──────────────────────────────────┐
    │                                      │
    ├──(has tool_calls)──► tools ──────────┘
    │
    └──(no tool_calls)──► END
"""

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import ChatState
from app.agent.nodes import (
    guardrail_node,
    context_node,
    agent_node,
    tools_node,
    route_after_guardrail,
    route_after_agent,
)

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(ChatState)

    # Register nodes
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("context",   context_node)
    graph.add_node("agent",     agent_node)
    graph.add_node("tools",     tools_node)

    # Edges
    graph.add_edge(START, "guardrail")

    graph.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"context": "context", "__end__": END},
    )

    # Context always flows to agent — no more hard clarify gate
    graph.add_edge("context", "agent")

    # Agent ↔ tools loop
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "__end__": END},
    )
    graph.add_edge("tools", "agent")

    # Compile with in-memory checkpointing (swap for SqliteSaver/RedisSaver in prod)
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)
    return compiled


# Module-level singleton — imported by routes and the terminal chat script
graph = build_graph()
