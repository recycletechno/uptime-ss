import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from uptime_ss.heartbeat import Heartbeat


@pytest.fixture
def fake_creds_file():
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


def test_heartbeat_init():
    hb = Heartbeat("test_bot", interval_minutes=3)
    assert hb.bot_name == "test_bot"
    assert hb.interval_minutes == 3
    assert hb._task is None


@pytest.mark.asyncio
async def test_heartbeat_start_bot_not_found(fake_creds_file):
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        hb = Heartbeat("unknown_bot")
        with patch("uptime_ss.heartbeat.SheetsClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.find_bot_row = AsyncMock(return_value=None)
            await hb.start()
    assert hb._task is None


@pytest.mark.asyncio
async def test_heartbeat_start_and_stop(fake_creds_file):
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        hb = Heartbeat("test_bot", interval_minutes=1)
        with patch("uptime_ss.heartbeat.SheetsClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.find_bot_row = AsyncMock(return_value=2)
            mock_instance.write_timestamp = AsyncMock()
            await hb.start()
            assert hb._task is not None
            # Let one tick happen
            await asyncio.sleep(0.1)
            mock_instance.write_timestamp.assert_called_with(2)
            await hb.stop()
            assert hb._task is None


@pytest.mark.asyncio
async def test_heartbeat_start_missing_creds():
    with patch.dict(os.environ, {}, clear=True):
        hb = Heartbeat("test_bot")
        await hb.start()
    assert hb._task is None
