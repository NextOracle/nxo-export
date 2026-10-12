// Runs on a flattened, light-theme topic AFTER figures were rasterised (docx_figures.js).
// Turns Writerside markup into semantic HTML that Pandoc maps onto Word constructs:
//   tables    -> real Word tables (column widths measured from the rendered layout, header row kept)
//   callouts  -> one-cell tables tagged by id (styled as Writerside callouts in post-processing)
//   code      -> <pre><code class="lang"> (Pandoc highlights it with a theme built from the rendered Prism colours)
//   images    -> original files at their rendered width; Writerside's bordered screenshots keep their border
//   anchors   -> heading ids and other link targets, prefixed per topic so a combined document stays unique
(opts) => {
  const article = document.querySelector('article.app__article .article') || document.querySelector('article.app__article');
  const P = opts.idPrefix;

  // 1. Prism token colours actually rendered (theme for Pandoc's highlighter).
  const prism = {};
  for (const s of article.querySelectorAll('pre span[class]')) {
    const types = [...s.classList]
      .map((c) => (c.startsWith('prism--') ? c.slice(7) : c))
      .filter((c) => c && c !== 'token' && !c.startsWith('language-'));
    if (!types.length || !s.textContent.trim()) continue;
    const st = getComputedStyle(s);
    for (const t of types) prism[t] ??= { color: st.color, bold: Number(st.fontWeight) >= 600, italic: st.fontStyle === 'italic' };
  }

  // 2. Measure while the layout is intact: column widths and the zoom fit.js applied to wide tables.
  const tables = [];
  [...article.querySelectorAll('table')].forEach((t, n) => {
    const rows = [...t.rows];
    const ncols = Math.max(0, ...rows.map((r) => [...r.cells].reduce((s, c) => s + (c.colSpan || 1), 0)));
    if (!ncols) return;
    let widths;
    const full = rows.find((r) => r.cells.length === ncols);
    if (full) widths = [...full.cells].map((c) => c.getBoundingClientRect().width);
    else {
      widths = [];
      for (const c of rows[0].cells) for (let i = 0; i < (c.colSpan || 1); i++) widths.push(c.getBoundingClientRect().width / (c.colSpan || 1));
    }
    const sum = widths.reduce((a, b) => a + b, 0) || 1;
    t.querySelectorAll(':scope > colgroup').forEach((c) => c.remove());
    const cg = document.createElement('colgroup');
    for (const w of widths) {
      const col = document.createElement('col');
      col.setAttribute('width', `${Math.max(1, Math.round((w / sum) * 1000) / 10)}%`);
      cg.appendChild(col);
    }
    t.prepend(cg);
    if (!t.tHead && rows.length > 1 && [...rows[0].cells].every((c) => c.tagName === 'TH')) {
      t.createTHead().appendChild(rows[0]);
    }
    const zoom = parseFloat(t.style.zoom) || 1;
    t.removeAttribute('style');
    t.id = `nxo-t-${opts.uid}-${n}`;
    tables.push({ id: t.id, scale: Math.round(zoom * 1000) / 1000 });
  });
  for (const img of article.querySelectorAll('img')) {
    const r = img.getBoundingClientRect();
    if (r.width > 0 && !img.hasAttribute('data-nxo-width')) {
      img.setAttribute('data-nxo-width', String(r.width));
      img.setAttribute('data-nxo-height', String(r.height));
    }
    if (img.closest('.article__bordered-element')) img.setAttribute('data-nxo-bordered', '1');
  }

  // 3. Interactive chrome and anything that is not content.
  const drop = ['.app__breadcrumbs', '.micro-format', '.a11y-title', '.permalink', 'button', '.collapse__button', '.table__fader',
                '.table__scroll-arrow', '[class*="copy-button"]', '[class*="feedback"]', 'script', 'style', 'noscript', 'template'];
  article.querySelectorAll(drop.join(',')).forEach((e) => e.remove());

  // 4. Callouts. Rendered: blockquote.prompt > .prompt__wrapper--type-<note|tip|warning> > .prompt__content
  //    (pre-hydration markup: aside.prompt[data-type]). A one-cell table holds any content (lists, code, tables).
  let callouts = 0;
  for (const q of [...article.querySelectorAll('blockquote.prompt, aside.prompt')]) {
    const wrapper = q.querySelector('[class*="prompt__wrapper--type-"]');
    const m = wrapper && [...wrapper.classList].map((c) => c.match(/^prompt__wrapper--type-(\w+)$/)).find(Boolean);
    const type = (m ? m[1] : q.getAttribute('data-type') || 'note').toLowerCase();
    const title = q.getAttribute('data-title');
    const content = q.querySelector('.prompt__content') || q;
    const table = document.createElement('table');
    table.id = `nxo-callout-${['tip', 'warning'].includes(type) ? type : 'note'}-${opts.uid}-${callouts++}`;
    table.innerHTML = '<colgroup><col width="100%"></colgroup><tbody><tr><td></td></tr></tbody>';
    const td = table.querySelector('td');
    if (title) { const p = document.createElement('p'); p.innerHTML = '<strong></strong>'; p.firstChild.textContent = title; td.appendChild(p); }
    td.append(...content.childNodes);
    q.replaceWith(table);
  }

  // 5. Flattened tabs (flatten.js) and collapsible titles without a heading inside.
  for (const t of [...article.querySelectorAll('.nxo-tabs__title')]) {
    const div = document.createElement('div');
    div.setAttribute('data-custom-style', 'Tab Title');
    const p = document.createElement('p'); p.textContent = t.textContent.trim();
    div.appendChild(p);
    t.replaceWith(div);
  }
  for (const t of [...article.querySelectorAll('.collapse__title, .collapse__header')]) {
    if (!t.querySelector('h1,h2,h3,h4,h5,h6')) {
      const p = document.createElement('p'); p.innerHTML = '<strong></strong>'; p.firstChild.textContent = t.textContent.trim();
      t.replaceWith(p);
    }
  }

  // 6. Code blocks: text + language only; Pandoc re-highlights with the Writerside colours.
  const alias = { markup: 'xml', ts: 'typescript', js: 'javascript', sh: 'bash', shell: 'bash', console: 'bash',
                  yml: 'yaml', kt: 'kotlin', 'c#': 'cs', csharp: 'cs', py: 'python', docker: 'dockerfile',
                  none: '', text: '', plaintext: '', plain: '' };
  // Text diagrams: a block without a programming language that draws with box-drawing characters (boxes,
  // trees) is a figure, not code. It becomes "Text Diagram" lines: exact spacing, no code box, no highlighting.
  const boxDrawing = /[\u2500-\u257F]/;
  for (const pre of [...article.querySelectorAll('pre')]) {
    let lang = ([...pre.classList].find((c) => c.startsWith('language-')) || '').slice(9);
    if (!lang) lang = pre.closest('[data-lang]')?.getAttribute('data-lang') || '';
    lang = lang.toLowerCase();
    lang = lang in alias ? alias[lang] : lang;
    const box = pre.closest('.code-block');
    const target = box && box.querySelectorAll('pre').length === 1 ? box : pre;
    const text = pre.innerText.replace(/\n$/, '');
    if (!lang && boxDrawing.test(text)) {
      const div = document.createElement('div');
      div.setAttribute('data-custom-style', 'Text Diagram');
      for (const line of text.split('\n')) {
        const p = document.createElement('p');
        p.textContent = line.replace(/ /g, '\u00A0') || '\u00A0';
        div.appendChild(p);
      }
      target.replaceWith(div);
      continue;
    }
    const code = document.createElement('code');
    if (lang) code.className = lang;
    code.textContent = pre.innerText.replace(/\n$/, '');
    const clean = document.createElement('pre');
    clean.appendChild(code);
    target.replaceWith(clean);
  }

  // 7. Leftover inline SVG (icons, decorations) has no place in a document.
  article.querySelectorAll('svg').forEach((s) => s.remove());

  // 8. Images: site-relative src (Pandoc resolves via --resource-path), rendered width, Writerside border.
  for (const img of [...article.querySelectorAll('img')]) {
    if (!img.hasAttribute('data-nxo-figure')) {
      const u = new URL(img.currentSrc || img.getAttribute('src') || '', location.href);
      if (u.origin === location.origin) img.setAttribute('src', decodeURIComponent(u.pathname.replace(/^\//, '')));
    }
    const w = Number(img.getAttribute('data-nxo-width')) || 0;
    const h = Number(img.getAttribute('data-nxo-height')) || 0;
    const bordered = img.getAttribute('data-nxo-bordered') === '1';
    for (const a of ['srcset', 'sizes', 'width', 'height', 'loading', 'class', 'style', 'data-dark-src', 'data-nxo-width',
                     'data-nxo-height', 'data-nxo-bordered', 'data-nxo-figure']) img.removeAttribute(a);
    // Pandoc sizes images from width/height attributes (CSS px at 96 dpi), not from style.
    if (w && h) { img.setAttribute('width', `${Math.round(w)}px`); img.setAttribute('height', `${Math.round(h)}px`); }
    const p = img.parentElement;
    if (bordered && p && p.tagName === 'P' && p.textContent.trim() === '' && p.children.length === 1) {
      const div = document.createElement('div');
      div.setAttribute('data-custom-style', 'Figure Bordered');
      p.replaceWith(div); div.appendChild(p);
    }
  }

  // 9. Zero-width no-break spaces that Writerside appends to headings.
  //    Emoji get the "Emoji" character style: body fonts have no emoji glyphs, and Word's own fallback is
  //    unreliable (empty boxes). Code blocks are left alone (Pandoc re-tokenises them).
  const emoji = /(?:\p{Extended_Pictographic}|\p{Regional_Indicator})(?:\uFE0F|\u200D(?:\p{Extended_Pictographic})|\p{Emoji_Modifier}|\p{Regional_Indicator})*/gu;
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
  const texts = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) texts.push(n);
  for (const n of texts) {
    if (n.nodeValue.includes('\uFEFF')) n.nodeValue = n.nodeValue.replace(/\uFEFF/g, '');
    if (n.parentElement.closest('pre, [data-custom-style="Text Diagram"]') || !n.nodeValue.match(emoji)) continue;
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of n.nodeValue.matchAll(emoji)) {
      if (m.index > last) frag.append(n.nodeValue.slice(last, m.index));
      const span = document.createElement('span');
      span.setAttribute('data-custom-style', 'Emoji');
      span.textContent = m[0];
      frag.append(span);
      last = m.index + m[0].length;
    }
    if (last < n.nodeValue.length) frag.append(n.nodeValue.slice(last));
    n.replaceWith(frag);
  }

  // 10. Link targets. Headings keep their id (Word bookmark); other targets become an empty anchor span at the
  //     start of the nearest paragraph-like element, so cross-topic links can land on them.
  const ids = new Set();
  const headings = [...article.querySelectorAll('h1,h2,h3,h4,h5,h6')];
  for (const h of headings) {
    if (!h.id) continue;
    h.id = P + h.id;
    if (ids.has(h.id)) h.removeAttribute('id'); else ids.add(h.id);
  }
  const first = headings[0];
  if (first && !first.id) { first.id = `${P}top`; ids.add(first.id); }
  const inlineOk = ['P', 'LI', 'TD', 'TH', 'DT', 'DD', 'SPAN', 'A', 'STRONG', 'EM', 'B', 'I', 'CODE'];
  for (const e of [...article.querySelectorAll('[id]')]) {
    if (/^H[1-6]$/.test(e.tagName) || /^nxo-(t|callout)-/.test(e.id)) continue;
    const id = P + e.id;
    e.removeAttribute('id');
    if (ids.has(id)) continue;
    let target = inlineOk.includes(e.tagName) ? e : e.querySelector('p,li,td,th,dt,dd');
    if (!target || target.closest('pre')) continue;
    // A span before a block child would become an empty paragraph (a bullet on its own line): go inside it.
    const fc = target.firstElementChild;
    if (['LI', 'TD', 'TH', 'DT', 'DD'].includes(target.tagName) && fc && fc.tagName === 'P'
        && !target.textContent.slice(0, target.textContent.indexOf(fc.textContent)).trim()) target = fc;
    const span = document.createElement('span');
    span.id = id;
    target.prepend(span);
    ids.add(id);
  }

  // 11. Nest the topic under its TOC position when requested (h1 of a level-2 topic becomes h3).
  if (opts.headingShift > 0) {
    for (const h of [...article.querySelectorAll('h1,h2,h3,h4,h5,h6')]) {
      const nh = document.createElement(`h${Math.min(6, Number(h.tagName[1]) + opts.headingShift)}`);
      for (const a of h.attributes) nh.setAttribute(a.name, a.value);
      nh.append(...h.childNodes);
      h.replaceWith(nh);
    }
  }
  return { prism, tables, ids: [...ids], anchor: first ? first.id : null, callouts };
};
