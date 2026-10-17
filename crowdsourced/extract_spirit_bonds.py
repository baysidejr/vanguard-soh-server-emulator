"""Extract explicit Shaman table observations without network access or entity joins."""
import hashlib
import json
import collect_archive as collector

URL = 'https://vgsoharchive.com/classes/shaman/spirit-bonds'


def parse_spirit_bonds(html):
    soup = collector.BeautifulSoup(html, 'html.parser')
    guide = soup.select_one('main .guide-body')
    if guide is None:
        raise ValueError('Missing guide body')
    tables = [t for t in guide.find_all('table')
              if [h.get_text(' ', strip=True) for h in t.find_all('th')] == ['Level', 'Name', 'Effect']
              and not t.find('table')]
    if len(tables) != 1:
        raise ValueError('Expected one leaf spirit bond table')
    records = []
    for row in tables[0].find_all('tr'):
        if row.find('th'):
            continue
        cells = row.find_all('td', recursive=False)
        if len(cells) != 4 or cells[1].get_text(strip=True) or cells[1].find(['a', 'img']):
            raise ValueError('Unexpected spirit bond row layout')
        level, _, name, effect = [c.get_text(' ', strip=True) for c in cells]
        if not name or not effect or (level != '??' and not level.isdecimal()):
            raise ValueError('Invalid spirit bond values')
        records.append(dict(type='ability', name=name, confidence='medium',
            sources=[dict(url=URL, title='Shaman — Spirit Bonds', date=None)],
            notes='Single Telon Project mirror observation. No name-only merge or historical era established. Level semantics remain unresolved.',
            canonical_client_id=None, source_era=None, level_required=None,
            provenance_group='telon-project-mirror', conversion_ready=False,
            spirit_bond_observation=dict(class_name='Shaman', table_row=len(records)+1,
                level_label='Level', level_text=level,
                level_recorded=None if level == '??' else int(level), effect_text=effect)))
    if not records:
        raise ValueError('Empty spirit bond table')
    return records


def main():
    path = collector.HERE/'.cache/archive'/(hashlib.sha256(URL.encode()).hexdigest()+'.txt')
    body = path.read_bytes()
    records = parse_spirit_bonds(body.decode('utf-8'))
    folder = collector.HERE/'raw/2026-10-17-iteration156-shaman-spirit-bonds'
    folder.mkdir(exist_ok=False)
    (folder/'ability.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
    (folder/'gaps.jsonl').write_text(json.dumps(dict(type='ability', name='Shaman spirit bonds', searched=[URL], notes='Historical era, canonical IDs, Level semantics and unquantified effect mechanics unresolved. Three source levels are explicitly unknown.'))+'\n', encoding='utf-8')
    collector.write_json(folder/'EVIDENCE.json', dict(source_url=URL,
        cache_path=path.relative_to(collector.HERE).as_posix(), sha256=hashlib.sha256(body).hexdigest(),
        records=len(records), network_requests=0, attribution='The Telon Project',
        original_url='http://thetelonproject.wikidot.com/shaman-spirit-bonds'))
    (folder/'REPORT.md').write_text('# Shaman spirit bond cache extraction\n\nTen explicit table observations; three unknown levels remain null. Exact effects retain printed percentages without inferring proc mechanics, duration or magnitude for unquantified effects. Level observations do not establish required level. Canonical IDs and historical era remain null. Telon Project mirrors are one provenance group; no name-only joins or conversion approval. Earlier metadata-only evidence is preserved.\n\nNetwork suspension remains preserved after automatic approval rejection `blocked by policy`; no restart or download occurred. Archive checkpoint: 26,918 completed, 77,954 pending. Alternate queue: 50 pending; persisted interval 60 seconds. Next actionable batch: inspect cached Shaman patrons for explicit patron observations and extraction gaps.\n', encoding='utf-8')
    from validate import validate
    _, issues = validate(folder)
    collector.write_json(folder/'VALIDATION.json', dict(issues=issues))
    print(folder, len(records), issues)


if __name__ == '__main__':
    main()
