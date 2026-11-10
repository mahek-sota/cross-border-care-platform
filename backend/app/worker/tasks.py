"""Celery tasks.

Document extraction lands here once the document-pipeline spec is in; the module
exists now so the worker container has a valid ``include`` target.
"""

from __future__ import annotations

from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.ping")
def ping() -> str:
    return "pong"
