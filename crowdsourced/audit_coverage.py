"""Read-only inventory/cache audit; publish research coverage under crowdsourced."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import collect_archive as collector


def route(url):
    parts=urlsplit(url).path.strip('/').split('/')
    return '/'+ '/'.join(parts[:2] if parts[:2] in (['crafting','recipes'],['diplomacy','cards']) else parts[:1])


def audit(root=collector.HERE):
    root=Path(root)
    inventory=json.loads((root/'.cache/collector/inventory.json').read_text(encoding='utf-8'))
    urls=list(dict.fromkeys(row['url'] for row in inventory))
    cached={p.name for p in (root/'.cache/archive').glob('*.txt')}
    published=set()
    published_with_issues=set()
    for manifest in (root/'raw').glob('*/manifest.json'):
        # A delivered batch must have a report and a successful structural validation.
        validation=manifest.parent/'VALIDATION.json'
        if not (manifest.parent/'REPORT.md').is_file() or not validation.is_file():
            continue
        check=json.loads(validation.read_text(encoding='utf-8'))
        data=json.loads(manifest.read_text(encoding='utf-8'))
        if check.get('issues') == [] and check.get('count') == 0:
            published.update(data.get('fetched_urls',[]))
        else:
            published_with_issues.update(data.get('fetched_urls',[]))
    counts=Counter()
    groups={}
    unsupported=[]
    for url in urls:
        supported=collector.detail_url(url)
        status=('published' if url in published else 'published_with_issues' if url in published_with_issues
                else 'cached_only' if hashlib.sha256(url.encode()).hexdigest()+'.txt' in cached else 'not_downloaded')
        group=groups.setdefault(route(url),Counter())
        group['inventory']+=1
        group[status]+=1
        group['supported' if supported else 'unsupported']+=1
        if collector.source_only_url(url):
            group['source_only']+=1
            counts['source_only']+=1
        counts[status]+=1
        counts['supported' if supported else 'unsupported']+=1
        if not supported:
            unsupported.append(dict(url=url,route=route(url),status=status))
    return dict(parser_version=collector.PARSER_VERSION,inventory_urls=len(urls),counts=dict(counts),
        routes={name:dict(values) for name,values in sorted(groups.items())},
        unsupported=unsupported,published_off_sitemap=sorted(published-set(urls)),
        notes='Published means a delivered extraction batch with zero validation issues reviewed the URL, not complete game mechanics. Published_with_issues means delivered research exists but its batch has unresolved validation issues; it is not validated coverage. A zero-issue batch takes precedence when both exist. Cached_only means no delivered batch with a validation report reviewed the URL. Unsupported includes index/navigation pages and unimplemented routes. Cache presence alone is not extraction completion.')


def main():
    data=audit()
    collector.write_json(collector.HERE/'reviewed/COVERAGE_AUDIT.json',data)
    print(json.dumps({k:v for k,v in data.items() if k in ('parser_version','inventory_urls','counts','routes')},indent=2))


if __name__=='__main__':
    main()
