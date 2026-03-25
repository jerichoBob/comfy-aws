# comfy-aws

Run ComfyUI on AWS behind a clean REST API. FastAPI sidecar wraps ComfyUI's native HTTP server, exposing typed endpoints for model listing, workflow selection, KSampler parameter control, and async job execution. Infrastructure is defined in CDK (TypeScript) and targets ECS on EC2 GPU instances.

## Architecture

```
Internet → ALB → FastAPI sidecar :8000
                     │  (localhost)
                 ComfyUI :8188  ←──── EBS /data/models
                                           ↑
                                    S3 sync on startup
```

- **Compute**: ECS on EC2 `g4dn.xlarge` Spot (T4 GPU, 16GB VRAM)
- **API**: FastAPI sidecar in same ECS task as ComfyUI
- **Storage**: S3 for models + generated outputs; DynamoDB for job state
- **Local dev**: `docker-compose` with ComfyUI (CPU mode) + LocalStack (S3/DynamoDB)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | ComfyUI reachability check |
| `GET` | `/models` | List checkpoints, LoRAs, VAEs |
| `GET` | `/workflows` | List available workflow templates |
| `GET` | `/workflows/{id}` | Workflow parameter schema |
| `POST` | `/jobs` | Submit a job `{workflow_id, params}` |
| `GET` | `/jobs/{id}` | Job status + presigned S3 image URLs |
| `DELETE` | `/jobs/{id}` | Cancel a queued job |

### Example

```bash
# List available models
curl http://localhost:8000/models

# Submit a txt2img job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "txt2img-sdxl",
    "params": {
      "positive_prompt": "a red cat on a rooftop at sunset",
      "steps": 25,
      "seed": -1
    }
  }'

# Poll for result
curl http://localhost:8000/jobs/{job_id}
```

## Workflow Template System

Each workflow is two files:

```
api/workflows/txt2img-sdxl/
├── workflow.json   # raw ComfyUI node graph
└── schema.json     # maps friendly param names → {node_id, input}
```

`schema.json` example:
```json
{
  "id": "txt2img-sdxl",
  "parameters": {
    "positive_prompt": {"node_id": "6", "input": "text", "type": "string", "required": true},
    "steps":           {"node_id": "3", "input": "steps", "type": "integer", "default": 20},
    "seed":            {"node_id": "3", "input": "seed",  "type": "integer", "default": -1}
  }
}
```

The API merges user params into the workflow graph before submitting to ComfyUI's `/prompt` endpoint.

## Local Development

```bash
# Start ComfyUI (CPU mode) + FastAPI + LocalStack
docker compose up

# Wait for ComfyUI to be ready (~60s on CPU)
curl http://localhost:8000/health

# Run unit tests (no external deps required)
cd api && pytest tests/test_workflow.py -v

# Run all integration tests (requires docker-compose running)
cd api && pytest tests/ -v
```

## Project Structure

```
comfy-aws/
├── api/                        # FastAPI sidecar (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── comfy_client.py     # HTTP + WebSocket bridge to ComfyUI
│   │   ├── routers/            # jobs, models, workflows
│   │   ├── services/           # job_service, dynamo, s3, workflow
│   │   └── models/             # pydantic models
│   ├── workflows/              # workflow templates (bundled in image)
│   │   └── txt2img-sdxl/
│   │       ├── workflow.json
│   │       └── schema.json
│   ├── tests/
│   └── Dockerfile
├── docker/
│   ├── comfyui/Dockerfile      # ComfyUI image (CPU + GPU modes)
│   └── model-sync/             # S3 → EBS sync init container
├── infra/                      # CDK TypeScript
│   └── lib/constructs/
│       ├── network.ts          # VPC, subnets, security groups
│       ├── storage.ts          # S3 bucket, DynamoDB table
│       ├── compute.ts          # ECS cluster, ASG g4dn.xlarge Spot
│       └── service.ts          # ECS task def, ALB, IAM roles
├── specs/                      # SDD specification documents
│   ├── README.md
│   └── spec-v1-comfy-aws.md
├── docker-compose.yml          # Local dev (CPU mode + LocalStack)
└── docker-compose.gpu.yml      # Local dev GPU override
```

## AWS Deployment

```bash
# Bootstrap CDK (one-time per account/region)
cd infra && cdk bootstrap

# Deploy all stacks
cdk deploy --all

# Upload models to S3
aws s3 sync ./models/ s3://{bucket}/models/

# Scale up ECS (ASG starts at 0)
aws autoscaling set-desired-capacity --auto-scaling-group-name comfy-asg --desired-capacity 1
```

## Specs

See [`specs/README.md`](specs/README.md) for the full implementation spec (v1, 25 tasks across 5 phases).

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, uvicorn, httpx, aioboto3 |
| Infra | AWS CDK v2 (TypeScript) |
| Compute | ECS on EC2 g4dn.xlarge Spot |
| Storage | S3, DynamoDB |
| Local dev | Docker Compose, LocalStack |
| Tests | pytest, pytest-asyncio (no mocks) |
