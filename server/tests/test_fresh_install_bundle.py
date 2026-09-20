"""Regression coverage for the production fresh-install-only bundle policy."""

import unittest

from core.bundle import BundleParser, ContentBundle
from core.config_manager import Config


def make_bundle(version: str) -> ContentBundle:
    bundle = ContentBundle()
    bundle.version = version
    bundle.prev_version = "0.0.0"
    bundle.app_version = "6.15.0"
    return bundle


class FreshInstallOnlyBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_bundles = BundleParser.bundles
        self.original_max = BundleParser.max_bundle_version
        self.original_next = BundleParser.next_versions
        self.original_index = BundleParser.version_tuple_bundles
        self.had_setting = hasattr(Config, "FRESH_INSTALL_ONLY_BUNDLE_VERSION")
        self.original_setting = getattr(Config, "FRESH_INSTALL_ONLY_BUNDLE_VERSION", None)

        fresh = make_bundle("6.15.95")
        current = make_bundle("6.15.136")
        BundleParser.bundles = {"6.15.0": [fresh, current]}
        BundleParser.max_bundle_version = {"6.15.0": "6.15.136"}
        BundleParser.next_versions = {"0.0.0": ["6.15.95", "6.15.136"]}
        BundleParser.version_tuple_bundles = {
            ("6.15.95", "0.0.0"): fresh,
            ("6.15.136", "0.0.0"): current,
        }
        Config.FRESH_INSTALL_ONLY_BUNDLE_VERSION = "6.15.95"
        BundleParser.get_bundles.cache_clear()

    def tearDown(self) -> None:
        BundleParser.bundles = self.original_bundles
        BundleParser.max_bundle_version = self.original_max
        BundleParser.next_versions = self.original_next
        BundleParser.version_tuple_bundles = self.original_index
        if self.had_setting:
            Config.FRESH_INSTALL_ONLY_BUNDLE_VERSION = self.original_setting
        else:
            delattr(Config, "FRESH_INSTALL_ONLY_BUNDLE_VERSION")
        BundleParser.get_bundles.cache_clear()

    def test_only_empty_content_versions_receive_fresh_bundle(self) -> None:
        for version in (None, "", "0.0.0"):
            with self.subTest(version=version):
                bundles = BundleParser.get_bundles("6.15.0", version)
                self.assertEqual([bundle.version for bundle in bundles], ["6.15.95"])

    def test_existing_content_versions_never_receive_downgrade(self) -> None:
        for version in ("6.15.95", "6.15.135", "6.15.136", "9.9.9"):
            with self.subTest(version=version):
                self.assertEqual(BundleParser.get_bundles("6.15.0", version), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
