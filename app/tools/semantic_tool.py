"""
Semantic search tool — pgvector cosine similarity across parts, Q&As, repair stories.
"""

import json
import asyncio
from typing import Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from app.database import execute_query
from app.config import get_settings


class SemanticInput(BaseModel):
    query: str = Field(description="The user's problem description in natural language.")
    appliance_type: Optional[str] = Field(
        default=None,
        description="'dishwasher' or 'refrigerator' — narrows results significantly if known."
    )
    model_number: Optional[str] = Field(
        default=None,
        description="e.g. 'WDT750SAHZ0' — filters parts to compatible ones only if known."
    )


async def _embed(text: str) -> list[float]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(model=settings.embedding_model, input=text)
    return response.data[0].embedding


def _vec_str(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


async def _search_parts(vec, appliance_type, model_number, limit):
    vs = _vec_str(vec)
    type_f = f"AND pc.appliance_type_id = {1 if appliance_type=='dishwasher' else 2}" if appliance_type else ""
    model_f = (
        f"AND p.id IN (SELECT mc.part_id FROM model_part_compat mc "
        f"JOIN appliance_model m ON m.id=mc.model_id "
        f"WHERE UPPER(m.model_number)=UPPER('{model_number}'))"
    ) if model_number else ""
    sql = f"""
    SELECT p.ps_number, p.name, p.price, p.in_stock, p.product_url,
           pc.name AS category, 1-(p.embedding <=> '{vs}') AS similarity
    FROM part p JOIN part_category pc ON pc.id=p.category_id
    WHERE p.embedding IS NOT NULL {type_f} {model_f}
    ORDER BY p.embedding <=> '{vs}' LIMIT {limit}"""
    rows = await execute_query(sql)
    for r in rows: r["_source"] = "part"
    return rows


async def _search_qas(vec, appliance_type, model_number, limit):
    vs = _vec_str(vec)
    type_f = f"AND at.id = {1 if appliance_type=='dishwasher' else 2}" if appliance_type else ""
    model_f = f"AND UPPER(am.model_number)=UPPER('{model_number}')" if model_number else ""
    sql = f"""
    SELECT qa.id, qa.question, qa.answer, qa.asker_name, qa.helpful_count,
           am.model_number, 1-(qa.embedding <=> '{vs}') AS similarity
    FROM expert_qa qa
    LEFT JOIN appliance_model am ON am.id=qa.model_id
    LEFT JOIN appliance_type at ON at.id=am.appliance_type_id
    WHERE qa.embedding IS NOT NULL {type_f} {model_f}
    ORDER BY qa.embedding <=> '{vs}' LIMIT {limit}"""
    rows = await execute_query(sql)
    for r in rows: r["_source"] = "expert_qa"
    return rows


async def _search_stories(vec, appliance_type, model_number, limit):
    vs = _vec_str(vec)
    type_f = f"AND at.id = {1 if appliance_type=='dishwasher' else 2}" if appliance_type else ""
    model_f = f"AND UPPER(am.model_number)=UPPER('{model_number}')" if model_number else ""
    sql = f"""
    SELECT rs.id, rs.story, rs.author, rs.difficulty, rs.repair_time, rs.tools,
           am.model_number, p.ps_number AS primary_part_ps,
           p.name AS primary_part_name, p.product_url AS primary_part_url,
           1-(rs.embedding <=> '{vs}') AS similarity
    FROM repair_story rs
    LEFT JOIN appliance_model am ON am.id=rs.model_id
    LEFT JOIN appliance_type at ON at.id=am.appliance_type_id
    LEFT JOIN repair_story_part rsp ON rsp.story_id=rs.id AND rsp.is_primary=true
    LEFT JOIN part p ON p.id=rsp.part_id
    WHERE rs.embedding IS NOT NULL {type_f} {model_f}
    ORDER BY rs.embedding <=> '{vs}' LIMIT {limit}"""
    rows = await execute_query(sql)
    for r in rows: r["_source"] = "repair_story"
    return rows


async def _run(query: str, appliance_type: Optional[str] = None, model_number: Optional[str] = None) -> str:
    settings = get_settings()
    limit = settings.semantic_search_limit
    try:
        vec = await _embed(query)
    except Exception as e:
        return f"EMBEDDING ERROR: {e}"
    try:
        parts, qas, stories = await asyncio.gather(
            _search_parts(vec, appliance_type, model_number, limit),
            _search_qas(vec, appliance_type, model_number, limit // 2),
            _search_stories(vec, appliance_type, model_number, limit // 2),
        )
    except Exception as e:
        return f"SEARCH ERROR: {e}"

    parts   = [r for r in parts   if float(r.get("similarity", 0)) > 0.3]
    qas     = [r for r in qas     if float(r.get("similarity", 0)) > 0.3]
    stories = [r for r in stories if float(r.get("similarity", 0)) > 0.3]

    if not parts and not qas and not stories:
        return "No similar results found. Try rephrasing or use execute_sql for a direct lookup."

    return json.dumps(
        {"query": query, "filters": {"appliance_type": appliance_type, "model_number": model_number},
         "parts": parts, "expert_qas": qas, "repair_stories": stories},
        indent=2, default=str,
    )


semantic_search = StructuredTool.from_function(
    coroutine=_run,
    name="semantic_search",
    description=(
        "Semantic similarity search across parts, expert Q&As, and repair stories. "
        "Use for ANY vague or symptom-based query: 'top rack keeps sagging', "
        "'fills but never sprays', 'loud grinding from freezer', "
        "'door drops open by itself', 'dishes come out dirty'. "
        "Pass appliance_type when known — significantly improves results. "
        "Pass model_number when confirmed — filters to compatible parts only. "
        "Returns ranked results from three sources in parallel: parts, Q&As, repair stories."
    ),
    args_schema=SemanticInput,
)
