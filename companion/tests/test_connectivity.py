"""Automated test suite for DeskBot Connectivity Supervisor and State Transitions."""

from __future__ import annotations

import time
from unittest.mock import patch
import pytest

from companion.connectivity import (
    ConnectivityManager,
    ConnectivityState,
    get_connectivity_manager,
)


@pytest.fixture(autouse=True)
def reset_connectivity_state():
    """Ensure clean connectivity manager state before and after each test."""
    mgr = get_connectivity_manager()
    mgr.set_override_state(None)
    mgr.stop_monitoring()
    yield mgr
    mgr.set_override_state(None)
    mgr.stop_monitoring()


def test_connectivity_state_enum():
    """Verify ConnectivityState enum values and properties."""
    assert ConnectivityState.ONLINE.value == "ONLINE"
    assert ConnectivityState.OFFLINE.value == "OFFLINE"
    assert ConnectivityState.DEGRADED.value == "DEGRADED"


def test_connectivity_manager_singleton():
    """Verify get_connectivity_manager returns the shared singleton instance."""
    m1 = get_connectivity_manager()
    m2 = get_connectivity_manager()
    assert m1 is m2
    assert isinstance(m1, ConnectivityManager)


def test_state_override(reset_connectivity_state):
    """Verify manual override mechanism for deterministic testing and demo modes."""
    mgr = reset_connectivity_state

    # 1. Force OFFLINE override
    mgr.set_override_state(ConnectivityState.OFFLINE)
    assert mgr.state == ConnectivityState.OFFLINE
    assert mgr.is_offline() is True
    assert mgr.is_online() is False
    assert mgr.is_degraded() is False

    # 2. Force DEGRADED override via string
    mgr.set_override_state("degraded")
    assert mgr.state == ConnectivityState.DEGRADED
    assert mgr.is_degraded() is True
    assert mgr.is_offline() is False
    assert mgr.is_online() is False

    # 3. Force ONLINE override
    mgr.set_override_state("online")
    assert mgr.state == ConnectivityState.ONLINE
    assert mgr.is_online() is True

    # 4. Clear override
    mgr.set_override_state(None)
    assert mgr._override_state is None


def test_evaluate_connectivity_online(reset_connectivity_state):
    """Verify evaluate_connectivity marks ONLINE when internet and API probes succeed."""
    mgr = reset_connectivity_state

    with patch.object(mgr, "check_internet", return_value=True), \
         patch.object(mgr, "check_cloud_api", return_value=True):
        state = mgr.evaluate_connectivity()
        assert state == ConnectivityState.ONLINE
        assert mgr.is_online() is True
        assert mgr.is_offline() is False


def test_evaluate_connectivity_offline(reset_connectivity_state):
    """Verify evaluate_connectivity marks OFFLINE when internet socket probes fail."""
    mgr = reset_connectivity_state

    with patch.object(mgr, "check_internet", return_value=False):
        state = mgr.evaluate_connectivity()
        assert state == ConnectivityState.OFFLINE
        assert mgr.is_offline() is True
        assert mgr.is_online() is False


def test_evaluate_connectivity_degraded(reset_connectivity_state):
    """Verify evaluate_connectivity marks DEGRADED when internet is active but API unreachable."""
    mgr = reset_connectivity_state

    with patch.object(mgr, "check_internet", return_value=True), \
         patch.object(mgr, "check_cloud_api", return_value=False):
        state = mgr.evaluate_connectivity()
        assert state == ConnectivityState.DEGRADED
        assert mgr.is_degraded() is True
        assert mgr.is_online() is False
        assert mgr.is_offline() is False


def test_report_api_failure_and_success_transitions(reset_connectivity_state):
    """Verify API failure degrades service and subsequent success restores ONLINE."""
    mgr = reset_connectivity_state
    mgr._state = ConnectivityState.ONLINE

    # Report API failure (e.g., timeout or 503)
    mgr.report_api_failure(TimeoutError("Read timed out after 10s"))
    assert mgr.state == ConnectivityState.DEGRADED
    assert mgr.is_degraded() is True

    # Report API success
    mgr.report_api_success()
    assert mgr.state == ConnectivityState.ONLINE
    assert mgr.is_online() is True


def test_connectivity_listener_notifications(reset_connectivity_state):
    """Verify registered listener callbacks are triggered upon state changes."""
    mgr = reset_connectivity_state
    notifications: list[tuple[ConnectivityState, str]] = []

    def callback(state: ConnectivityState, details: str):
        notifications.append((state, details))

    mgr.add_listener(callback)

    try:
        # Trigger state change
        mgr.set_override_state(ConnectivityState.OFFLINE)
        assert len(notifications) == 1
        assert notifications[0][0] == ConnectivityState.OFFLINE

        # Clear override
        mgr.set_override_state(None)
        assert len(notifications) == 2

        # Remove listener and ensure no more calls
        mgr.remove_listener(callback)
        mgr.set_override_state(ConnectivityState.DEGRADED)
        assert len(notifications) == 2
    finally:
        mgr.remove_listener(callback)


def test_background_monitoring_lifecycle(reset_connectivity_state):
    """Verify start_monitoring starts a daemon thread and stop_monitoring terminates it cleanly."""
    mgr = reset_connectivity_state

    with patch.object(mgr, "evaluate_connectivity") as mock_eval:
        mock_eval.return_value = ConnectivityState.ONLINE
        mgr.start_monitoring(interval_seconds=0.1)

        assert mgr._monitor_thread is not None
        assert mgr._monitor_thread.is_alive() is True

        time.sleep(0.25)
        assert mock_eval.call_count >= 1

        mgr.stop_monitoring()
        time.sleep(0.15)
        assert mgr._monitor_thread is None
