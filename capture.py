"""Read-only X alert capture. This module has no broker or order-execution code."""
from __future__ import annotations
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = 'https://api.x.com/2'
HANDLE = 'joealertz'
MAX_PAGES = 5
PATTERN = re.compile(
    r'^\s*(BUY|BOUGHT|PURCHASED|SELL|SOLD|CLOSED|EXITED)\s+'
    r'([1-9][0-9]{0,3})\s+(\$?[A-Z]{1,5}(?:\.[A-Z])?)'
    r'(?:\s+(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\s+'
    r'(\$?[0-9]{1,6}(?:\.[0-9]{1,3})?)\s*(C|P|CALLS?|PUTS?))?'
    r'(?:\s+(?:@|AT|LIMIT)\s*\$?([0-9]{1,7}(?:\.[0-9]{1,4})?))?'
    r'\s*[.!]?\s*$', re.I,
)
SPECULATIVE = re.compile(
    r'\b(maybe|watch|if|potential|would|could|might|hypothetical|example|spread|short|stop)\b', re.I,
)


def classify(text: str, referenced: bool = False) -> str:
    """Only return a syntactic candidate classification, never a trade recommendation."""
    if referenced or '\n' in text or '\r' in text or len(text) > 250 or 'http' in text.lower():
        return 'ignored'
    if SPECULATIVE.search(text):
        return 'ignored'
    m = PATTERN.fullmatch(text)
    if not m or not m.group(7):  # explicit price is mandatory
        return 'ignored'
    if m.group(4):
        try:
            expiry = m.group(4)
            if '-' in expiry:
                date.fromisoformat(expiry)
            else:
                month, day, year = map(int, expiry.split('/'))
                date(year, month, day)
        except ValueError:
            return 'ignored'
    return 'candidate_option' if m.group(4) else 'candidate_stock'


def request_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'User-Agent': 'stonks-joealertz-public-capture/0.3',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def get_author_id(token: str, request=request_json) -> str:
    user = (request(API + '/users/by/username/' + HANDLE, token).get('data') or {})
    if user.get('username', '').lower() != HANDLE or not str(user.get('id', '')).isdigit():
        raise ValueError('X account identity mismatch')
    return str(user['id'])


def get_posts(author_id: str, token: str, since: str | None, request=request_json) -> list[dict]:
    if not author_id.isdigit() or (since is not None and not since.isdigit()):
        raise ValueError('Invalid X author or cursor')
    seen: dict[str, dict] = {}
    next_token = None
    for _ in range(1 if since is None else MAX_PAGES):
        params = {'max_results': 100, 'tweet.fields': 'author_id,created_at,referenced_tweets'}
        if since:
            params['since_id'] = since
        if next_token:
            params['pagination_token'] = next_token
        url = API + '/users/' + author_id + '/tweets?' + urllib.parse.urlencode(params)
        result = request(url, token)
        for p in result.get('data') or []:
            pid = str(p.get('id', ''))
            if not pid.isdigit() or str(p.get('author_id', '')) != author_id:
                raise ValueError('X post identity mismatch')
            if not isinstance(p.get('text'), str) or not p.get('created_at'):
                raise ValueError('Incomplete X post')
            if since and int(pid) <= int(since):
                raise ValueError('X returned an older post with since_id')
            seen[pid] = p
        next_token = (result.get('meta') or {}).get('next_token')
        if not next_token:
            return sorted(seen.values(), key=lambda p: int(p['id']))
        if since is None:
            return sorted(seen.values(), key=lambda p: int(p['id']))
    raise RuntimeError('Too many X post pages; cursor unchanged')


def valid_state(s: dict) -> dict:
    if not isinstance(s, dict) or set(s) != {'version','author_id','cursor','events'}:
        raise ValueError('Bad state keys')
    if s['version'] != 1 or not str(s['author_id']).isdigit() or not str(s['cursor']).isdigit():
        raise ValueError('Bad state version or identity')
    events = s['events']
    if not isinstance(events, list) or len(events) > 1000:
        raise ValueError('Bad event list')
    for e in events:
        if not isinstance(e, dict) or set(e) != {'id','class'}:
            raise ValueError('State must contain only public IDs/classes')
        if not str(e['id']).isdigit() or e['class'] not in {'ignored','candidate_stock','candidate_option'}:
            raise ValueError('Bad event')
    return s


def save(path: str, state: dict) -> None:
    valid_state(state)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def poll(path: str, token: str, request=request_json) -> str:
    target = Path(path)
    state = valid_state(json.loads(target.read_text())) if target.exists() else None
    author_id = state['author_id'] if state else get_author_id(token, request)
    posts = get_posts(author_id, token, state['cursor'] if state else None, request)
    if state is None:
        if not posts:
            raise RuntimeError('No posts to baseline; refusing empty cursor')
        state = {'version':1, 'author_id':author_id,
                 'cursor':str(max(int(p['id']) for p in posts)), 'events':[]}
        save(path, state)
        return f'Initial baseline: skipped {len(posts)} historical posts; NO ORDERS'
    if not posts:
        return 'No new posts; NO ORDERS'
    for p in posts:
        pid = str(p['id'])
        cls = classify(p['text'], bool(p.get('referenced_tweets')))
        print(f'X post {pid}: {cls}; NO ORDERS')
        state['events'].append({'id':pid, 'class':cls})
    state['events'] = state['events'][-1000:]
    state['cursor'] = str(max(int(p['id']) for p in posts))
    save(path, state)
    return f'Captured {len(posts)} new posts; NO ORDERS'


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--state', default='runtime/state.json')
    args = p.parse_args()
    token = os.getenv('X_BEARER_TOKEN', '')
    if not token:
        print('Missing X_BEARER_TOKEN; NO ORDERS', file=sys.stderr)
        return 2
    try:
        print(poll(args.state, token))
        return 0
    except Exception as e:
        print('Capture failed closed:', type(e).__name__, str(e)[:120], file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
