"""Single-request, cached archive access with robots policy and a shared rate clock."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.robotparser import RobotFileParser

HERE = Path(__file__).resolve().parent
ORIGIN = "https://vgsoharchive.com"
USER_AGENT = "VanguardCrowdsourcedCollector/0.1"
MIN_REQUEST_INTERVAL = 15.0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected sitemap entry needs review; do not follow to another domain or filter.
        return None


class ArchiveClient:
    def __init__(self, cache=None):
        self.cache = Path(cache) if cache else HERE / ".cache" / "archive"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.clock = self.cache / "last-request.json"
        self.interval_path = self.cache / "request-interval.json"
        self.minimum_interval = max(MIN_REQUEST_INTERVAL, float(json.loads(self.interval_path.read_text(encoding="utf-8"))) if self.interval_path.exists() else MIN_REQUEST_INTERVAL)
        self.delay = self.minimum_interval
        self.network_requests = 0
        self.network_request_attempts = 0
        robots = self.get(ORIGIN + "/robots.txt", policy_check=False)
        self.policy = RobotFileParser()
        self.policy.parse(robots.splitlines())
        self.delay = max(self.minimum_interval, self.policy.crawl_delay(USER_AGENT) or 0)
        self.sitemaps = self.policy.site_maps() or []
        self.policy_checked_at = time.time()

    def get(self, url, policy_check=True):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "vgsoharchive.com" or parts.query or parts.fragment:
            raise ValueError(f"Only canonical archive URLs without queries or fragments are allowed: {url}")
        if policy_check and time.time() - self.policy_checked_at > 86400:
            robots = self.get(ORIGIN + "/robots.txt", policy_check=False)
            self.policy.parse(robots.splitlines())
            self.delay = max(self.minimum_interval, self.policy.crawl_delay(USER_AGENT) or 0)
            self.policy_checked_at = time.time()
        if policy_check and not self.policy.can_fetch(USER_AGENT, url):
            raise ValueError(f"robots.txt disallows {url}")
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".txt")
        if path.exists() and (url != ORIGIN + "/robots.txt" or time.time() - path.stat().st_mtime < 86400):
            return path.read_text(encoding="utf-8")
        previous = json.loads(self.clock.read_text(encoding="utf-8")) if self.clock.exists() else 0
        time.sleep(max(0, previous + self.delay - time.time()))
        self.clock.write_text(json.dumps(time.time()), encoding="utf-8")
        request = Request(url, headers={"User-Agent": USER_AGENT})
        self.network_request_attempts += 1
        # HTTP errors are surfaced; never retry 401/403 or bypass access restrictions.
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            final = urlsplit(response.url)
            if final.netloc != parts.netloc or final.query:
                raise ValueError(f"Unexpected noncanonical redirect: {response.url}")
            body = response.read(20_000_001)
            if len(body) > 20_000_000:
                raise ValueError(f"Response exceeds 20 MB: {url}")
            text = body.decode("utf-8")
        self.network_requests += 1
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(body)
        temporary.replace(path)
        metadata=path.with_suffix('.meta.json')
        staged=metadata.with_suffix('.tmp')
        staged.write_text(json.dumps(dict(url=url,downloaded_at=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(body).hexdigest()),ensure_ascii=False),encoding='utf-8')
        staged.replace(metadata)
        return text
