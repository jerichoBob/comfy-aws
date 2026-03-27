from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    comfyui_url: str = "http://localhost:8188"
    s3_bucket: str = ""
    dynamo_table: str = ""
    aws_default_region: str = "us-east-1"
    aws_endpoint_url: str = ""
    presigned_url_endpoint: str = ""  # Override endpoint in presigned URLs (local dev: http://localhost:4566)
    presigned_url_expiry_seconds: int = 3600
    job_ttl_days: int = 7
    job_timeout_seconds: int = 300

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
