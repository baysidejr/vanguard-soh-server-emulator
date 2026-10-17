import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from multisource_schedule import save, step


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / '.cache/collector'
        self.state.mkdir(parents=True)
        (self.state / 'run.lock').write_text(str(os.getpid()))
        self.url = 'https://vgoplayers.com/wiki/index.php/Test'
        self.other = 'https://vgoplayers.com/wiki/index.php/Other'
        self.queue = self.state / 'multisource_queue.json'
        save(self.queue, {'pending': [self.url], 'done': []})

    def test_publish_then_resume_without_repeating_completed_page(self):
        html = '<h1 id="firstHeading">Test</h1><div id="mw-content-text"><a href="' + self.other + '">Other</a></div>'
        digest = hashlib.sha256(self.url.encode()).hexdigest()
        meta = {'url': self.url, 'sha256': hashlib.sha256(html.encode()).hexdigest(),
                'downloaded_at': '2026-10-17T00:00:00+00:00'}
        save(self.root / '.cache/multisource' / (digest + '.meta.json'), meta)
        with patch('multisource_schedule.MultiSourceClient.get', return_value=html):
            batch = step(self.root)
        state = json.loads(self.queue.read_text())
        self.assertEqual(state, {'pending': [self.other], 'done': [self.url]})
        article = json.loads((batch / 'wiki_observations.jsonl').read_text())
        self.assertEqual(article['classification'], 'metadata only')
        self.assertEqual(article['response_evidence'], meta)
        self.assertFalse((self.state / 'done.json').exists())

    def test_timeout_preserves_queue_and_does_not_publish(self):
        before = self.queue.read_bytes()
        with patch('multisource_schedule.MultiSourceClient.get', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                step(self.root)
        self.assertEqual(self.queue.read_bytes(), before)
        self.assertFalse((self.root / 'raw').exists())

    def test_stop_prevents_request(self):
        (self.state / 'stop.request').touch()
        with patch('multisource_schedule.MultiSourceClient.get') as get:
            with self.assertRaises(InterruptedError):
                step(self.root)
            get.assert_not_called()

    def test_missing_robots_suspends_alternate_intake_without_losing_queue(self):
        error = HTTPError('https://vgoplayers.com/robots.txt', 404, 'Not Found', {}, None)
        with patch('multisource_schedule.MultiSourceClient.get', side_effect=error):
            batch = step(self.root)
        state = json.loads(self.queue.read_text())
        self.assertEqual(state['pending'], [self.url])
        self.assertEqual(state['done'], [])
        self.assertEqual(state['policy_review_required']['http_status'], 404)
        self.assertTrue((batch / 'manifest.json').exists())
        with patch('multisource_schedule.MultiSourceClient.get') as get:
            self.assertIsNone(step(self.root))
            get.assert_not_called()

    def test_missing_article_is_withheld_and_access_errors_remain_fatal(self):
        with patch('multisource_schedule.MultiSourceClient.get', side_effect=HTTPError(self.url, 404, 'Not Found', {}, None)):
            step(self.root)
        state = json.loads(self.queue.read_text())
        self.assertEqual(state['done'], [])
        self.assertEqual(state['pending'], [])
        self.assertEqual(state['unavailable'][0]['url'], self.url)
        save(self.queue, {'pending': [self.url], 'done': []})
        before = self.queue.read_bytes()
        for code in (401, 403, 429):
            with patch('multisource_schedule.MultiSourceClient.get', side_effect=HTTPError(self.url, code, 'Denied', {}, None)):
                with self.assertRaises(HTTPError):
                    step(self.root)
            self.assertEqual(self.queue.read_bytes(), before)
