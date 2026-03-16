import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.agent.graph import graph
from app.agent.state import ChatState

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's latest message")
    session_id: str = Field(..., description="Unique session/thread identifier")


class Product(BaseModel):
    ps_number: str
    name: str
    price: Optional[str] = None
    in_stock: Optional[bool] = None
    product_url: Optional[str] = None
    category: Optional[str] = None
    fix_rate_pct: Optional[float] = None
    similarity: Optional[float] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    context: dict
    products: list[Product] = []


def _extract_products(messages: list) -> list[Product]:
    """Extract unique product data from ToolMessage results."""
    seen = set()
    products = []

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            continue

        # Semantic search returns {"parts": [...], "expert_qas": [...], ...}
        if isinstance(data, dict) and "parts" in data:
            for p in data["parts"]:
                ps = p.get("ps_number")
                if ps and ps not in seen:
                    seen.add(ps)
                    products.append(Product(
                        ps_number=ps,
                        name=p.get("name", ""),
                        price=str(p["price"]) if p.get("price") else None,
                        in_stock=p.get("in_stock"),
                        product_url=p.get("product_url"),
                        category=p.get("category"),
                        similarity=p.get("similarity"),
                    ))

        # SQL results return a list of dicts
        if isinstance(data, list):
            for row in data:
                ps = row.get("ps_number")
                if ps and ps not in seen:
                    seen.add(ps)
                    products.append(Product(
                        ps_number=ps,
                        name=row.get("name", ""),
                        price=str(row["price"]) if row.get("price") else None,
                        in_stock=row.get("in_stock"),
                        product_url=row.get("product_url"),
                        fix_rate_pct=row.get("fix_rate_pct"),
                    ))

    return products


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Maintains conversation state by session_id.
    Returns the assistant reply, session context, and any products found.
    """
    config = {"configurable": {"thread_id": request.session_id}}

    # Get current state (may be None for a new session)
    current_state = await graph.aget_state(config)

    # Build initial state for new sessions
    if current_state.values:
        state_update = {"messages": [HumanMessage(content=request.message)]}
    else:
        state_update = {
            "messages": [HumanMessage(content=request.message)],
            "appliance_type": None,
            "brand": None,
            "model_number": None,
            "model_confidence": "none",
            "intent_category": None,
            "is_in_scope": True,
        }

    try:
        result = await graph.ainvoke(state_update, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Extract the last AI message as the reply
    messages = result.get("messages", [])
    reply = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            reply = msg.content
            break

    if not reply:
        reply = "I'm sorry, I wasn't able to generate a response. Please try again."

    # Extract structured product data from tool results
    products = _extract_products(messages)

    return ChatResponse(
        reply=reply,
        session_id=request.session_id,
        context={
            "appliance_type":   result.get("appliance_type"),
            "brand":            result.get("brand"),
            "model_number":     result.get("model_number"),
            "model_confidence": result.get("model_confidence", "none"),
        },
        products=products,
    )


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear conversation history for a session (start fresh)."""
    return {
        "message": "Start a new session by using a different session_id.",
        "session_id": session_id,
    }
