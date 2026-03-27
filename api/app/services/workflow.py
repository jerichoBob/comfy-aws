import copy
import json
import os
from pathlib import Path
from typing import Any

from app.models.workflow import WorkflowParam, WorkflowSchema

WORKFLOWS_DIR = Path(__file__).parent.parent.parent / "workflows"


def load_template(workflow_id: str) -> tuple[dict, WorkflowSchema]:
    """Load workflow.json and schema.json for a given workflow_id."""
    workflow_dir = WORKFLOWS_DIR / workflow_id
    if not workflow_dir.is_dir():
        raise FileNotFoundError(f"Workflow '{workflow_id}' not found")

    workflow_path = workflow_dir / "workflow.json"
    schema_path = workflow_dir / "schema.json"

    if not workflow_path.exists():
        raise FileNotFoundError(f"workflow.json not found for '{workflow_id}'")
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.json not found for '{workflow_id}'")

    with open(workflow_path) as f:
        graph = json.load(f)

    with open(schema_path) as f:
        raw_schema = json.load(f)

    params = {
        name: WorkflowParam(**param_def)
        for name, param_def in raw_schema.get("params", {}).items()
    }
    schema = WorkflowSchema(
        id=workflow_id,
        description=raw_schema.get("description", ""),
        params=params,
    )

    return graph, schema


def list_workflows() -> list[str]:
    """Return list of available workflow IDs."""
    if not WORKFLOWS_DIR.is_dir():
        return []
    return [
        d.name
        for d in sorted(WORKFLOWS_DIR.iterdir())
        if d.is_dir() and (d / "workflow.json").exists() and (d / "schema.json").exists()
    ]


def validate_params(schema: WorkflowSchema, user_params: dict[str, Any]) -> None:
    """Raise ValueError if required params are missing."""
    for name, param in schema.params.items():
        if param.required and name not in user_params:
            if param.default is None:
                raise ValueError(f"Missing required parameter: '{name}'")


def merge_params(
    graph: dict, schema: WorkflowSchema, user_params: dict[str, Any]
) -> dict:
    """Inject user params into a copy of the ComfyUI node graph."""
    merged = copy.deepcopy(graph)

    # Build effective params: defaults overridden by user values
    effective = {}
    for name, param in schema.params.items():
        if name in user_params:
            effective[name] = user_params[name]
        elif param.default is not None:
            effective[name] = param.default

    for name, value in effective.items():
        if name not in schema.params:
            continue
        param = schema.params[name]
        node_id = param.node_id
        input_key = param.input

        if node_id not in merged:
            raise ValueError(f"Node '{node_id}' not found in workflow graph")

        node = merged[node_id]
        if "inputs" not in node:
            node["inputs"] = {}
        node["inputs"][input_key] = value

    return merged
