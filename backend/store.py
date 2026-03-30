"""Redis-backed storage for pipeline run history."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis

log = logging.getLogger(__name__)

_RUNS_KEY = "pipeline_runs"
_RUN_PREFIX = "pipeline_run:"
_TTL_SECONDS = 14 * 24 * 3600  # 14 days


class RunStore:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        try:
            self.r = redis.from_url(redis_url, decode_responses=True)
            self.r.ping()
            self.connected = True
            log.info("Redis connected: %s", redis_url)
        except (redis.ConnectionError, redis.exceptions.ConnectionError):
            self.r = None
            self.connected = False
            log.warning("Redis not available — history will not be persisted")

    def save_run(self, query: str, stages: list[dict[str, Any]], decision: str | None = None) -> dict[str, Any]:
        run = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "stages": stages,
            "decision": decision,
            "total_duration_ms": sum(s.get("duration_ms", 0) for s in stages),
        }
        if self.r:
            key = f"{_RUN_PREFIX}{run['id']}"
            self.r.set(key, json.dumps(run, default=str), ex=_TTL_SECONDS)
            self.r.zadd(_RUNS_KEY, {run["id"]: datetime.now(timezone.utc).timestamp()})
        return run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        if not self.r:
            return None
        raw = self.r.get(f"{_RUN_PREFIX}{run_id}")
        return json.loads(raw) if raw else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.r:
            return []
        run_ids = self.r.zrevrange(_RUNS_KEY, 0, limit - 1)
        if not run_ids:
            return []
        pipe = self.r.pipeline()
        for rid in run_ids:
            pipe.get(f"{_RUN_PREFIX}{rid}")
        results = pipe.execute()
        return [json.loads(r) for r in results if r]

    def clear(self):
        if not self.r:
            return
        run_ids = self.r.zrange(_RUNS_KEY, 0, -1)
        if run_ids:
            self.r.delete(*[f"{_RUN_PREFIX}{rid}" for rid in run_ids])
        self.r.delete(_RUNS_KEY)
