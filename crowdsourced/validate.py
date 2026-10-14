"""Read-only validation of a crowdsourced batch, including delivery files and gaps."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from convert import Batch, HERE


def canonical_archive_url(value):
    if not isinstance(value,str):
        return False
    parts=urlsplit(value)
    return parts.scheme=='https' and parts.netloc=='vgsoharchive.com' and not parts.query and not parts.fragment


def metadata_errors(record):
    if not isinstance(record,dict):
        return ['metadata entry must be an object']
    errors=[]
    if not isinstance(record.get('name'),str) or not record['name'].strip():
        errors.append('missing source-page name')
    if record.get('record_kind')!='source_page':
        errors.append('source-page record_kind must be source_page')
    if not canonical_archive_url(record.get('url')):
        errors.append('source-page URL must be canonical archive URL')
    fields=record.get('fields')
    if not isinstance(fields,dict) or any(not isinstance(k,str) or not isinstance(values,list)
            or any(not isinstance(v,str) or len(v.split())>25 for v in values) for k,values in fields.items()):
        errors.append('source-page fields must contain short string lists')
    headings=record.get('headings')
    if not isinstance(headings,list) or any(not isinstance(h,str) for h in headings):
        errors.append('source-page headings must be strings')
    references=record.get('referenced_entities')
    if not isinstance(references,list) or any(not canonical_archive_url(u) for u in references):
        errors.append('source-page references must be canonical archive URLs')
    sections=record.get('sections',[])
    if not isinstance(sections,list):
        errors.append('source-page sections must be a list')
    else:
        for section in sections:
            if not isinstance(section,dict) or not isinstance(section.get('heading'),str) or not isinstance(section.get('linked_entities'),list):
                errors.append('invalid source-page section')
                continue
            for entry in section['linked_entities']:
                if not isinstance(entry,dict) or not isinstance(entry.get('name'),str) or not canonical_archive_url(entry.get('url')):
                    errors.append('invalid source-page section link')
    return errors


def validate(folder):
    folder = Path(folder)
    batch = Batch(str(folder), include_low=True)
    issues = list(batch.validation_issues)
    metadata=folder/'source_pages.json'
    if metadata.is_file():
        try:
            rows=json.loads(metadata.read_text(encoding='utf-8'))
            if not isinstance(rows,list):
                issues.append('source_pages.json: metadata must be a list')
            else:
                for n,row in enumerate(rows,1):
                    issues.extend(f'source_pages.json:{n}: {error}' for error in metadata_errors(row))
        except ValueError as error:
            issues.append(f'source_pages.json: bad JSON ({error})')
    if not (folder / "REPORT.md").is_file():
        issues.append("missing REPORT.md")
    gaps = folder / "gaps.jsonl"
    if not gaps.is_file():
        issues.append("missing gaps.jsonl")
    else:
        for n, line in enumerate(gaps.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if (not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k].strip()
                        for k in ("type", "name", "notes"))
                        or not isinstance(r.get("searched"), list) or not r["searched"]
                        or not all(isinstance(s, str) and s.strip() for s in r["searched"])):
                    issues.append(f"gaps.jsonl:{n}: invalid gap record")
            except ValueError as e:
                issues.append(f"gaps.jsonl:{n}: bad JSON ({e})")
    return batch, issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    args = parser.parse_args(argv)
    folder = Path(args.batch)
    if not folder.is_absolute():
        folder = Path(HERE) / folder
    batch, issues = validate(folder)
    print(json.dumps({kind: len(records) for kind, records in batch.records.items()}, sort_keys=True))
    for issue in issues:
        print(f"ERROR: {issue}")
    print(f"{len(issues)} validation issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
