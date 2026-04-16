"""Artifact service: store and retrieve prompts, playbooks, and other artifacts.

This module provides a simple interface to the ADK ArtifactService.
"""

from pathlib import Path

from google.adk.artifacts import InMemoryArtifactService

_artifact_service = InMemoryArtifactService()
_ARTIFACTS_DIR = Path("artifacts")
_ARTIFACTS_DIR.mkdir(exist_ok=True)


def init_artifact_service():
    """Initialize artifact service and load any saved artifacts."""
    try:
        for key in _artifact_service.list_artifact_keys(app_name="graphrag"):
            print(f"Loaded artifact: {key}")
    except Exception as e:
        print(f"Error loading artifacts: {e}")


def save_playbook(name: str, content: str, user_id: str = "system") -> str:
    """Save a playbook as an artifact."""
    key = f"playbooks/{user_id}/{name}"
    _artifact_service.save_artifact(
        app_name="graphrag",
        artifact_name=key,
        artifact_data=content,
    )
    return key


def load_playbook(name: str, user_id: str = "system") -> str | None:
    """Load a playbook artifact."""
    key = f"playbooks/{user_id}/{name}"
    try:
        return _artifact_service.load_artifact(
            app_name="graphrag",
            artifact_name=key,
        )
    except Exception:
        return None


def list_playbooks(user_id: str = "system") -> list[str]:
    """List available playbooks."""
    try:
        return _artifact_service.list_artifact_keys(
            app_name="graphrag",
            user_id=user_id,
        )
    except Exception:
        return []


def save_system_prompt(name: str, content: str) -> str:
    """Save a system prompt as an artifact."""
    key = f"prompts/{name}"
    _artifact_service.save_artifact(
        app_name="graphrag",
        artifact_name=key,
        artifact_data=content,
    )
    return key


def load_system_prompt(name: str) -> str | None:
    """Load a system prompt artifact."""
    key = f"prompts/{name}"
    try:
        return _artifact_service.load_artifact(
            app_name="graphrag",
            artifact_name=key,
        )
    except Exception:
        return None


def list_system_prompts() -> list[str]:
    """List available system prompts."""
    try:
        return _artifact_service.list_artifact_keys(
            app_name="graphrag",
        )
    except Exception:
        return []


def get_artifact_service() -> InMemoryArtifactService:
    """Get the artifact service instance."""
    return _artifact_service
