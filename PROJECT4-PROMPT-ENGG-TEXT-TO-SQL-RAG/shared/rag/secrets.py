import json
import os
from functools import lru_cache
from typing import Any

import boto3


@lru_cache(maxsize=16)
def load_secret(secret_name: str | None = None, region_name: str | None = None) -> dict[str, Any]:
    """Load a JSON secret from AWS Secrets Manager and cache it per container."""
    name = secret_name or os.environ.get("SECRET_NAME") or os.environ.get("RAG_SECRET_NAME")
    if not name:
        return {}

    region = region_name or os.environ.get("AWS_REGION_NAME") or os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=name)
    if "SecretString" not in response:
        raise ValueError(f"Secret {name} must be a JSON SecretString")
    return json.loads(response["SecretString"])


def get_config_value(key: str, default: Any = None, secret_name: str | None = None) -> Any:
    """Prefer environment variables, then Secrets Manager, then default."""
    if key in os.environ:
        return os.environ[key]
    secret = load_secret(secret_name)
    return secret.get(key, default)

