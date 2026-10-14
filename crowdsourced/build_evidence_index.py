"""Index immutable research records by name and explicit zone without merging their facts."""
from collections import Counter, defaultdict
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def normalized(name):
    return ' '.join(name.casefold().split())


def build(root=HERE):
    root = Path(root)
    records, names, zones, batches, errors = [], defaultdict(list), defaultdict(list), [], []
    kinds=defaultdict(list)
    for folder in sorted((root / 'raw').iterdir()):
        if not folder.is_dir() or not (folder / 'REPORT.md').is_file():
            continue
        counts = Counter()
        for path in sorted(folder.glob('*.jsonl')):
            if path.name == 'gaps.jsonl':
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if not isinstance(r, dict) or not isinstance(r.get('name'), str) or not isinstance(r.get('type'), str):
                        raise ValueError('missing record identity')
                except ValueError as error:
                    errors.append(dict(file=str(path.relative_to(root)), line=number, issue=str(error)))
                    continue
                identity = len(records)
                source_urls = [s.get('url') for s in r.get('sources', []) if isinstance(s, dict)]
                observed_zones = list(dict.fromkeys(
                    ([r['name']] if r['type'] == 'zone' else []) +
                    ([r['zone']] if isinstance(r.get('zone'), str) else []) +
                    [z for z in r.get('zones_recorded', []) if isinstance(z, str)]))
                entry = dict(id=identity, type=r['type'], name=r['name'], file=str(path.relative_to(root)),
                             line=number, confidence=r.get('confidence'), parser_version=r.get('parser_version'),
                             source_urls=source_urls, zones=observed_zones)
                for field in ('class', 'level', 'level_learned', 'rank', 'ability_ref_url', 'record_kind'):
                    if r.get(field) is not None:
                        entry[field] = r[field]
                records.append(entry)
                names[r['type'] + ':' + normalized(r['name'])].append(identity)
                kinds[r.get('record_kind') or r['type']].append(identity)
                for zone in observed_zones:
                    zones[zone].append(identity)
                counts[r['type']] += 1
        batches.append(dict(batch=str(folder.relative_to(root)), records=sum(counts.values()), counts=dict(counts)))
    summary = dict(batches=len(batches), research_rows=len(records), normalized_name_groups=len(names),
                   zones_with_explicit_records=len(zones), counts=dict(Counter(r['type'] for r in records)),
                   errors=len(errors), note='Rows and name groups are not counts of distinct game entities. Sources and conflicting versions remain separate.')
    return dict(summary=summary, batches=batches, records=records, by_name=dict(names), by_kind=dict(kinds), by_zone=dict(zones), errors=errors)


def publish(root=HERE):
    root=Path(root)
    data = build(root)
    destination = root / 'reviewed' / 'EVIDENCE_INDEX.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    import os
    temporary = destination.with_suffix(f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(destination)
    return data


def main():
    data=publish()
    print(json.dumps(data['summary'],sort_keys=True))
    return 1 if data['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
