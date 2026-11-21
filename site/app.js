// Renders site/data/*.json. All feed text goes through textContent — never innerHTML.
(function () {
  "use strict";
  const DAY_MS = 24 * 3600 * 1000;
  const MAX_CHARS = 280;
  const state = { meta: null, runs: [], articles: [], tab: "all" };

  function el(tag, opts, children) {
    const node = document.createElement(tag);
    if (opts) {
      if (opts.cls) node.className = opts.cls;
      if (opts.text != null) node.textContent = opts.text;
      if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
    }
    (children || []).forEach((c) => c && node.appendChild(c));
    return node;
  }

  function safeHref(url) {
    try {
      const u = new URL(url);
      return u.protocol === "http:" || u.protocol === "https:" ? u.href : "#";
    } catch (e) {
      return "#";
    }
  }

  const fmtFull = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const fmtTime = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

  function ago(date) {
    const mins = Math.max(0, Math.round((Date.now() - date) / 60000));
    if (mins < 60) return mins + "m ago";
    return Math.floor(mins / 60) + "h ago";
  }

  async function load(name, fallback) {
    try {
      const res = await fetch("data/" + name + ".json?t=" + Date.now());
      if (!res.ok) return fallback;
      return await res.json();
    } catch (e) {
      return fallback;
    }
  }

  function catName(id) {
    const c = (state.meta.categories || []).find((x) => x.id === id);
    return c ? c.name : id;
  }

  function renderTabs() {
    const nav = document.getElementById("tabs");
    nav.replaceChildren();
    const tabs = [{ id: "all", name: "All" }].concat(state.meta.categories || []);
    tabs.forEach((t) => {
      const b = el("button", { text: t.name, attrs: { type: "button", "aria-pressed": String(t.id === state.tab) } });
      b.addEventListener("click", () => {
        location.hash = t.id;
      });
      nav.appendChild(b);
    });
  }

  function pickCard(pick, catId) {
    const published = new Date(pick.published_at);
    const copy = el("button", { cls: "copy", text: "Copy", attrs: { type: "button" } });
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pick.post);
        copy.textContent = "Copied";
      } catch (e) {
        copy.textContent = "Copy failed";
      }
      setTimeout(() => (copy.textContent = "Copy"), 1500);
    });
    const row = el("div", { cls: "row" }, [
      copy,
      el("span", { cls: "muted", text: pick.post.length + "/" + MAX_CHARS }),
    ].concat((pick.flags || []).map((f) => el("span", { cls: "badge", text: "⚠ " + f }))));
    const link = el("a", { text: pick.title, attrs: { href: safeHref(pick.url), target: "_blank", rel: "noopener noreferrer" } });
    const meta = el("div", { cls: "meta" }, [
      el("span", { text: pick.source + " · " + fmtFull.format(published) + " · " + ago(published) + " · " }),
      link,
    ]);
    return el("article", { cls: "card" }, [
      state.tab === "all" ? el("div", { cls: "cat-label", text: catName(catId) }) : null,
      el("p", { cls: "post", text: pick.post }),
      row,
      pick.reason ? el("p", { cls: "reason", text: pick.reason }) : null,
      meta,
    ]);
  }

  function renderPicks() {
    const box = document.getElementById("picks");
    box.replaceChildren();
    const cutoff = Date.now() - DAY_MS;
    const runs = state.runs.filter((r) => new Date(r.run_at) >= cutoff).sort((a, b) => b.run_at.localeCompare(a.run_at));
    let shown = 0;
    runs.forEach((run) => {
      const items = [];
      Object.entries(run.categories || {}).forEach(([catId, cat]) => {
        if (state.tab !== "all" && state.tab !== catId) return;
        if (cat.status === "curation_failed") {
          items.push(el("p", { cls: "failed", text: (state.tab === "all" ? catName(catId) + ": " : "") + "Curation failed this run" }));
        }
        (cat.picks || []).forEach((p) => items.push(pickCard(p, catId)));
      });
      if (!items.length) return;
      shown += items.length;
      box.appendChild(el("h3", { text: fmtTime.format(new Date(run.run_at)) + " run" }));
      items.forEach((i) => box.appendChild(i));
    });
    if (!shown) box.appendChild(el("p", { cls: "empty", text: "Nothing new in the last 24 hours." }));
  }

  function renderArticles() {
    const list = document.getElementById("articles");
    list.replaceChildren();
    const items = state.articles
      .filter((a) => state.tab === "all" || a.category === state.tab)
      .sort((a, b) => b.published_at.localeCompare(a.published_at));
    if (!items.length) {
      list.appendChild(el("li", { cls: "empty", text: "No articles." }));
      return;
    }
    items.forEach((a) => {
      const d = new Date(a.published_at);
      list.appendChild(el("li", null, [
        el("span", { cls: "when", text: fmtFull.format(d) }),
        el("div", null, [
          el("a", { text: a.title, attrs: { href: safeHref(a.url), target: "_blank", rel: "noopener noreferrer" } }),
          el("span", { cls: "src", text: a.source + (state.tab === "all" ? " · " + catName(a.category) : "") + " · " + ago(d) }),
        ]),
      ]));
    });
  }

  function render() {
    const valid = ["all"].concat((state.meta.categories || []).map((c) => c.id));
    const wanted = decodeURIComponent(location.hash.slice(1));
    state.tab = valid.includes(wanted) ? wanted : "all";
    renderTabs();
    renderPicks();
    renderArticles();
  }

  async function init() {
    const [meta, runs, articles] = await Promise.all([load("meta", null), load("picks", []), load("articles", [])]);
    const lastRun = document.getElementById("last-run");
    if (!meta) {
      lastRun.textContent = "No data yet. The first run hasn't published.";
      document.querySelector("main").replaceChildren();
      return;
    }
    state.meta = meta;
    state.runs = Array.isArray(runs) ? runs : [];
    state.articles = Array.isArray(articles) ? articles : [];
    const d = new Date(meta.last_run_at);
    lastRun.textContent = "Last run: " + fmtFull.format(d) + " (" + ago(d) + ")";
    window.addEventListener("hashchange", render);
    render();
  }

  init();
})();
