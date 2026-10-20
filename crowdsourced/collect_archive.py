"""Inventory canonical archive pages and collect explicit facts into immutable batches.

The collector never requests query URLs, follows external domains, or modifies server content.
Run with -B. Install requirements into crowdsourced/.tools-current before use.
"""
import argparse
import errno
from collections import Counter, deque
from datetime import datetime, timezone
from http.client import RemoteDisconnected
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / ".tools-current" if (HERE / ".tools-current").is_dir() else HERE / ".tools"))
from bs4 import BeautifulSoup
from archive_client import ArchiveClient, ORIGIN
from convert import record_errors
from archive_extract import enrich_record, role_services, class_abilities, class_trainers

STATE = HERE / ".cache" / "collector"
PARSER_VERSION = 100
CANONICAL_ROOT_PATHS = frozenset(('/', '/items', '/quests', '/mobs', '/zones',
    '/classes', '/races', '/abilities', '/effects', '/stats', '/skills', '/gameplay',
    '/diplomacy', '/diplomacy/cards', '/crafting', '/harvesting', '/crafting/recipes',
    '/lore', '/world', '/mounts', '/walkthroughs', '/angry-goblins',
    '/ten-ton-hammer', '/vgoemulator'))
SUPPLEMENTAL = ('world','guides','lore','ten-ton-hammer','walkthroughs','angry-goblins','races','harvesting','mounts','vgoemulator','crafting','diplomacy')
SUPPORTED = ("/zones/", "/quests/", "/mobs/", "/items/", "/abilities/", "/crafting/recipes/", "/diplomacy/cards/", "/classes/", "/effects/")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_url(url):
    p = urlsplit(url)
    return p.scheme == "https" and p.netloc == "vgsoharchive.com" and not p.query and not p.fragment


def detail_url(url):
    if not safe_url(url):
        return False
    path = urlsplit(url).path
    if source_only_url(url):
        return True
    if path.startswith(('/crafting/recipes/', '/diplomacy/cards/')):
        return len(path.strip('/').split('/')) == 3
    if path.startswith('/classes/'):
        parts=path.strip('/').split('/')
        return len(parts)==2 or (len(parts)==3 and parts[-1]=='trainers')
    return (path.startswith(SUPPORTED[:5] + ('/effects/',)) and len(path.strip('/').split('/')) == 2
            and path != '/quests/events')


def source_only_url(url):
    if not safe_url(url):
        return False
    # Canonical sitemap landing pages remain research until typed extraction is
    # reviewed. Do not turn index headings into synthetic game entities.
    if urlsplit(url).path in CANONICAL_ROOT_PATHS:
        return True
    parts=urlsplit(url).path.strip('/').split('/')
    if parts in (['abilities','as-it-was'],['abilities','not-in-the-emulator']):
        return True
    # Nested reference pages are research sources, not standalone class/quest
    # records. Preserve their metadata and links until fact extraction exists.
    if len(parts)==3 and parts[:2]==['crafting','enhancements']:
        return True
    if len(parts)==3 and parts[0]=='classes' and parts[-1]!='trainers':
        return True
    if parts==['quests','events'] or (len(parts)==3 and parts[:2]==['quests','events']):
        return True
    return len(parts)==2 and parts[0] in SUPPLEMENTAL and parts[1] not in ('recipes','cards')


def source_metadata(main,url):
    body=main.select_one('.guide-body') or main
    heading_tags=['h2','h3','h4','h5','h6']
    # Mirrored class references credit their original source above guide-body.
    # Only explicit attribution paragraphs qualify; side navigation is excluded.
    attribution=[node for node in main.find_all('p')
                 if node.find_parent(class_='guide-nav') is None
                 and re.match(r'^(?:mirrored from\b|sourced from\b|source:)',plain(node),re.I)]
    sections=[]
    for heading in body.find_all(heading_tags):
        entities=[]
        for node in heading.next_siblings:
            if getattr(node,'name',None) in heading_tags:
                break
            if not hasattr(node,'find_all'):
                continue
            for link in node.find_all('a',href=True):
                absolute=urljoin(ORIGIN,link['href'])
                if detail_url(absolute):
                    candidate=dict(name=plain(link),url=absolute)
                    if candidate not in entities:
                        entities.append(candidate)
        sections.append(dict(heading=plain(heading),linked_entities=entities))
    return dict(name=plain(main.find('h1')),url=url,record_kind='source_page',
        fields={key:[value for value in values if len(value.split())<=25] for key,values in kv(body).items()},
        headings=[plain(h) for h in body.find_all(heading_tags)],sections=sections,
        referenced_entities=detail_links(body),
        original_source_urls=unique(a['href'] for scope in [body]+attribution for a in scope.find_all('a',href=True)
            if a['href'].startswith(('https://','http://')) and not a['href'].startswith(ORIGIN)),
        source_date=None,parsed_at=timestamp())


def unique(values):
    return list(dict.fromkeys(values))


def cached_trainer_urls(client,indexes):
    """Discover published trainer links from downloaded class pages, even off-sitemap."""
    cache=getattr(client,'cache',None)
    if cache is None:
        return []
    result=[]
    for url in indexes:
        if len(urlsplit(url).path.strip('/').split('/'))!=2:
            continue
        path=Path(cache)/(hashlib.sha256(url.encode()).hexdigest()+'.txt')
        if not path.is_file():
            continue
        main=BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser').find('main')
        if main:
            result.extend(u for u in detail_links(main) if urlsplit(u).path.endswith('/trainers'))
    return unique(result)


def plain(node):
    return node.get_text(" ", strip=True) if node else ""


def number(text):
    text = text.strip().replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None
    return float(text) if "." in text else int(text)


def kv(main):
    out = {}
    for dl in main.select("dl.kv, dl.facts"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                out.setdefault(plain(dt).lower(), []).append(plain(dd))
    for row in main.select("table.detail tr"):
        th, td = row.find("th"), row.find("td")
        if th and td:
            out.setdefault(plain(th).lower(), []).append(plain(td))
    return out


def section(main, heading):
    """Only siblings up to the next heading, never silently include another section."""
    for h in main.find_all(["h2", "h3"]):
        if re.sub(r"\s+", " ", plain(h)).lower().split(" (")[0] == heading.lower():
            result = []
            for node in h.next_siblings:
                if getattr(node, "name", None) in ("h1", "h2", "h3"):
                    break
                if getattr(node, "name", None):
                    result.append(node)
            return result
    return []


def section_links(main, heading, prefix):
    return unique(plain(a) for node in section(main, heading)
                  for a in node.find_all("a", href=True) if a["href"].startswith(prefix))


def detail_links(main):
    return unique(urljoin(ORIGIN, a["href"]) for a in main.find_all("a", href=True)
                  if a["href"].startswith(SUPPORTED) and detail_url(urljoin(ORIGIN, a["href"])))


def explicit_money(text):
    """Only explicit coin denominations; an unlabelled numeric coin field is unknown."""
    text = text.strip().lower().replace(",", "")
    if re.fullmatch(r"\d+c", text):
        return int(text[:-1])
    matches = re.findall(r"(\d+)\s*(platinum|gold|silver|copper)\b", text)
    if not matches:
        return None
    remainder = re.sub(r"\d+\s*(?:platinum|gold|silver|copper)\b", "", text).strip(" ,")
    if remainder:
        return None
    units = {"copper": 1, "silver": 100, "gold": 10000, "platinum": 1000000}
    return sum(int(n) * units[unit] for n, unit in matches)


def parse_page(url, html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if main is None or main.find("h1") is None:
        raise ValueError("Expected main and entity h1 missing; parser drift")
    name = plain(main.find("h1"))
    if not name:
        raise ValueError("Empty entity name")
    path = urlsplit(url).path
    data = kv(main)
    get = lambda k: data.get(k, [None])[0]
    notes = ["Single archive transcription; historical patch and page date unknown. Unrecorded values remain null."]
    conflict = main.find(string=re.compile(r"recorded disagreement|another source disagrees", re.I))
    if conflict:
        notes.append("Archive reports contradictions; alternatives require manual verification. Rebuilt tooltips are not game screenshots.")
    common = {"name": name, "sources": [{"url": url, "title": plain(soup.title) or name, "date": None}],
              "confidence": "low" if conflict else "medium", "notes": "",
              "parser_version": PARSER_VERSION,
              "collected_at": timestamp(), "archive_fields": data,
              "referenced_entities": unique_json([dict(name=plain(a), url=urljoin(ORIGIN, a['href']))
                  for a in main.find_all('a', href=True) if a['href'].startswith(SUPPORTED)
                  and detail_url(urljoin(ORIGIN, a['href']))])}
    conflicts = []
    for table in main.find_all('table'):
        headers = [plain(h).lower() for h in table.find_all('th')]
        if headers[:3] == ['field', 'here', 'there']:
            for row in table.find_all('tr'):
                cells = row.find_all('td', recursive=False)
                if len(cells) >= 3:
                    conflicts.append(dict(field=plain(cells[0]), here=plain(cells[1]), there=plain(cells[2]),
                        source_urls=[a['href'] for a in cells[-1].find_all('a', href=True)] if len(cells) > 3 else []))
    if conflicts:
        common['archive_conflicts'] = conflicts
        common['confidence'] = 'low'
        notes.append('Conflicting recorded facts: ' + json.dumps(conflicts, ensure_ascii=False))
    if source_only_url(url):
        return [], detail_links(main.select_one('.guide-body') or main)
    if path.startswith('/classes/'):
        records = class_trainers(main,common) if path.endswith('/trainers') else class_abilities(main, name, common)
        for r in records:
            errors = record_errors(r)
            if errors:
                raise ValueError(f'Class-table record failed validation: {errors}')
        # Early ranks first when this page is used for local discovery.
        levels = {r['ability_ref_url']: r['level_learned'] for r in records if r.get('ability_ref_url')}
        return records, sorted(detail_links(main), key=lambda u: (levels.get(u, 10000), u))
    records = []
    head = main.select_one(".detail-head")
    level_match = re.search(r"\bLevel\s+(\d+)\b", plain(head.find('p') if head else None))
    level = int(level_match.group(1)) if level_match else None
    zones = section_links(main, "Where they stood", "/zones/")
    canonical_zones = unique(plain(a) for a in head.find_all("a", href=True) if a["href"].startswith("/zones/")) if head else []
    if path.startswith("/zones/"):
        record = dict(common, type="zone", continent=get("continent"), chunks=None,
                      level_range=None, cities_and_outposts=None, riftways=None, bind_spots=[])
        band = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", get("mob levels") or "")
        if band:
            record["level_range"] = [int(band.group(1)), int(band.group(2))]
        places = []
        for table in main.find_all("table"):
            headers = [plain(h) for h in table.find_all("th")]
            if "Place" not in headers or "Coordinates" not in headers:
                continue
            for row in table.select("tbody tr"):
                cells = row.find_all("td", recursive=False)
                if len(cells) < 5:
                    continue
                place, coords = plain(cells[1]), plain(cells[2])
                location = dict(raw=coords, format="source map point; axis order and spawn precision unspecified", chunk=name) if coords else None
                places.append(dict(name=place, location=location,
                    entities=[plain(a) for a in cells[3].find_all("a")],
                    quests=[plain(a) for a in cells[4].find_all("a")]))
                if place.lower() == "bindstone" and location:
                    record["bind_spots"].append(location)
        record["map_places"] = places
        notes.append("Map points are not exact entity spawns. Mob level band is not a player requirement. Adjacent-zone links are discovery hints, not zone contents.")
    elif path.startswith("/items/"):
        types = {"jewelry": "jewelry", "medium armor": "armor", "heavy armor": "armor", "light armor": "armor",
                 "armor": "armor", "weapon": "weapon", "shield": "shield", "container": "container",
                 "food": "food", "drink": "drink", "quest item": "quest", "misc": "misc",
                 "quest": "quest", "quest — miscellaneous": "quest", "weapon — greataxe": "weapon",
                 "cloak armor": "armor", "crafting tool": "tool", "crafting material": "resource"}
        slots = {"head":"head", "chest":"chest", "legs":"legs", "hands":"hands", "feet":"feet",
                 "waist":"waist", "cloak":"cloak", "shoulders":"shoulders", "wrists":"wrists",
                 "neck":"neck", "earleft":"ear", "earright":"ear", "fingerleft":"finger",
                 "fingerright":"finger", "heldprimary":"primary", "heldsecondary":"secondary",
                 "twohands":"two-hand", "ranged":"ranged", "ammo":"ammo", "container":"bag"}
        record = dict(common, type="item", item_type=types.get((get("type") or "").lower()),
                      slot=slots.get((get("slot") or "").lower()), rarity=None, level_required=None,
                      armor=number(get("armor class") or ""), stats={}, class_restrictions=None,
                      race_restrictions=None, bind=None, value_copper=None, item_level=number(get("item level") or ""))
        item_heading = BeautifulSoup(str(main.find('h1')), 'html.parser').find('h1')
        name_labels = [plain(label) for label in item_heading.select('.tag-crafted, .tag-tool, .tag-material')]
        if name_labels:
            for label in item_heading.select('.tag-crafted, .tag-tool, .tag-material'):
                label.decompose()
            record['archive_display_name'] = name
            record['archive_name_labels'] = name_labels
            record['name'] = plain(item_heading)
            notes.append('Item display tags retained separately from the item name.')
        category, separator, subtype = (get('type') or '').partition(' — ')
        if separator and category.lower() == 'weapon' and subtype.strip():
            record['item_type'] = 'weapon'
            record['weapon_type_recorded'] = subtype.strip()
        rarity = (get("rarity") or "").lower()
        if rarity in ("mundane", "common", "uncommon", "rare", "heroic", "fabled", "legendary"):
            record["rarity"] = rarity
        requires = re.fullmatch(r"level (\d+) Adventuring", get("requires") or "", re.I)
        if requires:
            record["level_required"] = int(requires.group(1))
        classes = section_links(main, "Usable by", "/classes/")
        record["class_restrictions"] = classes or None
        stat_rows = []
        for node in section(main, "Stats"):
            for li in node.find_all("li"):
                a, code = li.find("a"), li.find("span", title="Game enum code")
                value_node = li.find("span", class_="muted")
                value = number(plain(value_node))
                if a and value is not None:
                    stat_name = plain(code).lower() if code and plain(code) else re.sub(r"\W+", "_", plain(a).lower()).strip("_")
                    if stat_name in record["stats"]:
                        notes.append(f"Duplicate stat {stat_name} not summed; manual review required.")
                        record["confidence"] = "low"
                    else:
                        record["stats"][stat_name] = value
                    stat_rows.append(dict(name=plain(a), code=plain(code) or None, value=value))
        record["archive_stats"] = stat_rows
        for field, label in (("bag_slots", "capacity"), ("stack_size", "stack size")):
            record[field] = number(get(label) or "")
        if record["item_type"] is None or (get("slot") and record["slot"] is None):
            notes.append("Unmapped item type or slot retained in archive_fields; not guessed.")
        notes.append("Archive item levels are separate from required level. No price inferred from unlabelled numbers; source restrictions and effects need manual review.")
    elif path.startswith("/mobs/"):
        given = section_links(main, "Quests given", "/quests/")
        role = (get("role") or "").lower()
        npc = "npc" in role or bool(given) or bool(role_services(role))
        record = dict(common, type="npc" if npc else "creature", level=level, zone=get("zone"),
                      health=None, damage=None)
        race = get("race")
        if npc:
            record.update(race=race if race not in (None, "N/A", "Unknown") else None,
                          title=None, services=["quest giver"] if given else [], quests_given=given,
                          chunk=get("chunk"), location=None)
            if get("location"):
                record["location"] = dict(raw=get("location"), format="source coordinates; axis order unspecified", chunk=get("chunk") or get("zone"))
        else:
            if not role:
                record['confidence'] = 'low'
            record.update(creature_kind=None, difficulty=get("difficulty"), spawn_areas=[],
                          aggressive=None, aggro_range=None, respawn_time=None)
            notes.append("The archive groups NPCs, containers and creatures together; no explicit NPC role or quest-giver relationship was found. Entity kind/model requires review.")
        record["zones_recorded"] = unique(([get("zone")] if get("zone") else []) + zones)
        observations = []
        for node in section(main, "Loot"):
            for row in node.select("tbody tr"):
                cells = row.find_all("td", recursive=False)
                if len(cells) < 3:
                    continue
                a = cells[0].find("a", href=re.compile(r"^/items/"))
                rate = re.search(r"(\d+(?:\.\d+)?)\s*%", plain(cells[-1]))
                # Unlinked archive rows still carry observations. Read only the
                # leading name, excluding descriptive spans and tooltip fields.
                item_name = plain(a) if a else " ".join(
                    str(child).strip() for child in cells[0].children
                    if isinstance(child, str) and str(child).strip())
                if item_name:
                    observations.append(dict(item=item_name, chance=rate.group(0) if rate else None, quantity=None,
                                             observed_sample=plain(cells[-1]), url=urljoin(ORIGIN, a["href"]) if a else None))
        if observations:
            loot = dict(common, type="loot", source=name, drops=observations, confidence="low",
                        notes="Observed sample frequencies, not developer drop probabilities. Quantity ranges unknown. Not safe as a production loot table.")
            records.append(loot)
            record["loot_ref"] = name
        notes.append("Unknown models, health, combat values, respawns and precise spawns are not filled. An absent loot section does not mean no drops.")
    elif path.startswith("/quests/"):
        record = dict(common, type="quest", level=level, zone=get("starts in"), giver=get("starts with") or get("start"),
                      turn_in=get("finish"), prerequisites=None, steps=None, repeatable=None,
                      start_text=None, completion_text=None, description=None, summary=None,
                      rewards=dict(xp=None, coin_copper=None, items=None, choice=None))
        if record["zone"] is None and canonical_zones:
            record["zone"] = canonical_zones[0]
        record['repeatable'] = {'yes': True, 'no': False}.get((get('repeatable') or '').strip().lower())
        for field, label in (('chain_previous', 'previous'), ('chain_next', 'next')):
            value = get(label)
            if value and ('{{' in value or '}}' in value):
                notes.append(f'Unresolved {label} template retained in archive_fields; chain link unknown.')
                value = None
            record[field] = value
        record["rewards"]["coin_copper"] = explicit_money(get("coin reward") or "")
        notes.append("Unknown objective triggers and missing dialogue remain unresolved. Previous/next links are not enforced prerequisites. Partial counter matches are not a complete quest specification.")
    elif path.startswith("/abilities/"):
        class_link = head.find("a", href=re.compile(r"^/classes/")) if head else None
        record = dict(common, type="ability", **{"class": plain(class_link) or get("class"), "level_learned": number(get("level") or ""),
                      "rank": get("rank"), "category": get("type") or get("category"), "cost": None,
                      "cast_time_seconds": None, "refresh_seconds": None, "duration_seconds": None,
                      "range": None, "tooltip": None, "icon_name": get("icon"), "ranks": []})
        for node in section(main, "Ranks"):
            for row in node.select("tbody tr"):
                cells = row.find_all("td", recursive=False)
                if len(cells) >= 3:
                    rank, learned = plain(cells[0]), number(plain(cells[1]))
                    if re.fullmatch(r"[IVX]+", rank) and isinstance(learned, int):
                        record["ranks"].append(dict(rank=rank, level_learned=learned, cost_raw=plain(cells[2]) or None))
                    else:
                        record["confidence"] = "low"
                        notes.append("Malformed rank row withheld; rank table requires review.")
        notes.append("Only explicit numeric fields extracted. Tooltip, timing units, costs and per-rank damage/healing require review.")
    elif path.startswith('/effects/'):
        effect_heading=BeautifulSoup(str(main.find('h1')), 'html.parser').find('h1')
        pills=[plain(pill) for pill in effect_heading.select('.pill')]
        for pill in effect_heading.select('.pill'):
            pill.decompose()
        lead=main.select_one('p.lead')
        tooltip=plain(lead)
        record=dict(common,type='ability',name=plain(effect_heading),record_kind='item_effect',
                    category='item effect',activation_labels=pills,tooltip=tooltip if len(tooltip.split())<=25 else None,
                    effect_observations=None,items_recorded=section_links(main,'Items with this effect','/items/'),
                    cost=None,cast_time_seconds=None,refresh_seconds=None,duration_seconds=None,range=None)
        from archive_extract import effect_facts
        facts=effect_facts(tooltip)
        if facts:
            record['effect_observations']=[dict(scope='current',facts=facts)]
        notes.append('Item-effect record, not a trainable class ability. Activation labels and linked items are explicit; mechanics, triggers and timing remain unknown. Archive tooltip transcription claim is not independently verified.')
    elif path.startswith("/crafting/recipes/"):
        record = dict(common, type="recipe", craft=get("crafting class"), level=number(get("recipe level") or ""),
                      station=None, ingredients=None, tools=None, utilities=None, output=None,
                      steps=None, trainer=None, price_copper=None)
        notes.append("Only explicit recipe labels extracted. Template placeholders, products, ingredients and crafting actions require verification.")
        if "<" in (get("recipe level") or "") or name.lower().startswith("adding "):
            record["confidence"] = "low"
            notes.append("Page appears to be an unfilled documentation template; not a verified in-game recipe.")
    elif path.startswith("/diplomacy/cards/"):
        record = dict(common, type="diplomacy", kind="card", expression=None, cost=None,
                      gain=None, push=None, effects=None, level=None, how_obtained=None,
                      opponent_gain=None, influence_range=None, timer_turns=None)
        expression = (get("expression") or "").lower()
        record["expression"] = {"demand":"demand", "reason":"reason", "inspire":"inspire", "flattery":"flatter"}.get(expression)
        for label, field in (("cost", "cost"), ("to player", "gain"), ("to opponent", "opponent_gain")):
            for dt in main.find_all("dt"):
                if plain(dt).lower() == label:
                    dd = dt.find_next_sibling("dd")
                    values = {s.get("title", "").lower(): number(plain(s)) for s in dd.select("span[title]")} if dd else {}
                    if len(values) == 4 and all(v is not None for v in values.values()):
                        record[field] = values
        for label, field in (("influence", "influence_range"), ("timer", "timer_turns")):
            match = re.fullmatch(r"(\d+)-(\d+)(?: turns)?", get(label) or "")
            if match:
                record[field] = [int(match.group(1)), int(match.group(2))]
        notes.append("Expression pools retain their labelled values; influence range is not guessed as a single push. Acquisition and level unknown unless explicitly recorded.")
    else:
        raise ValueError(f"Unsupported detail route: {path}")
    notes.extend(enrich_record(record, main))
    record["notes"] = " ".join(notes)
    if record['type'] == 'npc' and 'merchant' in record.get('services', []):
        stock = []
        for node in section(main, 'Sells'):
            for a in node.find_all('a', href=True):
                item_url = urljoin(ORIGIN, a['href'])
                if (urlsplit(item_url).path.startswith('/items/') and
                        detail_url(item_url) and plain(a)):
                    sale = dict(item=plain(a), item_url=item_url, price_copper=None)
                    if sale not in stock:
                        stock.append(sale)
        merchant = dict(common, type='merchant', npc=name, zone=record.get('zone'), sells=None, buys=None,
                        notes='Merchant service explicitly recorded. Inventory and prices not found by the current extraction rules; null stock is not an empty in-game inventory.')
        if stock:
            merchant['sells'] = stock
            merchant['notes'] = ('Items explicitly linked in the Sells section; completeness, quantities and purchase prices unknown. '
                                 'Tooltip item values are not merchant prices. Unknown prices withhold conversion.')
        records.append(merchant)
    record["original_source_urls"] = unique(a["href"] for heading in ("Source", "Sources")
        for node in section(main, heading) for a in node.find_all('a', href=True)
        if a["href"].startswith(('http://', 'https://')) and not a["href"].startswith(ORIGIN))
    records.insert(0, record)
    links = detail_links(main)
    if path.startswith('/zones/'):
        # Adjacency does not establish ownership; finish the requested zone's linked entities first.
        links = [link for link in links if not urlsplit(link).path.startswith('/zones/')]
    for r in records:
        errors = record_errors(r)
        if errors:
            raise ValueError(f"Extracted record failed validation: {errors}")
    return records, links


def inventory(client, batch):
    batch.mkdir(parents=True, exist_ok=False)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    index_url = ORIGIN + "/sitemap.xml"
    index = ET.fromstring(client.get(index_url))
    sitemaps = unique(e.text for e in index.findall("s:sitemap/s:loc", ns))
    urls, errors = {}, []
    for sitemap in sitemaps:
        try:
            root = ET.fromstring(client.get(sitemap))
            for node in root.findall("s:url", ns):
                url = node.findtext("s:loc", namespaces=ns)
                if safe_url(url):
                    urls[url] = dict(url=url, lastmod=node.findtext("s:lastmod", namespaces=ns), sitemap=sitemap)
            print(f"Inventory: {sitemap.rsplit('/',1)[-1]} — {len(urls)} URLs", flush=True)
        except Exception as e:
            errors.append(dict(type="zone", name=sitemap, searched=[sitemap], notes=f"Inventory fetch failed: {type(e).__name__}: {e}"))
            break
    counts = Counter(urlsplit(u).path.split('/')[1] or 'home' for u in urls)
    write_json(batch / "source_inventory.json", list(urls.values()))
    write_json(batch / "manifest.json", dict(collected_at=timestamp(), kind="URL inventory, not harvested entity records",
                 urls=len(urls), counts=dict(counts), sitemaps=sitemaps, errors=len(errors)))
    (batch / "robots.txt").write_text(client.get(ORIGIN + "/robots.txt"), encoding="utf-8")
    (batch / "gaps.jsonl").write_text(''.join(json.dumps(e) + '\n' for e in errors), encoding="utf-8")
    (batch / "REPORT.md").write_text(
        "# Archive canonical URL inventory\n\n" + f"Collected {len(urls):,} canonical URLs at {timestamp()}. This is a discovery inventory, not {len(urls):,} game records.\n\n"
        + "Source: https://vgsoharchive.com/sitemap.xml. Five-second minimum spacing, no query-string URLs. Duplicate sitemap references are deduplicated. Sitemap lastmod describes the archive build, not the historical game-data date. No linked structured export was found on the homepage or sitemap-pages listing.\n\n"
        + '\n'.join(f"- {kind}: {n:,}" for kind,n in sorted(counts.items()))
        + f"\n\n{len(errors)} inventory fetch gap(s). source_inventory.json is metadata; it must not be converted as game facts.\n", encoding="utf-8")
    write_json(STATE / "inventory.json", list(urls.values()))
    return list(urls)


def batch_path(topic):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic):
        raise ValueError("topic must contain lowercase letters, digits and hyphens only")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    return HERE / "raw" / f"{stamp}-{topic}"


def unique_json(values):
    seen, result = set(), []
    for value in values:
        signature = json.dumps(value, sort_keys=True)
        if signature not in seen:
            seen.add(signature)
            result.append(value)
    return result


def collect(client, urls, limit, topic, follow_links=False, publish_status=True):
    requests_at_start = client.network_requests
    attempts_at_start = getattr(client, 'network_request_attempts', None)
    batch = batch_path(topic)
    done_path = STATE / "done.json"
    done = set(json.loads(done_path.read_text(encoding="utf-8"))) if done_path.exists() else set()
    queue = deque(u for u in unique(urls) if u not in done)
    enqueued = set(queue)
    write_json(STATE / "active_queue.json", list(queue))
    records, gaps, fetched = {}, [], []
    metadata = []
    started = timestamp()
    fatal = False
    client.transient_connection_failure = False
    for _ in range(limit):
        if (STATE / 'stop.request').exists():
            break
        while queue and queue[0] in done:
            queue.popleft()
        if not queue:
            break
        url = queue.popleft()
        try:
            html = client.get(url)
            found, links = parse_page(url, html)
            if source_only_url(url):
                main=BeautifulSoup(html,'html.parser').find('main')
                metadata.append(source_metadata(main,url))
                gaps.append(dict(type='zone',name=plain(main.find('h1')),searched=[url],
                    notes='Supplemental source page downloaded and catalogued. Full typed game-fact extraction remains pending; metadata is not conversion-ready content.'))
            if urlsplit(url).path.startswith('/classes/'):
                soup = BeautifulSoup(html, 'html.parser')
                main = soup.find('main')
                metadata.append(dict(name=plain(main.find('h1')), url=url, fields=kv(main),
                                     source_date=None, parsed_at=timestamp()))
                # Class tables expose low-level ability URLs without disallowed filter requests.
                priorities = unique(r['ability_ref_url'] for r in sorted(found, key=lambda r: r.get('level_learned') or 0)
                                    if r.get('level_learned') is not None and r['level_learned'] <= 20
                                    and r.get('ability_ref_url')
                                    and r.get('ability_ref_url') not in done)
                priorities += unique(r['npc_ref_url'] for r in found if r.get('npc_ref_url') and r['npc_ref_url'] not in done)
                if getattr(client, 'cache_only', False):
                    priorities = [u for u in priorities if u in enqueued]
                pending_classes = [u for u in queue if urlsplit(u).path.startswith('/classes/')]
                promoted = set(priorities) | set(pending_classes)
                queue = deque(pending_classes + priorities + [u for u in queue if u not in promoted])
                enqueued.update(priorities)
            for r in found:
                identity = (r["type"], r.get('record_kind') or '', r["name"])
                if identity in records:
                    previous = records[identity]
                    previous["sources"].extend(s for s in r["sources"] if s not in previous["sources"])
                    previous["confidence"] = "low"
                    if r['type'] == 'ability':
                        previous['classes_recorded'] = unique(
                            previous.get('classes_recorded', []) + [name for name in
                            (previous.get('class'), r.get('class')) if name])
                    if r['type']=='npc' and r.get('npc_ref_url') and (
                            previous.get('npc_ref_url')==r['npc_ref_url'] or
                            any(s.get('url')==r['npc_ref_url'] for s in previous['sources'])):
                        # The trainer list explicitly links this same archive entity. Preserve
                        # service relationships without blending level, race or coordinate values.
                        previous['services']=unique(previous.get('services',[])+r.get('services',[]))
                        previous['training_classes_recorded']=unique(previous.get('training_classes_recorded',[])
                            +[v for v in (previous.get('trainer_of'),r.get('trainer_of')) if v])
                        if len(previous['training_classes_recorded'])==1:
                            previous['trainer_of']=previous['training_classes_recorded'][0]
                        else:
                            previous['trainer_of']=None
                    previous["notes"] += " Same name appears on more than one page; possible distinct entities. See archive_variants."
                    previous.setdefault("archive_variants", []).append(r)
                else:
                    records[identity] = r
            done.add(url)
            fetched.append(url)
            if follow_links:
                for link in links:
                    if link not in enqueued and link not in done:
                        queue.append(link)
                        enqueued.add(link)
            print(f"Collected {len(fetched)}/{limit}: {url} ({len(records)} records)", flush=True)
        except Exception as e:
            gaps.append(dict(type="zone", name=url, searched=[url], notes=f"Fetch or parse failed: {type(e).__name__}: {e}"))
            # Stop immediately on access/rate/server/parser failure instead of hammering the host.
            queue.appendleft(url)
            fatal = True
            client.transient_connection_failure = transient_connection_error(e)
            print(gaps[-1]["notes"], flush=True)
            break
    queue = deque(u for u in queue if u not in done)
    batch.mkdir(parents=True, exist_ok=False)
    if metadata:
        classes=[r for r in metadata if r.get('record_kind')!='source_page']
        pages=[r for r in metadata if r.get('record_kind')=='source_page']
        if classes:
            write_json(batch / 'class_metadata.json', classes)
        if pages:
            write_json(batch / 'source_pages.json', pages)
    for kind in sorted(set(r["type"] for r in records.values())):
        (batch / f"{kind}.jsonl").write_text(''.join(json.dumps(r,ensure_ascii=False) + '\n'
        for (t,subtype,n),r in sorted(records.items()) if t == kind), encoding="utf-8")
    if queue:
        gaps.append(dict(type="zone", name="Pending collection queue", searched=[ORIGIN + "/sitemap.xml"],
                         notes=f"{len(queue)} queued pages remain; queue.json preserves their URLs. This is not a completed zone or full-site dump."))
    (batch / "gaps.jsonl").write_text(''.join(json.dumps(g,ensure_ascii=False)+'\n' for g in gaps), encoding="utf-8")
    write_json(batch / "queue.json", list(queue))
    counts = Counter(r["type"] for r in records.values())
    manifest = dict(started_at=started, finished_at=timestamp(), pages=len(fetched), counts=dict(counts),
                    fetched_urls=fetched, pending=len(queue), stopped_on_error=fatal,
                    network_requests=client.network_requests - requests_at_start)
    manifest['network_requests_definition'] = 'Successful network responses during this batch; excludes cache hits and requests before batch start.'
    manifest['network_request_attempts'] = (client.network_request_attempts - attempts_at_start
        if attempts_at_start is not None else (0 if getattr(client, 'cache_only', False) else None))
    manifest['stop_requested'] = (STATE / 'stop.request').exists()
    write_json(batch / "manifest.json", manifest)
    (batch / "REPORT.md").write_text("# Archive facts collection\n\n"
        + f"{len(records)} records from {len(fetched)} canonical detail pages. Started {started}; finished {timestamp()}.\n\n"
        + '\n'.join(f"- {kind}.jsonl: {n}" for kind,n in sorted(counts.items()))
        + f"\n\n{len(gaps)} gap records; {len(queue)} queued pages remain. This batch is immutable after this run.\n\n"
        + "Records use the crowdsourced common fields. archive_fields and map_places preserve explicit labels, coordinates and relationships; they are not server schemas. Unknown values remain null. Contradictions are low confidence. Loot frequencies are observations, not guaranteed probabilities, and quantities remain unknown. No exact spawns are inferred from map landmarks. No source guide prose, forum identities or client files are copied.\n\n"
        + "Quests are discovery records until objective/reward logic is manually checked; no quest steps are invented. Item type/slot mappings only use exact recognized labels. Archive model names and rebuild tooltips do not establish client race IDs or screenshots. External original-source links are not fetched or treated as independent verification.\n\n"
        + "Crawl policy: https://vgsoharchive.com/robots.txt. Single process, cached canonical pages, minimum 15 seconds between network starts (increased after closed connections), no query URLs. source_inventory.json is separate URL metadata, not harvested data.\n\n"
        + "See manifest.json for exact page coverage and queue.json for incomplete work. Run crowdsourced/validate.py on this batch before conversion. Nothing outside crowdsourced is modified.\n", encoding="utf-8")
    # Mark pages done only after the entire immutable batch has been published.
    # Interrupted fetches are replayed from cache rather than silently lost.
    # Validation reports are part of the delivered batch; semantic gaps do not become guessed facts.
    from validate import validate
    _, validation_issues = validate(batch)
    write_json(batch / "VALIDATION.json", dict(issues=validation_issues, count=len(validation_issues)))
    write_json(done_path, sorted(done))
    write_json(STATE / "active_queue.json", list(queue))
    write_json(STATE / "latest.json", dict(batch=str(batch.relative_to(HERE)), **manifest))
    if publish_status:
        write_json(HERE / "reviewed" / "COLLECTION_STATUS.json", dict(updated_at=timestamp(),
                   latest_batch=str(batch.relative_to(HERE)), total_pages_collected=len(done),
                   pending_pages=len(queue), stopped_on_error=fatal, latest_counts=dict(counts),
                   latest_validation_issues=len(validation_issues), parser_version=PARSER_VERSION))
        from build_evidence_index import publish
        publish(HERE)
    print(f"BATCH {batch}: {dict(counts)}, {len(queue)} pending", flush=True)
    return list(queue), fatal, batch


def transient_connection_error(error):
    """Retry only transport failures, never HTTP responses or parser failures."""
    if isinstance(error, HTTPError):
        return False
    if isinstance(error, URLError):
        error = error.reason
    if isinstance(error, OSError) and (
            error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN)
            or getattr(error, 'winerror', None) in (10050, 10051, 10065)):
        return True
    return isinstance(error, (TimeoutError, RemoteDisconnected, ConnectionResetError,
                              ConnectionAbortedError, BrokenPipeError))


def recover_closed_connection(client):
    """Keep the failed URL pending and cool down; never reduce a longer robots delay."""
    client.minimum_interval = min(60.0, max(15.0, client.minimum_interval) + 15.0)
    client.delay = max(client.delay, client.minimum_interval)
    write_json(client.interval_path, client.minimum_interval)
    print(f"Transient connection failure: retrying saved queue after {client.delay:g}s; request interval {client.delay:g}s", flush=True)
    deadline = time.monotonic() + client.delay
    while time.monotonic() < deadline:
        if (STATE / 'stop.request').exists():
            return False
        time.sleep(min(1.0, max(0, deadline - time.monotonic())))
    return not (STATE / 'stop.request').exists()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("inventory", "collect", "run"))
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--queue", type=Path)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--follow-links", action="store_true")
    ap.add_argument("--topic", default="archive-facts")
    args = ap.parse_args(argv)
    if args.limit < 1:
        ap.error("limit must be positive")
    STATE.mkdir(parents=True, exist_ok=True)
    lock = STATE / "run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        ap.error("Another collector is running (or a stale run.lock needs checking)")
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        client = ArchiveClient()
        if args.action == "inventory":
            inventory(client, batch_path("archive-catalog"))
            return 0
        urls = list(args.seed)
        if args.queue:
            queue = args.queue.resolve()
            if not queue.is_relative_to(HERE):
                ap.error("queue must be inside crowdsourced")
            urls += json.loads(queue.read_text(encoding="utf-8"))
        if args.action == "run":
            source = json.loads((STATE / "inventory.json").read_text(encoding="utf-8"))
            order = {"/zones/": 0, "/abilities/": 1, "/quests/": 2, "/mobs/": 3, "/items/": 4,
                     "/crafting/recipes/": 5, "/diplomacy/cards/": 6, '/classes/': -1, '/effects/': 7}
            class_indexes = [r['url'] for r in source if urlsplit(r['url']).path.startswith('/classes/') and detail_url(r['url'])]
            urls = class_indexes + cached_trainer_urls(client,class_indexes) + urls
            discovery=HERE/'reviewed/OFF_SITEMAP_DISCOVERY.json'
            if discovery.is_file():
                urls += [u for u in json.loads(discovery.read_text(encoding='utf-8')).get('urls',[]) if detail_url(u)]
            urls += sorted((r["url"] for r in source if detail_url(r["url"])),
                           key=lambda url: (next((v for k,v in order.items() if urlsplit(url).path.startswith(k)),8), url))
        if not urls:
            ap.error("provide --seed, --queue, or use run after inventory")
        while urls:
            if args.action == 'run' and (HERE / '.cache/multisource-bootstrap.done').exists():
                from multisource_schedule import step
                try:
                    step(HERE)
                except InterruptedError:
                    return 0
                except Exception as error:
                    if transient_connection_error(error):
                        if recover_closed_connection(client):
                            continue
                        return 0
                    raise
            urls, fatal, batch = collect(client, urls, args.limit, args.topic, args.follow_links or args.action=='run')
            if (fatal and args.action == "run" and getattr(client, "transient_connection_failure", False)
                    and not (STATE / "stop.request").exists()):
                if recover_closed_connection(client):
                    continue
            if fatal or args.action != "run" or (STATE / 'stop.request').exists():
                return 1 if fatal else 0
    finally:
        lock.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
