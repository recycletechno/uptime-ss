# Adding uptime-ss to a Python project (Agent Guide)

## What this does

Adds heartbeat monitoring to an async Python bot. The bot periodically writes a timestamp to a Google Sheet. If it stops updating, the operator gets a Telegram alert.

## Agent steps

### 1. Install the package

```bash
pip install git+https://github.com/recycletechno/uptime-ss.git
```

Or add to `requirements.txt`:
```
uptime-ss @ git+https://github.com/recycletechno/uptime-ss.git
```

### 2. Add environment variable

Add to the project's `.env` file:
```
UPTIME_SS_CREDS=C:\Users\user\Files\CursorProjects\uptime-ss\credentials\gs_cred.json
```

### 3. Add to the bot's async entry point

```python
from uptime_ss import Heartbeat

# At the start of the main async function:
hb = Heartbeat("BOT_NAME", interval_minutes=5)
await hb.start()

# On shutdown:
await hb.stop()
```

Typical pattern:
```python
async def main():
    hb = Heartbeat("BOT_NAME", interval_minutes=5)
    await hb.start()
    try:
        await run_bot()
    finally:
        await hb.stop()
```

### 4. Ask the operator

Before completing, ask the operator to do the following manually:

> I've added uptime-ss heartbeat monitoring to the project.
> Please do the following in the Google Sheet (Control tab):
>
> 1. Add a new row with:
>    - **Column A (bot name):** `BOT_NAME` (must match exactly)
>    - **Column B:** leave empty
>    - **Column C (active):** `1`
>    - **Column D (tg_sent):** `0`
>    - **Column E (chat_id):** *(your Telegram chat ID for alerts)*
>    - **Column F (notify):** *(your Telegram @username)*
>    - **Column G (mins_to_alert):** `15` (or 2-3x the interval_minutes)
>
> What bot name and interval would you like to use?

## Notes

- `BOT_NAME` should be unique and descriptive (e.g., `funding_farm_bot`, `spread_finder`)
- `interval_minutes` default is 5 — use smaller for critical bots, larger for less important ones
- `mins_to_alert` should be at least 2x `interval_minutes` to avoid false alerts
- The heartbeat never crashes the host bot — if credentials are missing or the sheet is unreachable, it logs an error and continues silently
- Requires `UPTIME_SS_CREDS` env variable pointing to `gs_cred.json`
