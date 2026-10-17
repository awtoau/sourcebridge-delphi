#!/usr/bin/env python3
"""Operationally monitor the local Ollama model process table in a terminal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import time
from urllib import request


def poll(endpoint: str, timeout: float = 10.0) -> list[dict[str, object]]:
    req = request.Request(endpoint.rstrip("/") + "/api/ps", method="GET")
    with request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise ValueError("Ollama /api/ps response has a non-array models field")
    return [
        {
            "name": model.get("name", model.get("model")),
            "digest": model.get("digest"),
            "size": model.get("size"),
            "expires_at": model.get("expires_at"),
        }
        for model in models
        if isinstance(model, dict)
    ]


def emit(endpoint: str, timeout: float) -> None:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        models = poll(endpoint, timeout)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"{checked_at} Ollama monitor error: {error}", flush=True)
        return
    print(
        json.dumps(
            {
                "checked_at": checked_at,
                "endpoint": endpoint,
                "models": models,
                "purpose": "operational-only; not evidence or validation",
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama base URL (default: OLLAMA_HOST or http://localhost:11434)",
    )
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    args = parser.parse_args(argv)
    if args.interval <= 0 or args.timeout <= 0:
        parser.error("--interval and --timeout must be positive")
    print(
        "Ollama monitor: operational only; not evidence or validation",
        flush=True,
    )
    while True:
        emit(args.endpoint, args.timeout)
        if args.once:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("Ollama monitor stopped.", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
