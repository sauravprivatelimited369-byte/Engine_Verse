"""The gallery is readable and navigable before client-side enhancement."""
from html.parser import HTMLParser
from pathlib import Path

from scripts.export_pages import rewrite_html
from web.atlas import OBJECTS


class GalleryTags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


def test_exhibit_index_resolves_without_javascript(client):
    response = client.get("/")
    assert response.status_code == 200
    nodes = GalleryTags(response.text).nodes
    ids = [attrs['id'] for _, attrs in nodes if 'id' in attrs]
    assert len(ids) == len(set(ids))
    links = [attrs['href'] for tag, attrs in nodes if tag == 'a']
    assert all(link[1:] in ids for link in links if link.startswith('#'))
    for obj in OBJECTS:
        assert '#' + obj['slug'] in links
        assert obj['description'] in response.text


def test_static_exhibition_keeps_local_illustrations(client):
    nodes = GalleryTags(rewrite_html(client.get('/').text, '/atlas/')).nodes
    sources = {attrs['src'] for tag, attrs in nodes if tag == 'img'}
    assert len(sources) == len(OBJECTS)
    for src in sources:
        assert src.startswith('/atlas/static/img/atlas/')
        assert (Path(__file__).resolve().parents[1] / src.removeprefix('/atlas/')).is_file()


def test_studio_experiments_match_parameter_ranges(client):
    html = client.get('/').text
    for obj in OBJECTS:
        assert obj['minimum'] < obj['initial'] < obj['maximum']
        assert obj['step'] > 0
        assert obj['trial'] in html and obj['finding'] in html
        assert obj['invariant'] in html
