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
    "Others",
    "Switch",
    "Television",
    "Washer",
    "SmartPlug",
}


class TestMapTypeToCategory(unittest.TestCase):
    """Tests for type hint mapping."""

    def test_known_mappings(self):
        """Maps known synonyms to categories."""
        self.assertEqual(map_type_to_category("light"), "Light")
        self.assertEqual(map_type_to_category(" Lamp "), "Light")
        self.assertEqual(map_type_to_category("ac"), "AirConditioner")
        self.assertEqual(map_type_to_category("air conditioner"), "AirConditioner")

        for hint in ["light", "ac", "air conditioner"]:
            result = map_type_to_category(hint)
            self.assertIn(result, ALLOWED_CATEGORIES)

    def test_unknown_returns_none(self):
        """Unknown or empty hints return None."""
        self.assertIsNone(map_type_to_category(""))
        self.assertIsNone(map_type_to_category("unknown"))
        self.assertIsNone(map_type_to_category(None))


class TestFilterByCategory(unittest.TestCase):
    """Tests for device filtering by category."""

    def test_filter_by_type_match(self):
        """Filters devices by type value."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", type="Light"),
            Device(id="d2", name="Blind", room="Living", type="Blind"),
        ]

        filtered = filter_by_category(devices, "Light")
        ids = {d.id for d in filtered}

        self.assertEqual(ids, {"d1"})

    def test_filter_by_type_substring(self):
        """Matches category in type string."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", type="smartthings:light"),
            Device(id="d2", name="Blind", room="Living", type="smartthings:blind"),
        ]

        filtered = filter_by_category(devices, "Light")
        ids = {d.id for d in filtered}

        self.assertEqual(ids, {"d1"})

    def test_filter_by_explicit_category_attribute(self):
        """Uses explicit category attribute when present."""
        device = Device(id="d1", name="Lamp", room="Living", type="unknown")
        device.type = "Light"

        filtered = filter_by_category([device], "Light")
        self.assertEqual([d.id for d in filtered], ["d1"])

    def test_empty_category_returns_all(self):
        """Empty category should skip filtering."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", type="Light"),
            Device(id="d2", name="Blind", room="Living", type="Blind"),
        ]

        filtered = filter_by_category(devices, "")
        self.assertEqual([d.id for d in filtered], ["d1", "d2"])

    def test_unknown_category_returns_all(self):
        """Unknown category should skip filtering."""
        devices = [
            Device(id="d1", name="Lamp", room="Living", type="Light"),
            Device(id="d2", name="Blind", room="Living", type="Blind"),
        ]

        filtered = filter_by_category(devices, "UnknownCategory")
        self.assertEqual([d.id for d in filtered], ["d1", "d2"])


if __name__ == "__main__":
    unittest.main()
