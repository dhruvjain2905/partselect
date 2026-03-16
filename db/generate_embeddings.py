"""
Generates and stores embeddings for the three tables that use pgvector:
  - part           (name + description)
  - expert_qa      (question + answer)
  - repair_story   (story text)

Run once after load_excel.py. Safe to re-run — only processes NULL rows.

Usage:
    python db/generate_embeddings.py

Cost estimate: ~$0.002 for the full dataset (25 + 10 + 8 rows).
"""

import asyncio
import asyncpg
import openai
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://partselect:partselect@localhost:5432/partselect")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
BATCH_SIZE = 50  # rows per API call


async def embed_batch(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def process_table(
    conn: asyncpg.Connection,
    client: openai.AsyncOpenAI,
    table: str,
    id_col: str,
    text_cols: list[str],
) -> int:
    """Embed all rows in `table` where embedding IS NULL. Returns count updated."""
    rows = await conn.fetch(
        f"SELECT {id_col}, {', '.join(text_cols)} FROM {table} WHERE embedding IS NULL"
    )
    if not rows:
        print(f"  {table}: all embeddings already populated, skipping.")
        return 0

    print(f"  {table}: embedding {len(rows)} rows...")
    updated = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [" ".join(str(r[col]) for col in text_cols if r[col]) for r in batch]
        embeddings = await embed_batch(client, texts)

        for row, emb in zip(batch, embeddings):
            # Store as pgvector literal string
            vec_str = "[" + ",".join(str(x) for x in emb) + "]"
            await conn.execute(
                f"UPDATE {table} SET embedding = $1::vector WHERE {id_col} = $2",
                vec_str,
                row[id_col],
            )
            updated += 1

        print(f"    batch {i // BATCH_SIZE + 1}: {len(batch)} rows done")

    return updated


async def build_ivfflat_indexes(conn: asyncpg.Connection):
    """
    Build IVFFlat approximate nearest-neighbour indexes.
    Must run AFTER embeddings are populated (IVFFlat requires data at index build time).
    """
    print("\nBuilding pgvector IVFFlat indexes...")
    index_cmds = [
        ("idx_part_embedding",
         "CREATE INDEX IF NOT EXISTS idx_part_embedding ON part "
         "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"),
        ("idx_qa_embedding",
         "CREATE INDEX IF NOT EXISTS idx_qa_embedding ON expert_qa "
         "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20)"),
        ("idx_story_embedding",
         "CREATE INDEX IF NOT EXISTS idx_story_embedding ON repair_story "
         "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20)"),
    ]
    for name, sql in index_cmds:
        print(f"  Building {name}...")
        await conn.execute(sql)
    print("  Indexes built.")


async def run():
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set in .env")

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    conn = await asyncpg.connect(DATABASE_URL)

    # Ensure pgvector extension
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    print("Generating embeddings...\n")

    total = 0
    total += await process_table(conn, client, "part", "id", ["name", "description"])
    total += await process_table(conn, client, "expert_qa", "id", ["question", "answer"])
    total += await process_table(conn, client, "repair_story", "id", ["story"])

    if total > 0:
        await build_ivfflat_indexes(conn)

    await conn.close()
    print(f"\n✓ Done. {total} embeddings generated.")
    print("The chatbot's semantic search is now fully operational.")


if __name__ == "__main__":
    asyncio.run(run())
