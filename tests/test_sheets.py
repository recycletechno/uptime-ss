import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch
from uptime_ss.sheets import SheetsClient


@pytest.fixture
def fake_creds_file():
    """Create a temporary fake service account JSON file."""
    creds_data = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(creds_data, f)
        return f.name


def test_load_creds_from_env(fake_creds_file):
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        client = SheetsClient()
    assert client.creds is not None


def test_load_creds_missing_env():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="UPTIME_SS_CREDS"):
            SheetsClient()


def test_load_creds_file_not_found():
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": "C:\\nonexistent\\path.json"}):
        with pytest.raises(FileNotFoundError):
            SheetsClient()


@pytest.fixture
def sheets_client(fake_creds_file):
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        return SheetsClient()


@pytest.mark.asyncio
async def test_find_bot_row_found(sheets_client):
    mock_result = {"values": [["1"], ["cvi_bot"], ["cvi_oracle"]]}

    with patch.object(sheets_client, "_api_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_result
        row = await sheets_client.find_bot_row("cvi_bot")

    assert row == 2


@pytest.mark.asyncio
async def test_find_bot_row_not_found(sheets_client):
    mock_result = {"values": [["1"], ["cvi_bot"]]}

    with patch.object(sheets_client, "_api_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_result
        row = await sheets_client.find_bot_row("unknown_bot")

    assert row is None


@pytest.mark.asyncio
async def test_write_timestamp(sheets_client):
    with patch.object(sheets_client, "_api_call", new_callable=AsyncMock) as mock_call:
        await sheets_client.write_timestamp(3)

    mock_call.assert_called_once()
    call_args = mock_call.call_args
    assert call_args[0][0] == "update"
    assert call_args[0][1] == 3
