"""Worker process entrypoints.

Run the production Celery worker:
    python -m app.workers.run celery

Run the local fallback worker (no Redis):
    python -m app.workers.run local
"""

from __future__ import annotations

import argparse
import logging
import sys

from ..config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="beatscout-worker")
    parser.add_argument("mode", nargs="?", default="auto",
                        choices=["auto", "celery", "local"])
    args = parser.parse_args()
    logging.basicConfig(level=get_settings().LOG_LEVEL,
                        format="[%(levelname)s] %(name)s: %(message)s")

    mode = args.mode
    if mode == "auto":
        mode = "celery" if get_settings().REDIS_URL else "local"

    if mode == "celery":
        from .tasks import celery_app
        if celery_app is None:
            sys.exit("REDIS_URL not configured — can't run celery. Use `local`.")
        logging.getLogger("beatscout").info("starting celery worker")
        celery_app.worker_main(argv=["worker", "--loglevel=INFO", "--concurrency=2"])
    else:
        from ..services.jobs import LocalWorker
        logging.getLogger("beatscout").info("starting local fallback worker")
        worker = LocalWorker(poll_seconds=get_settings().WORKER_POLL_SECONDS)
        try:
            worker.start()
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            worker.stop()


if __name__ == "__main__":
    main()