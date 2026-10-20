"""Backend test suite."""

import os

# This package init runs before conftest imports anything from ``app``, and the
# suite must stay offline and deterministic whatever the developer's local
# backend/.env opts into. Real environment variables beat the .env file in
# pydantic precedence, and app.core.db constructs settings at import time, so
# the pin has to happen here, before the first app import.
os.environ["RAG_LLM_PROVIDER"] = "stub"
os.environ["RAG_ENVIRONMENT"] = "dev"
