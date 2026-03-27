from typing import Any

from pydantic import BaseModel


class WorkflowParam(BaseModel):
    node_id: str
    input: str
    type: str = "string"
    required: bool = True
    default: Any = None
    description: str = ""


class WorkflowSchema(BaseModel):
    id: str
    description: str = ""
    params: dict[str, WorkflowParam]
