from typing import Optional

import mistune
from django import template
from django.utils.safestring import mark_safe
from mistune import HTMLRenderer, Markdown, BlockParser, InlineParser, safe_entity
from mistune.plugins.formatting import strikethrough as plugin_strikethrough
from mistune.plugins.url import url as plugin_url


register = template.Library()


class CustomRenderer(HTMLRenderer):
    def link(self, text: str, url: str, title: Optional[str] = None) -> str:
        s = '<a rel="nofollow" target="_blank" href="' + self.safe_url(url) + '"'
        if title:
            s += ' title="' + safe_entity(title) + '"'
        return s + ">" + text + "</a>"

    def paragraph(self, text: str) -> str:
        return text + "\n"

    def softbreak(self) -> str:
        return "\n"

    def blank_line(self) -> str:
        return "\n"


block = BlockParser()
block.rules = ["blank_line"]
inline = InlineParser(hard_wrap=False)
inline.rules = [
    "emphasis",
    "link",
    "auto_link",
    "auto_email",
    "linebreak",
    "softbreak",
]
markdown = Markdown(
    renderer=CustomRenderer(escape=False),
    block=block,
    inline=inline,
    plugins=[plugin_strikethrough, plugin_url],
)


@register.filter(name="limited_markdown")
def limited_markdown(value):
    return mark_safe(markdown(value))
