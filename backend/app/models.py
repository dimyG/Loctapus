"""The model registry: one import that registers every ORM model before use.

Only entry points import this module - ``app.main``, ``app.workers.celery_app``,
``app.workers.dispatcher``, and ``alembic/env.py``. Feature modules import their own
models and must never import this one: mapper configuration is global, and only an
entry point needs the whole registry at once. Importing this module registers every
table on the shared ``Base.metadata`` and configures the mappers, so cross-module
foreign keys and relationship partners resolve no matter which module chain an entry
point pulled in first.
"""

from sqlalchemy.orm import configure_mappers

from app.conversations import models as conversations_models  # noqa: F401
from app.core import models as core_models  # noqa: F401
from app.identity import models as identity_models  # noqa: F401
from app.ingestion import models as ingestion_models  # noqa: F401
from app.outbox import models as outbox_models  # noqa: F401
from app.projects import models as projects_models  # noqa: F401
from app.retrieval import models as retrieval_models  # noqa: F401
from app.sources import models as sources_models  # noqa: F401

configure_mappers()
