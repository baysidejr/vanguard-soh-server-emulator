"""Build reviewable conversion proposals from all closed raw batches; never import."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import convert as converter

HERE = Path(__file__).resolve().parent
FILES = ('items.json', 'mobs.json', 'quests.json', 'loot.json', 'merchants.json')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def select_records(root):
    """Supersede replays only for identical type, exact name and complete source URL set.

    Highest parser version, then collection timestamp, then batch name wins.
    Different source sets stay separate, so Batch withholds same-name ambiguity.
    Equal-rank conflicting bodies are withheld, never arbitrarily selected.
    """
    groups, errors, files = {}, [], []
    rows = 0
    for batch in sorted((root / 'raw').iterdir()):
        if not batch.is_dir() or not (batch / 'REPORT.md').exists():
            continue
        # Network batches are closed only once their validation report exists.
        if (batch / 'manifest.json').exists() and not (batch / 'VALIDATION.json').exists():
            continue
        for path in sorted(batch.glob('*.jsonl')):
            if path.stem not in converter.RECORD_TYPES:
                continue
            body = path.read_bytes()
            files.append({'path': path.relative_to(root).as_posix(),
                          'sha256': hashlib.sha256(body).hexdigest()})
            for line_number, line in enumerate(body.decode('utf-8').splitlines(), 1):
                if not line.strip():
                    continue
                rows += 1
                ref = {'file': path.relative_to(root).as_posix(), 'line': line_number}
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError('record is not an object')
                    urls = tuple(sorted(set(s['url'] for s in record.get('sources', [])
                                            if isinstance(s, dict) and isinstance(s.get('url'), str))))
                    if (not urls or record.get('type') not in converter.RECORD_TYPES
                            or not isinstance(record.get('name'), str) or not record['name'].strip()):
                        raise ValueError('missing source URLs, type or name')
                    identity = (record['type'], record['name'], urls)
                    version = record.get('parser_version', 0)
                    version = version if type(version) is int else 0
                    rank = (version, str(record.get('collected_at') or ''), batch.name)
                    groups.setdefault(identity, []).append((rank, record, ref))
                except (ValueError, TypeError, KeyError) as error:
                    errors.append({**ref, 'reason': str(error)})
    selected, ledger = [], []
    for identity, entries in sorted(groups.items()):
        best = max(entry[0] for entry in entries)
        winners = [entry for entry in entries if entry[0] == best]
        bodies = {json.dumps(entry[1], sort_keys=True, ensure_ascii=False) for entry in winners}
        if len(bodies) != 1:
            errors.append({'type': identity[0], 'name': identity[1],
                           'reason': 'equal-rank conflicting source transcriptions; all withheld',
                           'locations': [entry[2] for entry in entries]})
            continue
        selected.append(winners[0][1])
        ledger.append({'type': identity[0], 'name': identity[1], 'source_urls': identity[2],
                       'selected': winners[0][2], 'selection_rank': best,
                       'superseded_or_duplicate_locations': [e[2] for e in entries if e is not winners[0]]})
    return selected, ledger, errors, files, rows


def output_identity(record):
    kind, name = record['type'], record['name']
    if kind == 'item':
        return 'items.json', name
    if kind in ('npc', 'creature'):
        return 'mobs.json', converter.key(name)
    if kind == 'quest':
        return 'quests.json', converter.slug(name)
    if kind == 'loot':
        return 'loot.json', converter.slug(record.get('source') or name)
    if kind == 'merchant':
        return 'merchants.json', converter.slug(record.get('npc') or name)
    return None


def build(root=HERE):
    root = Path(root)
    records, ledger, selection_errors, inputs, rows = select_records(root)
    destination = root / 'reviewed/conversion-handoff'
    scratch = root / '.cache/conversion-handoff-input'
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / 'records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n'
                                                for r in records), encoding='utf-8')
    batch = converter.Batch(str(scratch))
    proposals = converter.convert(batch, converter.creature_races())
    references = converter.reference_issues(proposals)
    issues = list(dict.fromkeys(batch.issues + references))
    for name in FILES:
        save(destination / 'proposed' / name, proposals[name])
    save(destination / 'SELECTIONS.json', ledger)
    save(destination / 'INPUTS.json', inputs)
    save(destination / 'SELECTION_ERRORS.json', selection_errors)
    save(destination / 'ISSUES.json', issues)
    save(destination / 'UNRESOLVED_REFERENCES.json', references)
    accepted = {json.dumps(r, sort_keys=True, ensure_ascii=False)
                for values in batch.records.values() for r in values}
    def index_issues(values):
        indexed = {}
        for value in values:
            # Index every separator so names containing colons remain exact.
            for match in re.finditer(': ', value):
                indexed.setdefault(value[:match.start()], []).append(value)
        return indexed
    issue_index, reference_index = index_issues(issues), index_issues(references)
    disposition = []
    for r, provenance in zip(records, ledger):
        identity = output_identity(r)
        exported = (json.dumps(r, sort_keys=True, ensure_ascii=False) in accepted and identity is not None
                    and identity[1] in proposals[identity[0]])
        relevant = list(issue_index.get(f"{r['type']} {r['name']}", []))
        if r['type'] in ('npc', 'creature'):
            relevant += reference_index.get(f"mob {converter.key(r['name'])}", [])
        elif identity:
            owner = {'quests.json': 'quest', 'merchants.json': 'merchant', 'loot.json': 'loot'}.get(identity[0])
            if owner:
                relevant += reference_index.get(f'{owner} {identity[1]}', [])
        disposition.append({**provenance, 'status': 'proposal_requires_review' if exported else 'withheld',
                            'output': list(identity) if exported else None,
                            'reasons': list(dict.fromkeys(relevant)) or
                              (['Excluded by validation/confidence/identity checks; see ISSUES.json']
                               if not exported and r['type'] in ('npc', 'creature', 'item', 'quest', 'loot', 'merchant')
                               else ['No automatic converter for this record type'] if not exported else []),
                            'confidence': r.get('confidence')})
    save(destination / 'DISPOSITION.json', disposition)
    counts = {name: len(proposals[name]) for name in FILES}
    assert sum(d['status'] == 'proposal_requires_review' for d in disposition) == sum(counts.values())
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'raw_rows_examined': rows, 'raw_files_examined': len(inputs),
              'selected_source_records': len(records), 'selected_types': dict(Counter(r['type'] for r in records)),
              'candidate_counts': counts, 'candidate_total': sum(counts.values()),
              'withheld_selected_records': sum(r['status'] == 'withheld' for r in disposition),
              'selection_error_groups': len(selection_errors), 'conversion_issues': len(issues),
              'unresolved_reference_issues': len(references), 'imported_by_this_tool': 0,
              'status': 'conversion proposals generated; integration and historical review required',
              'selection_rule': 'Same exact type/name/source-URL-set: highest parser version, collection timestamp, batch name. No field merging. Different sources remain separate; equal-rank conflicts withheld.',
              'limitations': ['No server files are modified. Proposals are merge candidates, not replacement files.',
                             'All candidates need review; unresolved references and _unsupported fields are not import-ready.',
                             'Item/loot icon 443 is an operational fallback, not a recovered historical icon.',
                             'Source observations not represented in server schema remain in referenced raw records.',
                             'Ability, recipe, diplomacy, spawn and other unsupported types are accounted for but withheld.',
                             'Live content was read only for mappings and reference checks; no integrated server test is claimed.']}
    save(destination / 'SUMMARY.json', report)
    (destination / 'HANDOFF.md').write_text(
        '# Conversion handoff\n\n'
        f"{report['candidate_total']} conversion candidates from {len(records)} selected source records "
        f"({rows} raw rows examined). Nothing imported.\n\n"
        + '\n'.join(f'- {name}: {count}' for name, count in counts.items())
        + '\n\nReview `proposed/` alongside `DISPOSITION.json`, `ISSUES.json`, '
          '`UNRESOLVED_REFERENCES.json` and the exact raw file/line pointers in `SELECTIONS.json`. '
          '`INPUTS.json` hashes the snapshot inputs. Withheld records retain their source pointers and reasons.\n\n'
          'Do not overwrite live content with these files. Merge reviewed entries individually. Resolve '
          'references, identity conflicts, unsupported mechanics, icon fallback and schema changes first; '
          'then run the receiving server validation and integration tests. No candidate is certified '
          'historically complete or import-ready merely because conversion succeeded.\n\n'
          'Rebuild from the repository root: `python -B crowdsourced/build_handoff.py`. '
          'No network access; only closed raw batches are read. Source replay selection never merges fields; '
          'distinct source sets remain separate and ambiguous identities are withheld.\n', encoding='utf-8')
    # Verify the actual files delivered, not just in-memory conversion counts.
    for name, count in counts.items():
        assert len(json.loads((destination / 'proposed' / name).read_text(encoding='utf-8'))) == count
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == '__main__':
    build()
