"""Tests that the outbox routing map and the Celery task signatures agree."""

import inspect

from app.outbox.events import EVENT_ROUTES
from app.workers.celery_app import celery_app


def test_task_signatures_match_event_payloads() -> None:
    """Check that every routed task exists and takes exactly its payload keys as kwargs."""

    # The include list registers its tasks only when the loader imports it, exactly as
    # a worker boot does; a fresh process starts with an empty registry.
    celery_app.loader.import_default_modules()
    for event_type, route in EVENT_ROUTES.items():
        task = celery_app.tasks[route.task_name]
        parameters = inspect.signature(task.run).parameters
        keyword_only = {
            name for name, parameter in parameters.items() if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        }
        assert keyword_only == route.payload_keys, f"{event_type} task signature disagrees with its payload"
