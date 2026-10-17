"""Conservative wiki observations; no canonical IDs or name-only joins."""
from discover_multisource import BeautifulSoup, wiki_links


def parse_wiki(url, html):
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#mw-content-text')
    heading = soup.select_one('#firstHeading')
    if content is None or heading is None:
        raise ValueError('Missing wiki article content or title')
    observations = []
    for table in content.select('table.infobox'):
        for row in table.select('tr'):
            cells = row.find_all(['th', 'td'], recursive=False)
            if len(cells) != 2 or cells[0].name != 'th':
                continue
            label, value = (cell.get_text(' ', strip=True) for cell in cells)
            if label and value and len(label.split()) <= 8 and len(value.split()) <= 25:
                observations.append({'label': label, 'value': value,
                                     'source_url': url})
    return {'record_kind': 'wiki_article_observations',
            'name': heading.get_text(' ', strip=True), 'source_url': url,
            'canonical_client_id': None, 'source_era': None,
            'provenance_group': 'vgoplayers-wiki',
            'conversion_ready': False, 'observations': observations,
            'classification': 'labelled observations' if observations else 'metadata only',
            'gaps': ['Historical era and game entity identity require review.',
                     'Article prose and other tables have not been fully extracted.']}, wiki_links(html, url)
