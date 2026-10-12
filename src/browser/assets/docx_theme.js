// Reads the computed Writerside light theme from real rendered elements of a flattened topic (what readers see).
// Returns raw CSS values; Python converts them to Word units and falls back to measured defaults for anything
// a topic does not contain.
() => {
  const art = document.querySelector('article.app__article .article') || document.querySelector('article.app__article');
  if (!art) return {};
  const visible = (e) => e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const pick = (sel) => [...art.querySelectorAll(sel)].find(visible) || null;
  const css = (e, props) => {
    if (!e) return null;
    const c = getComputedStyle(e);
    return Object.fromEntries(props.map((p) => [p, c[p]]));
  };
  const text = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'color'];
  const out = {};
  const put = (k, v) => { if (v) out[k] = v; };
  put('p', css(pick('p'), text));
  put('h1', css(pick('h1:not(.a11y-title)'), text));
  put('h2', css(pick('h2:not(.a11y-title)'), text));
  put('h3', css(pick('h3:not(.a11y-title)'), text));
  put('h4', css(pick('h4:not(.a11y-title)'), text));
  put('code', css(pick('p code, li code, td code'), [...text, 'backgroundColor']));
  const pre = pick('pre');
  put('pre', css(pre, text));
  put('preBox', css(pre && (pre.closest('.code-block') || pre.parentElement), ['backgroundColor', 'borderRadius']));
  put('a', css(pick('p a[href]:not(.permalink), li a[href]:not(.permalink)'),
    ['color', 'textDecorationLine', 'borderBottomColor', 'borderBottomWidth', 'borderBottomStyle']));
  for (const t of ['note', 'tip', 'warning']) {
    put(t, css(pick(`.prompt__wrapper--type-${t}`), ['backgroundColor', 'color', 'paddingTop', 'paddingLeft']));
  }
  put('th', css(pick('th'), ['backgroundColor', 'borderTopColor', 'paddingTop', 'paddingLeft', 'fontWeight']));
  put('td', css(pick('td'), ['borderTopColor', 'paddingTop', 'paddingLeft']));
  return out;
};
