"""Tests for easy_movie_studio/settings.py: app-wide preferences storage."""

import json
import os
import tempfile
import unittest

from easy_movie_studio.settings import AppSettings, SettingsStore


class AppSettingsValidationTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        AppSettings().validate()  # should not raise

    def test_unknown_export_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            AppSettings(default_export_preset="nonsense").validate()

    def test_too_small_proxy_width_is_rejected(self):
        with self.assertRaises(ValueError):
            AppSettings(proxy_min_width=10).validate()

    def test_update_is_atomic(self):
        settings = AppSettings()
        with self.assertRaises(ValueError):
            settings.update(default_export_preset="nonsense")
        self.assertEqual(settings.default_export_preset, "recommended")

    def test_update_rejects_unknown_fields(self):
        settings = AppSettings()
        with self.assertRaises(AttributeError):
            settings.update(not_a_real_field=1)

    def test_update_applies_valid_changes(self):
        settings = AppSettings()
        settings.update(default_export_preset="hq", proxy_min_width=1280)
        self.assertEqual(settings.default_export_preset, "hq")
        self.assertEqual(settings.proxy_min_width, 1280)


class RoundTripTests(unittest.TestCase):
    def test_from_dict_recovers_saved_values(self):
        original = AppSettings(default_export_preset="mobile", default_project_dir="/movies",
                               ffmpeg_dir="/opt/ffmpeg", proxy_min_width=1280)
        restored = AppSettings.from_dict(original.to_dict())
        self.assertEqual(restored, original)

    def test_from_dict_with_invalid_preset_falls_back_to_defaults(self):
        restored = AppSettings.from_dict({"default_export_preset": "not-a-real-preset"})
        self.assertEqual(restored, AppSettings())

    def test_from_dict_ignores_unknown_keys(self):
        restored = AppSettings.from_dict({"default_export_preset": "hq", "bogus": 123})
        self.assertEqual(restored.default_export_preset, "hq")

    def test_from_dict_with_wrong_type_for_one_field_keeps_the_rest(self):
        restored = AppSettings.from_dict({"default_export_preset": "hq",
                                          "proxy_min_width": {"not": "a number"}})
        self.assertEqual(restored.default_export_preset, "hq")
        self.assertEqual(restored.proxy_min_width, AppSettings().proxy_min_width)


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "nested", "settings.json")

    def test_load_with_no_file_returns_defaults(self):
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())

    def test_save_then_load_round_trips(self):
        store = SettingsStore(self.path)
        settings = AppSettings(default_export_preset="youtube", proxy_min_width=1600)
        store.save(settings)
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(store.load(), settings)

    def test_load_with_corrupted_json_returns_defaults(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())

    def test_load_with_a_json_list_instead_of_object_returns_defaults(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())

    def test_save_never_raises_when_the_directory_cant_be_created(self):
        store = SettingsStore("/root/not_writable_xyz/settings.json")
        store.save(AppSettings())  # must not raise


if __name__ == "__main__":
    unittest.main()
