import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/traces", tags=["traces"])

TRACES_DIR = Path("traces")


@router.get(
    "/",
    summary="List retrieval traces",
    description="List available retrieval trace files.",
)
async def list_traces():
    if not TRACES_DIR.exists():
        return {"traces": [], "total": 0}
    trace_files = sorted(TRACES_DIR.glob("*.jsonl"), reverse=True)[:50]
    return {
        "traces": [f.stem for f in trace_files],
        "total": len(trace_files),
    }


@router.get(
    "/search/",
    summary="Search traces by query",
    description="Search traces that contain a specific query substring.",
)
async def search_traces(query: str, limit: int = 10):
    if not TRACES_DIR.exists():
        return {"results": [], "total": 0}
    results = []
    query_lower = query.lower()
    for trace_file in sorted(TRACES_DIR.glob("*.jsonl"), reverse=True):
        if len(results) >= limit:
            break
        with open(trace_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if query_lower in entry.get("query", "").lower():
                        results.append(entry)
                        break
                except json.JSONDecodeError:
                    continue
    return {"results": results, "total": len(results)}


@router.get(
    "/{trace_id}",
    summary="Get retrieval trace details",
    description="Get all trace entries for a specific trace ID.",
)
async def get_trace(trace_id: str):
    if ".." in trace_id or "/" in trace_id:
        raise HTTPException(status_code=400, detail="Invalid trace ID")
    trace_file = TRACES_DIR / f"{trace_id}.jsonl"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    entries = []
    with open(trace_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {"trace_id": trace_id, "entries": entries, "total": len(entries)}
