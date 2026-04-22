import json
import logging
import uuid
from typing import AsyncIterator

import httpx
import websockets

from app.config import settings

logger = logging.getLogger(__name__)


class ComfyClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.comfyui_url).rstrip("/")
        self._ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")

    async def health_check(self) -> dict:
        """GET /system_stats — returns ComfyUI system info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/system_stats", timeout=10.0)
            response.raise_for_status()
            return response.json()

    async def submit_prompt(self, workflow_graph: dict) -> str:
        """POST /prompt — submit a workflow graph, returns prompt_id."""
        client_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow_graph, "client_id": client_id},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict | None:
        """GET /history/{prompt_id} — returns execution result dict if completed, else None."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return data.get(prompt_id)

    async def watch_execution(
        self, prompt_id: str
    ) -> AsyncIterator[dict]:
        """Open WebSocket /ws and yield execution events for the given prompt_id."""
        ws_url = f"{self._ws_url}/ws?clientId={prompt_id}"
        async with websockets.connect(ws_url) as ws:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                yield msg

                # Stop iterating once execution is done
                msg_type = msg.get("type")
                if msg_type == "executed" and msg.get("data", {}).get("prompt_id") == prompt_id:
                    break
                if msg_type == "execution_error" and msg.get("data", {}).get("prompt_id") == prompt_id:
                    break

    async def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """GET /view — download a generated image as bytes."""
        params = {"filename": filename, "type": image_type}
        if subfolder:
            params["subfolder"] = subfolder
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/view",
                params=params,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.content

    async def get_models(self) -> dict[str, list[str]]:
        """GET /object_info — extract model lists (checkpoints, loras, vae)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/object_info", timeout=30.0)
            response.raise_for_status()
            info = response.json()

        checkpoints = (
            info.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[], {}])[0]
        )
        loras = (
            info.get("LoraLoader", {})
            .get("input", {})
            .get("required", {})
            .get("lora_name", [[], {}])[0]
        )
        vaes = (
            info.get("VAELoader", {})
            .get("input", {})
            .get("required", {})
            .get("vae_name", [[], {}])[0]
        )

        return {
            "checkpoints": checkpoints if isinstance(checkpoints, list) else [],
            "loras": loras if isinstance(loras, list) else [],
            "vaes": vaes if isinstance(vaes, list) else [],
        }

    async def upload_image(self, filename: str, image_data: bytes) -> str:
        """POST /upload/image — upload image bytes, returns the filename ComfyUI stored it as."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/upload/image",
                files={"image": (filename, image_data, "image/png")},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()["name"]

    async def interrupt(self) -> None:
        """POST /interrupt — stop the currently executing generation."""
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/interrupt", timeout=10.0)
            response.raise_for_status()

    async def delete_from_queue(self, prompt_id: str) -> None:
        """POST /queue — delete a pending prompt from the queue."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/queue",
                json={"delete": [prompt_id]},
                timeout=10.0,
            )
            response.raise_for_status()
