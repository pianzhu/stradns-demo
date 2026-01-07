"""Tests for category gating utilities."""

import unittest

from context_retrieval.category_gating import (
    filter_by_category,
    map_type_to_category,
)
from context_retrieval.models import Device

ALLOWED_CATEGORIES = {
    "AirConditioner",
    "Blind",
    "Charger",
    "Fan",
    "Hub",
    "Light",
    "NetworkAudio",
    "Unknown",
    "Switch",
    "Television",
    "Washer",
    "SmartPlug",
}


class TestMapTypeToCategory(unittest.TestCase):
    """Tests for type hint mapping."""

    def test_canonicalization(self):
        """Normalizes case, whitespace, and separators."""
        self.assertEqual(map_type_to_category("Light"), "Light")
        self.assertEqual(map_type_to_category(" light "), "Light")
        self.assertEqual(map_type_to_category("Smart Plug"), "SmartPlug")
        self.assertEqual(map_type_to_category("Network Audio"), "NetworkAudio")
        self.assertEqual(map_type_to_category("air conditioner"), "AirConditioner")
        self.assertEqual(
            map_type_to_category("smartthings:air-conditioner"),
            "AirConditioner",
        )

        for hint in [
            "Light",
            " light ",
            "Smart Plug",
            "Network Audio",
            "air conditioner",
            "smartthings:air-conditioner",
        ]:
            result = map_type_to_category(hint)
            self.assertIn(result, ALLOWED_CATEGORIES)

    def test_empty_or_invalid_returns_none(self):
        """Empty or invalid hints return None."""
        self.assertIsNone(map_type_to_category(""))
        self.assertIsNone(map_type_to_category("invalid_category"))
        self.assertIsNone(map_type_to_category(None))

    def test_unknown_maps_to_unknown(self):
        """Unknown hint maps to Unknown category."""
        self.assertEqual(map_type_to_category("unknown"), "Unknown")
        self.assertEqual(map_type_to_category("Unknown"), "Unknown")


class TestFilterByCategory(unittest.TestCase):
    """Tests for device filtering by category."""

    def test_filter_by_type_match(self):
        """Filters devices by category value."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", category="Light"),
            Device(id="d2", name="Blind", room="Living", category="Blind"),
        ]

        filtered = filter_by_category(devices, "Light")
        ids = {d.id for d in filtered}

        self.assertEqual(ids, {"d1"})

    def test_filter_by_type_substring(self):
        """Matches category in category string."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", category="smartthings:light"),
            Device(id="d2", name="Blind", room="Living", category="smartthings:blind"),
        ]

        filtered = filter_by_category(devices, "Light")
        ids = {d.id for d in filtered}

        self.assertEqual(ids, {"d1"})

    def test_filter_by_explicit_category_attribute(self):
        """Uses explicit category attribute when present."""
        device = Device(id="d1", name="Lamp", room="Living", category="Light")

        filtered = filter_by_category([device], "Light")
        self.assertEqual([d.id for d in filtered], ["d1"])

    def test_empty_category_returns_all(self):
        """Empty category should skip filtering."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", category="Light"),
            Device(id="d2", name="Blind", room="Living", category="Blind"),
        ]

        filtered = filter_by_category(devices, "")
        self.assertEqual([d.id for d in filtered], ["d1", "d2"])

    def test_unknown_category_returns_all(self):
        """Unknown category should skip filtering."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", category="Light"),
            Device(id="d2", name="Blind", room="Living", category="Blind"),
        ]

        filtered = filter_by_category(devices, "UnknownCategory")
        self.assertEqual([d.id for d in filtered], ["d1", "d2"])

    def test_no_match_falls_back_to_all(self):
        """Valid category with no matches should fall back to all devices."""
        devices = [
            Device(id="d1", name="Blind", room="Living", category="Blind"),
        ]

        filtered = filter_by_category(devices, "Light")
        self.assertEqual([d.id for d in filtered], ["d1"])


if __name__ == "__main__":
    unittest.main()
