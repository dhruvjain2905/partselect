"""
Conversation state that persists across every turn in a session.

LangGraph's MemorySaver checkpoints this state by thread_id so
every message in a session has access to the accumulated context.
"""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ChatState(TypedDict):
    # Full message history — LangGraph's add_messages reducer handles appending
    messages: Annotated[list[BaseMessage], add_messages]

    # Appliance context — extracted progressively across turns
    # Once set, these persist for the entire session
    appliance_type: Optional[str]      # "dishwasher" | "refrigerator"
    brand: Optional[str]               # "whirlpool" | "kitchenaid" etc.
    model_number: Optional[str]        # "WDT750SAHZ0" — the gold standard
    model_confidence: str              # "none" | "partial" | "confirmed"

    # Guardrail output from the current turn
    intent_category: Optional[str]     # see INTENT_CATEGORIES below
    is_in_scope: bool


# Intent categories the guardrail classifies into
INTENT_CATEGORIES = [
    "part_lookup",           # user has a part number and wants info
    "compatibility_check",   # "is this part compatible with my model"
    "symptom_diagnosis",     # "my dishwasher is not draining"
    "installation_help",     # "how do I install part X"
    "model_overview",        # "what parts should I know about for my model"
    "general_appliance",     # general appliance question (still in scope)
    "greeting",              # hello, hi, etc.
    "out_of_scope",          # anything unrelated to dishwasher/fridge parts
]
