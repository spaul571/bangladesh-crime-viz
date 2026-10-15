"""Print the website to a PDF: light theme, white background, every chart drawn.

    python make_pdf.py [URL]

URL defaults to the live site, so the links inside the PDF point there. Writes
pdf/Bangladesh_Crime_Story_2019-2026.pdf: A4 landscape pages, scaled so the
site keeps its desktop layout (dashboard on page 1, then the story).

Needs Playwright (pip install playwright) and Microsoft Edge; without Edge,
run "playwright install chromium" once and the bundled Chromium is used.
"""
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://spaul571.github.io/bangladesh-crime-viz/"
OUT = Path(__file__).resolve().parent / "pdf" / "Bangladesh_Crime_Story_2019-2026.pdf"

# A4 landscape with 8 mm sides, 8/12 mm top/bottom and scale 0.75 is a 1416 x 957 px page
W, H, SCALE = 1416, 957, 0.75
CSS = f"""
:root, :root[data-theme] {{ --page: #ffffff !important; --surface: #ffffff !important; }}
html, body, .story {{ background: #ffffff !important; }}
.dash {{ height: {H - 52}px !important; break-after: page; }}
.chapter h2, .viz-head, .story-head h1 {{ break-after: avoid; }}
.chapter > p {{ orphans: 3; widows: 3; }}
.methodology, .table-wrap {{ break-inside: avoid; }}
/* keep the page footer on the last page of the story */
.story {{ padding-bottom: 16px !important; }}
.site-foot {{ padding-top: 12px !important; padding-bottom: 0 !important; break-before: avoid; }}
"""
# the charts paint their own off-white surface (#fcfcfb); turn it white
WHITEN = """() => {
  const off = new Set(['rgb(252, 252, 251)', '#fcfcfb']);
  document.querySelectorAll('svg, svg *').forEach((el) => {
    for (const prop of ['fill', 'stroke']) {
      const a = el.getAttribute(prop);
      if (a && off.has(a.trim().toLowerCase())) el.setAttribute(prop, '#ffffff');
      const s = el.style.getPropertyValue(prop);
      if (s && off.has(s.trim().toLowerCase())) el.style.setProperty(prop, '#ffffff');
    }
  });
  document.querySelectorAll('*').forEach((el) => {
    if (getComputedStyle(el).backgroundColor === 'rgb(252, 252, 251)') el.style.backgroundColor = '#ffffff';
  });
}"""
FOOTER = ('<div style="font-size:8px;width:100%;text-align:center;color:#898781;'
          'font-family:Segoe UI,Arial,sans-serif">Fewer cases, more crime: Bangladesh 2019–2026 · '
          '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')


def main(url=URL):
    OUT.parent.mkdir(exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, color_scheme="light")
        page.emulate_media(media="print", color_scheme="light")
        page.goto(url, wait_until="networkidle")
        page.add_style_tag(content=CSS)
        page.wait_for_function("document.querySelectorAll('#overview .ex-chart .main-svg').length >= 8",
                               timeout=60000)
        # the story's charts load as they scroll into view
        for cid in page.eval_on_selector_all(".chart[data-id]", "els => els.map(e => e.dataset.id)"):
            page.locator(f'.chart[data-id="{cid}"]').scroll_into_view_if_needed()
            page.wait_for_selector(f'.chart[data-id="{cid}"] .main-svg, .chart[data-id="{cid}"] svg.marks',
                                   timeout=60000)
        time.sleep(3)
        page.evaluate("window.scrollTo(0, 0)")
        page.evaluate(WHITEN)
        page.pdf(path=str(OUT), format="A4", landscape=True, scale=SCALE, print_background=True,
                 margin={"top": "8mm", "bottom": "12mm", "left": "8mm", "right": "8mm"},
                 display_header_footer=True, header_template="<span></span>", footer_template=FOOTER)
        browser.close()
    print("PDF written to", OUT)


if __name__ == "__main__":
    main(*sys.argv[1:2])
