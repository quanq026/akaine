"""Focused source/asset boundary checks for the current versioned patchset."""
import struct
import unittest
import build_android_client as client

resources = client.load_patch_module('resource_tests', client.PATCH / 'resources.py')
native = client.load_patch_module('native_tests', client.PATCH / 'native/build.py')
managed = client.load_patch_module('managed_tests', client.PATCH / 'smali/build.py')


class CurrentPatchTests(unittest.TestCase):
    def test_resource_string_pools_round_trip_without_losing_unicode(self):
        values = ['', 'AkaineXD', 'Tiếng Việt', '🎵', 'x' * 140]
        for flags in (0, 0x100):
            encoded = resources.write_pool(values, flags)
            actual, actual_flags = resources.read_pool(encoded)
            self.assertEqual(actual, values)
            self.assertEqual(actual_flags, flags)

    def test_wrong_resource_and_asset_preimages_are_rejected(self):
        for transform in (resources.patch_manifest, resources.patch_resources):
            with self.assertRaises(ValueError):
                transform(b'not the supported APK')
        with self.assertRaises(ValueError):
            native.apply_stock_plan(b'not a native library')
        with self.assertRaises((ValueError, AssertionError, struct.error)):
            resources.Reader(b'bad').u32(0)

    def test_managed_patches_never_guess_missing_or_repeated_source(self):
        for text in ('absent', 'fixture fixture'):
            with self.assertRaises(ValueError):
                managed.replace_once(text, 'fixture', 'changed')
        with self.assertRaises(ValueError):
            managed.patch_renderer('unrelated method', '', '')

    def test_native_branch_requires_valid_instruction_alignment_and_range(self):
        self.assertEqual(native.branch(0x1000, 0x1004), bytes.fromhex('01000014'))
        for target in (0x1001, 0x1000 + (1 << 27)):
            with self.assertRaises(ValueError):
                native.branch(0x1000, target)


if __name__ == '__main__':
    unittest.main()
