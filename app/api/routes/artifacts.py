from fastapi import APIRouter, HTTPException

from app.agents.artifacts import (
    list_playbooks,
    list_system_prompts,
    load_playbook,
    load_system_prompt,
    save_playbook,
    save_system_prompt,
)

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("/prompts")
async def list_prompts():
    return {"prompts": list_system_prompts()}


@router.get("/prompts/{name}")
async def get_prompt(name: str):
    result = load_system_prompt(name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Prompt {name} not found")
    return {"name": name, "content": result}


@router.post("/prompts/{name}")
async def create_prompt(name: str, content: str):
    key = save_system_prompt(name, content)
    return {"name": name, "artifact": key}


@router.get("/playbooks")
async def list_all_playbooks(user_id: str = "system"):
    return {"playbooks": list_playbooks(user_id)}


@router.get("/playbooks/{name}")
async def get_playbook(name: str, user_id: str = "system"):
    result = load_playbook(name, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Playbook {name} not found")
    return {"name": name, "content": result}


@router.post("/playbooks/{name}")
async def create_playbook(name: str, content: str, user_id: str = "system"):
    key = save_playbook(name, content, user_id)
    return {"name": name, "artifact": key, "user_id": user_id}
