"""The named run statuses and the states that end a run."""

from enum import StrEnum


class RunStatus(StrEnum):
    """Every status an ingestion run can hold."""

    QUEUED = "queued"
    FETCHING = "fetching"
    PROCESSING = "processing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


TERMINAL_RUN_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.READY, RunStatus.FAILED})
