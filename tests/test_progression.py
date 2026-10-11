import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from progression.tracker import ROOT, build, replay, graph

RULES=json.loads((ROOT/'progression/rules.json').read_text())
def event(id,kind='training',**extra):
    return dict(id=id,kind=kind,occurred_at='2026-10-11T02:40:00Z',summary='Synthetic test event',**extra)

class ProgressionTests(unittest.TestCase):
    def test_transformation_access_expires_but_progress_and_unlock_stay(self):
        start=event('start','transformation_start',form='Test eruption',all_types=True)
        active=replay(RULES,[start])
        self.assertTrue(all(t['temporary_access'] for t in active['types'].values()))
        self.assertFalse(any(t['mastered'] or t['unlocked'] for t in active['types'].values()))
        events=[start,event('fight','fight',gains={'ki':4,'chakra':3},type_gains={'fire':2}),
                event('unlock','breakthrough',unlocks=['fire']),event('end','transformation_end')]
        final=replay(RULES,events)
        self.assertIsNone(final['active_form'])
        self.assertFalse(any(t['temporary_access'] for t in final['types'].values()))
        self.assertEqual(final['types']['fire']['xp'],2)
        self.assertTrue(final['types']['fire']['unlocked'])
        self.assertFalse(final['types']['water']['unlocked'])
        self.assertEqual(final['xp']['ki'],4)
        self.assertEqual(final,replay(RULES,events))

    def test_invalid_events_are_rejected(self):
        bad=[event('x',gains={'ki':True}),event('x',gains={'ki':-1}),event('x',type_gains={'fire':1}),
             event('x',mastered=['water']),event('x','transformation_end'),event('x',unlocks=['invented']),
             event('x','transformation_start',form='Eruption',all_types='false'),event('x',form='unallowed')]
        for item in bad:
            with self.subTest(item=item),self.assertRaises(ValueError):replay(RULES,[item])
        a=event('same')
        with self.assertRaises(ValueError):replay(RULES,[a,a])
        start=event('start','transformation_start',form='A',all_types=True)
        with self.assertRaises(ValueError):replay(RULES,[start,{**start,'id':'second'}])

    def test_record_is_idempotent_and_invalid_record_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'progression').mkdir()
            shutil.copy(ROOT/'progression/rules.json',root/'progression/rules.json')
            (root/'progression/events.json').write_text('[]\n')
            e=event('once',gains={'control':2})
            self.assertEqual(build(root,e),build(root,e))
            before={p.name:p.read_bytes() for p in (root/'progression').iterdir() if p.is_file()}
            for bad in [event('bad',unlocks=['invalid']),{**e,'summary':'Conflicting duplicate'}]:
                with self.assertRaises(ValueError):build(root,bad)
            after={p.name:p.read_bytes() for p in (root/'progression').iterdir() if p.is_file()}
            self.assertEqual(before,after)
            build(root,check=True)

    def test_mastery_explicit_and_svg_escaped(self):
        s=replay(RULES,[event('u','breakthrough',unlocks=['fire'],mastered=['fire']),
                        event('t','transformation_start',form='<script>bad</script>',types=['water'])])
        self.assertTrue(s['types']['fire']['mastered'])
        self.assertNotIn('<script>',graph(s))
        self.assertEqual(s['sage_status'],'undecided')

if __name__=='__main__':unittest.main()
