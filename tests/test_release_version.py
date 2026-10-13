"""The version shown by the API and mobile asset URLs must stay in sync.

Telegram's WebView can cache JS/CSS aggressively, so a release must update
both query-string cache keys whenever the interface changes.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_and_asset_cache_keys_match():
    backend = (ROOT / 'app.py').read_text(encoding='utf-8')
    index = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
    match = re.search(r"^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", backend, re.M)
    assert match, 'A single APP_VERSION constant is required'
    version = match.group(1)
    assert 'version=APP_VERSION' in backend
    assert "'version':APP_VERSION" in backend
    assert f'/static/app.js?v={version}' in index
    assert f'/static/style.css?v={version}' in index
