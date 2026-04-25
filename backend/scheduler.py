from __future__ import annotations

import logging
import threading

from .service import DealsService


class SyncScheduler:
    def __init__(
        self,
        service: DealsService,
        interval_hours: int,
        pages: int,
        include_rent: bool | None = None,
        locality_region_id: int | None = None,
        flat_only: bool | None = None,
    ) -> None:
        self.service = service
        self.interval_seconds = max(interval_hours, 1) * 3600
        self.pages = pages
        self.include_rent = include_rent
        self.locality_region_id = locality_region_id
        self.flat_only = flat_only
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sync-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.service.run_sync(
                    max_pages=self.pages,
                    include_rent=self.include_rent,
                    locality_region_id=self.locality_region_id,
                    flat_only=self.flat_only,
                )
            except Exception:
                logging.exception("Scheduled sync failed")
