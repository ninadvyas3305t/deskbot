"""Tests for DeskBot platform layer, credential storage, device discovery, and packaging."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure companion is on sys.path
COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

from companion.assistant.lifecycle import (
    AppLifecycleManager,
    AppLifecycleState,
    get_lifecycle_manager,
)
from companion.device.deskbot_device import DeskBotDevice
from companion.device.discovery import is_candidate_port, scan_candidate_ports
from companion.platform.config_manager import ConfigManager
from companion.platform.credentials import CredentialStore
from companion.platform.paths import (
    get_app_data_dir,
    get_cache_dir,
    get_config_path,
    get_log_dir,
    get_log_file_path,
    get_model_cache_dir,
)
from companion.platform.permissions import (
    check_microphone_permission,
    check_screen_recording_permission,
)
from companion.ui.icon import create_tray_icon_image


class TestPlatformPaths(unittest.TestCase):
    def test_paths_types_and_resolution(self):
        app_dir = get_app_data_dir()
        self.assertIsInstance(app_dir, Path)
        self.assertTrue(app_dir.name == "DeskBot" or "deskbot" in str(app_dir).lower())

        config_path = get_config_path()
        self.assertEqual(config_path.name, "config.json")
        self.assertEqual(config_path.parent, app_dir)

        log_dir = get_log_dir()
        self.assertEqual(log_dir.name, "logs")

        log_file = get_log_file_path()
        self.assertEqual(log_file.name, "deskbot.log")

        model_cache = get_model_cache_dir()
        self.assertEqual(model_cache.name, "models")

        cache_dir = get_cache_dir()
        self.assertEqual(cache_dir.name, "cache")


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.mgr = ConfigManager(self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_defaults_and_get(self):
        self.assertEqual(self.mgr.get("wake_word"), "hey_jarvis")
        self.assertEqual(self.mgr.get("serial_port"), "auto")
        self.assertFalse(self.mgr.get("developer_mode"))
        self.assertEqual(self.mgr.get("nonexistent_key", "fallback"), "fallback")

    def test_set_and_persist(self):
        self.mgr.set("developer_mode", True)
        self.mgr.set("wake_threshold", 0.72)

        # Ensure file exists and reads back identically
        self.assertTrue(self.config_path.is_file())
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertTrue(data["developer_mode"])
        self.assertEqual(data["wake_threshold"], 0.72)

        # Fresh manager instance reading the same file
        new_mgr = ConfigManager(self.config_path)
        self.assertTrue(new_mgr.get("developer_mode"))
        self.assertEqual(new_mgr.get("wake_threshold"), 0.72)

    def test_update_multiple(self):
        self.mgr.update({"wake_model": "custom_wake", "baud_rate": 115200})
        self.assertEqual(self.mgr.get("wake_model"), "custom_wake")
        self.assertEqual(self.mgr.get("baud_rate"), 115200)


class TestCredentialStore(unittest.TestCase):
    def setUp(self):
        self.mock_keyring = {}

        def mock_set(service, key, value):
            self.mock_keyring[(service, key)] = value

        def mock_get(service, key):
            return self.mock_keyring.get((service, key))

        def mock_del(service, key):
            self.mock_keyring.pop((service, key), None)

        self.patch_set = patch("keyring.set_password", side_effect=mock_set)
        self.patch_get = patch("keyring.get_password", side_effect=mock_get)
        self.patch_del = patch("keyring.delete_password", side_effect=mock_del)

        self.patch_set.start()
        self.patch_get.start()
        self.patch_del.start()

        self.cred = CredentialStore()

    def tearDown(self):
        self.patch_set.stop()
        self.patch_get.stop()
        self.patch_del.stop()

    def test_key_lifecycle(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.cred.has_api_key())
            self.assertIsNone(self.cred.get_api_key())

            self.cred.set_api_key("nvapi-test1234567890abcdef")
            self.assertTrue(self.cred.has_api_key())
            self.assertEqual(self.cred.get_api_key(), "nvapi-test1234567890abcdef")

            self.assertEqual(self.cred.get_masked_key(), "nvapi-te...cdef")

            self.cred.delete_api_key()
            self.assertFalse(self.cred.has_api_key())
            self.assertEqual(self.cred.get_masked_key(), "Not Set")

    def test_env_var_precedence(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-from-env"}):
            self.assertTrue(self.cred.has_api_key())
            self.assertEqual(self.cred.get_api_key(), "nvapi-from-env")


class TestDeviceDiscovery(unittest.TestCase):
    def test_candidate_port_filtering(self):
        # Known ESP32 / USB Serial signatures
        self.assertTrue(is_candidate_port("/dev/cu.usbmodem1101", "USB JTAG/serial debug unit", "VID:PID=303A:1001"))
        self.assertTrue(is_candidate_port("COM3", "Silicon Labs CP210x USB to UART Bridge", "USB\\VID_10C4&PID_EA60"))
        self.assertTrue(is_candidate_port("COM4", "USB-SERIAL CH340", "USB\\VID_1A86&PID_7523"))
        self.assertTrue(is_candidate_port("/dev/ttyUSB0", "FTDI FT232R USB UART", "FTDI"))

        # Non-matching devices
        self.assertFalse(is_candidate_port("COM1", "Communications Port", "ACPI\\PNP0501"))
        self.assertFalse(is_candidate_port("/dev/cu.Bluetooth-Incoming-Port", "n/a", "n/a"))


class TestDeskBotDevice(unittest.TestCase):
    def test_init_and_state(self):
        device = DeskBotDevice(preferred_port="auto", baud=921600)
        self.assertFalse(device.is_connected)
        self.assertIsNone(device.active_port)

    def test_send_command_unconnected(self):
        device = DeskBotDevice()
        self.assertFalse(device.send_command("STATE_THINKING"))


class TestLifecycleManager(unittest.TestCase):
    def test_lifecycle_transitions_and_callbacks(self):
        mgr = AppLifecycleManager()
        self.assertEqual(mgr.current_state, AppLifecycleState.STARTING)

        recorded = []
        def listener(st, details):
            recorded.append((st, details))

        mgr.add_listener(listener)

        mgr.transition_to(AppLifecycleState.WAITING_FOR_DEVICE, "Waiting for USB")
        self.assertEqual(mgr.current_state, AppLifecycleState.WAITING_FOR_DEVICE)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0], (AppLifecycleState.WAITING_FOR_DEVICE, "Waiting for USB"))

        mgr.transition_to(AppLifecycleState.READY, "Handshake ok")
        self.assertEqual(mgr.current_state, AppLifecycleState.READY)
        self.assertEqual(len(recorded), 2)
        self.assertIn("Ready", mgr.get_status_description())


class TestPermissions(unittest.TestCase):
    def test_permissions_check(self):
        # Microphone check returns (bool, message)
        mic_ok, mic_msg = check_microphone_permission()
        self.assertIsInstance(mic_ok, bool)
        self.assertIsInstance(mic_msg, str)

        # Screen capture check returns (bool, message)
        screen_ok, screen_msg = check_screen_recording_permission()
        self.assertIsInstance(screen_ok, bool)
        self.assertIsInstance(screen_msg, str)


class TestIconGenerator(unittest.TestCase):
    def test_all_moods(self):
        moods = ["ready", "listening", "thinking", "disconnected", "error"]
        for mood in moods:
            img = create_tray_icon_image(mood, size=64)
            self.assertEqual(img.size, (64, 64))
            self.assertEqual(img.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
