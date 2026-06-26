from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Operating mode
    mode: Literal["byok", "saas"] = "byok"

    # Neo4j
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    neo4j_database: str = ""
    aura_instanceid: str = ""
    aura_instancename: str = ""

    # BYOK (OpenRouter — single key, access to all providers)
    openrouter_api_key: str = ""

    # Search API keys (BYOK or server-side)
    exa_api_key: str = ""
    firecrawl_api_key: str = ""

    # Graphiti
    graphiti_namespace: str = "default"
    graphiti_model: str = "openai/gpt-4o-mini"

    # SaaS-only — Clerk auth
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""

    # SaaS-only — AWS resources
    sqs_queue_url: str = ""
    dynamodb_jobs_table: str = "whitespace-jobs"
    dynamodb_usage_table: str = "whitespace-usage"
    aws_region: str = "us-east-1"

    # Observability
    langsmith_api_key: str = ""
    langsmith_project: str = ""
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_consent_tier: Literal["full", "anonymised", "metadata_only"] = "full"

    @model_validator(mode="after")
    def _derive_aura_uri(self) -> "Config":
        if self.neo4j_uri == "" and self.aura_instanceid != "" and self.aura_instancename != "":
            self.neo4j_uri = f"neo4j+s://{self.aura_instanceid}.databases.neo4j.io"
        return self
