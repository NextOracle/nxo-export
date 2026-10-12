"""Resolve the symbolic same-site links (nxo:<page>#<anchor>) emitted by flatten.js for one output document."""

from __future__ import annotations

import html as _html
import re
from collections.abc import Callable, Mapping

from ..topic import TopicHtml

_A = re.compile(r'<a\b([^>]*?)\bhref="nxo:([^"]*)"([^>]*)>(.*?)</a>', re.S)


class LinkResolver:
    """Internal targets become in-document links (heading/anchor bookmark, else the topic start); others go to the
    published site (render.link_base_url) or become plain text."""

    def __init__(self, topics: Mapping[str, TopicHtml], link_base_url: str | None):
        self.topics = topics
        self.link_base_url = link_base_url

    def resolve(self, html: str, *, current: TopicHtml, internal: Callable[[str], bool]) -> str:
        """`internal(url)`: whether that topic is part of the output document being written."""

        def sub(m: re.Match[str]) -> str:
            pre, target, post, inner = m.groups()
            target = _html.unescape(target)
            path, _, frag = target.partition("#")
            topic = self.topics.get(path) if path else current
            if topic is not None and internal(topic.node.url or ""):
                prefix = f"{topic.node.slug}--"
                anchor = prefix + frag if frag and prefix + frag in topic.ids else topic.anchor
                if anchor:
                    return f'<a{pre}href="#{_html.escape(anchor)}"{post}>{inner}</a>'
            if self.link_base_url and path:
                url = self.link_base_url.rstrip("/") + "/" + path + (f"#{frag}" if frag else "")
                return f'<a{pre}href="{_html.escape(url)}"{post}>{inner}</a>'
            return f"<span>{inner}</span>"

        return _A.sub(sub, html)
