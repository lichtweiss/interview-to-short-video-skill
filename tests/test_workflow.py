"""Behavioral regressions using generated bars/tone; no private media or models."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from create_demo import create
from export_review import export
from render_interview import srt_read
from validate_editorial_plan import validate


def command(script, *args):
    return subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str,args)],
                          capture_output=True, text=True)


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='interview 中文 space ')
        cls.root = Path(cls.temp.name)
        font = os.environ.get('TEST_FONT', '/System/Library/Fonts/STHeiti Medium.ttc')
        family = os.environ.get('TEST_FONT_FAMILY', 'Heiti TC')
        if not Path(font).is_file():
            raise RuntimeError('Set TEST_FONT and TEST_FONT_FAMILY to an installed font; see README')
        cls.work = create(cls.root/'demo', font, family)
        cls.plan = json.loads((cls.work/'plan.json').read_text())
        cls.render = cls.work/'preview'
        result = command('render_interview.py', cls.work/'spec.json', '--out', cls.render)
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_preview_and_formal_state(self):
        self.assertFalse(validate(self.plan))
        p = copy.deepcopy(self.plan)
        p['stage'] = p['state']['status'] = 'formal'
        self.assertTrue(validate(p))
        p['state']['canonical_manifest'] = 'plan.json'
        p['copy_confirmation'] = {'status': 'user-confirmed', 'revision_id': 'synthetic-test'}
        p['identity_map'][0].update(status='confirmed', confirmed_by='synthetic test', evidence={'visual':'generated fixture'})
        p['clips'][0].update(copy_status='user-confirmed', machine_qc='passed', human_review=dict.fromkeys(['identity','audio','semantic','visual'], 'approved'))
        self.assertFalse(validate(p))
        p['clips'][0]['human_review']['audio'] = 'pending'
        self.assertTrue(validate(p))

    def test_invalid_times(self):
        for start,end in [(float('nan'),2),(-1,2),(0,float('inf')),(True,2),(2,1)]:
            with self.subTest(start=start, end=end):
                p = copy.deepcopy(self.plan)
                p['clips'][0]['source_windows'] = [{'start':start,'end':end}]
                self.assertTrue(validate(p))
        p = copy.deepcopy(self.plan)
        p['clips'][0]['chapters'][1]['start'] = 99
        self.assertTrue(validate(p))

    def test_malformed_shapes_report_errors(self):
        for key,values in [('stage',[[],{},None,1]),('clips',[[None],[],{},None]),('identity_map',[[None],None]),('themes',[[],None,[{}]])]:
            for value in values:
                with self.subTest(key=key,value=value):
                    p = copy.deepcopy(self.plan); p[key] = value
                    self.assertTrue(validate(p))
        for field in ('human_review','composition','chapters','speakers','layout'):
            for value in ([],None,{},True):
                with self.subTest(field=field,value=value):
                    p = copy.deepcopy(self.plan)
                    p['stage'] = p['state']['status'] = 'formal'
                    p['clips'][0][field] = value
                    self.assertTrue(validate(p))

    def test_theme_contract(self):
        for field,value in [('theme_id','missing'),('series_order',True),('theme_basis','')]:
            p = copy.deepcopy(self.plan); p['clips'][0][field]=value
            self.assertTrue(validate(p))
        p = copy.deepcopy(self.plan)
        second = copy.deepcopy(p['clips'][0]);second['id']='02';p['clips'].append(second)
        self.assertTrue(validate(p))
        second['series_order']=2
        p['batch_audit']={'chapter_reviewed':True}
        self.assertFalse(validate(p))

    def test_cli_malformed_json(self):
        path=self.root/'bad.json'; path.write_text('{')
        r=command('validate_editorial_plan.py',path,'--json')
        self.assertNotEqual(r.returncode,0)
        self.assertFalse(json.loads(r.stdout)['valid'])
        self.assertNotIn('Traceback', r.stderr)

    def test_srt_overlap_and_controls(self):
        path=self.root/'bad.srt'
        for text in ['1\n00:00:00,000 --> 00:00:00,700\nx\n\n2\n00:00:00,600 --> 00:00:01,000\ny',
                     '1\n00:00:00,000 --> 00:00:00,700\n{bad}',
                     '1\n00:00:00,000 --> 00:00:03,000\nx']:
            path.write_text(text)
            with self.assertRaises(ValueError):srt_read(path,2)

    def test_render_decode_tail_and_pending(self):
        qc=json.loads((self.render/'qc.json').read_text())
        self.assertEqual(qc['machine_checks'],'passed')
        self.assertTrue(qc['full_decode'])
        self.assertAlmostEqual(qc['output_duration'],2.2,places=2)
        self.assertAlmostEqual(qc['added_freeze_seconds'],.2,places=2)
        for field in ('visual_review','listening_review','semantic_review'):
            self.assertEqual(qc[field],'pending')
        self.assertEqual(hashlib.sha256((self.render/'video.mp4').read_bytes()).hexdigest(),qc['sha256'])
        for name in ('opening.jpg','middle.jpg','tail.jpg'):
            self.assertGreater((self.render/name).stat().st_size,0)
        r=command('render_interview.py',self.work/'spec.json','--out',self.render)
        self.assertNotEqual(r.returncode,0)

    def test_render_rejects_source_overrun(self):
        spec=json.loads((self.work/'spec.json').read_text());spec['source_end']=3
        path=self.work/'overrun.json';path.write_text(json.dumps(spec))
        r=command('render_interview.py',path,'--out',self.root/'overrun')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('exceeds source',r.stderr)
        self.assertFalse((self.root/'overrun').exists())

    def test_copy_confirmation_and_paths(self):
        base=json.loads((self.work/'spec.json').read_text());base['no']='01'
        path=self.work/'legacy.json';path.write_text(json.dumps(base))
        sheet=self.work/'copy.md'
        self.assertEqual(command('copy_sheet.py','export',path,sheet).returncode,0)
        self.assertIn('SRT',sheet.read_text())
        out=self.work/'nested'/'compiled.json'
        self.assertNotEqual(command('copy_sheet.py','apply',path,sheet,'--out',out).returncode,0)
        self.assertNotEqual(command('copy_sheet.py','apply',path,sheet,'--out',out,'--approval','synthetic test').returncode,0)
        r=command('copy_sheet.py','apply',path,sheet,'--out',out,'--accept-default','--approval','Synthetic fixture: explicitly accept default')
        self.assertEqual(r.returncode,0,r.stderr)
        compiled=json.loads(out.read_text())
        self.assertEqual(compiled['copy_approval']['mode'],'default-accepted')
        self.assertEqual(Path(compiled['source']),self.work/'source.mp4')
        self.assertEqual(compiled['srt_sha256'],hashlib.sha256((self.work/'captions.srt').read_bytes()).hexdigest())
        # The same confirmed version renders. Changed SRT and sheet both invalidate it.
        r=command('render_interview.py',out,'--out',self.work/'confirmed-render')
        self.assertEqual(r.returncode,0,r.stderr)
        original=(self.work/'captions.srt').read_text()
        try:
            (self.work/'captions.srt').write_text(original.replace('Synthetic','Changed'))
            r=command('render_interview.py',out,'--out',self.work/'stale-subtitles')
            self.assertNotEqual(r.returncode,0);self.assertIn('SRT changed',r.stderr)
        finally:(self.work/'captions.srt').write_text(original)
        sheet.write_text(sheet.read_text()+'\nchanged')
        r=command('render_interview.py',out,'--out',self.work/'stale-sheet')
        self.assertNotEqual(r.returncode,0);self.assertIn('Copy sheet changed',r.stderr)
        # Edited-confirmed route is separate from accepting default.
        sheet.write_text(sheet.read_text().replace('needs-user-review','user-confirmed'))
        r=command('copy_sheet.py','apply',path,sheet,'--out',self.work/'edited.json','--approval','Synthetic edited confirmation')
        self.assertEqual(r.returncode,0,r.stderr)
        base['source_end']=1.5;path.write_text(json.dumps(base))
        r=command('copy_sheet.py','apply',path,sheet,'--out',self.work/'stale-base.json','--approval','test')
        self.assertNotEqual(r.returncode,0);self.assertIn('Source specs changed',r.stderr)

    def test_grouped_export(self):
        p=copy.deepcopy(self.plan)
        p['themes'].append({'id':'second','name':'另一主题 / <>&'})
        p['clips'][0]['render_dir']='preview'
        second=copy.deepcopy(p['clips'][0]);second.update(id='02',theme_id='second',title='Second demo',render_dir='second-preview')
        p['clips'].append(second);p['batch_audit']={'chapter_reviewed':True}
        spec=json.loads((self.work/'spec.json').read_text());spec.update(id='02',theme_id='second',title='Second demo')
        spec_path=self.work/'second-spec.json';spec_path.write_text(json.dumps(spec))
        r=command('render_interview.py',spec_path,'--out',self.work/'second-preview')
        self.assertEqual(r.returncode,0,r.stderr)
        path=self.work/'export-plan.json';path.write_text(json.dumps(p))
        out=self.root/'grouped output'
        result=export(path,out)
        self.assertEqual(len(result['clips']),2)
        self.assertEqual(result['stage'],'preview')
        text=(out/'index.html').read_text()
        self.assertNotIn('<script>',text)
        for record in result['clips']:
            self.assertTrue((out/record['video']).is_file())
            self.assertEqual(record['human_review']['audio'],'pending')
        for href in re.findall(r'(?:src|href)="([^"]+)"',text):
            self.assertTrue((out/unquote(href)).is_file())
        with self.assertRaises(FileExistsError):export(path,out)
        p['clips'][0]['source_windows']=[{'start':10,'end':12}];path.write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, 'source window'):export(path,self.root/'wrong-window')
        p['clips'][0]['source_windows']=[{'start':0,'end':2}]
        p['clips'][1]['render_dir']='preview';path.write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, 'does not match'):export(path,self.root/'wrong-mapping')
        self.assertFalse((self.root/'wrong-mapping').exists())

    def test_palette_and_overrun(self):
        r=command('suggest_palette.py',self.work/'source.mp4','--end',2,'--out',self.root/'palette')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((self.root/'palette'/'palette.json').is_file())
        for end in ('3','nan'):
            r=command('suggest_palette.py',self.work/'source.mp4','--end',end,'--out',self.root/'invalid-palette')
            self.assertNotEqual(r.returncode,0)
            self.assertNotIn('Traceback',r.stderr)


if __name__=='__main__':unittest.main()
