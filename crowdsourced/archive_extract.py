"""Extract additional explicit facts from cached archive HTML; no network or server writes."""
import re
from bs4 import BeautifulSoup


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def numeric(value):
    value = value.strip().replace(',', '')
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
        return float(value) if '.' in value else int(value)
    return None


def effect_facts(value):
    """Numeric observations, not a complete combat formula or guessed condition tree."""
    facts = []
    num = r'(\d+(?:\.\d+)?)'
    fence = re.fullmatch(
        r'Raises your chance to parry incoming attacks by (\d+)% for (\d+) seconds '
        r'or until you parry\. This turns off your auto-attack\.', value.strip(), re.I)
    if fence:
        percent, duration = map(int, fence.groups())
        if percent > 0 and duration > 0:
            facts.append(dict(kind='conditional_parry_buff_observation',
                parry_chance_increase_percent_recorded=percent,
                duration_seconds_recorded=duration,
                early_expiry_condition_recorded='until you parry',
                auto_attack_disabled_recorded=True, percent_interpretation=None,
                guaranteed_parry=None, expiry_event_order=None,
                affected_attack_types=None, conditions_unparsed=True))
    echo = re.fullmatch(
        r'You shout after a successful parry, dealing (\d+) to (\d+) damage '
        r'and restoring (\d+) of your endurance\. Only usable after you parry\.',
        value.strip(), re.I)
    if echo:
        minimum, maximum, endurance = map(int, echo.groups())
        if 0 < minimum <= maximum and endurance > 0:
            facts.append(dict(kind='parry_damage_endurance_observation',
                damage_minimum_recorded=minimum, damage_maximum_recorded=maximum,
                endurance_restored_recorded=endurance,
                prerequisite_recorded='successful parry', damage_school=None,
                damage_target=None, activation_window_seconds=None, scaling=None,
                conditions_unparsed=True))
    charm = re.fullmatch(
        r'Charms your opponent, forcing it to fight for you for (\d+) seconds\. '
        r'Effective on targets level (\d+) and lower\.', value.strip(), re.I)
    if charm:
        duration, level = map(int, charm.groups())
        if duration > 0 and level > 0:
            facts.append(dict(kind='charm_duration_target_level_observation',
                charm_duration_seconds_recorded=duration,
                maximum_target_level_recorded=level, target_recorded='opponent',
                resist_check=None, break_conditions=None,
                player_target_applicability=None, stacking=None,
                conditions_unparsed=True))
    needle = re.fullmatch(
        r"A fast piercing attack that deals (\d+)% of weapon damage and lowers your opponent's damage by (\d+) for (\d+) sec\.",
        value.strip(), re.I)
    if needle:
        percent, reduction, duration = map(int, needle.groups())
        if percent > 0 and reduction > 0 and duration > 0:
            facts.append(dict(kind='weapon_damage_and_opponent_reduction_observation',
                weapon_damage_percent_recorded=percent,
                opponent_damage_reduction_recorded=reduction,
                reduction_duration_seconds_recorded=duration,
                damage_reduction_unit=None, weapon_damage_basis=None,
                damage_school=None, target_recorded='opponent', stacking=None,
                conditions_unparsed=True))
    chant = re.fullmatch(
        r'You begin to chant (?:vile|fiery|chilling) words, inflicting (\d+) to (\d+) '
        r'(physical|fire|cold) damage over (\d+) seconds\.', value.strip(), re.I)
    if chant:
        lower, upper, damage_type, duration = chant.groups()
        if int(lower) <= int(upper) and int(duration) > 0:
            facts.append(dict(kind='damage_over_duration_range_observation',
                values=[int(lower), int(upper)], damage_type_recorded=damage_type.lower(),
                duration_seconds=int(duration), tick_interval_seconds=None,
                tick_count=None, damage_per_tick=None, target_recorded=None,
                range_basis=None, conditions_unparsed=True))
    # Some embedded tooltips append Details labels after the complete sentence.
    # Only the explicit Cost label is a boundary; trailing prose is not discarded.
    bellow = re.match(
        rf'You bellow, blasting your opponent for {num}(?: to |-){num} arcane damage\.(?=$| Cost:)',
        value.strip(), re.I)
    if bellow:
        lower, upper = map(numeric, bellow.groups())
        if lower <= upper:
            facts.append(dict(kind='damage_range', values=[lower, upper],
                damage_type_recorded='arcane', target_recorded='your opponent',
                range_basis=None, conditions_unparsed=True))
    counter_removal = re.fullmatch(
        r'(?:Purifies|Cures) all group members within (\d+)m, removing (\d+) (disease|poison) counters\.',
        value.strip(), re.I)
    if counter_removal:
        radius, count, counter_type = counter_removal.groups()
        if int(radius) > 0 and int(count) > 0:
            facts.append(dict(kind='group_counter_removal_observation',
                counter_type_recorded=counter_type.lower(), counters_removed=int(count),
                target_recorded='all group members',
                radius_recorded=dict(value=int(radius), unit='m'), conditions_unparsed=True))
    group_restoration = re.fullmatch(
        rf'Restores {num} to {num} energy, depending on your level, to your group every {num} sec\.',
        value.strip(), re.I)
    if group_restoration:
        lower, upper, interval = map(numeric, group_restoration.groups())
        if lower <= upper and interval > 0:
            facts.append(dict(kind='periodic_group_energy_restoration_range_observation',
                values=[lower, upper], resource='energy', interval_seconds=interval,
                target_recorded='your group', scaling_condition_recorded='depending on your level',
                level_to_value_mapping=None, range_basis=None, conditions_unparsed=True))
    compound_restoration = re.fullmatch(
        rf'Reduces Song cost by {num} and restores {num} hit points every {num} seconds\.',
        value.strip(), re.I)
    if compound_restoration:
        cost, amount, interval = map(numeric, compound_restoration.groups())
        if interval > 0:
            facts.extend([
                dict(kind='song_cost_reduction_observation', values=[cost],
                    resource=None, unit=None, conditions_unparsed=True),
                dict(kind='periodic_hit_point_restoration_observation', values=[amount],
                    resource_recorded='hit points', interval_seconds=interval,
                    target_recorded=None, conditions_unparsed=True)])
    song_cost = re.fullmatch(
        rf'(?:This rest song reduces|Reduces?) song cost by {num}\.?',
        value.strip(), re.I)
    if song_cost:
        facts.append(dict(kind='song_cost_reduction_observation',
            values=[numeric(song_cost.group(1))], resource=None, unit=None,
            conditions_unparsed=True))
    group_attributes = re.fullmatch(
        rf'Increases the (strength|dexterity|intelligence|wisdom|constitution|vitality) and '
        rf'(strength|dexterity|intelligence|wisdom|constitution|vitality) of your group by {num}-{num}\.?',
        value.strip(), re.I)
    if group_attributes:
        first, second, lower, upper = group_attributes.groups()
        if first.lower() != second.lower() and numeric(lower) <= numeric(upper):
            facts.append(dict(kind='group_attribute_range_observation',
                attributes_recorded=[first.lower(), second.lower()],
                values=[numeric(lower), numeric(upper)], target_recorded='your group',
                range_basis=None, conditions_unparsed=True))
    patterns = [
        ('damage_range', rf'\b(?:deals?|inflicts?|inflicting)\s+(?:an additional\s+)?{num}\s+to\s+{num}\s+damage'),
        ('damage_bonus', rf'\b(?:normal|weapon|melee) damage\s+(?:plus|by)\s+{num}(?!\d|%|\.\d)'),
        ('damage_bonus', rf'\bincreases melee damage by\s+{num}(?!\d|%|\.\d)'),
        ('damage_percent', rf'\b{num}%\s+(?:weapon\s+)?damage'),
    ]
    for kind, pattern in patterns:
        for match in re.finditer(pattern, value, re.I):
            numbers = [numeric(n) for n in match.groups()]
            fact = dict(kind=kind, values=numbers, conditions_unparsed=True)
            if fact not in facts:
                facts.append(fact)
    pattern = rf'\b(?:restoring|restores)\s+{num}\s+to\s+{num}\s+(energy|endurance|mana)\s+over\s+{num}\s+seconds?'
    for match in re.finditer(pattern,value,re.I):
        facts.append(dict(kind='resource_restoration', resource=match.group(3).lower(),
                          values=[numeric(match.group(1)),numeric(match.group(2))],
                          duration_seconds=numeric(match.group(4)),conditions_unparsed=True))
    heal=rf'\b(?:heals?|healing)\s+(your defensive target|an ally|your allies|it|all allies within {num}m)\s+for\s+{num}(?:\s+to\s+{num})?(?!\d|%|\.\d)(?!\s+to\s+\d)(?:\s+over\s+{num}\s+(?:sec|seconds?)\b)?'
    for match in re.finditer(heal,value,re.I):
        target,radius,amount,upper,duration=match.groups()
        facts.append(dict(kind='healing_amount',values=[numeric(amount)]+([numeric(upper)] if upper else []),
            target_recorded=target,radius_recorded=dict(value=numeric(radius),unit='m') if radius else None,
            duration_seconds=numeric(duration) if duration else None,conditions_unparsed=True))
    periodic=rf'\b(?:restores|restoring)\s+{num}\s+(energy|endurance|mana)\s+every\s+{num}\s+(?:sec|seconds?)\b'
    for match in re.finditer(periodic,value,re.I):
        facts.append(dict(kind='periodic_resource_restoration',values=[numeric(match.group(1))],
            resource=match.group(2).lower(),interval_seconds=numeric(match.group(3)),conditions_unparsed=True))
    attribute = rf"\b(?:increases?|increasing)\s+(?:your|the users|the user's)\s+(strength|dexterity|intelligence|wisdom|constitution|vitality)\s+by\s+{num}(?!\d|%|\.\d|\s+%)"
    for match in re.finditer(attribute, value, re.I):
        facts.append(dict(kind='attribute_increase', attribute=match.group(1).lower(),
            values=[numeric(match.group(2))], conditions_unparsed=True))
    sleep = rf'\bputs the target into a deep sleep for\s+{num}\s+(?:sec|seconds?)\b'
    for match in re.finditer(sleep, value, re.I):
        facts.append(dict(kind='crowd_control_duration', effect='sleep',
            duration_seconds=numeric(match.group(1)), conditions_unparsed=True))
    effect_duration = rf'\bthis effect will stay on the user for\s+{num}\s+(hours?|minutes?|seconds?|sec)\b'
    for match in re.finditer(effect_duration, value, re.I):
        amount = numeric(match.group(1))
        unit = match.group(2).lower()
        multiplier = 3600 if unit.startswith('hour') else 60 if unit.startswith('minute') else 1
        facts.append(dict(kind='effect_duration', duration_seconds=amount * multiplier,
            conditions_unparsed=True))
    proc = rf'\b{num}% chance on attack to heal wearer\b'
    for match in re.finditer(proc, value, re.I):
        chance = numeric(match.group(1))
        if 0 <= chance <= 100:
            facts.append(dict(kind='trigger_chance_observation', chance_percent=chance,
                trigger_recorded='attack', action_recorded='heal wearer',
                healing_amount=None, conditions_unparsed=True))
    critical = rf'\battacks have a\s+{num}% greater chance of scoring a critical hit\b'
    for match in re.finditer(critical, value, re.I):
        facts.append(dict(kind='critical_chance_increase_observation', values=[numeric(match.group(1))],
            unit='percent', basis_unresolved=True, conditions_unparsed=True))
    modifier = r'([+-]\d+(?:\.\d+)?)\s+(Arcane Spell Damage|Spiritual Spell Damage|Health|Arcane Absorption|Spiritual Absorption)\b'
    for match in re.finditer(modifier, value, re.I):
        facts.append(dict(kind='effect_stat_modifier_observation', stat_recorded=match.group(2),
            values=[numeric(match.group(1))], conditions_unparsed=True))
    return facts


def section_nodes(main, label):
    for heading in main.find_all(['h2', 'h3']):
        if re.sub(r'\s+', ' ', text(heading)).lower().split(' (')[0] == label.lower():
            result = []
            for sibling in heading.next_siblings:
                if getattr(sibling, 'name', None) in ('h1', 'h2', 'h3'):
                    break
                if getattr(sibling, 'name', None):
                    result.append(sibling)
            return result
    return []


def field(record, *labels):
    for label in labels:
        values = record.get('archive_fields', {}).get(label, [])
        if values:
            return values[0]
    return None


def role_services(role):
    role = (role or '').lower()
    services = []
    for pattern, service in [(r'\bmerchant\b|\bvendor\b', 'merchant'), (r'\brepair', 'repair'),
                             (r'\bbanker\b', 'banker'), (r'\btrainer\b|\binstructor\b', 'trainer'),
                             (r'\btask ?master\b', 'task master'), (r'\bbroker\b', 'broker'),
                             (r'\bmailbox\b', 'mailbox'), (r'\brift keeper\b|\briftway\b', 'riftway')]:
        if re.search(pattern, role):
            services.append(service)
    return services


def denominations(value):
    value = value.strip().lower().replace(',', '')
    if re.fullmatch(r'\d+c', value):
        return int(value[:-1])
    matches = re.findall(r'(\d+)\s*(platinum|gold|silver|copper)\b', value)
    remainder = re.sub(r'\d+\s*(?:platinum|gold|silver|copper)\b', '', value).strip(' ,')
    if not matches or remainder:
        return None
    units = dict(copper=1, silver=100, gold=10000, platinum=1000000)
    return sum(int(n) * units[unit] for n, unit in matches)


def table_items(nodes):
    """Recognize labelled game-item rows, not arbitrary tables or guide prose."""
    items = []
    for node in nodes:
        tables = [node] if node.name == 'table' else node.find_all('table')
        for table in tables:
            for row in table.find_all('tr'):
                cells = row.find_all('td', recursive=False)
                if len(cells) < 7:
                    continue
                quantity = re.fullmatch(r'(\d+)\s*x', text(cells[0]), re.I)
                if not quantity or not re.fullmatch(r'\[Clvl\s+\d+\]', text(cells[4]), re.I):
                    continue
                if not re.fullmatch(r'\[Ilvl\s+\d+\]', text(cells[5]), re.I):
                    continue
                name = text(cells[6])
                if name:
                    items.append(dict(item=name, count=int(quantity.group(1)), item_type=text(cells[2]),
                                      slot_raw=text(cells[3]), character_level_raw=text(cells[4]), item_level_raw=text(cells[5])))
    return items


def enrich_item(record, main):
    notes = []
    classes = []
    for node in section_nodes(main, 'Usable by'):
        for link in node.find_all('a', href=True):
            # Read the class labels already on the page; never request filtered links.
            if link['href'].startswith('/classes/') or re.match(r'^/items\?(?:[^#]*&)?class=', link['href']):
                classes.append(text(link))
    if classes:
        record['class_restrictions'] = list(dict.fromkeys(classes))
    record['zone'] = field(record, 'zone')
    for labels, target in [(('stack size', 'max stack'), 'stack_size'), (('capacity', 'slots'), 'bag_slots'),
                           (('value', 'sell value'), 'value_copper')]:
        raw = field(record, *labels)
        if raw:
            value = denominations(raw) if target == 'value_copper' else numeric(raw)
            if value is not None:
                record[target] = value
    raw_damage = field(record, 'damage')
    if raw_damage:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)', raw_damage)
        if match and float(match.group(1)) <= float(match.group(2)):
            record['damage'] = [numeric(match.group(1)), numeric(match.group(2))]
    raw_delay = field(record, 'delay', 'speed')
    if raw_delay:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)', raw_delay, re.I)
        if match:
            record['delay_seconds'] = numeric(match.group(1))
    raw_bind = (field(record, 'bind', 'binding') or '').lower()
    if raw_bind in ('on equip', 'bind on equip'):
        record['bind'] = 'on equip'
    elif raw_bind in ('on pickup', 'bind on pickup'):
        record['bind'] = 'on pickup'
    # Explicit flags can be preserved without pretending that Soulbound specifies a binding trigger.
    flags = []
    for node in main.select('.tt-fields .tt-line'):
        content = text(node)
        if content in ('No Trade', 'Unique', 'Soulbound', 'No Drop'):
            flags.append(content)
    if flags:
        record['flags_recorded'] = list(dict.fromkeys(flags))
    effects = []
    for node in section_nodes(main, 'Effects'):
        paragraphs = [node] if node.name == 'p' else node.find_all('p')
        for paragraph in paragraphs:
            name = paragraph.find('strong')
            if not text(name):
                continue
            description = paragraph.select_one('span.muted')
            effects.append(dict(name=text(name),
                activation_labels=list(dict.fromkeys(text(pill) for pill in paragraph.select('.pill'))),
                observations=effect_facts(text(description)) or None))
    if effects:
        record['archive_item_effects'] = effects
        notes.append('Explicit item-effect names and activation labels recorded. Numeric observations retain unresolved conditions; unknown or malformed effect mechanics are not inferred.')
    return notes


def enrich_quest(record, main):
    notes = []
    if not record.get('turn_in'):
        record['turn_in'] = field(record, 'hand in to', 'turn in to', 'ends with')
    record['quest_chain'] = dict(name=field(record, 'series'), position=None) if field(record, 'series') else None
    required = table_items(section_nodes(main, 'Quest Required Items'))
    if required:
        record['archive_required_items'] = required
    reward_nodes = section_nodes(main, 'Quest Rewards')
    reward_items = table_items(reward_nodes)
    reward_values = []
    for node in reward_nodes:
        if node.name == 'table':
            continue
        for line in node.get_text('\n', strip=True).splitlines():
            coin = denominations(line)
            xp = re.fullmatch(r'([\d,]+)\s*(?:XP|experience)', line, re.I)
            scoped_xp = re.fullmatch(r'([\d,]+)\s*(?:XP|experience)\s+at\s+(?:Lvl|Level)\s+(\d+)', line, re.I)
            if scoped_xp:
                record.setdefault('archive_level_reward_observations', []).append(dict(
                    kind='xp', value=int(scoped_xp.group(1).replace(',', '')),
                    player_level=int(scoped_xp.group(2)), raw=line))
            if coin is not None:
                reward_values.append(dict(kind='coin_copper', value=coin))
            if xp:
                reward_values.append(dict(kind='xp', value=int(xp.group(1).replace(',', ''))))
    for key in ('xp', 'coin_copper'):
        values = list(dict.fromkeys(entry['value'] for entry in reward_values if entry['kind'] == key))
        if len(values) == 1:
            previous = record['rewards'].get(key)
            if previous is not None and previous != values[0]:
                record['confidence'] = 'low'
                notes.append(f'Conflicting {key}: field gives {previous}, reward section gives {values[0]}; both retained in archive_reward_values.')
            else:
                record['rewards'][key] = values[0]
        elif len(values) > 1:
            record['confidence'] = 'low'
            notes.append(f'Multiple {key} values in rewards; not combined.')
    if reward_values:
        record['archive_reward_values'] = reward_values
    if reward_items:
        record['archive_reward_items'] = reward_items
        reward_text = ' '.join(text(node) for node in reward_nodes)
        if re.search(r'\bchoose one of\b', reward_text, re.I):
            record['rewards']['choice'] = list(dict.fromkeys(r['item'] for r in reward_items))
        else:
            # A list of rewards without an explicit choice/all rule remains unresolved.
            notes.append('Reward item rows found, but a guaranteed-versus-choice rule was not explicit; retained for review.')

    objective_nodes = section_nodes(main, 'Objectives')
    objective_text = '\n'.join(node.get_text('\n', strip=True) for node in objective_nodes)
    counters = []
    for match in re.finditer(r'(?m)(?:^|(?<=\n)|(?<=\))|(?<= - )|(?<=\. ))\s*([^\n().!?]{1,100}?)\s*\((?:\d+\s*/\s*)?(\d+)\)', objective_text):
        label = re.sub(r'^-\s+', '', match.group(1).strip())
        count = int(match.group(2))
        if not label or re.search(r'[.!?]', label):
            continue
        # This is an explicit tracker counter, not a deduction from a walkthrough.
        counters.append(dict(label=label, count=count, objective=match.group(0).strip()))
    if counters:
        record['archive_objective_counters'] = counters
        steps = []
        entity_names = [e['name'] for e in record.get('referenced_entities', []) if '/mobs/' in e['url']]
        for counter in counters:
            label, count = counter['label'], counter['count']
            kind, target = None, None
            kill_prefix = re.fullmatch(r'(?:slay|kill)\s+(.+)', label, re.I)
            if kill_prefix:
                kind = 'kill'
                candidate = kill_prefix.group(1).strip()
                target = candidate if candidate in entity_names else None
            elif label.lower().endswith(' slain'):
                kind = 'kill'
                candidate = label[:-6].strip()
                target = candidate if candidate in entity_names else None
            else:
                candidates = [r['item'] for r in required if r['count'] == count and r['item_type'].lower() == 'quest item']
                if label in candidates:
                    kind, target = 'collect', label
                elif len(candidates) == 1 and re.search(r'\bcollect\b|\bgather\b|\bretrieve\b', objective_text, re.I):
                    kind, target = 'collect', candidates[0]
                elif re.search(r'\bcollect\b|\bgather\b|\bretrieve\b', objective_text, re.I):
                    # The tracker supplies the item name exactly; no singularization or typo correction.
                    kind, target = 'collect', label
            steps.append(dict(objective=counter['objective'], kind=kind, target=target, count=count))
        # Only claim the step list is complete when the source contains nothing beyond these counters.
        residual = objective_text
        for counter in counters:
            residual = residual.replace(counter['objective'], '')
        record['steps'] = steps if not residual.strip() and all(s['kind'] and s['target'] for s in steps) else None
        record['candidate_steps'] = steps
        if record['steps'] is None:
            notes.append('Explicit tracker counters extracted, but complete objective coverage or exact targets remain unresolved; candidate_steps are not conversion-ready steps.')
    return notes


def enrich_ability(record, main):
    notes = []
    record['target_recorded']=field(record,'target')
    head=main.select_one('.detail-head')
    aliases=[]
    if head:
        for paragraph in head.find_all('p'):
            value=text(paragraph)
            if value.startswith('Also recorded as '):
                aliases.append(value.removeprefix('Also recorded as '))
    if aliases:
        record['aliases_recorded']=list(dict.fromkeys(aliases))
    levels=[]
    for label,values in record.get('archive_fields',{}).items():
        if not re.fullmatch(r'level in \d{4}(?:-\d{4})?',label):
            continue
        for raw in values:
            match=re.fullmatch(r'(\d+)(?:\s*[—–]\s*now\s*\d+)?',raw)
            if match:
                levels.append(dict(scope=label,level_learned=int(match.group(1)),raw=raw))
    if levels:
        record['historical_level_observations']=levels
        notes.append('Historical learned levels are separate from the current labelled level; no patch-era value substituted.')
    historical_sources=[]
    for node in section_nodes(main,'As it was earlier'):
        for link in node.find_all('a',href=True):
            if link['href'].startswith(('http://','https://')) and not link['href'].startswith('https://vgsoharchive.com'):
                if link['href'] not in historical_sources:
                    historical_sources.append(link['href'])
    if historical_sources:
        record['historical_source_urls_recorded']=historical_sources
    rank = re.search(r'\s([IVX]+)$',record['name'])
    if record.get('rank') is None and rank:
        record['rank'] = rank.group(1)
    cost_values = {resource: [] for resource in ('mana','energy','endurance')}
    for resource in cost_values:
        for raw in record.get('archive_fields',{}).get(resource+' cost',[]):
            value=numeric(raw)
            if value is not None and value>=0:
                cost_values[resource].append(value)
    raw_cost = field(record,'cost')
    if raw_cost:
        matches=re.findall(r'(\d+)\s*(mana|energy|endurance)\b',raw_cost,re.I)
        residue=re.sub(r'\d+\s*(?:mana|energy|endurance)\b','',raw_cost,flags=re.I).strip(' ,+')
        if not residue:
            for value,resource in matches:
                cost_values[resource.lower()].append(int(value))
    observed={resource:list(dict.fromkeys(values)) for resource,values in cost_values.items() if values}
    if observed:
        record['cost_observations']=observed
        if all(len(values)==1 for values in observed.values()):
            record['cost']={resource:values[0] for resource,values in observed.items()}
        else:
            record['cost']=None
            record['confidence']='low'
            notes.append('Contradictory labelled resource costs retained in cost_observations; no operative cost chosen.')
    timings = {}
    for label, target in [('cast time', 'cast_time_seconds'), ('refresh', 'refresh_seconds'),
                          ('recast', 'refresh_seconds'), ('duration', 'duration_seconds')]:
        for raw in record.get('archive_fields', {}).get(label, []):
            value = None
            if raw.lower()=='instant':
                value = 0
            else:
                match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(s|secs?|seconds?|minutes?)', raw, re.I)
                if match:
                    value = numeric(match.group(1))
                    if match.group(2).lower().startswith('minute'):
                        value *= 60
            if value is not None:
                timings.setdefault(target, []).append(dict(label=label, raw=raw, seconds=value))
    if timings:
        record['timing_observations'] = timings
        for target, observations in timings.items():
            values = list(dict.fromkeys(o['seconds'] for o in observations))
            record[target] = values[0] if len(values) == 1 else None
            if len(values) > 1:
                record['confidence'] = 'low'
                notes.append(f'Contradictory {target} values retained in timing_observations; no operative timing chosen.')
    raw_range = field(record, 'range')
    if raw_range:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(m|meters?|feet|ft)', raw_range, re.I)
        if match:
            record['range'] = dict(value=numeric(match.group(1)), unit=match.group(2).lower(), raw=raw_range)
        interval = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(m|meters?|feet|ft)', raw_range, re.I)
        if interval and numeric(interval.group(1)) <= numeric(interval.group(2)):
            record['range_interval_reported_by_archive'] = dict(
                minimum=numeric(interval.group(1)), maximum=numeric(interval.group(2)),
                unit=interval.group(3).lower(), raw=raw_range,
                historical_authentication=None)
    record['trainer'] = field(record, 'learned from', 'trainer')
    record['requirements']=field(record,'requires')
    record['causes_weakness']=field(record,'causes weakness','causes')
    record['exploits_weakness']=field(record,'exploits weakness')
    observations=[]
    for heading,scope in [('Effect','current'),('Alternate description','alternate'),('As it was earlier','historical')]:
        parts=section_nodes(main,heading)
        tips=[]
        for node in parts:
            if 'tooltip' in node.get('class',[]):
                tips.append(node)
            tips.extend(node.select('.tooltip'))
        for tip in tips:
            value=text(tip)
            facts=effect_facts(value)
            if facts:
                observations.append(dict(scope=scope,facts=facts))
            if scope=='current' and record.get('tooltip') is None and len(value.split())<=25:
                record['tooltip']=value
    if observations:
        record['effect_observations']=observations
        if any(o['scope']!='current' for o in observations):
            notes.append('Current, alternate and historical effect figures are separate observations; no single historical ruleset selected.')
    note_text=' '.join(text(n) for n in section_nodes(main,'Notes'))
    if 'Read from the in-game tooltip' in note_text:
        record['verification_reported_by_archive']='tooltip read in VGO Emulator; not independently verified by this collector'
    elif 'tooltip has not been read' in note_text:
        record['verification_reported_by_archive']='spellbook existence only; numerical tooltip unverified'
    if any(text(n.select_one('strong')) == 'Not in the emulator.'
           for n in main.select('p.absent-note')):
        record['emulator_absence_reported_by_archive'] = dict(
            reported_absent=True, independently_verified=False,
            emulator_build=None, historical_authentication=None)
    return notes


def enrich_recipe(record, main):
    notes=[]
    record['crafting_stage']=field(record,'sub-class')
    record['skill']=field(record,'skill')
    for heading,target in [('Ingredients','ingredients'),('Tools','tools'),('Utilities','utilities'),('Enhancements','enhancements_recorded'),('Produces','products_recorded')]:
        observations=[]
        for node in section_nodes(main,heading):
            for li in node.select('ul.component-list > li'):
                copy=BeautifulSoup(str(li),'html.parser').find('li')
                guide=bool(copy.select('.guide-mark'))
                quantity=copy.select_one('.qty')
                raw_quantity=text(quantity) if quantity else None
                count_match=re.fullmatch(r'\((\d+)\)',raw_quantity or '')
                count=int(count_match.group(1)) if count_match else None
                link=copy.find('a',href=re.compile(r'^/items/[^/?#]+$'))
                name=text(link) if link else None
                for hidden in copy.select('.tt, .guide-mark, .qty'):
                    hidden.decompose()
                name=name or text(copy)
                if not name:
                    continue
                observations.append(dict(item=name,count=count,quantity_raw=raw_quantity,
                    item_ref_url='https://vgsoharchive.com'+link['href'] if link else None,
                    evidence_scope='launch-era guide; unconfirmed by archive' if guide else 'archive recorded'))
        if observations:
            record[target]=observations
            if any(o['evidence_scope'].startswith('launch-era') for o in observations):
                record['confidence']='low'
        if target=='ingredients' and observations:
            notes.append('Ingredient rows preserve the printed list; simultaneous requirements versus alternative materials are unverified. Missing quantities remain null.')
    raw_level=field(record,'recipe level')
    if raw_level and numeric(raw_level) is None:
        record['confidence']='low'
        notes.append('Recipe level is a nonnumeric source placeholder; no level inferred.')
    if record.get('products_recorded'):
        notes.append('Listed products are candidate outcomes, not a guaranteed single output; output remains unknown.')
    return notes


def enrich_record(record, main):
    if record['type'] in ('creature', 'npc'):
        observations = []
        for node in section_nodes(main, 'Where they stood') if main is not None else []:
            for row in node.find_all('li'):
                zones = [dict(name=text(a), url='https://vgsoharchive.com'+a['href'])
                         for a in row.find_all('a', href=re.compile(r'^/zones/[^/?#]+$'))]
                coordinates = re.search(r'—\s*([+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?)(?:\s|$)', text(row))
                observations.append(dict(source_text=text(row), zone_links=zones,
                    coordinates_raw=coordinates.group(1) if coordinates else None,
                    coordinate_format=None, spawn_certainty=None))
        record['map_location_observations'] = observations or None
    if record['type'] == 'creature':
        for target, label in [('continent', 'continent'),
                              ('locations_seen_recorded', 'locations seen'),
                              ('difficulty_recorded', 'difficulty')]:
            values = record.get('archive_fields', {}).get(label, [])
            record[target] = values[0] if len(values) == 1 else None
        return []
    if record['type'] == 'item':
        return enrich_item(record, main)
    if record['type'] == 'quest':
        return enrich_quest(record, main)
    if record['type'] == 'ability':
        return enrich_ability(record, main)
    if record['type'] == 'recipe':
        return enrich_recipe(record, main)
    if record['type'] == 'npc':
        role=field(record,'role')
        services = role_services(role)
        record['services'] = list(dict.fromkeys(record.get('services', []) + services))
        record['title'] = field(record, 'title')
        trainer=re.fullmatch(r'Class Trainer\s*[-–—]\s*(.+)',role or '',re.I)
        if trainer:
            record['trainer_of']=trainer.group(1).strip()
            record['training_classes_recorded']=[record['trainer_of']]
        record['continent']=field(record,'continent')
        record['locations_seen_recorded']=field(record,'locations seen')
        record['difficulty_recorded']=field(record,'difficulty')
        return []
    return []


def class_abilities(main, class_name, common):
    """Extract only labelled ability-table facts; bare cost/range numbers keep unknown units."""
    records = []
    unchecked = set()
    for node in section_nodes(main, 'Not yet checked against the client'):
        unchecked.update(a.get('href') for a in node.find_all('a', href=True))
    for table in main.find_all('table'):
        headers = [text(h).lower() for h in table.find_all('th')]
        if headers[:7] != ['lv', 'ability', 'school', 'cost', 'cast', 'range', 'effect']:
            continue
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) < 7:
                continue
            link = cells[1].find('a', href=re.compile(r'^/abilities/[^/?#]+$'))
            level = numeric(text(cells[0]))
            if not link or not isinstance(level, int) or level < 0:
                continue
            name = text(link)
            rank = re.search(r'\s([IVX]+)$', name)
            cast = text(cells[4])
            record = dict(common, type='ability', name=name, **{'class':class_name}, level_learned=level,
                rank=rank.group(1) if rank else None, category=text(cells[2]) or None,
                cost=None, cast_time_seconds=0 if cast.lower() == 'instant' else None,
                refresh_seconds=None, duration_seconds=None, range=None, tooltip=None,
                ability_ref_url='https://vgsoharchive.com'+link['href'],
                cost_recorded=dict(value=numeric(text(cells[3])), resource=None, raw=text(cells[3]) or None),
                range_recorded=dict(value=numeric(text(cells[5])), unit=None, raw=text(cells[5]) or None),
                cast_recorded=dict(value=numeric(cast), unit=None, raw=cast or None),
                notes='Explicit class-table facts. Cost resource and bare timing/range units are unknown; effect prose and truncated tooltips are not copied. Individual ability page still needs review.')
            # Each row owns its evidence list. Merging a shared spell across classes must not
            # add unrelated class-page citations to all other abilities from the first class.
            record['sources'] = [dict(source) for source in common['sources']]
            record['referenced_entities'] = [dict(name=name, url=record['ability_ref_url'])]
            record['archive_fields'] = {}
            if link['href'] in unchecked:
                record['confidence'] = 'low'
                record['notes'] += ' Listed as not yet checked against the client.'
            records.append(record)
    return records


def class_trainers(main, common):
    """Trainer roles and labelled locations from canonical class trainer lists."""
    class_link=main.find('a',href=re.compile(r'^/classes/[^/?#]+$'))
    class_name=text(class_link) or None
    records=[]
    for node in main.select('.trainer-body'):
        link=node.find('a',href=re.compile(r'^/mobs/[^/?#]+$'))
        if not link:
            continue
        zone_link=node.find('a',href=re.compile(r'^/zones/[^/?#]+$'))
        loc=node.find('code')
        raw=text(loc) if loc else None
        location=None
        if raw:
            numeric_loc=bool(re.fullmatch(r'/loc\s+[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?',raw))
            location=dict(raw=raw,format='/loc as printed by source' if numeric_loc else 'descriptive source /loc label',chunk=None)
        labels=[]
        for span in node.find_all('span',recursive=False):
            if not span.find(['a','code']) and 'civic parley' not in text(span).lower():
                if text(span):labels.append(text(span))
        continent=node.find_previous('h3',class_='trainer-continent')
        record=dict(common,type='npc',name=text(link),sources=[dict(s) for s in common['sources']],
                    level=None,race=None,health=None,damage=None,zone=text(zone_link) or None,
                    chunk=None,location=location,services=['trainer'],trainer_of=class_name,
                    region_labels=labels,continent=text(continent) or None,
                    npc_ref_url='https://vgsoharchive.com'+link['href'],
                    referenced_entities=[dict(name=text(link),url='https://vgsoharchive.com'+link['href'])],
                    notes='Explicit class-trainer listing. Race, level and health unknown. Unlinked region labels are preserved without guessing a zone or chunk. Textual /loc labels are not numeric spawn coordinates.')
        records.append(record)
    return records
