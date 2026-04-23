import asyncio
import datetime
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
        path = f.name
    yield path
    os.unlink(path)


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


@pytest.mark.asyncio
async def test_tick_retries_then_succeeds(fake_creds_file):
    """Test that _tick retries on failure and succeeds on third attempt."""
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        hb = Heartbeat("test_bot")
        with patch("uptime_ss.heartbeat.SheetsClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.find_bot_row = AsyncMock(return_value=2)
            mock_instance.write_timestamp = AsyncMock(
                side_effect=[Exception("fail1"), Exception("fail2"), None]
            )
            await hb.start()

            # Patch backoff delays to be instant for testing
            with patch("uptime_ss.heartbeat.BACKOFF_DELAYS", [0, 0, 0]):
                await hb._tick()

            # 1 call from start's first loop iteration + 3 from our _tick call
            assert mock_instance.write_timestamp.call_count >= 3
            await hb.stop()


@pytest.mark.asyncio
async def test_tick_all_retries_fail(fake_creds_file):
    """Test that _tick logs error after all retries fail."""
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        hb = Heartbeat("test_bot")
        with patch("uptime_ss.heartbeat.SheetsClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.find_bot_row = AsyncMock(return_value=2)
            mock_instance.write_timestamp = AsyncMock(
                side_effect=Exception("always fails")
            )
            await hb.start()

            with patch("uptime_ss.heartbeat.BACKOFF_DELAYS", [0, 0, 0]):
                await hb._tick()

            # Should have attempted MAX_RETRIES times in our _tick call
            # (plus attempts from the background loop)
            assert mock_instance.write_timestamp.call_count >= 3
            await hb.stop()


@pytest.mark.asyncio
async def test_heartbeat_stop_without_start():
    """Test that stop() is safe to call without start()."""
    hb = Heartbeat("test_bot")
    await hb.stop()  # Should not raise
    assert hb._task is None


@pytest.mark.asyncio
async def test_heartbeat_passes_timeout_to_client(fake_creds_file):
    """Heartbeat forwards its timeout arg to SheetsClient."""
    with patch.dict(os.environ, {"UPTIME_SS_CREDS": fake_creds_file}):
        hb = Heartbeat("test_bot", interval_minutes=1, timeout=42.0)
        with patch("uptime_ss.heartbeat.SheetsClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.find_bot_row = AsyncMock(return_value=2)
            mock_instance.write_timestamp = AsyncMock()
            await hb.start()
            MockClient.assert_called_once_with(timeout=42.0)
            await hb.stop()


@pytest.mark.asyncio
async def test_tick_retries_on_timeout_error():
    """TimeoutError from write_timestamp is treated like any other exception."""
    hb = Heartbeat("test_bot")
    hb._row = 2
    hb._client = AsyncMock()
    hb._client.write_timestamp = AsyncMock(
        side_effect=[asyncio.TimeoutError(), asyncio.TimeoutError(), None]
    )

    with patch("uptime_ss.heartbeat.BACKOFF_DELAYS", [0, 0, 0]):
        await hb._tick()

    assert hb._client.write_timestamp.call_count == 3
    assert hb.last_success_at is not None


@pytest.mark.asyncio
async def test_tick_recovers_after_transient_500():
    """Regression: transient 500 on first attempt recovers on retry."""
    hb = Heartbeat("test_bot")
    hb._row = 2
    hb._client = AsyncMock()

    class FakeHTTPError(Exception):
        pass

    hb._client.write_timestamp = AsyncMock(
        side_effect=[FakeHTTPError("500 Internal Server Error"), None]
    )

    with patch("uptime_ss.heartbeat.BACKOFF_DELAYS", [0, 0, 0]):
        await hb._tick()

    assert hb._client.write_timestamp.call_count == 2
    assert hb.last_success_at is not None


@pytest.mark.asyncio
async def test_tick_no_sleep_after_final_attempt():
    """Backoff sleep runs between attempts only, not after the last one."""
    hb = Heartbeat("test_bot")
    hb._row = 2
    hb._client = AsyncMock()
    hb._client.write_timestamp = AsyncMock(side_effect=Exception("always fails"))

    with patch("uptime_ss.heartbeat.BACKOFF_DELAYS", [0, 0, 0]):
        with patch(
            "uptime_ss.heartbeat.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await hb._tick()

    # MAX_RETRIES=3 → 2 inter-attempt sleeps, no sleep after the final failure.
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_loop_survives_unexpected_exception():
    """An unexpected exception inside _tick must not kill the background loop."""
    hb = Heartbeat("test_bot")
    hb._row = 2

    call_count = 0

    async def flaky_tick():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("unexpected — not caught by _tick's retry loop")

    hb._tick = flaky_tick

    real_sleep = asyncio.sleep

    async def no_sleep(_):
        await real_sleep(0)

    with patch("uptime_ss.heartbeat.asyncio.sleep", no_sleep):
        task = asyncio.create_task(hb._loop())
        for _ in range(20):
            await real_sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert call_count >= 2


@pytest.mark.asyncio
async def test_stop_cancels_cleanly_even_when_tick_always_fails():
    """stop() must cancel the loop task even if ticks have been raising."""
    hb = Heartbeat("test_bot", interval_minutes=1)
    hb._row = 2

    async def bad_tick():
        raise RuntimeError("boom")

    hb._tick = bad_tick
    hb._task = asyncio.create_task(hb._loop())

    await asyncio.sleep(0.02)
    await hb.stop()
    assert hb._task is None


@pytest.mark.asyncio
async def test_last_success_at_set_after_successful_tick():
    hb = Heartbeat("test_bot")
    hb._row = 2
    hb._client = AsyncMock()
    hb._client.write_timestamp = AsyncMock()

    assert hb.last_success_at is None
    await hb._tick()
    assert isinstance(hb.last_success_at, datetime.datetime)


@pytest.mark.asyncio
async def test_is_healthy_lifecycle():
    hb = Heartbeat("test_bot", interval_minutes=5)
    assert hb.is_healthy is False  # never ticked

    hb._row = 2
    hb._client = AsyncMock()
    hb._client.write_timestamp = AsyncMock()
    await hb._tick()
    assert hb.is_healthy is True

    # Simulate last success older than 2 * interval → unhealthy
    hb.last_success_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=11)
    assert hb.is_healthy is False
