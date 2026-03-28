import json
import logging
import os
import time
from typing import Optional

from aiogoogle import Aiogoogle
from aiogoogle.auth.creds import ServiceAccountCreds

log = logging.getLogger(__name__)

SPREADSHEET_ID = "1f0dQSyH5dtcFVadvj4XNB2fVrGcV6MMp99GkK7ygUgM"
SHEET_NAME = "Control"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsClient:
    def __init__(self):
        creds_path = os.environ.get("UPTIME_SS_CREDS")
        if not creds_path:
            raise ValueError(
                "UPTIME_SS_CREDS environment variable is not set. "
                "Set it to the path of your gs_cred.json file."
            )
        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                f"Credentials file not found at: {creds_path}"
            )
        with open(creds_path, "r") as f:
            cred_data = json.load(f)
        self.creds = ServiceAccountCreds(scopes=SCOPES, **cred_data)

    async def find_bot_row(self, bot_name: str) -> Optional[int]:
        """Find the row number (1-indexed) for the given bot name in column A."""
        async with Aiogoogle(service_account_creds=self.creds) as aiog:
            sheets = await aiog.discover("sheets", "v4")
            request = sheets.spreadsheets.values.get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:A",
                valueRenderOption="FORMATTED_VALUE",
            )
            result = await aiog.as_service_account(request)

        values = result.get("values", [])
        for i, row in enumerate(values):
            if row and row[0] == bot_name:
                return i + 1  # 1-indexed row number
        return None

    async def write_timestamp(self, row: int) -> None:
        """Write current UTC timestamp to column B of the given row."""
        now_utc = time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime())
        body = {"values": [[now_utc]]}

        async with Aiogoogle(service_account_creds=self.creds) as aiog:
            sheets = await aiog.discover("sheets", "v4")
            request = sheets.spreadsheets.values.update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!B{row}",
                valueInputOption="USER_ENTERED",
                json=body,
            )
            await aiog.as_service_account(request)
