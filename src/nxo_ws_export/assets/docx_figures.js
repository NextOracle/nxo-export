// Runs on a flattened, light-theme topic BEFORE any DOCX cleanup (and freezes it first, see below), so every figure still carries the exact
// styles it is rendered with (Mermaid keeps its colours in a <style> inside the SVG; removing it paints shapes black).
// Marks what must be rasterised: inline SVG diagrams (Mermaid, PlantUML, ...) and SVG/data images, which Word
// cannot show reliably (foreignObject text, CSS). Raster images keep their original file.
async (opts) => {
  // Freeze the page: the Writerside React app re-renders on its own (timers, observers) and, finding its DOM
  // mutated, swaps the topic for an error view. An inert deep clone keeps every node and computed style.
  const root = document.getElementById('webhelp-root');
  if (root && !root.hasAttribute('data-nxo-frozen')) {
    const frozen = root.cloneNode(true);
    frozen.setAttribute('data-nxo-frozen', '1');
    root.replaceWith(frozen);
    await Promise.all([...frozen.querySelectorAll('img')].map((i) => (i.complete ? null : i.decode().catch(() => null))));
  }
  const article = document.querySelector('article.app__article .article') || document.querySelector('article.app__article');
  const figures = [];
  const mark = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < opts.minFigure || r.height < opts.minFigure) return;
    const id = `nxo-fig-${figures.length}`;
    el.setAttribute('data-nxo-fig', id);
    figures.push({ id, width: Math.round(r.width * 100) / 100, height: Math.round(r.height * 100) / 100 });
  };
  for (const svg of article.querySelectorAll('svg')) {
    if (svg.parentElement?.closest('svg') || svg.closest('button, .code-block, [class*="copy"]')) continue;
    mark(svg);
  }
  for (const img of article.querySelectorAll('img')) {
    const src = img.currentSrc || img.src || '';
    if (/^data:/i.test(src) || /\.svg([?#]|$)/i.test(src)) mark(img);
  }
  return figures;
};
