import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from multisource_client import MultiSourceClient


class MultiSourceClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.client = MultiSourceClient(self.temp.name)
        self.client.state.mkdir(parents=True)
        (self.client.state / 'run.lock').write_text(str(os.getpid()))
        self.client.clock.parent.mkdir(parents=True)
        self.client.interval.write_text(json.dumps(60))

    def test_requires_same_collector_and_respects_stop(self):
        (self.client.state / 'run.lock').write_text('0')
        with self.assertRaises(RuntimeError):
            self.client.get('https://vgoplayers.com/items.php')
        (self.client.state / 'run.lock').write_text(str(os.getpid()))
        (self.client.state / 'stop.request').touch()
        with self.assertRaises(InterruptedError):
            self.client.get('https://vgoplayers.com/items.php')

    def test_host_policy_allows_queries_and_longer_delay(self):
        with patch.object(self.client, 'download', side_effect=[
                'User-agent: *\nDisallow: /private\nCrawl-delay: 90', 'content']) as download:
            self.assertEqual(self.client.get('https://vgoplayers.com/items.php?name=test'), 'content')
            self.assertEqual(download.call_args.args, ('https://vgoplayers.com/items.php?name=test', 90))
            with self.assertRaises(ValueError):
                self.client.get('https://vgoplayers.com/private')
            self.assertEqual(download.call_count, 2)

    def test_robots_http_denial_never_requests_content(self):
        for code in (401, 403, 429):
            error = HTTPError('url', code, 'denied', {}, None)
            self.addCleanup(error.close)
            with patch.object(self.client, 'download', side_effect=error) as download:
                with self.assertRaises(HTTPError):
                    self.client.get('https://vanguard.fandom.com/wiki/Telonica')
                self.assertEqual(download.call_count, 1)

    def test_rejects_other_hosts_and_fragment_before_network(self):
        with patch.object(self.client, 'download') as download:
            for url in ('https://elsewhere.test/', 'http://vgoplayers.com/',
                        'https://vgoplayers.com/items.php#x'):
                with self.assertRaises(ValueError):
                    self.client.get(url)
            download.assert_not_called()

    def test_missing_robots_allows_polite_content_but_only_for_robots_url(self):
        for code in (404, 410):
            self.client.policies.clear()
            robots_url = 'https://vgoplayers.com/robots.txt'
            error = HTTPError(robots_url, code, 'missing', {}, None)
            with patch.object(self.client, 'download', side_effect=[error, 'page', 'next']) as download:
                self.assertEqual(self.client.get('https://vgoplayers.com/items.php'), 'page')
                self.assertEqual(self.client.get('https://vgoplayers.com/quests.php'), 'next')
                self.assertEqual(download.call_count, 3)
                self.assertEqual(download.call_args.args[1], 60)
                self.assertEqual(self.client.policy_evidence['vgoplayers.com']['http_status'], code)
        self.client.policies.clear()
        error = HTTPError('https://vgoplayers.com/other', 404, 'missing', {}, None)
        self.addCleanup(error.close)
        with patch.object(self.client, 'download', side_effect=error) as download:
            with self.assertRaises(HTTPError):
                self.client.get('https://vgoplayers.com/items.php')
            self.assertEqual(download.call_count, 1)
