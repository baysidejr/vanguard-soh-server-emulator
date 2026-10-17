"""Offline Shaman patron observations; no typed entity joins or network fallback."""
import hashlib
import re
import collect_archive as collector

URL = 'https://vgsoharchive.com/classes/shaman/patrons'


def parse_patrons(html):
    soup = collector.BeautifulSoup(html, 'html.parser')
    guide = soup.select_one('main .guide-body')
    if guide is None:
        raise ValueError('Missing guide body')
    headings = guide.find_all('h4')
    if not headings:
        raise ValueError('No patron headings')
    observations = []
    for heading in headings:
        label = heading.get_text(' ', strip=True)
        match = re.fullmatch(r'([^()]+) \(([^()]+)\)', label)
        description = heading.find_next_sibling('p')
        endowments = description.find_next_sibling('ul') if description else None
        if not match or description is None or endowments is None:
            raise ValueError('Unexpected patron layout')
        # Do not cross a section boundary or silently ignore extra prose/links.
        siblings = []
        for node in heading.next_siblings:
            if getattr(node, 'name', None) == 'h4':
                break
            if getattr(node, 'name', None):
                siblings.append(node)
        if [n.name for n in siblings] != ['p', 'ul', 'hr'] or len(endowments.find_all('li')) != 1:
            raise ValueError('Unexpected patron section content')
        if any(n.find('a') for n in siblings):
            raise ValueError('Patron links require separate review')
        text = description.get_text(' ', strip=True)
        if not text:
            raise ValueError('Empty patron description')
        observations.append(dict(heading=label, name_recorded=match[1],
            totem_recorded=match[2], description_text=text,
            endowments_label=endowments.get_text(' ', strip=True),
            canonical_client_id=None, level_required=None, source_era=None))
    if len({o['name_recorded'] for o in observations}) != len(observations):
        raise ValueError('Duplicate patron names require collision review')
    return observations


def main():
    path = collector.HERE/'.cache/archive'/(hashlib.sha256(URL.encode()).hexdigest()+'.txt')
    body = path.read_bytes()
    observations = parse_patrons(body.decode('utf-8'))
    folder = collector.HERE/'raw/2026-10-17-iteration157-shaman-patrons'
    folder.mkdir(exist_ok=False)
    collector.write_json(folder/'source_pages.json', [dict(name='Shaman — Patrons',
        record_kind='source_page', url=URL, fields={},
        headings=[o['heading'] for o in observations], referenced_entities=[],
        extraction_status='extracted_research_observations', metadata_only=False,
        patron_observations=observations, conversion_ready=False,
        provenance_group='telon-project-mirror')])
    collector.write_json(folder/'EVIDENCE.json', dict(source_url=URL,
        cache_path=path.relative_to(collector.HERE).as_posix(), sha256=hashlib.sha256(body).hexdigest(),
        observations=len(observations), network_requests=0,
        original_url='http://thetelonproject.wikidot.com/shaman-patrons',
        attribution='The Telon Project'))
    import json
    (folder/'gaps.jsonl').write_text(json.dumps(dict(type='class', name='Shaman patrons',
        searched=[URL], notes='Patron descriptions only. Numeric mechanics, endowment details, levels, canonical IDs and historical era remain unresolved. No operative entities or name-only joins.'))+'\n', encoding='utf-8')
    (folder/'REPORT.md').write_text('# Cached Shaman patron observations\n\nThree named patron/totem descriptions and their printed endowment labels are extracted research observations, not metadata-only coverage or operative abilities. Exact prose is preserved without interpreting role descriptions as numeric bonuses. Canonical IDs, required levels and historical era remain null. Telon Project mirrors share one provenance group. Earlier immutable metadata evidence is preserved.\n\nNetwork suspension remains in effect after automatic approval rejection `blocked by policy`; no reset, restart or download occurred. Archive checkpoint: 26,918 completed and 77,954 pending. Alternate queue: 50 pending; persisted interval: 60 seconds. Next actionable batch: inspect cached Shaman endowment pages for explicit linked or tabular mechanics, retaining unknowns and source provenance.\n', encoding='utf-8')
    from validate import validate
    _, issues = validate(folder)
    collector.write_json(folder/'VALIDATION.json', dict(issues=issues, patron_observations=len(observations)))
    print(folder, len(observations), issues)


if __name__ == '__main__':
    main()
