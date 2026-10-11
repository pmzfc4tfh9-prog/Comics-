"""Lucid progression ledger and deterministic graph; Python standard library only."""
import argparse
from contextlib import contextmanager
from datetime import datetime
from html import escape
import json
import math
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'mission', 'training', 'fight', 'breakthrough', 'discovery', 'recovery',
         'transformation_start', 'transformation_end'}
FIELDS = {'id', 'kind', 'occurred_at', 'summary', 'story_ref', 'gains',
          'type_gains', 'unlocks', 'mastered', 'form', 'all_types', 'types'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def names(value, allowed, label):
    require(isinstance(value, list), f'{label} must be a list')
    require(all(isinstance(v, str) and v in allowed for v in value), f'Unknown {label}')
    require(len(value) == len(set(value)), f'Duplicate {label}')
    return value

def points(value, allowed, label):
    require(isinstance(value, dict), f'{label} must be an object')
    for key, amount in value.items():
        require(key in allowed, f'Unknown {label} key: {key}')
        require(type(amount) is int and 0 <= amount <= 1000000,
                f'{label}.{key} must be a nonnegative integer <= 1000000')
    return value

def replay(rules, events):
    require(isinstance(rules, dict) and rules.get('schema_version') == 1, 'Unsupported rules version')
    for field in ('tracks', 'types'):
        v = rules.get(field)
        require(isinstance(v, list) and bool(v), f'Missing {field}')
        require(all(isinstance(s, str) and s and s.replace('_', '').isalnum() for s in v), f'Invalid {field}')
        require(len(set(v)) == len(v), f'Duplicate {field}')
    require(isinstance(events, list), 'events.json must be an array')
    unlocked = set(names(rules.get('initial_unlocked', []), rules['types'], 'initial_unlocked'))
    transform_types = names(rules['transformation_types'], rules['types'], 'transformation_types')
    state = {'schema_version': 1, 'character': rules['character'], 'event_count': 0,
             'xp': dict.fromkeys(rules['tracks'], 0), 'types': {}, 'active_form': None,
             'sage_status': rules.get('sage_status', 'undecided'), 'history': []}
    for name in rules['types']:
        state['types'][name] = {'unlocked': name in unlocked, 'mastered': False,
                                'xp': 0, 'temporary_access': False}
    seen = set()
    for event in events:
        require(isinstance(event, dict), 'Each event must be an object')
        require(not (set(event) - FIELDS), f'Unknown event fields: {set(event) - FIELDS}')
        event_id = event.get('id')
        require(isinstance(event_id, str) and 0 < len(event_id) <= 160, 'A unique event id is required')
        require(event_id not in seen, f'Duplicate event id: {event_id}')
        seen.add(event_id)
        kind = event.get('kind')
        require(kind in KINDS, f'Unknown event kind: {kind}')
        summary = event.get('summary')
        require(isinstance(summary, str) and 0 < len(summary.strip()) <= 2000, 'A summary is required (max 2000 characters)')
        require(isinstance(event.get('occurred_at'), str), 'occurred_at must be an ISO timestamp')
        try:
            stamp = datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
        except (ValueError, TypeError):
            raise ValueError('occurred_at must be an ISO timestamp') from None
        require(stamp.tzinfo is not None, 'occurred_at needs a timezone')
        require(isinstance(event.get('story_ref', ''), str), 'story_ref must be text')
        special = {'form', 'all_types', 'types'} & set(event)
        if kind != 'transformation_start':
            require(not special, 'form/all_types/types are only valid on transformation_start')
        gains = points(event.get('gains', {}), rules['tracks'], 'gains')
        type_gains = points(event.get('type_gains', {}), rules['types'], 'type_gains')
        opened = names(event.get('unlocks', []), rules['types'], 'unlocks')
        mastered = names(event.get('mastered', []), rules['types'], 'mastered')
        if kind == 'transformation_start':
            require(state['active_form'] is None, 'End the active transformation before starting another')
            require(isinstance(event.get('form'), str) and bool(event['form'].strip()), 'Transformation needs a form name')
            all_types = event.get('all_types', False)
            require(type(all_types) is bool, 'all_types must be a boolean')
            require(not (all_types and 'types' in event), 'Choose all_types or an explicit types list')
            selected = transform_types if all_types else names(event.get('types', []), rules['types'], 'types')
            require(bool(selected), 'A transformation must grant at least one type')
            state['active_form'] = {'name': event['form'], 'started_by': event_id, 'types': list(selected)}
            for name in selected:
                state['types'][name]['temporary_access'] = True
        if kind == 'transformation_end':
            require(state['active_form'] is not None, 'No active transformation to end')
            state['active_form'] = None
            for item in state['types'].values():
                item['temporary_access'] = False
        for name in opened:
            state['types'][name]['unlocked'] = True
        for name in mastered:
            require(state['types'][name]['unlocked'], f'Mastery requires a permanent unlock: {name}')
            state['types'][name]['mastered'] = True
        for name, amount in type_gains.items():
            item = state['types'][name]
            require(item['unlocked'] or item['temporary_access'], f'Cannot train inaccessible type: {name}')
            item['xp'] += amount
        for name, amount in gains.items():
            state['xp'][name] += amount
        state['history'].append({'id': event_id, 'kind': kind, 'summary': summary,
                                 'occurred_at': event['occurred_at'], 'story_ref': event.get('story_ref', ''),
                                 'xp_after': dict(state['xp']), 'active_form_after': state['active_form']})
    state['event_count'] = len(events)
    return state

def status(item):
    if item['mastered']: return 'mastered'
    if item['unlocked']: return 'awakened'
    if item['temporary_access']: return 'temporary'
    if item['xp']: return 'dormant'
    return 'unspecified'

def graph(state):
    """SVG uses real text and exact coordinates; no generated-image labels."""
    track_extra = max(0, len(state['xp']) - 7) * 43
    bottom_extra = track_extra + max(0, math.ceil(len(state['types']) / 4) - 5) * 91
    height = 1280 + bottom_extra
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
              '<title id="title">Lucid progression graph</title>',
              '<desc id="desc">Logged XP, elemental access, mastery and active transformation. Zero means no progress logged, not zero power.</desc>',
              f'<rect width="1100" height="{height}" fill="#0b121b"/>']
    def text(x,y,s,size=19,color='#eaf0f8'):
        chunks.append(f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" fill="{color}">{escape(str(s))}</text>')
    def box(x,y,w,h,color,stroke='#304155'):
        chunks.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{color}" stroke="{stroke}"/>')
    text(44,52,'LUCID / LIVE PROGRESSION',32,'#72e4a8')
    text(44,89,f'{state["event_count"]} recorded events | Sage path: {state["sage_status"]}',18)
    text(44,124,'XP tracks growth since logging began; baseline power is unspecified.',18,'#adbdce')
    form = state['active_form']['name'] if state['active_form'] else 'Base state'
    text(44,167,f'Current form: {form[:70]}',24,'#e9c67d')
    maximum = max([1, *state['xp'].values()])
    for i,(name,value) in enumerate(state['xp'].items()):
        y=210+i*43
        text(44,y+21,name.replace('_',' ').title(),20)
        box(200,y,716,26,'#1d2b3c')
        if value: box(200,y,716*value/maximum,26,'#57bc94')
        text(941,y+21,value,19)
    text(44,560+track_extra,'POWER TYPES / ACCESS IS SEPARATE FROM MASTERY',23,'#75d7f5')
    text(44,593+track_extra,'Gray: unspecified or dormant | Green: awakened | Gold: temporary | Purple: mastered',16,'#adbdce')
    colors={'unspecified':'#9aa8b8','dormant':'#afbac7','awakened':'#72e4a8','temporary':'#e9c67d','mastered':'#baa2ef'}
    for i,(name,item) in enumerate(state['types'].items()):
        x=44+(i%4)*255;y=621+track_extra+(i//4)*91
        label=status(item);color=colors[label]
        box(x,y,236,73,'#142131',color)
        text(x+13,y+29,name.replace('_',' ').title(),20,color)
        text(x+13,y+54,f'{label} | {item["xp"]} XP',16,'#adbdce')
    text(44,1110+bottom_extra,'Transformation access ends when the form ends. Earned progress stays.',19)
    text(44,1142+bottom_extra,'Permanent unlocks and mastery need explicit recorded milestones.',19)
    text(44,1190+bottom_extra,'Updated from progression/events.json; full history is kept in the ledger.',18,'#adbdce')
    text(44,1230+bottom_extra,'Original Lucid system. Element names are an editable registry, not fixed anime rules.',17,'#adbdce')
    chunks.append('</svg>')
    return '\n'.join(chunks)+'\n'

def markdown(state):
    def safe(s):return escape(str(s)).replace('|','&#124;').replace('\n',' ')
    lines=['# Lucid progression', '', '![Current power graph](graph.svg)', '',
           'Zero XP means no new progression logged, not zero power. Starting affinities remain unspecified.', '',
           '| Event | Kind | Story reference | Change |', '| --- | --- | --- | --- |']
    for event in state['history']:
        lines.append('| '+' | '.join(safe(event[k]) for k in ('id','kind','story_ref','summary'))+' |')
    if not state['history']:lines.append('| - | - | - | No events recorded yet. |')
    return '\n'.join(lines)+'\n'

def atomic(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,encoding='utf-8',delete=False) as f:
        f.write(content);temp=Path(f.name)
    temp.replace(path)

@contextmanager
def locked(root):
    lock=root/'progression'/'.tracker.lock'
    try:lock.mkdir()
    except FileExistsError:raise ValueError('Tracker is already running; wait or remove a stale .tracker.lock') from None
    try:yield
    finally:lock.rmdir()

def build(root=ROOT, event=None, check=False):
    root=Path(root)
    with locked(root):
        rules=read(root/'progression/rules.json');events=read(root/'progression/events.json')
        require(isinstance(events,list),'events.json must be an array')
        if event is not None:
            require(isinstance(event,dict),'Event must be an object')
            existing=next((e for e in events if isinstance(e,dict) and e.get('id')==event.get('id')),None)
            require(existing is None or existing==event,'Event id already exists with different content')
            if existing is None:events.append(event)
        state=replay(rules,events)  # Validate everything before touching any tracked file.
        content={'progression/state.json':json.dumps(state,indent=2,ensure_ascii=False)+'\n',
                 'progression/graph.svg':graph(state),'progression/README.md':markdown(state)}
        if check:
            for name,value in content.items():
                require((root/name).exists() and (root/name).read_text(encoding='utf-8')==value,f'Stale generated file: {name}')
        else:
            if event is not None:atomic(root/'progression/events.json',json.dumps(events,indent=2,ensure_ascii=False)+'\n')
            for name,value in content.items():atomic(root/name,value)
        return state

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['build','check','record'])
    group=p.add_mutually_exclusive_group();group.add_argument('--event-file',type=Path);group.add_argument('--event-json')
    args=p.parse_args()
    try:
        if args.command=='record':
            require(args.event_file is not None or args.event_json is not None,'record needs --event-file or --event-json')
            event=read(args.event_file) if args.event_file else json.loads(args.event_json)
        else:
            require(args.event_file is None and args.event_json is None,'Event input is only valid with record');event=None
        state=build(event=event,check=args.command=='check')
    except (ValueError,OSError) as exc:p.exit(1,f'Error: {exc}\n')
    print(f'Lucid: {state["event_count"]} events; graph and state {"verified" if args.command=="check" else "updated"}.')

if __name__=='__main__':main()
