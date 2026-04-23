# uptime-ss

Lightweight async Python heartbeat monitor via Google Sheets.

Your Python bots periodically update a timestamp in a shared Google Sheet. A Google Apps Script checks for stale timestamps and sends Telegram alerts when a bot stops responding.

## Installation

```bash
pip install git+https://github.com/recycletechno/uptime-ss.git
```

Or in `requirements.txt`:

```
uptime-ss @ git+https://github.com/recycletechno/uptime-ss.git
```

## Setup

### 1. Set environment variable

Point `UPTIME_SS_CREDS` to your Google Service Account credentials file:

```
UPTIME_SS_CREDS=C:\path\to\gs_cred.json
```

Add this to your project's `.env` file or set it as a system environment variable.

### 2. Add your bot to the Google Sheet

In the "Control" tab, add a row:

| A (bot name) | B (datetime) | C (active) | D (tg_sent) | E (chat_id) | F (notify) | G (mins_to_alert) |
|---|---|---|---|---|---|---|
| my_bot | *(leave empty)* | 1 | 0 | -335796822 | @username | 10 |

- **A**: bot name — must match the string you pass to `Heartbeat`
- **B**: leave empty, filled automatically
- **C**: `1` to monitor, `0` to ignore
- **D**: `0` (managed by Apps Script)
- **E**: Telegram chat ID for alerts
- **F**: Telegram usernames to mention in alerts
- **G**: minutes without update before alerting

### 3. Add to your bot code

```python
import asyncio
from uptime_ss import Heartbeat

async def main():
    hb = Heartbeat("my_bot", interval_minutes=5)
    await hb.start()

    try:
        await run_my_bot()
    finally:
        await hb.stop()

asyncio.run(main())
```

That's it. The bot updates its timestamp every N minutes. If it stops, you get a Telegram notification.

## API

### `Heartbeat(bot_name, interval_minutes=5, timeout=30.0)`

- `bot_name` (str): must match column A in the Google Sheet
- `interval_minutes` (int): how often to send heartbeat (default: 5)
- `timeout` (float): per-request hard timeout in seconds for each Google Sheets API call (default: 30). Prevents a stuck HTTP connection from silently freezing the heartbeat.

### `await hb.start()`

Loads credentials, finds the bot's row, starts background heartbeat task and an internal watchdog.
Does nothing (logs error) if credentials are missing or bot not found in sheet.

### `await hb.stop()`

Stops the background heartbeat task and the watchdog.

### `hb.last_success_at`

`datetime` (UTC) of the most recent successful tick, or `None` if none has happened yet. Useful for exposing health in your own `/health` endpoint.

### `hb.is_healthy`

`True` when the last successful tick was within `2 * interval_minutes`, `False` otherwise (including before the first tick).

## Error Handling

- Missing credentials or bot not in sheet: logs error, heartbeat doesn't start, bot continues running
- Network/API errors during a tick: retries up to 3 times with jittered backoff (~5s, ~15s between attempts), then waits for the next interval. The final attempt does not sleep after failing.
- Per-request timeout: each Sheets API call is wrapped in `asyncio.wait_for(..., timeout=...)`, so a hung connection raises `TimeoutError` and is retried like any other exception.
- Any unexpected exception inside the tick loop is caught and logged with a full traceback — the background task cannot die silently.
- Watchdog: if no tick has succeeded for `2 * interval_minutes`, a `WARNING` is logged each interval so a stuck heartbeat is visible in logs even without the external sheet monitor.
- Never crashes the host bot.

## Google Apps Script

Copy the contents of `appscript/check_bots.js` into your Google Sheet's Apps Script editor (Extensions > Apps Script). Replace `YOUR_TOKEN_HERE` with your Telegram bot token. Set up a time-driven trigger to run `checkBots` every 5 minutes.

Make sure the Google Sheet timezone is set to GMT (File > Settings > Time zone).
