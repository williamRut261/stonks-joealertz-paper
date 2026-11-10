"""All tests are offline; mocked X responses, no credentials or orders."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from capture import classify, poll, valid_state, get_posts
from restore_state import restore, extract

AUTHOR = '12345'

def api(url, token):
    if '/users/by/username/' in url:
        return {'data': {'username':'joealertz', 'id':AUTHOR}}
    if 'since_id=' not in url:
        return {'data':[{'id':'100','author_id':AUTHOR,'created_at':'2026-11-01T13:00:00Z',
                          'text':'BUY 1 SPY @ 500'}]}
    return {'data':[
        {'id':'101','author_id':AUTHOR,'created_at':'2026-11-01T13:01:00Z','text':'BUY 2 AAPL @ 200'},
        {'id':'102','author_id':AUTHOR,'created_at':'2026-11-01T13:02:00Z','text':'watch TSLA'}]}


class Tests(unittest.TestCase):
    def test_strict_parser(self):
        self.assertEqual(classify('BUY 2 AAPL @ 200'),'candidate_stock')
        self.assertEqual(classify('BUY 1 SPY 2026-12-18 500C @ 2.5'),'candidate_option')
        for text in ['watch AAPL', 'BUY AAPL', 'BUY 2 AAPL',
                     'BUY 1 SPY 2026-02-30 500C @ 2.5',
                     'BUY 1 AAPL @ 2\nSELL 1 AAPL','BUY 1 AAPL @ 2 https://x.com']:
            self.assertEqual(classify(text),'ignored')
        self.assertEqual(classify('BUY 2 AAPL @ 200', True),'ignored')

    def test_baseline_and_update(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d)/'state.json')
            self.assertIn('baseline',poll(p,'FAKE',api).lower())
            st = json.loads(Path(p).read_text())
            self.assertEqual(st['cursor'],'100')
            self.assertEqual(st['events'],[])
            self.assertIn('Captured 2',poll(p,'FAKE',api))
            st = json.loads(Path(p).read_text())
            self.assertEqual(st['cursor'],'102')
            self.assertEqual([x['class'] for x in st['events']], ['candidate_stock','ignored'])
            self.assertNotIn('post_text',Path(p).read_text())

    def test_bad_state(self):
        with self.assertRaises(ValueError):
            valid_state({'version':1,'author_id':'123','cursor':'bad','events':[]})

    def test_bad_author(self):
        def wrong(url,token):
            if '/users/by/username/' in url: return api(url,token)
            return {'data':[{'id':'200','author_id':'OTHER','text':'BUY 1 SPY @ 2','created_at':'2026-11-01T13:00:00Z'}]}
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d)/'state.json')
            with self.assertRaises(ValueError): poll(p,'FAKE',wrong)
            self.assertFalse(Path(p).exists())

    def test_pagination_limit(self):
        def endless(url,token):
            return {'data':[{'id':'200','author_id':AUTHOR,'text':'BUY 1 SPY @ 2','created_at':'2026-11-01T13:00:00Z'}],
                    'meta':{'next_token':'NEXT'}}
        with self.assertRaises(RuntimeError): get_posts(AUTHOR,'FAKE','100',endless)

    def test_artifact(self):
        blob = json.dumps({'version':1,'author_id':'1','cursor':'2','events':[]}).encode()
        b = io.BytesIO()
        with zipfile.ZipFile(b,'w') as z: z.writestr('state.json',blob)
        self.assertEqual(extract(b.getvalue()),blob)
        with self.assertRaises((ValueError,zipfile.BadZipFile)): extract(b'not-a-zip')

    def test_missing_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'state.json')
            self.assertEqual(restore('a/b','FAKE',path,
              lambda url,token:b'{"artifacts":[]}'),'bootstrap')
            self.assertFalse(Path(path).exists())

    def test_no_private_text_state(self):
        with self.assertRaises(ValueError):
            valid_state({'version':1,'author_id':'1','cursor':'2',
              'events':[{'id':'10','class':'ignored','text':'DO NOT SAVE'}]})

if __name__ == '__main__': unittest.main()
