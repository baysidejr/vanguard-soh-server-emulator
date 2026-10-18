"""Conservative wiki observations; no canonical IDs or name-only joins."""
from discover_multisource import BeautifulSoup, wiki_links


def parse_wiki(url, html):
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#mw-content-text')
    heading = soup.select_one('#firstHeading')
    if content is None or heading is None:
        raise ValueError('Missing wiki article content or title')
    observations = []
    # Preserve omitted article regions for review without promoting prose or
    # navigation tables to game facts. Outermost tables retain nested cells once.
    review_evidence = []
    for element in content.find_all(['table', 'p', 'li']):
        if element.find_parent('table') is not None:
            continue
        if element.name == 'table' and 'infobox' in element.get('class', []):
            continue
        if element.name == 'li' and element.find_parent('li') is not None:
            continue
        if element.name == 'p' and element.find_parent('li') is not None:
            continue
        text = element.get_text(' ', strip=True)
        if not text:
            continue
        review_evidence.append({'kind': 'table' if element.name == 'table' else 'prose',
                                'text': text, 'source_html': str(element),
                                'source_url': url, 'game_fact': False})
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
            'unreviewed_article_evidence': review_evidence,
            'classification': 'labelled observations' if observations else 'metadata only',
            'gaps': ['Historical era and game entity identity require review.',
                     'Article prose and other tables have not been fully extracted.']}, wiki_links(html, url)
