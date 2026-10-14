"""Celery app construction.

``make_celery_app`` is the broker twin of ``make_engine``: every environment (dev,
pytest, e2e) builds its app from its own ``broker_url`` vhost, while the module-level
``celery_app`` points at the dev vhost exactly as ``SessionLocal`` points at the dev
database. The worker's startup and readiness handlers live in ``app.workers.signals``.
"""

from celery import Celery

import app.models  # noqa: F401
from app.core.config import get_settings


def make_celery_app(*, broker_url: str) -> Celery:
    """Return a Celery app bound to ``broker_url`` with late acks and publisher confirms.

    The app moves messages only - there is no result backend, because task outcomes
    live in Postgres on the ingestion runs.
    """

    app = Celery(broker=broker_url, include=["app.workers.tasks", "app.workers.signals"])
    # Late acks re-deliver a task whose worker died mid-run, and publisher confirms
    # make send_task a real wait for the broker's basic.ack.
    app.conf.task_acks_late = True
    app.conf.broker_transport_options = {"confirm_publish": True}
    return app


celery_app = make_celery_app(broker_url=get_settings().broker_url)
