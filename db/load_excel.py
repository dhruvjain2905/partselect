"""
Loads partselect_real_data.xlsx into the Postgres database.
Run this AFTER docker-compose up (schema.sql auto-runs via docker entrypoint).
 
Usage:
    python db/load_excel.py partselect_real_data.xlsx
 
The script is idempotent — safe to re-run, uses ON CONFLICT DO NOTHING.
Insert order respects all FK constraints.
"""
 
import sys
import asyncio
import pandas as pd
import asyncpg
from datetime import date
from dotenv import load_dotenv
import os
 
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://partselect:partselect@localhost:5432/partselect")
 
 
def to_date(val):
    """Convert any pandas date representation to a real datetime.date object.
    asyncpg requires datetime.date — it refuses plain strings for DATE columns."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):        # pandas Timestamp
        return val.date()
    try:
        return pd.to_datetime(str(val)).date()
    except Exception:
        return None
 
 
def load_sheet(xl: dict, name: str) -> pd.DataFrame:
    """Load a sheet and strip the header comment row (row 0 has '--' markers)."""
    df = xl[name].copy()
    df = df[pd.to_numeric(df.iloc[:, 0], errors="coerce").notna()].reset_index(drop=True)
    df.iloc[:, 0] = df.iloc[:, 0].astype(int)
    return df
 
 
async def run(xlsx_path: str):
    xl = pd.read_excel(xlsx_path, sheet_name=None)
    conn = await asyncpg.connect(DATABASE_URL)
 
    print("Connected to database.")
 
    async def insert(table: str, rows: list[dict], conflict_cols: list[str]):
        if not rows:
            return
        cols = list(rows[0].keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        conflict = ", ".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO NOTHING"
        )
        data = [tuple(r[c] for c in cols) for r in rows]
        await conn.executemany(sql, data)
        print(f"  {table}: {len(data)} rows loaded")
 
    def rows(df: pd.DataFrame) -> list[dict]:
        return [
            {k: (None if pd.isna(v) else v) for k, v in row.items()}
            for _, row in df.iterrows()
        ]
 
    print("\nLoading taxonomy tables...")
    await insert("appliance_type", rows(load_sheet(xl, "appliance_type")), ["id"])
    await insert("brand", rows(load_sheet(xl, "brand")), ["id"])
    await insert("part_category", rows(load_sheet(xl, "part_category")), ["id"])
    await insert("symptom", rows(load_sheet(xl, "symptom")), ["id"])
 
    print("\nLoading entity tables...")
    await insert("appliance_model", rows(load_sheet(xl, "appliance_model")), ["id"])
 
    part_df = load_sheet(xl, "part")
    part_rows = []
    for _, r in part_df.iterrows():
        part_rows.append({
            "id":              int(r["id"]),
            "ps_number":       str(r["ps_number"]),
            "mfr_part_number": str(r["mfr_part_number"]),
            "name":            str(r["name"]),
            "description":     str(r["description"]),
            "price":           float(r["price"]) if pd.notna(r["price"]) else None,
            "in_stock":        bool(r["in_stock"]) if pd.notna(r["in_stock"]) else True,
            "category_id":     int(r["category_id"]),
            "product_url":     str(r["product_url"]) if "product_url" in r.index and pd.notna(r.get("product_url")) else None,
        })
    await insert("part", part_rows, ["id"])
 
    print("\nLoading junction tables...")
    ps_df = load_sheet(xl, "part_supersedes")
    await insert("part_supersedes",
                 [{"part_id": int(r["part_id"]), "old_part_number": str(r["old_part_number"])}
                  for _, r in ps_df.iterrows()],
                 ["part_id", "old_part_number"])
 
    mc_df = load_sheet(xl, "model_part_compat")
    await insert("model_part_compat",
                 [{"model_id": int(r["model_id"]), "part_id": int(r["part_id"])}
                  for _, r in mc_df.iterrows()],
                 ["model_id", "part_id"])
 
    psf_df = load_sheet(xl, "part_symptom_fix")
    await insert("part_symptom_fix",
                 [{"part_id": int(r["part_id"]), "symptom_id": int(r["symptom_id"]),
                   "fix_rate_pct": int(r["fix_rate_pct"])}
                  for _, r in psf_df.iterrows()],
                 ["part_id", "symptom_id"])
 
    print("\nLoading knowledge tables...")
 
    # expert_qa — asked_at is a DATE column, must be datetime.date not str
    qa_df = load_sheet(xl, "expert_qa")
    qa_rows = []
    for _, r in qa_df.iterrows():
        qa_rows.append({
            "id":            int(r["id"]),
            "model_id":      int(r["model_id"]) if pd.notna(r["model_id"]) else None,
            "question":      str(r["question"]),
            "answer":        str(r["answer"]),
            "asker_name":    str(r["asker_name"]) if pd.notna(r.get("asker_name")) else None,
            "asked_at":      to_date(r.get("asked_at")),
            "helpful_count": int(r["helpful_count"]) if pd.notna(r.get("helpful_count")) else 0,
        })
    await insert("expert_qa", qa_rows, ["id"])
 
    # repair_story — no date column but keeping consistent
    rs_df = load_sheet(xl, "repair_story")
    rs_rows = []
    for _, r in rs_df.iterrows():
        rs_rows.append({
            "id":          int(r["id"]),
            "model_id":    int(r["model_id"]) if pd.notna(r["model_id"]) else None,
            "story":       str(r["story"]),
            "author":      str(r["author"]) if pd.notna(r.get("author")) else None,
            "difficulty":  str(r["difficulty"]) if pd.notna(r.get("difficulty")) else None,
            "repair_time": str(r["repair_time"]) if pd.notna(r.get("repair_time")) else None,
            "tools":       str(r["tools"]) if pd.notna(r.get("tools")) else None,
        })
    await insert("repair_story", rs_rows, ["id"])
 
    qpr_df = load_sheet(xl, "qa_part_ref")
    await insert("qa_part_ref",
                 [{"qa_id": int(r["qa_id"]), "part_id": int(r["part_id"])}
                  for _, r in qpr_df.iterrows()],
                 ["qa_id", "part_id"])
 
    rsp_df = load_sheet(xl, "repair_story_part")
    await insert("repair_story_part",
                 [{"story_id": int(r["story_id"]), "part_id": int(r["part_id"]),
                   "is_primary": bool(r["is_primary"])}
                  for _, r in rsp_df.iterrows()],
                 ["story_id", "part_id"])
 
    # part_review — created_at is a DATE column
    pr_df = load_sheet(xl, "part_review")
    pr_rows = []
    for _, r in pr_df.iterrows():
        pr_rows.append({
            "id":                int(r["id"]),
            "part_id":           int(r["part_id"]),
            "rating":            int(r["rating"]),
            "body":              str(r["body"]) if pd.notna(r.get("body")) else None,
            "author":            str(r["author"]) if pd.notna(r.get("author")) else None,
            "created_at":        to_date(r.get("created_at")),
            "verified_purchase": bool(r["verified_purchase"]) if pd.notna(r.get("verified_purchase")) else False,
        })
    await insert("part_review", pr_rows, ["id"])
 
    v_df = load_sheet(xl, "video")
    v_rows = []
    for _, r in v_df.iterrows():
        v_rows.append({
            "id":            int(r["id"]),
            "part_id":       int(r["part_id"]),
            "title":         str(r["title"]),
            "url":           str(r["url"]),
            "thumbnail_url": None,
        })
    await insert("video", v_rows, ["id"])
 
    await conn.close()
    print("\n✓ All data loaded successfully.")
    print("Next step: run `python db/generate_embeddings.py` to populate vector columns.")
 
 
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "partselect_real_data.xlsx"
    asyncio.run(run(path))