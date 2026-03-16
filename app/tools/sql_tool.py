"""
Text-to-SQL tool.

The LLM receives the full schema as context inside the tool description,
writes a SELECT statement, and we validate + execute it safely.
We never interpolate user input into SQL — only the LLM-generated query runs,
and it is validated to be a read-only SELECT before execution.
"""

import re
import json
import sqlparse
import asyncpg
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from app.database import execute_query
from app.config import get_settings

# ---------------------------------------------------------------------------
# Full schema context — injected into tool description so the LLM knows
# every table and column when writing queries.
# ---------------------------------------------------------------------------
SCHEMA_CONTEXT = """
DATABASE SCHEMA (PostgreSQL + pgvector)
========================================
appliance_type(id, name, slug)  — id=1 Dishwasher, id=2 Refrigerator
brand(id, name, slug)  — 1=Whirlpool,2=KitchenAid,3=Kenmore,4=Maytag,5=Bosch,6=GE,7=Frigidaire,8=LG,9=Samsung
part_category(id, name, appliance_type_id, slug)  — dishwasher ids 1-11, refrigerator ids 12-21
symptom(id, name, appliance_type_id)  — dishwasher 1-9, fridge 10-15
appliance_model(id, model_number, brand_id, appliance_type_id, description)
part(id, ps_number, mfr_part_number, name, description, price, in_stock, category_id, product_url)
  — NOTE: do NOT select the embedding column
  — ps_number examples: PS11750093 PS10065979 PS972325 PS11731570 PS11756967 PS11738151
  — PS12348515 PS11759673 PS11752389 PS11701542 PS11749668 PS11757023
model_part_compat(model_id, part_id)  — compatibility junction
part_supersedes(part_id, old_part_number)  — legacy number resolution
part_symptom_fix(part_id, symptom_id, fix_rate_pct)  — fix_rate_pct 1-100
expert_qa(id, model_id, question, answer, asker_name, asked_at, helpful_count)
repair_story(id, model_id, story, author, difficulty, repair_time, tools)
repair_story_part(story_id, part_id, is_primary)
part_review(id, part_id, rating, body, author, created_at, verified_purchase)
video(id, part_id, title, url)
qa_part_ref(qa_id, part_id)
========================================
RULES: SELECT only. LIMIT 20 max. Never select embedding. Use ILIKE for text.
EXAMPLE — compatibility:
  SELECT EXISTS(SELECT 1 FROM model_part_compat mc
    JOIN appliance_model m ON m.id=mc.model_id JOIN part p ON p.id=mc.part_id
    WHERE UPPER(m.model_number)=UPPER('WDT750SAHZ0') AND UPPER(p.ps_number)=UPPER('PS11750093')) AS is_compatible
EXAMPLE — ranked symptom fix:
  SELECT p.ps_number,p.name,p.price,p.product_url,psf.fix_rate_pct
    FROM part p JOIN part_symptom_fix psf ON psf.part_id=p.id
    JOIN symptom s ON s.id=psf.symptom_id
    JOIN model_part_compat mc ON mc.part_id=p.id
    JOIN appliance_model m ON m.id=mc.model_id
    WHERE UPPER(m.model_number)=UPPER('WDT750SAHZ0') AND s.name ILIKE '%drain%'
    ORDER BY psf.fix_rate_pct DESC LIMIT 10
EXAMPLE — legacy part:
  SELECT p.ps_number,p.name,p.price,p.product_url FROM part p
    JOIN part_supersedes s ON s.part_id=p.id WHERE s.old_part_number='W10195840'
"""


class SQLInput(BaseModel):
    query: str = Field(description="A valid SQL SELECT statement to run against the PartSelect database.")


def _validate_sql(sql: str) -> tuple[bool, str]:
    cleaned = sql.strip().rstrip(";").strip()
    first_word = cleaned.split()[0].upper() if cleaned.split() else ""
    if first_word not in ("SELECT", "WITH"):
        return False, f"Only SELECT statements allowed. Got: {first_word}"
    dangerous = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|TRUNCATE|ALTER|GRANT|REVOKE|EXECUTE|EXEC|COPY)\b",
        re.IGNORECASE,
    )
    if dangerous.search(cleaned):
        return False, f"Disallowed keyword: {dangerous.search(cleaned).group()}"
    if re.search(r"\bembedding\b", cleaned, re.IGNORECASE):
        return False, "Do not select the embedding column."
    try:
        stmts = sqlparse.parse(cleaned)
        if len(stmts) != 1:
            return False, "Only one statement per call."
    except Exception as e:
        return False, f"Parse error: {e}"
    return True, ""


def _ensure_limit(sql: str, max_rows: int) -> str:
    upper = sql.upper()
    if "LIMIT" in upper or "COUNT(" in upper or "EXISTS(" in upper:
        return sql
    return sql.rstrip().rstrip(";") + f"\nLIMIT {max_rows}"


async def _run(query: str) -> str:
    settings = get_settings()
    is_valid, error = _validate_sql(query)
    if not is_valid:
        return f"INVALID QUERY: {error}"
    sql = _ensure_limit(query, settings.sql_result_limit)
    try:
        rows = await execute_query(sql, timeout=settings.sql_timeout_seconds)
    except asyncpg.PostgresError as e:
        return f"DATABASE ERROR: {e}"
    except Exception as e:
        return f"EXECUTION ERROR: {e}"
    if not rows:
        return "No results found."
    return json.dumps(rows, indent=2, default=str)


execute_sql = StructuredTool.from_function(
    coroutine=_run,
    name="execute_sql",
    description=(
        "Execute a SQL SELECT query against the PartSelect database. "
        "Use for structured lookups: compatibility checks, part number lookups, "
        "legacy part number resolution, symptom-ranked part lists, reviews, "
        "videos, repair stories, model overviews. "
        "The query must be a SELECT. Never include the embedding column. "
        "SCHEMA AND EXAMPLES:\n" + SCHEMA_CONTEXT
    ),
    args_schema=SQLInput,
)