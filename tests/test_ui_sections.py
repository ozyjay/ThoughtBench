import unittest

from thoughtbench.ui import (
    DEFAULT_SECTION_ID,
    EXPECTED_SECTION_IDS,
    build_section_registry,
)


class UiSectionRegistryTests(unittest.TestCase):
    def test_section_registry_exposes_expected_sidebar_sections_in_order(self):
        sections = build_section_registry()

        self.assertEqual([section.section_id for section in sections], list(EXPECTED_SECTION_IDS))
        self.assertEqual(DEFAULT_SECTION_ID, "chat")

    def test_section_registry_has_builder_for_each_section(self):
        for section in build_section_registry():
            self.assertTrue(section.label)
            self.assertTrue(section.builder_name.startswith("_build_"))
            self.assertTrue(section.builder_name.endswith("_section"))


if __name__ == "__main__":
    unittest.main()
