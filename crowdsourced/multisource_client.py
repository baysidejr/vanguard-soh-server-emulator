"""Policy-aware alternate-source transport for the sole collector process.

Not a second collector entrypoint. A caller must own the existing collector lock.
Uses the archive request clock and persisted interval so source switches cannot
create a faster or concurrent stream. HTTP errors are surfaced without retry.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.robotparser import RobotFileParser

from archive_client import NoRedirect, USER_AGENT

HERE = Path(__file__).resolve().parent
HOSTS = frozenset(('vgoplayers.com', 'vgoemulator.net', 'vanguard.fandom.com'))


class MultiSourceClient:
    def __init__(self, root=HERE):
        self.root = Path(root)
        self.cache = self.root / '.cache/multisource'
        self.state = self.root / '.cache/collector'
        self.clock = self.root / '.cache/archive/last-request.json'
        self.interval = self.clock.with_name('request-interval.json')
        self.policies = {}
        self.policy_evidence = {}

    def check_owner(self):
        lock = self.state / 'run.lock'
        if not lock.exists() or int(lock.read_text(encoding='utf-8').strip()) != os.getpid():
            raise RuntimeError('Alternate requests require ownership of the sole collector run.lock')
        if (self.state / 'stop.request').exists():
            raise InterruptedError('Graceful collector stop requested')

    def wait(self, delay):
        previous = float(json.loads(self.clock.read_text(encoding='utf-8'))) if self.clock.exists() else 0
        while time.time() < previous + delay:
            self.check_owner()
            time.sleep(min(0.25, max(0, previous + delay - time.time())))
        self.check_owner()

    def download(self, url, delay, ttl=None):
        self.check_owner()
        digest = hashlib.sha256(url.encode()).hexdigest()
        body_path = self.cache / (digest + '.html')
        meta_path = self.cache / (digest + '.meta.json')
        if body_path.exists() and meta_path.exists():
            body = body_path.read_bytes()
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            if meta['url'] != url or hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise ValueError('Alternate-source cache integrity failure')
            age = time.time() - datetime.fromisoformat(meta['downloaded_at']).timestamp()
            if ttl is None or age < ttl:
                return body.decode('utf-8')
        self.wait(delay)
        self.clock.parent.mkdir(parents=True, exist_ok=True)
        self.clock.write_text(json.dumps(time.time()), encoding='utf-8')
        with build_opener(NoRedirect()).open(Request(url, headers={'User-Agent': USER_AGENT}), timeout=30) as response:
            if response.url != url:
                raise ValueError('Unexpected redirect')
            body = response.read(20_000_001)
            if len(body) > 20_000_000:
                raise ValueError('Response exceeds 20 MB')
            text = body.decode('utf-8')
        self.cache.mkdir(parents=True, exist_ok=True)
        for path, value in ((body_path, body), (meta_path, json.dumps({
                'url': url, 'downloaded_at': datetime.now(timezone.utc).isoformat(),
                'sha256': hashlib.sha256(body).hexdigest()}).encode('utf-8'))):
            temporary = path.with_suffix(path.suffix + '.tmp')
            temporary.write_bytes(value)
            temporary.replace(path)
        return text

    def get(self, url):
        self.check_owner()
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.netloc not in HOSTS or parts.fragment:
            raise ValueError('Unsupported alternate source URL')
        minimum = max(15.0, float(json.loads(self.interval.read_text(encoding='utf-8')))
                      if self.interval.exists() else 15.0)
        policy_entry = self.policies.get(parts.netloc)
        if policy_entry is None or time.time() - policy_entry[0] >= 86400:
            robots_url = 'https://' + parts.netloc + '/robots.txt'
            status = 200
            try:
                robots = self.download(robots_url, minimum, ttl=86400)
            except HTTPError as error:
                # Missing robots is not a prohibition. Access/rate/server failures
                # still propagate before any content request; never bypass them.
                if error.code not in (404, 410) or error.url != robots_url:
                    raise
                status = error.code
                error.close()
                robots = 'User-agent: *\nAllow: /\n'
            evidence = {'url': robots_url, 'http_status': status,
                        'checked_at': datetime.now(timezone.utc).isoformat(),
                        'interpretation': 'missing robots; conservative collection allowed'
                            if status in (404, 410) else 'published robots rules applied'}
            self.policy_evidence[parts.netloc] = evidence
            self.cache.mkdir(parents=True, exist_ok=True)
            evidence_path = self.cache / (parts.netloc + '.policy.json')
            staged = evidence_path.with_suffix('.tmp')
            staged.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
            staged.replace(evidence_path)
            policy = RobotFileParser()
            policy.parse(robots.splitlines())
            policy_entry = (time.time(), policy)
            self.policies[parts.netloc] = policy_entry
        policy = policy_entry[1]
        if not policy.can_fetch(USER_AGENT, url):
            raise ValueError('robots.txt disallows ' + url)
        # Query permissions belong to this host's robots, not archive rules.
        delay = max(minimum, policy.crawl_delay(USER_AGENT) or 0)
        rate = policy.request_rate(USER_AGENT)
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        return self.download(url, delay)
