"""Offline extraction of the archive's labelled Bard instrument table."""
import hashlib
import json
from urllib.parse import urljoin
import collect_archive as collector

URL = 'https://vgsoharchive.com/classes/bard/instruments'


def parse_instruments(html):
    soup = collector.BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if main is None:
        raise ValueError('Missing main content')
    records = []
    for table in main.find_all('table'):
        labels = [h.get_text(' ', strip=True) for h in table.select('thead th')]
        if labels != ['Name', 'Mod', 'Level', 'Origin', 'Drops from / quest']:
            raise ValueError('Unexpected instrument table columns')
        category = table.find_previous(['h2', 'h3']).get_text(' ', strip=True)
        for ordinal, row in enumerate(table.select('tbody tr'), 1):
            cells = row.find_all('td', recursive=False)
            if len(cells) != 5:
                raise ValueError('Unexpected instrument row width')
            link = cells[0].find('a')
            badges = [b.get_text(' ', strip=True) for b in cells[0].select('.pill')]
            for badge in cells[0].select('.pill'):
                badge.decompose()
            values = [cell.get_text(' ', strip=True) for cell in cells]
            level = None if values[2] == '\u2014' else int(values[2])
            records.append(dict(type='item', name=values[0], confidence='medium',
                sources=[dict(url=URL, title='Bard — Instrument List', date=None)],
                notes='Single mirrored Telon Project table observation; incomplete source list. No name-only merge, canonical ID or historical era established. Level label is not assumed to mean required level.',
                level_required=None, canonical_client_id=None, source_era=None,
                provenance_group='telon-project-mirror', conversion_ready=False,
                instrument_observation=dict(category=category, modifier=float(values[1]),
                    level_label='Level', level_recorded=level,
                    origin=None if values[3]=='\u2014' else values[3],
                    drops_from_or_quest=None if values[4]=='\u2014' else values[4],
                    handedness_badges=badges,
                    linked_item_url=urljoin(URL,link['href']) if link else None,
                    table_row=ordinal)))
    if not records:
        raise ValueError('No instrument records')
    return records


def main():
    path=collector.HERE/'.cache/archive'/(hashlib.sha256(URL.encode()).hexdigest()+'.txt')
    body=path.read_bytes()
    records=parse_instruments(body.decode('utf-8'))
    folder=collector.HERE/'raw/2026-10-17-iteration155-bard-instruments'
    folder.mkdir(exist_ok=False)
    (folder/'item.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    (folder/'gaps.jsonl').write_text(json.dumps(dict(type='item',name='Bard instruments',searched=[URL],notes='Other supplemental pages remain metadata-only. Historical era, canonical IDs and unlabelled level semantics require review; no detail downloads or source joins performed.'))+'\n',encoding='utf-8')
    collector.write_json(folder/'EVIDENCE.json',dict(source_url=URL,cache_path=str(path.relative_to(collector.HERE)),sha256=hashlib.sha256(body).hexdigest(),records=len(records),network_requests=0,expected_source_total=84))
    (folder/'REPORT.md').write_text(f'# Bard instrument cache extraction\n\n{len(records)} item observations extracted offline from four labelled tables. Source declares 84 instruments and 74 linked items. Attribution: The Telon Project, mirrored by Vanguard Archive. Mirrors are one provenance group. Numeric Mod and Level observations are retained without converting Level to required level. Em-dash cells remain null; handedness badges are separate from names. No canonical IDs, item merges or historical dates inferred. Source is explicitly incomplete.\n\nNetwork suspension remains unchanged after automatic approval rejection `blocked by policy`; no collector restarted. Archive checkpoints: 26,918 completed, 77,954 pending; alternate queue: 50 pending; persisted interval: 60 seconds. Next: extract cached Shaman spirit-bond level/effect observations with historical provenance uncertainty.\n',encoding='utf-8')
    from validate import validate
    _, issues=validate(folder)
    collector.write_json(folder/'VALIDATION.json',dict(issues=issues))
    print(folder, len(records), issues)


if __name__=='__main__':
    main()
