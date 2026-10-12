"""Browser-level checks of the in-page assets (needs `playwright install chromium`)."""

import pytest

from nxo_export.browser.assets import read_asset as asset

pytestmark = pytest.mark.browser

LONG = "very_long_identifier_without_any_break_opportunity_" * 3


def _page(cells: list[str], width: int = 628, code: bool = True):
    wrap = (lambda c: f'<code class="code">{c}</code>') if code else (lambda c: c)
    row = "".join(f'<td class="table__td"><p>{wrap(c)}</p></td>' for c in cells)
    return f"""<html class="nxo-print"><body><div style="width:{width}px"><article class="app__article">
      <div class="table table--with-scroll"><div class="table__wrapper table__wrapper--with-scroll"
           style="overflow-x:auto"><table class="table__content"><tr>{row}</tr></table></div></div>
    </article></div></body></html>"""


@pytest.mark.parametrize("cells,code,breaks", [
    (["a", "b"], True, False),                                   # fits already: untouched
    (["column_value_" + str(i) for i in range(7)], True, False),  # ~795px: zoom only
    ([LONG] * 6, True, True),                                     # far too wide: zoom + break identifiers
    ([LONG] * 6, False, True),                                    # plain words never break: zoom further
])
def test_tables_always_fit_article_width(cells, code, breaks):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium not installed: {e}")
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        page.set_content(_page(cells, code=code))
        page.add_style_tag(content=asset("print.css"))
        page.evaluate(asset("fit.js"), {"maxFigureHeight": 1000, "tableMinScale": 0.75})
        width = page.evaluate("document.querySelector('table').getBoundingClientRect().width")
        broke = page.evaluate("document.querySelector('table').classList.contains('nxo-table-break')")
        browser.close()
    assert width <= 628 + 0.5
    assert broke is breaks
