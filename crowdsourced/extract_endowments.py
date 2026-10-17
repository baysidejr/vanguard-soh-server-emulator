"""Cache-only Disciple endowment research; no ability joins or network access."""
import hashlib
import re
import collect_archive as c

URL = 'https://vgsoharchive.com/classes/disciple/endowments'


def parse_endowments(html):
    soup = c.BeautifulSoup(html, 'html.parser')
    tables = soup.select('main .guide-body table')
    if len(tables) != 1:
        raise ValueError('Expected one endowment table')
    result = []
    for row in tables[0].find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != 3 or cells[0].get_text(strip=True) or row.find('a'):
            raise ValueError('Unreviewed table layout or links')
        title = cells[1].find('strong', recursive=False)
        chain = cells[1].find_all('p', recursive=False)
        level = re.fullmatch(r'Level Possible\s*:\s*(\d+)', cells[2].get_text(' ', strip=True))
        if title is None or len(chain) != 1 or level is None:
            raise ValueError('Missing name, chain or level')
        chain_text = chain[0].get_text(' ', strip=True)
        if not chain_text.startswith('Chain:'):
            raise ValueError('Missing chain label')
        # Retain printed chain punctuation and effect prose without resolving names.
        title_text = title.get_text(' ', strip=True)
        chain[0].extract()
        title.extract()
        effect = cells[1].get_text(' ', strip=True)
        if not effect or not title_text.endswith(':') or not chain_text[6:].strip():
            raise ValueError('Empty observation')
        result.append(dict(name_recorded=title_text[:-1], effect_text=effect,
            chain_text=chain_text[6:].strip(), level_possible_recorded=int(level[1]),
            canonical_client_id=None, source_era=None))
    if not result or len({r['name_recorded'] for r in result}) != len(result):
        raise ValueError('Empty or colliding observations')
    return result


def main():
    import json
    from validate import validate
    path = c.HERE/'.cache/archive'/(hashlib.sha256(URL.encode()).hexdigest()+'.txt')
    body = path.read_bytes()
    meta = json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(body).hexdigest()
    normalized_digest = hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    if meta['url'] != URL or meta['sha256'] != normalized_digest:
        raise ValueError('Cache evidence mismatch')
    rows = parse_endowments(body.decode('utf-8'))
    folder = c.HERE/'raw/2026-10-17-iteration158-disciple-endowments'
    folder.mkdir(exist_ok=False)
    c.write_json(folder/'source_pages.json', [dict(name='Disciple — Endowments',
        record_kind='source_page', url=URL, fields={}, headings=[], referenced_entities=[],
        extraction_status='extracted_research_observations', metadata_only=False,
        endowment_observations=rows, conversion_ready=False,
        provenance_group='telon-project-mirror')])
    c.write_json(folder/'EVIDENCE.json', dict(source_url=URL, sha256=digest,
        cache_path=path.relative_to(c.HERE).as_posix(), response_metadata=meta, normalized_text_sha256=normalized_digest,
        cache_newline_note='Windows cache CRLF normalized to LF reproduces response metadata hash',
        original_url='http://thetelonproject.wikidot.com/disciple-endowments',
        network_requests=0, observations=len(rows)))
    (folder/'gaps.jsonl').write_text(json.dumps(dict(type='class', name='Disciple endowments', searched=[URL], notes='Printed levels are Level Possible, not inferred training requirements. Chain names are not joined to abilities. Canonical IDs and historical era unknown.'))+'\n', encoding='utf-8')
    (folder/'REPORT.md').write_text('# Cached Disciple endowment observations\n\nThree printed effects, chains and Level Possible values retained as research. No inferred ability IDs, chain activation rules or historical era. Telon Project mirrors are one provenance group. Earlier batches remain immutable.\n\nShaman patron cache inspection found three plain endowment labels with no detail links; no Shaman mechanics are inferred from this separate Disciple page.\n\nSuspension remains preserved following automatic approval rejection `blocked by policy`; no network request, suspension reset or restart occurred. Checkpoints remain 26,918 completed archive pages, 77,954 pending, 50 alternate articles and 60-second interval. Next: inspect cached Disciple forms for explicit stance mechanics.\n', encoding='utf-8')
    _, issues = validate(folder)
    c.write_json(folder/'VALIDATION.json', dict(issues=issues, endowment_observations=len(rows)))
    print(folder, len(rows), issues)


if __name__ == '__main__':
    main()
