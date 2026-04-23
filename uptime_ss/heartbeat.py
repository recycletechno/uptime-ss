import asyncio
import datetime
import logging
import random
from typing import Optional

from uptime_ss.sheets import SheetsClient, DEFAULT_TIMEOUT

log = logging.getLogger(__name__)

MAX_RETRIES = 3
# Base delays for the gaps between attempts. Only the first MAX_RETRIES - 1 are used,
# because there is no point sleeping after the final failed attempt.
BACKOFF_DELAYS = [5, 15, 45]
BACKOFF_JITTER = 0.25  # up to +25% random jitter on each backoff sleep


class Heartbeat:
    def __init__(
        self,
        bot_name: str,
        interval_minutes: int = 5,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.bot_name = bot_name
        self.interval_minutes = interval_minutes
        self.timeout = timeout
        self.last_success_at: Optional[datetime.datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._client: Optional[SheetsClient] = None
        self._row: Optional[int] = None

    @property
    def is_healthy(self) -> bool:
        """True if a tick has succeeded within the last 2 * interval."""
        if self.last_success_at is None:
            return False
        elapsed = (
            datetime.datetime.now(datetime.timezone.utc) - self.last_success_at
        ).total_seconds()
        return elapsed <= 2 * self.interval_minutes * 60

    async def start(self) -> None:
        """Start the heartbeat background task."""
        try:
            self._client = SheetsClient(timeout=self.timeout)
        except (ValueError, FileNotFoundError) as e:
            log.error(f"Heartbeat [{self.bot_name}]: {e}")
            return

        self._row = await self._client.find_bot_row(self.bot_name)
        if self._row is None:
            log.error(
                f"Heartbeat [{self.bot_name}]: bot not found in sheet. "
                f"Add a row with '{self.bot_name}' in column A."
            )
            return

        self._task = asyncio.create_task(self._loop())
        self._watchdog_task = asyncio.create_task(self._watchdog())
        log.info(
            f"Heartbeat [{self.bot_name}]: started, "
            f"row={self._row}, interval={self.interval_minutes}m, "
            f"timeout={self.timeout}s"
        )

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        for attr in ("_task", "_watchdog_task"):
            task = getattr(self, attr)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, attr, None)
        log.info(f"Heartbeat [{self.bot_name}]: stopped")

    async def _loop(self) -> None:
        """Background loop: write timestamp, sleep, repeat.

        Any exception escaping _tick is logged with full traceback so the
        background task cannot die silently. CancelledError still propagates
        so stop() works.
        """
        interval_seconds = self.interval_minutes * 60
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception(
                    f"Heartbeat [{self.bot_name}]: unexpected error in tick loop"
                )
            await asyncio.sleep(interval_seconds)

    async def _watchdog(self) -> None:
        """Warn when no successful tick has been observed for 2 * interval."""
        interval_seconds = self.interval_minutes * 60
        threshold = 2 * interval_seconds
        started_at = datetime.datetime.now(datetime.timezone.utc)
        while True:
            await asyncio.sleep(interval_seconds)
            reference = self.last_success_at or started_at
            elapsed = (
                datetime.datetime.now(datetime.timezone.utc) - reference
            ).total_seconds()
            if elapsed > threshold:
                log.warning(
                    f"Heartbeat [{self.bot_name}]: no successful tick in "
                    f"{elapsed:.0f}s (threshold {threshold:.0f}s) — may be stuck"
                )

    async def _tick(self) -> None:
        """Single heartbeat tick with retry logic."""
        last_exc: Optional[BaseException] = None
        for attempt in range(MAX_RETRIES):
            try:
                await self._client.write_timestamp(self._row)
                self.last_success_at = datetime.datetime.now(datetime.timezone.utc)
                log.debug(f"Heartbeat [{self.bot_name}]: timestamp updated")
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1:
                    base = BACKOFF_DELAYS[attempt]
                    delay = base + random.uniform(0, base * BACKOFF_JITTER)
                    log.warning(
                        f"Heartbeat [{self.bot_name}]: tick failed "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

        log.error(
            f"Heartbeat [{self.bot_name}]: all {MAX_RETRIES} retries failed "
            f"(last error: {last_exc}). Will try again next interval."
        )
