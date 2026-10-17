"""One alternate article per archive batch, using the existing collector owner."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

from discover_multisource import wiki_links
from multisource_client import MultiSourceClient
from multisource_extract import parse_wiki


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def step(root):
    """Publish before checkpointing; replay a published page after interruption safely.

    Failures leave the URL pending and propagate to the sole runner's recovery.
    No independent process, network entrypoint or archive checkpoint mutation.
    """
    root = Path(root)
    client = MultiSourceClient(root)
    client.check_owner()
    state_path = client.state / 'multisource_queue.json'
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
    else:
        pending = set()
        for meta_path in client.cache.glob('*.meta.json'):
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            if not meta['url'].startswith('https://vgoplayers.com/wiki/index.php/'):
                continue
            body = meta_path.with_name(meta_path.name.replace('.meta.json', '.html')).read_bytes()
            if hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise ValueError('Discovery cache integrity failure')
            pending.update(wiki_links(body.decode('utf-8'), meta['url']))
        state = {'pending': sorted(pending), 'done': []}
        save(state_path, state)
    if not state['pending']:
        return None
    if state.get('policy_review_required'):
        return None
    url = state['pending'][0]
    try:
        html = client.get(url)
    except HTTPError as error:
        robots_failure = error.url == 'https://' + urlsplit(url).netloc + '/robots.txt'
        if error.code not in (404, 410) or (error.url != url and not robots_failure):
            error.close()
            raise
        evidence = {'url': error.url, 'pending_article': url, 'http_status': error.code,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'classification': 'unavailable source; no extracted game facts',
                    'review_required': 'Review missing linked article; never treat as extracted coverage'}
        error.close()
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S-%f')
        batch = root / 'raw' / (stamp + '-alternate-unavailable')
        save(batch / 'manifest.json', evidence)
        if robots_failure:
            evidence['review_required'] = 'Robots retrieval failed; alternate network intake suspended pending policy review'
            state['policy_review_required'] = evidence
        else:
            state.setdefault('unavailable', []).append(evidence)
            state['pending'] = state['pending'][1:]
        save(batch / 'manifest.json', evidence)
        save(batch / 'queue.json', state['pending'])
        (batch / 'REPORT.md').write_text('Unavailable alternate source. No game facts extracted.\n' + evidence['review_required'] + '\n', encoding='utf-8')
        (batch / 'gaps.jsonl').write_text(json.dumps({'type': 'source', 'name': evidence['url'],
            'notes': evidence['review_required'], 'searched': [evidence['url']]}) + '\n', encoding='utf-8')
        save(state_path, state)
        print(f'ALTERNATE UNAVAILABLE {url}: HTTP {error.code}; evidence {batch}', flush=True)
        return batch
    article, links = parse_wiki(url, html)
    digest = hashlib.sha256(url.encode()).hexdigest()
    meta = json.loads((client.cache / (digest + '.meta.json')).read_text(encoding='utf-8'))
    article['response_evidence'] = meta
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S-%f')
    batch = root / 'raw' / (stamp + '-alternate-wiki')
    batch.mkdir(parents=True)
    (batch / 'wiki_observations.jsonl').write_text(json.dumps(article, ensure_ascii=False) + '\n', encoding='utf-8')
    done = set(state['done']) | {url}
    pending = sorted((set(state['pending'][1:]) | set(links)) - done)
    save(batch / 'manifest.json', {'source': 'vgoplayers-wiki', 'fetched_urls': [url],
         'response_evidence': meta, 'classification': article['classification'],
         'pending': len(pending), 'conversion_ready': False,
         'review_required': article['gaps']})
    save(batch / 'queue.json', pending)
    state.update({'pending': pending, 'done': sorted(done)})
    save(state_path, state)
    print(f'ALTERNATE BATCH {batch}: 1 article, {len(pending)} pending', flush=True)
    return batch
