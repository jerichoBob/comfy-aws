from fastapi import APIRouter, HTTPException

from app.services.workflow import list_workflows, load_template

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("")
async def get_workflows():
    return {"workflows": list_workflows()}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    try:
        _, schema = load_template(workflow_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return schema
