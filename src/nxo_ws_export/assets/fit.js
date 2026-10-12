// Runs after print.css is applied: scales figures taller than one page so they are never clipped,
// and makes the page-margin colour equal the article background (Chromium paints the root background there).
(opts) => {
  const article = document.querySelector('article.app__article');
  let fitted = 0;
  // Tables: Writerside scrolls wide tables horizontally; on paper they must fit the article width.
  let tables = 0;
  const minScale = opts.tableMinScale ?? 0.75;
  for (const t of article ? article.querySelectorAll('table') : []) {
    const box = (t.closest('.table__wrapper') || t.parentElement);
    const avail = box.clientWidth;
    const overflow = () => t.getBoundingClientRect().width - avail;
    if (!avail || overflow() <= 1) continue;
    tables += 1;
    // 1) shrink (keeps words intact) down to the minimum scale
    let k = Math.max(minScale, avail / t.getBoundingClientRect().width);
    t.style.setProperty('zoom', String(k), 'important');
    if (overflow() <= 0.5) continue;
    // 2) still too wide: allow long code identifiers to break, then 3) shrink whatever remains
    t.classList.add('nxo-table-break');
    for (let i = 0; i < 6 && overflow() > 0.5; i++) {
      k *= (avail - 0.5) / t.getBoundingClientRect().width;  // layout is not exactly linear in zoom: iterate
      t.style.setProperty('zoom', String(k), 'important');
    }
  }
  for (const el of article ? article.querySelectorAll('svg, img') : []) {
    if (el.closest('button') || (el.tagName.toLowerCase() === 'svg' && el.parentElement?.closest('svg'))) continue;
    const r = el.getBoundingClientRect();
    if (r.height > opts.maxFigureHeight && r.width > 0) {
      const k = opts.maxFigureHeight / r.height;
      el.style.setProperty('width', `${Math.floor(r.width * k)}px`, 'important');
      el.style.setProperty('height', `${Math.floor(opts.maxFigureHeight)}px`, 'important');
      el.style.setProperty('max-width', '100%', 'important');
      fitted += 1;
    }
  }
  let bg = 'rgba(0, 0, 0, 0)';
  for (let e = article; e; e = e.parentElement) {
    const c = getComputedStyle(e).backgroundColor;
    if (c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c)) { bg = c; break; }
  }
  if (bg !== 'rgba(0, 0, 0, 0)') {
    document.documentElement.style.setProperty('background', bg, 'important');
    document.body.style.setProperty('background', bg, 'important');
  }
  const text = document.querySelector('.article') || document.body;
  document.documentElement.style.setProperty('--nxo-fg', getComputedStyle(text).color);
  return { fitted, tables, background: bg };
};
