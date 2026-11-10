"""Restore a public-safe GitHub Actions capture state. No broker interactions."""
import io
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from capture import valid_state

NAME = 'joealertz-public-capture-state'
MAX_ZIP = 1024 * 1024
MAX_STATE = 300 * 1024


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        nxt = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nxt and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            nxt.remove_header('Authorization')
        return nxt


def fetch(url: str, token: str) -> bytes:
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'stonks-joealertz-public-capture/0.3'
    })
    with urllib.request.build_opener(SafeRedirect()).open(req, timeout=30) as res:
        body = res.read(MAX_ZIP + 1)
        if len(body) > MAX_ZIP:
            raise ValueError('Artifact exceeds maximum size')
        return body


def extract(blob: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        items = [i for i in archive.infolist() if i.filename == 'state.json' and not i.is_dir()]
        if len(items) != 1 or items[0].file_size > MAX_STATE:
            raise ValueError('Invalid state archive')
        raw = archive.read(items[0])
    valid_state(json.loads(raw))
    return raw


def restore(repo: str, token: str, target: str, fetcher=fetch) -> str:
    if not token or '/' not in repo:
        raise ValueError('GitHub repository/token missing')
    url = f'https://api.github.com/repos/{repo}/actions/artifacts?name={NAME}&per_page=100'
    artifacts = json.loads(fetcher(url, token)).get('artifacts') or []
    branch = os.getenv('GITHUB_REF_NAME','main')
    candidates = sorted(
        (a for a in artifacts if a.get('name') == NAME and not a.get('expired')
         and (a.get('workflow_run') or {}).get('head_branch') == branch and a.get('archive_download_url')),
        key=lambda a: a.get('created_at',''), reverse=True)
    if not candidates:
        print('No state found: next capture baselines history without replay.')
        return 'bootstrap'
    body = extract(fetcher(candidates[0]['archive_download_url'], token))
    p = Path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(body)
    print('Restored capture state from artifact', candidates[0]['id'])
    return 'restored'


if __name__ == '__main__':
    try:
        restore(os.getenv('GITHUB_REPOSITORY',''), os.getenv('GITHUB_TOKEN',''), 'runtime/state.json')
    except Exception as e:
        print('State restore failed closed:', type(e).__name__, str(e)[:120], file=sys.stderr)
        raise SystemExit(2) from None
