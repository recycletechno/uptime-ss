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

### `Heartbeat(bot_name, interval_minutes=5)`

- `bot_name` (str): must match column A in the Google Sheet
- `interval_minutes` (int): how often to send heartbeat (default: 5)

### `await hb.start()`

Loads credentials, finds the bot's row, starts background heartbeat task.
Does nothing (logs error) if credentials are missing or bot not found in sheet.

### `await hb.stop()`

Stops the background heartbeat task.

## Error Handling

- Missing credentials or bot not in sheet: logs error, heartbeat doesn't start, bot continues running
- Network/API errors during heartbeat: retries 3 times with backoff (5s, 15s, 45s), then waits for next interval
- Never crashes the host bot

## Google Apps Script

Copy the contents of `appscript/check_bots.js` into your Google Sheet's Apps Script editor (Extensions > Apps Script). Replace `YOUR_TOKEN_HERE` with your Telegram bot token. Set up a time-driven trigger to run `checkBots` every 5 minutes.

Make sure the Google Sheet timezone is set to GMT (File > Settings > Time zone).
