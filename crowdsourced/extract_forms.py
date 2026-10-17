"""Cache-only Disciple stance research; no ability joins or network access."""
import hashlib
import re
import collect_archive as c

URL = 'https://vgsoharchive.com/classes/disciple/forms'


def parse_forms(html):
    soup = c.BeautifulSoup(html, 'html.parser')
    tables = soup.select('main .guide-body table')
    if len(tables) != 1:
        raise ValueError('Expected one stance table')
    intro = soup.select('main .guide-body p')
    if len(intro) != 1:
        raise ValueError('Expected explicit stance introduction')
    level = re.fullmatch(r'At level (\d+), the Disciple receives (\d+) combat stances\.', intro[0].get_text(' ', strip=True))
    if level is None:
        raise ValueError('Unreviewed level statement')
    result = []
    for row in tables[0].find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != 2 or cells[0].get_text(strip=True) or row.find('a'):
            raise ValueError('Unreviewed table layout or links')
        title = cells[1].find('strong', recursive=False)
        if title is None or len(cells[1].find_all('strong')) != 1:
            raise ValueError('Missing or ambiguous stance name')
        name = title.get_text(' ', strip=True)
        title.extract()
        effect = cells[1].get_text(' ', strip=True)
        if not name.endswith(':') or not effect:
            raise ValueError('Empty observation')
        result.append(dict(name_recorded=name[:-1], effect_text=effect,
            level_received_recorded=int(level[1]), canonical_client_id=None, source_era=None))
    if len(result) != int(level[2]) or len({r['name_recorded'] for r in result}) != len(result):
        raise ValueError('Count mismatch or colliding observations')
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
    rows = parse_forms(body.decode('utf-8'))
    folder = c.HERE/'raw/2026-10-17-iteration159-disciple-forms'
    folder.mkdir(exist_ok=False)
    c.write_json(folder/'source_pages.json', [dict(name='Disciple — Forms',
        record_kind='source_page', url=URL, fields={}, headings=[], referenced_entities=[],
        extraction_status='extracted_research_observations', metadata_only=False,
        stance_observations=rows, conversion_ready=False,
        provenance_group='telon-project-mirror')])
    c.write_json(folder/'EVIDENCE.json', dict(source_url=URL, sha256=digest,
        cache_path=path.relative_to(c.HERE).as_posix(), response_metadata=meta, normalized_text_sha256=normalized_digest,
        cache_newline_note='Windows cache CRLF normalized to LF reproduces response metadata hash',
        original_url='http://thetelonproject.wikidot.com/disciple-forms',
        network_requests=0, observations=len(rows)))
    (folder/'gaps.jsonl').write_text(json.dumps(dict(type='class', name='Disciple forms', searched=[URL], notes='Printed stance effects and received level only. Named abilities are not joined or assigned IDs; historical era unknown.'))+'\n', encoding='utf-8')
    (folder/'REPORT.md').write_text('# Cached Disciple stance observations\n\nTwo stance names, complete effect texts and the explicit level-10 introduction are preserved as research. Effect prose remains verbatim, including the printed regens1 typo. No inferred ability IDs or historical era. Telon Project mirrors are one provenance group. Earlier batches remain immutable.\n\nSuspension remains preserved following automatic approval rejection `blocked by policy`; resumption requires resolution and recorded policy disposition as documented in COLLECTION.md, then process/lock inspection and collection.ps1 Start. No network request, suspension reset or restart occurred. Checkpoints remain 26,918 completed archive pages, 77,954 pending, 50 alternate articles and 60-second interval. Next: inspect cached Disciple armor-set tables for explicit item associations.\n', encoding='utf-8')
    _, issues = validate(folder)
    c.write_json(folder/'VALIDATION.json', dict(issues=issues, stance_observations=len(rows)))
    print(folder, len(rows), issues)


if __name__ == '__main__':
    main()
