// Turns a rendered Writerside page into static, printable content.
// Runs after the Writerside app.js has hydrated the page, so it acts on the real rendered DOM.
// Selectors are pinned to the builder version in config (builder.image); the smoke tests guard them.
async (opts) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const article = document.querySelector('article.app__article');
  if (!article) return { error: 'article.app__article not found' };
  const stats = { collapsibles: 0, tabs: 0, links: 0, images: 0 };

  const expandIn = async (root) => {
    const closed = [...root.querySelectorAll('.collapse__button[aria-expanded="false"]')];
    closed.forEach((b) => b.click());
    stats.collapsibles += closed.length;
    if (closed.length) await sleep(150);
  };

  // 1. Collapsibles (Writerside's own toggle, so content renders exactly as when a reader opens it).
  await expandIn(article);

  // 2. Tabs -> each panel in sequence, titled with its tab label.
  for (const wrapper of [...article.querySelectorAll('.tabs__wrapper')]) {
    const tabs = [...wrapper.querySelectorAll('[role="tab"]')];
    const parts = [];
    for (const tab of tabs) {
      tab.click();
      await sleep(60);
      const panel = [...wrapper.querySelectorAll('.tabs__content-wrapper, [role="tabpanel"]')]
        .find((p) => p.offsetHeight > 0) || wrapper.querySelector('.tabs__content');
      if (panel) await expandIn(panel);
      parts.push({ title: tab.textContent.trim(), panel: panel ? panel.cloneNode(true) : null });
    }
    const flat = document.createElement('div');
    flat.className = 'nxo-tabs';
    for (const { title, panel } of parts) {
      const t = document.createElement('div');
      t.className = 'nxo-tabs__title';
      t.textContent = title;
      flat.appendChild(t);
      if (panel) {
        panel.removeAttribute('style');
        panel.querySelectorAll('[style*="height"]').forEach((e) => e.style.removeProperty('height'));
        const body = document.createElement('div');
        body.className = 'nxo-tabs__panel';
        body.append(...panel.childNodes);
        flat.appendChild(body);
      }
    }
    wrapper.replaceWith(flat);
    stats.tabs += 1;
  }
  await expandIn(article);

  // 3. Links: same-site page links make no sense in an offline document.
  //    DOCX keeps them symbolic (nxo:<page>#<anchor>); Python resolves them per output document.
  const here = location.origin;
  for (const a of [...article.querySelectorAll('a[href]')]) {
    const url = new URL(a.getAttribute('href'), location.href);
    if (url.origin !== here) continue;
    if (opts.symbolicLinks) {
      a.setAttribute('href', 'nxo:' + decodeURIComponent(url.pathname.replace(/^\//, '')) + url.hash);
      stats.links += 1;
      continue;
    }
    if (url.pathname === location.pathname && url.hash) continue; // in-page anchor: keep
    stats.links += 1;
    if (opts.linkBaseUrl) {
      a.setAttribute('href', opts.linkBaseUrl.replace(/\/?$/, '/') + url.pathname.replace(/^\//, '') + url.hash);
    } else {
      a.removeAttribute('href');
      a.classList.add('nxo-unlinked');
    }
  }

  // 4. Make sure every image is loaded before printing.
  const imgs = [...article.querySelectorAll('img')];
  imgs.forEach((i) => { i.loading = 'eager'; });
  await Promise.all(imgs.map((i) => (i.complete ? Promise.resolve() : i.decode().catch(() => {}))));
  stats.images = imgs.length;

  document.documentElement.classList.add('nxo-print');
  return stats;
};
