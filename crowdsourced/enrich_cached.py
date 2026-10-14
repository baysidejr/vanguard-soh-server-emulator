"""Re-extract downloaded archive pages into a new immutable batch, without network access."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import collect_archive as collector


class CacheOnlyClient:
    network_requests = 0
    cache_only = True

    def __init__(self, cache):
        self.cache = Path(cache)

    def get(self, url):
        if not collector.detail_url(url):
            raise ValueError(f'Not a supported canonical detail URL: {url}')
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
        if not path.is_file():
            raise FileNotFoundError(f'Page not in cache: {url}')
        return path.read_text(encoding='utf-8')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--limit', type=int, default=1000)
    args = ap.parse_args(argv)
    if args.limit < 1:
        ap.error('limit must be positive')
    root = collector.HERE
    rows = json.loads((root / '.cache/collector/inventory.json').read_text(encoding='utf-8'))
    client = CacheOnlyClient(root / '.cache/archive')
    cache_files = {path.name for path in client.cache.glob('*.txt')}
    candidates=[row['url'] for row in rows]
    for name in ('done.json','active_queue.json'):
        path=root/'.cache/collector'/name
        if path.is_file():
            candidates+=json.loads(path.read_text(encoding='utf-8'))
    indexes=[url for url in candidates if '/classes/' in url and collector.detail_url(url)]
    candidates+=collector.cached_trainer_urls(client,indexes)
    for path in client.cache.glob('*.meta.json'):
        metadata=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(metadata.get('url'),str):candidates.append(metadata['url'])
    urls = [url for url in collector.unique(candidates) if collector.detail_url(url) and
            hashlib.sha256(url.encode()).hexdigest()+'.txt' in cache_files]
    # Separate extraction state: never overwrite the live downloader's queue, checkpoint or status.
    collector.STATE = root / '.cache' / f'enrichment-v{collector.PARSER_VERSION}'
    collector.STATE.mkdir(parents=True, exist_ok=True)
    lock = collector.STATE / 'run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        queue, fatal, batch = collector.collect(client, urls, args.limit,
            f'archive-enriched-v{collector.PARSER_VERSION}', publish_status=False)
        print(f'Cache-only extraction: {batch}; network requests=0', flush=True)
        return 1 if fatal else 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
