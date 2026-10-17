"""Offline alternate-source discovery; never guesses quest detail endpoints."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / '.tools-current'))
from bs4 import BeautifulSoup


def item_search_form(html, base):
    """Preserve observed controls, including duplicate labels, without ID mapping."""
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.select_one('form#itemSearchForm')
    if form is None:
        raise ValueError('Missing item search form')
    action = urljoin(base, form.get('action', ''))
    p = urlsplit(action)
    if p.scheme != 'https' or p.netloc != 'vgoplayers.com' or p.path != '/items.php':
        raise ValueError('Unexpected item search endpoint')
    controls = []
    for control in form.select('input[name], select[name]'):
        row = {'name': control['name'], 'kind': control.name,
               'input_type': control.get('type', 'text') if control.name == 'input' else None,
               'default_value': control.get('value') if control.name == 'input' else None}
        if control.name == 'select':
            row['options'] = [{'source_value': option.get('value'),
                               'label': option.get_text(' ', strip=True)}
                              for option in control.select('option')]
        controls.append(row)
    return {'source_url': base, 'method': form.get('method', 'get').upper(),
            'action': action.split('#', 1)[0], 'controls': controls,
            'classification': 'Search interface metadata; not item facts',
            'canonical_id_mapping': None, 'source_era': None,
            'policy_status': 'Requires current per-host robots evaluation before submission'}


def wiki_links(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#mw-content-text')
    if content is None:
        raise ValueError('Missing wiki content region')
    urls = set()
    for link in content.select('a[href]'):
        url = urljoin(base, link['href'])
        p = urlsplit(url)
        if (p.scheme == 'https' and p.netloc == 'vgoplayers.com'
                and p.path.startswith('/wiki/index.php/') and not p.query
                and not p.fragment):
            title = p.path.split('/wiki/index.php/', 1)[1]
            if title and ':' not in title.replace('Category:', '', 1):
                urls.add(url)
    return sorted(urls - {base})


def audit(cache, inventory):
    rows = json.loads(Path(inventory).read_text(encoding='utf-8'))
    groups = {}
    for row in rows:
        groups.setdefault(row['name'].casefold(), []).append(row)
    collisions = [v for v in groups.values() if len(v) > 1]
    pending = set()
    evidence = []
    for meta in Path(cache).glob('*.meta.json'):
        m = json.loads(meta.read_text(encoding='utf-8'))
        body = meta.with_name(meta.name.replace('.meta.json', '.html')).read_bytes()
        if hashlib.sha256(body).hexdigest() != m['sha256']:
            raise ValueError('Cache digest mismatch: ' + str(meta))
        if '/wiki/index.php/' in m['url']:
            pending.update(wiki_links(body.decode('utf-8'), m['url']))
        evidence.append(m)
    return {'network_requests': 0, 'source_quest_rows': len(rows),
            'quest_detail_endpoint': None,
            'quest_detail_gap': 'Index contains plain ID/name text, no detail links. Do not synthesize endpoints or canonical IDs.',
            'name_collision_groups': collisions,
            'collision_policy': 'Full index records preserved; no name-only merging or conversion.',
            'pending_wiki_urls': sorted(pending), 'cache_evidence': evidence,
            'source_era': 'Mixed or unknown; modern emulator wiki observations require per-page era review.',
            'status': 'Discovery metadata only; typed game facts and network collection pending.'}


if __name__ == '__main__':
    print(json.dumps(audit(HERE / '.cache/multisource', HERE / 'raw/2026-10-17-133425-multisource-bootstrap/vgoplayers_quest_inventory.json'), ensure_ascii=False, indent=2))
