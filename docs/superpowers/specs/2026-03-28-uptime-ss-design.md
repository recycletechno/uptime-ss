# uptime-ss Design Spec

## Overview

A lightweight Python package that lets any async Python bot report its uptime to a shared Google Sheet. A Google Apps Script monitors the sheet and sends Telegram alerts when a bot stops updating.

## Goals

- One `pip install` + three lines of code to add uptime monitoring to any bot
- No external scheduler dependencies — pure asyncio
- Shared Google Sheet as a dashboard for all bots
- Telegram alerts when a bot goes down or recovers

## Non-Goals

- Auto-registration of new bots in the sheet (manual row setup)
- Sync Python support (async-only)
- Web UI or dashboard beyond the Google Sheet

---

## Architecture

```
Python Bot                    Google Sheet ("Control")         Google Apps Script
    |                               |                               |
    |-- writes UTC timestamp ------>|  (column B, every N min)      |
    |                               |                               |
    |                               |<-- checks timestamps ---------|  (every 5 min trigger)
    |                               |                               |
    |                               |   if stale → Telegram alert --|-->  Telegram Bot API
    |                               |   if recovered → notify ------|-->  Telegram Bot API
```

---

## Python Package: `uptime_ss`

### Package Structure

```
uptime-ss/
├── uptime_ss/
│   ├── __init__.py          # exports Heartbeat
│   ├── heartbeat.py         # Heartbeat class (background task, retry logic)
│   └── sheets.py            # Google Sheets API logic (find row, write timestamp)
├── credentials/
│   └── .gitkeep             # gs_cred.json goes here (gitignored)
├── .gitignore
├── pyproject.toml           # package metadata, dependencies
└── README.md
```

### Dependencies

- `aiogoogle` — async Google Sheets API client (pulls in `aiohttp`)

No other dependencies. No APScheduler, no external scheduler.

### Credentials

- Google Service Account JSON file (`gs_cred.json`)
- Stored locally on the machine (NOT in git)
- Path provided via environment variable: `UPTIME_SS_CREDS`
- Each project that uses uptime-ss must have this env variable set (e.g., in `.env` file)

### Heartbeat Class

```python
from uptime_ss import Heartbeat

hb = Heartbeat("my_bot", interval_minutes=5)
await hb.start()

# ... bot runs ...

await hb.stop()  # on shutdown
```

#### Constructor: `Heartbeat(bot_name: str, interval_minutes: int = 5)`

- `bot_name` — must match column A in the Google Sheet
- `interval_minutes` — how often to update the timestamp (default: 5)

#### `start()` behavior

1. Reads `UPTIME_SS_CREDS` env variable → loads service account credentials (once)
2. Finds the bot's row in the sheet by searching column A (once, cached)
3. If bot not found → logs error, does NOT start the background task
4. Starts an `asyncio.Task` that loops: write UTC timestamp to column B → sleep interval → repeat

#### Heartbeat tick

Each tick does one thing: writes the current UTC timestamp (`dd-MM-YYYY HH:mm:ss`) to column B of the bot's row. One API call.

#### Retry on failure

If a tick fails (network error, API quota, etc.):
- Retry up to 3 times with exponential backoff: 5s → 15s → 45s
- If all 3 retries fail → log error, wait for next regular interval
- Never crashes or raises exceptions to the host bot

#### `stop()` behavior

Cancels the background asyncio task cleanly.

### Sheets Module

Handles all Google Sheets API interaction.

#### `find_bot_row(bot_name: str) -> int | None`

- Reads column A of the "Control" sheet
- Returns the row number (1-indexed) where `bot_name` is found
- Returns `None` if not found

#### `write_timestamp(row: int) -> None`

- Writes current UTC timestamp to column B of the given row
- Format: `dd-MM-YYYY HH:mm:ss`
- Uses `valueInputOption="USER_ENTERED"` so Google Sheets parses it as a date

#### Configuration (hardcoded)

- Spreadsheet ID: `1f0dQSyH5dtcFVadvj4XNB2fVrGcV6MMp99GkK7ygUgM`
- Sheet name: `Control`
- Scopes: `https://www.googleapis.com/auth/spreadsheets`

---

## Google Sheet Structure

Sheet tab: `Control`

| Column | Name | Description | Managed by |
|--------|------|-------------|------------|
| A | (bot name) | Unique bot identifier | Manual |
| B | datetime | Last heartbeat UTC timestamp | Python module |
| C | active | 1 = monitored, 0 = ignored | Manual |
| D | tg_sent | 1 = alert sent, 0 = not sent | Apps Script |
| E | chat_id | Telegram chat ID for alerts | Manual |
| F | notify | Telegram usernames to mention | Manual |
| G | mins_to_alert | Minutes without update before alerting | Manual |

Row 1 is headers. Bot data starts at row 2.

---

## Google Apps Script

Runs on a time-driven trigger (every 5 minutes). Checks each bot row in the "Control" sheet.

### Logic

For each row where `active == 1`:
1. Read `datetime` (column B) and `mins_to_alert` (column G)
2. Calculate how many minutes since the last update (using UTC)
3. If `minutes_since_update > mins_to_alert`:
   - If `tg_sent == 0` → send Telegram alert, set `tg_sent = 1`
4. If `minutes_since_update <= mins_to_alert`:
   - If `tg_sent == 1` → send recovery message, set `tg_sent = 0`

### Telegram messages

- **Alert:** `"Bot [bot_name] stopped updating since dd-MM-YYYY HH:mm:ss @user1 @user2"`
- **Recovery:** `"Bot [bot_name] resumed at dd-MM-YYYY HH:mm:ss @user1 @user2"`

### Timezone handling

- Python writes UTC timestamps
- Apps Script compares using UTC (`Session.getScriptTimeZone()` set to GMT, or explicit UTC conversion)
- No manual timezone offset hacks

### Telegram bot token

Hardcoded in the Apps Script (not in this spec for security). Same bot as currently used.

---

## Integration Guide

### How to add uptime-ss to any Python project

#### Prerequisites

- Python 3.10+
- An async Python bot (uses `asyncio`)
- Environment variable `UPTIME_SS_CREDS` set to the path of `gs_cred.json`
- A row for your bot in the Google Sheet (column A = bot name, C = 1, E = chat_id, F = notify users, G = mins_to_alert)

#### Step 1: Install

```bash
pip install git+https://github.com/YOUR_USER/uptime-ss.git
```

Or add to `requirements.txt`:
```
uptime-ss @ git+https://github.com/YOUR_USER/uptime-ss.git
```

#### Step 2: Set environment variable

Add to your project's `.env` file:
```
UPTIME_SS_CREDS=C:\path\to\gs_cred.json
```

Or set it as a system environment variable.

#### Step 3: Add to your bot code

```python
import asyncio
from uptime_ss import Heartbeat

async def main():
    # Initialize heartbeat
    hb = Heartbeat("my_bot_name", interval_minutes=5)
    await hb.start()

    try:
        # Your bot logic here
        await run_my_bot()
    finally:
        await hb.stop()

asyncio.run(main())
```

#### Step 4: Add your bot to the Google Sheet

Manually add a row in the "Control" tab:
- Column A: your bot name (must match the string passed to `Heartbeat`)
- Column B: (leave empty — will be filled automatically)
- Column C: `1` (active)
- Column D: `0` (no alert sent yet)
- Column E: Telegram chat ID where alerts should go
- Column F: Telegram usernames to mention (e.g., `@shvsa`)
- Column G: Minutes without update before alerting (e.g., `10`)

#### That's it!

The bot will update its timestamp every N minutes. If it stops, you'll get a Telegram notification.

---

## Error Scenarios

| Scenario | Behavior |
|----------|----------|
| `UPTIME_SS_CREDS` not set | `start()` logs error, heartbeat does not run, bot continues |
| Cred file not found at path | `start()` logs error, heartbeat does not run, bot continues |
| Bot name not in sheet | `start()` logs error, heartbeat does not run, bot continues |
| Network error during tick | Retry 3x with backoff (5s, 15s, 45s), then wait for next interval |
| Google API quota exceeded | Same retry logic as network error |
| Bot shuts down without `stop()` | Task is garbage collected, timestamp stops updating, Apps Script will alert |
