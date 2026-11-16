/* Shared helpers for every page: money formatting, JSON POST, toasts,
   debounced search, mobile nav and global keyboard shortcuts. */
(function () {
  const SI = {};

  SI.money = (value, places = 2) => {
    const n = Number(value) || 0;
    const text = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: places, maximumFractionDigits: places });
    return (n < 0 ? '-' : '') + '৳' + text;
  };

  SI.escape = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  SI.postJSON = async (url, data) => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF },
      body: JSON.stringify(data),
      credentials: 'same-origin',
    });
    let body = {};
    try { body = await res.json(); } catch (e) { body = { ok: false, error: 'The server returned an unexpected response.' }; }
    if (!res.ok && body.ok !== false) body = { ok: false, error: 'Request failed (' + res.status + ').' };
    return body;
  };

  SI.getJSON = async (url) => {
    const res = await fetch(url, { credentials: 'same-origin' });
    try { return await res.json(); } catch (e) { return {}; }
  };

  SI.debounce = (fn, ms = 180) => {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  };

  SI.toast = (text, kind = 'success') => {
    const box = document.getElementById('toasts');
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.setAttribute('role', 'status');
    el.innerHTML = '<i class="bi ' + (kind === 'error' ? 'bi-exclamation-circle-fill' : 'bi-check-circle-fill') + '"></i><div></div><button class="close" aria-label="Dismiss"><i class="bi bi-x-lg"></i></button>';
    el.querySelector('div').textContent = text;
    box.appendChild(el);
    autoHide(el);
  };

  function autoHide(el) {
    const ms = el.classList.contains('error') ? 7000 : 4000;
    setTimeout(() => el.remove(), ms);
  }

  document.addEventListener('click', (e) => {
    const close = e.target.closest('.toast .close');
    if (close) close.closest('.toast').remove();
    if (e.target.closest('[data-nav-toggle]')) document.body.classList.add('nav-open');
    if (e.target.closest('[data-nav-close]')) document.body.classList.remove('nav-open');
  });
  document.querySelectorAll('#toasts .toast').forEach(autoHide);

  // F2 opens the POS from anywhere (the POS page handles it itself).
  document.addEventListener('keydown', (e) => {
    if (e.key === 'F2' && !document.body.dataset.pos) {
      e.preventDefault();
      window.location.href = '/pos/';
    }
  });

  /* Product combobox used by POS and Stock screens.
     opts: {input, list, url(q) -> string, onPick(product), render(product) -> html, minChars} */
  SI.combo = (opts) => {
    const { input, list } = opts;
    let items = [], active = -1, seq = 0;

    const close = () => { list.hidden = true; active = -1; };
    const paint = () => {
      if (!items.length) {
        list.innerHTML = '<div class="combo-empty">No matching products</div>';
      } else {
        list.innerHTML = items.map((p, i) =>
          '<div class="combo-item' + (i === active ? ' active' : '') + (opts.disabled && opts.disabled(p) ? ' disabled' : '') + '" data-i="' + i + '">' + opts.render(p) + '</div>'
        ).join('');
      }
      list.hidden = false;
    };
    const pick = (i) => {
      const p = items[i];
      if (!p || (opts.disabled && opts.disabled(p))) return;
      opts.onPick(p);
      input.value = '';
      close();
    };
    const search = SI.debounce(async () => {
      const q = input.value.trim();
      if (q.length < (opts.minChars ?? 1)) { close(); return; }
      const mine = ++seq;
      const data = await SI.getJSON(opts.url(q));
      if (mine !== seq) return;
      items = data.results || [];
      active = items.length ? 0 : -1;
      paint();
    });

    input.addEventListener('input', search);
    input.addEventListener('focus', () => { if (input.value.trim()) search(); });
    input.addEventListener('keydown', (e) => {
      if (list.hidden) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); paint(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (active >= 0) pick(active); }
      else if (e.key === 'Escape') { close(); }
    });
    list.addEventListener('mousedown', (e) => {
      const row = e.target.closest('.combo-item');
      if (row) { e.preventDefault(); pick(Number(row.dataset.i)); }
    });
    document.addEventListener('click', (e) => { if (!list.contains(e.target) && e.target !== input) close(); });
    return { close, refresh: search };
  };

  // ----- Themes: saved in a cookie so the server renders the right one first.
  SI.setTheme = (key) => {
    document.body.classList.add('theme-switching');
    document.documentElement.dataset.theme = key;
    document.cookie = 'si_theme=' + key + '; path=/; max-age=31536000; SameSite=Lax';
    document.querySelectorAll('[data-set-theme]').forEach((b) => b.classList.toggle('selected', b.dataset.setTheme === key));
    window.dispatchEvent(new CustomEvent('si:theme', { detail: key }));
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove('theme-switching')));
  };

  document.addEventListener('click', (e) => {
    const setter = e.target.closest('[data-set-theme]');
    if (setter) { SI.setTheme(setter.dataset.setTheme); }
    const toggle = e.target.closest('[data-menu-toggle]');
    document.querySelectorAll('.menu-pop').forEach((pop) => {
      const mine = toggle && toggle.parentElement.contains(pop);
      if (mine) pop.hidden = !pop.hidden;
      else if (!pop.contains(e.target) || setter) pop.hidden = true;
    });
  });

  // ----- Command palette (Ctrl/⌘ + K): pages, products and customers.
  const palette = document.getElementById('cmdk');
  if (palette) {
    const input = document.getElementById('cmdkInput');
    const list = document.getElementById('cmdkList');
    let items = [], active = 0, seq = 0;

    const pageItems = (q) => (window.SI_PAGES || [])
      .filter(([name]) => !q || name.toLowerCase().includes(q.toLowerCase()))
      .map(([name, url, icon]) => ({ group: 'Pages', title: name, url, icon }));

    function paint() {
      if (!items.length) { list.innerHTML = '<div class="combo-empty">Nothing found</div>'; return; }
      let group = null;
      list.innerHTML = items.map((it, i) => {
        const head = it.group !== group ? '<div class="cmdk-group">' + SI.escape(it.group) + '</div>' : '';
        group = it.group;
        return head + '<div class="cmdk-item' + (i === active ? ' active' : '') + '" data-i="' + i + '">' +
          '<span class="ic"><i class="bi ' + it.icon + '"></i></span>' +
          '<div style="min-width:0"><div class="ellipsis strong">' + SI.escape(it.title) + '</div>' + (it.meta ? '<div class="meta ellipsis">' + SI.escape(it.meta) + '</div>' : '') + '</div>' +
          (it.right ? '<div class="right">' + it.right + '</div>' : '') + '</div>';
      }).join('');
      const el = list.querySelector('.cmdk-item.active');
      if (el) el.scrollIntoView({ block: 'nearest' });
    }

    const search = SI.debounce(async () => {
      const q = input.value.trim();
      const mine = ++seq;
      items = pageItems(q).slice(0, q ? 5 : 8);
      active = 0;
      paint();
      if (q.length < 2) return;
      const [products, customers] = await Promise.all([
        SI.getJSON(window.SI_URLS.productSearch + '?q=' + encodeURIComponent(q)),
        SI.getJSON(window.SI_URLS.customerSearch + '?q=' + encodeURIComponent(q)),
      ]);
      if (mine !== seq) return;
      const prod = (products.results || []).slice(0, 7).map((p) => ({
        group: 'Products', title: p.name, meta: p.sku + ' · ' + p.category, icon: 'bi-box',
        right: SI.money(p.price) + '<div class="meta">' + (p.qty > 0 ? p.qty + ' in stock' : 'Out of stock') + '</div>',
        url: window.SI_URLS.productBase + p.id + '/',
      }));
      const cust = (customers.results || []).slice(0, 4).map((c) => ({
        group: 'Customers', title: c.name || c.phone, meta: c.name ? c.phone : '', icon: 'bi-person',
        right: c.orders + ' orders', url: window.SI_URLS.customerBase + c.id + '/',
      }));
      items = [...prod, ...cust, ...items];
      active = 0;
      paint();
    }, 150);

    SI.openPalette = () => {
      palette.hidden = false;
      input.value = '';
      search();
      setTimeout(() => input.focus(), 0);
    };
    const closePalette = () => { palette.hidden = true; };

    input.addEventListener('input', search);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); paint(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) window.location.href = items[active].url; }
      else if (e.key === 'Escape') { closePalette(); }
    });
    list.addEventListener('mousemove', (e) => {
      const row = e.target.closest('.cmdk-item');
      if (row && Number(row.dataset.i) !== active) { active = Number(row.dataset.i); paint(); }
    });
    list.addEventListener('click', (e) => {
      const row = e.target.closest('.cmdk-item');
      if (row) window.location.href = items[Number(row.dataset.i)].url;
    });
    palette.addEventListener('mousedown', (e) => { if (e.target === palette) closePalette(); });
    document.addEventListener('click', (e) => { if (e.target.closest('[data-cmdk]')) SI.openPalette(); });
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        palette.hidden ? SI.openPalette() : closePalette();
      } else if (e.key === 'Escape' && !palette.hidden) {
        closePalette();
      }
    });
  }

  window.SI = SI;
})();
