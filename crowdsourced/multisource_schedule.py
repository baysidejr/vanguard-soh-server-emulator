"""One alternate article per archive batch, using the existing collector owner."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

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
    url = state['pending'][0]
    article, links = parse_wiki(url, client.get(url))
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
    save(state_path, {'pending': pending, 'done': sorted(done)})
    print(f'ALTERNATE BATCH {batch}: 1 article, {len(pending)} pending', flush=True)
    return batch
