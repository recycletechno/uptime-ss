import asyncio
import logging
from uptime_ss.sheets import SheetsClient

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_DELAYS = [5, 15, 45]


class Heartbeat:
    def __init__(self, bot_name: str, interval_minutes: int = 5):
        self.bot_name = bot_name
        self.interval_minutes = interval_minutes
        self._task = None
        self._client = None
        self._row = None

    async def start(self) -> None:
        """Start the heartbeat background task."""
        try:
            self._client = SheetsClient()
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
        log.info(
            f"Heartbeat [{self.bot_name}]: started, "
            f"row={self._row}, interval={self.interval_minutes}m"
        )

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log.info(f"Heartbeat [{self.bot_name}]: stopped")

    async def _loop(self) -> None:
        """Background loop: write timestamp, sleep, repeat."""
        interval_seconds = self.interval_minutes * 60
        while True:
            await self._tick()
            await asyncio.sleep(interval_seconds)

    async def _tick(self) -> None:
        """Single heartbeat tick with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                await self._client.write_timestamp(self._row)
                log.debug(f"Heartbeat [{self.bot_name}]: timestamp updated")
                return
            except Exception as e:
                delay = BACKOFF_DELAYS[attempt]
                log.warning(
                    f"Heartbeat [{self.bot_name}]: tick failed "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)

        log.error(
            f"Heartbeat [{self.bot_name}]: all {MAX_RETRIES} retries failed. "
            f"Will try again next interval."
        )
