"""
Usage:
  python scripts/bulk_ingest.py \
    --project-id <uuid> \
    --folder ./my_legal_pdfs \
    --token <your_jwt> \
    --api http://localhost:8000

Walks folder recursively, uploads every supported file.
"""

import argparse
import asyncio
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm

SUPPORTED = {".pdf", ".docx", ".txt", ".doc", ".md", ".xlsx", ".pptx", ".html", ".epub"}


async def ingest_all(project_id, folder, token, api):
    files = [f for f in Path(folder).rglob("*") if f.suffix.lower() in SUPPORTED]
    print(f"Found {len(files)} files")
    headers = {"Authorization": f"Bearer {token}"}
    success, failed = 0, []

    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        for fp in tqdm(files, desc="Uploading"):
            try:
                with open(fp, "rb") as f:
                    r = await client.post(
                        f"{api}/projects/{project_id}/documents",
                        files={"files": (fp.name, f)},
                    )
                r.raise_for_status()
                success += 1
            except Exception as e:
                failed.append((fp.name, str(e)))

    print(f"\nDone: {success} uploaded, {len(failed)} failed")
    for name, err in failed:
        print(f"  FAILED: {name} — {err}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--project-id", required=True)
    p.add_argument("--folder", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--api", default="http://localhost:8000")
    args = p.parse_args()
    asyncio.run(ingest_all(args.project_id, args.folder, args.token, args.api))
