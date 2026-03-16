"""
LangGraph nodes. Each node receives the full ChatState and returns
a partial state update (only the keys that changed).

Node order per turn:
  guardrail_node → context_node → agent_node ↔ tools_node
"""

import json
import re
from typing import Literal

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.agent.state import ChatState
from app.agent.prompts import (
    AGENT_SYSTEM,
    GUARDRAIL_SYSTEM,
    OUT_OF_SCOPE_RESPONSE,
    GREETING_RESPONSE,
)
from app.config import get_settings
from app.tools import TOOLS

# ---------------------------------------------------------------------------
# Model clients (initialised lazily so env vars load first)
# ---------------------------------------------------------------------------

_agent_llm = None
_guardrail_client = None


def _get_agent_llm():
    global _agent_llm
    if _agent_llm is None:
        settings = get_settings()
        _agent_llm = ChatAnthropic(
            model=settings.agent_model,
            anthropic_api_key=settings.anthropic_api_key,
            max_tokens=2048,
        ).bind_tools(TOOLS)
    return _agent_llm


def _get_guardrail_client():
    global _guardrail_client
    if _guardrail_client is None:
        settings = get_settings()
        _guardrail_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _guardrail_client


# ---------------------------------------------------------------------------
# NODE 1: Guardrail
# Fast intent classification before any tools or DB calls.
# ---------------------------------------------------------------------------

async def guardrail_node(state: ChatState) -> dict:
    """
    Classify intent and extract context from the latest user message.
    Uses a cheap/fast model. Runs before anything expensive.
    """
    settings = get_settings()
    client = _get_guardrail_client()

    # Get last human message
    last_human = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if not last_human:
        return {"is_in_scope": True, "intent_category": "greeting"}

    # Build context summary for the guardrail
    context_summary = ""
    if state.get("model_number"):
        context_summary = f"\n[Session context: user has model {state['model_number']}]"
    if state.get("appliance_type"):
        context_summary += f"\n[Appliance type: {state['appliance_type']}]"

    try:
        response = client.messages.create(
            model=settings.guardrail_model,
            max_tokens=256,
            system=GUARDRAIL_SYSTEM,
            messages=[{"role": "user", "content": last_human + context_summary}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if the model added them
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()

        classification = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        # If guardrail fails, default to in-scope to avoid blocking valid queries
        classification = {
            "category": "general_appliance",
            "is_in_scope": True,
            "appliance_type": None,
            "model_number": None,
            "brand": None,
        }

    category = classification.get("category", "general_appliance")
    is_in_scope = classification.get("is_in_scope", True)

    # Handle greeting immediately — no tools needed
    if category == "greeting":
        return {
            "is_in_scope": True,
            "intent_category": "greeting",
            "messages": [AIMessage(content=GREETING_RESPONSE)],
        }

    # Handle out-of-scope immediately
    if not is_in_scope or category == "out_of_scope":
        return {
            "is_in_scope": False,
            "intent_category": "out_of_scope",
            "messages": [AIMessage(content=OUT_OF_SCOPE_RESPONSE)],
        }

    # Merge any newly extracted context into state (don't overwrite confirmed values)
    updates: dict = {
        "is_in_scope": True,
        "intent_category": category,
    }

    extracted_type = classification.get("appliance_type")
    if extracted_type and not state.get("appliance_type"):
        updates["appliance_type"] = extracted_type

    extracted_brand = classification.get("brand")
    if extracted_brand and not state.get("brand"):
        updates["brand"] = extracted_brand

    extracted_model = classification.get("model_number")
    if extracted_model:
        current_confidence = state.get("model_confidence", "none")
        if current_confidence != "confirmed":
            updates["model_number"] = extracted_model
            updates["model_confidence"] = "confirmed"

    return updates


# ---------------------------------------------------------------------------
# NODE 2: Context extractor
# Runs after guardrail passes. Refines context with regex patterns.
# ---------------------------------------------------------------------------

# Patterns for common model number formats
_MODEL_PATTERN = re.compile(
    r"\b([A-Z]{2,5}[0-9]{2,4}[A-Z0-9]{3,10})\b",
    re.IGNORECASE,
)


def context_node(state: ChatState) -> dict:
    """
    Refine session context from the latest message using regex.
    Always returns at least one key so LangGraph doesn't reject the update.
    """
    updates = {}

    last_human = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if not last_human:
        return {"intent_category": state.get("intent_category")}

    # Try to extract model number if we don't have a confirmed one
    if state.get("model_confidence", "none") != "confirmed":
        match = _MODEL_PATTERN.search(last_human)
        if match:
            candidate = match.group(1).upper()
            # Sanity check: at least 6 chars, has both letters and numbers
            if (len(candidate) >= 6
                    and any(c.isdigit() for c in candidate)
                    and any(c.isalpha() for c in candidate)):
                updates["model_number"] = candidate
                updates["model_confidence"] = "confirmed"

    # Infer appliance type from keywords if not already known
    if not state.get("appliance_type"):
        lower = last_human.lower()
        if any(w in lower for w in ["dishwasher", "dish washer", "dishes", "rack", "spray arm", "detergent dispenser"]):
            updates["appliance_type"] = "dishwasher"
        elif any(w in lower for w in ["refrigerator", "fridge", "freezer", "ice maker", "crisper", "water dispenser", "filter"]):
            updates["appliance_type"] = "refrigerator"

    # LangGraph requires at least one key in the update
    if not updates:
        updates["intent_category"] = state.get("intent_category")

    return updates


# ---------------------------------------------------------------------------
# NODE 3: Agent
# Claude with tools. Loops with tool_node until no more tool calls.
# ---------------------------------------------------------------------------

async def agent_node(state: ChatState) -> dict:
    """
    Main reasoning node. Claude decides which tools to call and synthesises
    the final response once tools return results.
    """
    llm = _get_agent_llm()

    # Build the system message with current session context injected
    context_note = _build_context_note(state)
    system_content = AGENT_SYSTEM
    if context_note:
        system_content += f"\n\n## CURRENT SESSION CONTEXT\n{context_note}"

    messages = list(state["messages"])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_content)] + messages
    else:
        messages[0] = SystemMessage(content=system_content)

    response = await llm.ainvoke(messages)
    return {"messages": [response]}


def _build_context_note(state: ChatState) -> str:
    """Summarise confirmed session context for the agent system prompt."""
    parts = []
    if state.get("appliance_type"):
        parts.append(f"Appliance type: {state['appliance_type']}")
    if state.get("brand"):
        parts.append(f"Brand: {state['brand']}")
    if state.get("model_number"):
        conf = state.get("model_confidence", "partial")
        parts.append(f"Model number: {state['model_number']} (confidence: {conf})")
    else:
        parts.append("Model number: NOT YET PROVIDED — ask gently if it would help, but don't block the conversation on it.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# NODE 4: Tools
# Standard LangGraph ToolNode — executes whatever tool the agent called.
# ---------------------------------------------------------------------------

tools_node = ToolNode(TOOLS)


# ---------------------------------------------------------------------------
# ROUTING FUNCTIONS
# These determine which node runs next based on current state.
# ---------------------------------------------------------------------------

def route_after_guardrail(state: ChatState) -> Literal["context", "__end__"]:
    """After guardrail: continue if in scope, end if not (message already added)."""
    if not state.get("is_in_scope", True):
        return "__end__"
    if state.get("intent_category") == "greeting":
        return "__end__"
    return "context"


def route_after_agent(state: ChatState) -> Literal["tools", "__end__"]:
    """After agent: run tools if tool_calls present, else we're done."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "__end__"
