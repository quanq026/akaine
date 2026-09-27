"""The bundle decision depends on client headers and must never be cached."""

import unittest
from unittest.mock import patch

import main


class ContentBundleCacheTests(unittest.TestCase):
    def test_bundle_response_is_not_cacheable(self):
        route = next(
            rule.rule for rule in main.app.url_map.iter_rules()
            if rule.endpoint.endswith('.game_content_bundle')
        )
        with patch('server.others.Connect'), patch(
            'server.others.BundleDownload.get_bundle_list', return_value=[]
        ):
            response = main.app.test_client().get(
                route,
                headers={'AppVersion': '7.0.255', 'ContentBundle': '7.0.255.8'},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')


if __name__ == '__main__':
    unittest.main()
