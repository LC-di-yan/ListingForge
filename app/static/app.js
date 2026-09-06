/* ListingForge 前端逻辑（vanilla JS，无构建依赖） */
const state = { meta: null, product: null, images: null, listings: [], tasks: [], step: 1 };
const PLATFORM_LABEL = { amazon: "亚马逊", aliexpress: "速卖通", tiktok_shop: "TikTok Shop", shopify: "Shopify" };
const LANG_LABEL = { en: "英语", es: "西语", pt: "葡语", ar: "阿语" };

async function api(path, opts = {}) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let msg = resp.status + " " + resp.statusText;
    try { msg = (await resp.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return resp.json();
}

function toast(text, isErr = false) {
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

async function formPost(path, data) {
  const fd = new FormData();
  Object.entries(data).forEach(([k, v]) => {
    if (v === null || v === undefined) return;
    if (Array.isArray(v)) v.forEach(x => fd.append(k, x)); else fd.append(k, v);
  });
  return api(path, { method: "POST", body: fd });
}

const $ = s => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };

/* 服务器绝对路径 -> /data 静态 URL（兼容 Windows 反斜杠） */
function toWeb(p) {
  const norm = String(p).replace(/\\/g, "/");
  const i = norm.indexOf("data/");
  return i >= 0 ? "/data/" + norm.slice(i + 5) : p;
}


/* ================= v1.5 前端体验层（零依赖） ================= */

/* ---- 主题（localStorage 持久化 + 系统偏好默认） ---- */
function applyTheme(t) {
  document.documentElement.classList.toggle("dark", t === "dark");
  $("#themeToggle").textContent = t === "dark" ? "☀️" : "🌙";
  localStorage.setItem("lf-theme", t);
}
function toggleTheme() {
  applyTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
}

/* ---- promise 化确认模态（替代原生 confirm） ---- */
function uiConfirm(message, title) {
  title = title || "请确认";
  return new Promise(resolve => {
    const mask = el("div", "modal-mask");
    mask.innerHTML = '<div class="modal" role="alertdialog" aria-modal="true" aria-label="' + esc(title) + '">'
      + "<h4>" + esc(title) + "</h4><p>" + esc(message) + "</p>"
      + '<div class="modal-actions"><button class="btn ghost" data-act="cancel">取消</button>'
      + '<button class="btn primary" data-act="ok">确认</button></div></div>';
    const done = v => { mask.remove(); resolve(v); };
    mask.addEventListener("click", e => {
      if (e.target === mask) return done(false);
      const act = e.target.closest("[data-act]");
      if (act) done(act.dataset.act === "ok");
    });
    document.body.appendChild(mask);
    mask.querySelector("[data-act='ok']").focus();
  });
}

/* ---- 图片灯箱 ---- */
function openLightbox(src, caption) {
  const box = el("figure", "lightbox",
    '<img src="' + src + '" alt="' + esc(caption || "") + '"><figcaption>'
    + esc(caption || "") + ' · 点击任意处或 ESC 关闭</figcaption>');
  box.addEventListener("click", () => box.remove());
  document.body.appendChild(box);
  const onKey = e => { if (e.key === "Escape") { box.remove(); document.removeEventListener("keydown", onKey); } };
  document.addEventListener("keydown", onKey);
}
function initLightbox() {
  document.addEventListener("click", e => {
    const img = e.target.closest("img[data-lightbox], .variants img, .img-preview img.big");
    if (img && img.naturalWidth > 0) {
      const cap = img.alt || (img.closest(".v") && img.closest(".v").querySelector("small")?.textContent) || "图片预览";
      openLightbox(img.src, cap);
    }
  });
}

/* ---- 复制到剪贴板 ---- */
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    if (btn) {
      btn.classList.add("done"); btn.textContent = "✓ 已复制";
      setTimeout(() => { btn.classList.remove("done"); btn.textContent = "复制"; }, 1600);
    } else toast("已复制到剪贴板");
  } catch (e) { toast("复制失败：" + e.message, true); }
}
function initCopyButtons() {
  document.addEventListener("click", e => {
    const b = e.target.closest(".copy-btn");
    if (b) copyText(decodeURIComponent(b.dataset.copy || ""), b);
  });
}

/* ---- CountUp 数字动效 ---- */
function countUp(node, target, dur) {
  dur = dur || 700;
  const t0 = performance.now();
  (function frame(now) {
    const k = Math.min(1, (now - t0) / dur);
    node.textContent = Math.round(target * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(frame);
  })(performance.now());
}

/* ---- 成功彩带（灵感：catdad/canvas-confetti，内联零依赖实现） ---- */
function fireConfetti() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const cv = $("#confettiCanvas");
  cv.width = innerWidth; cv.height = innerHeight;
  const ctx = cv.getContext("2d");
  const colors = ["#4f46e5", "#7c6cff", "#8cecb4", "#fbbf24", "#f87171", "#60a5fa"];
  const parts = Array.from({ length: 150 }, () => ({
    x: innerWidth / 2 + (Math.random() - .5) * 280, y: innerHeight * 0.7,
    vx: (Math.random() - .5) * 13, vy: -(7 + Math.random() * 8),
    s: 5 + Math.random() * 6, r: Math.random() * Math.PI, vr: (Math.random() - .5) * .3,
    c: colors[Math.floor(Math.random() * colors.length)], life: 90 + Math.random() * 40,
  }));
  (function frame() {
    ctx.clearRect(0, 0, cv.width, cv.height);
    let alive = false;
    for (const pt of parts) {
      if (pt.life <= 0) continue;
      alive = true;
      pt.vy += 0.22; pt.x += pt.vx; pt.y += pt.vy; pt.r += pt.vr; pt.life--;
      ctx.save(); ctx.translate(pt.x, pt.y); ctx.rotate(pt.r);
      ctx.globalAlpha = Math.max(0, Math.min(1, pt.life / 40));
      ctx.fillStyle = pt.c; ctx.fillRect(-pt.s / 2, -pt.s / 2, pt.s, pt.s * 0.6);
      ctx.restore();
    }
    if (alive) requestAnimationFrame(frame); else ctx.clearRect(0, 0, cv.width, cv.height);
  })();
}

/* ---- ⌘K 命令面板（灵感：cmdk / GitHub palette，轻量自研） ---- */
let palSel = 0, palItems = [];
function paletteCommands() {
  const cmds = [
    { icon: "①", label: "商品录入", hint: "步骤 1", run: () => goto(1) },
    { icon: "②", label: "AI 结构化", hint: "步骤 2", run: () => goto(2) },
    { icon: "③", label: "文案生成", hint: "步骤 3", run: () => goto(3) },
    { icon: "④", label: "规则校验", hint: "步骤 4", run: () => goto(4) },
    { icon: "⑤", label: "审核放行", hint: "步骤 5", run: () => goto(5) },
    { icon: "⑥", label: "一键上架", hint: "步骤 6", run: () => goto(6) },
    { icon: "🌓", label: "切换亮色/暗色主题", hint: "快捷键 D", run: toggleTheme },
    { icon: "⬇", label: "导出全部物料 CSV", hint: "需已生成物料",
      run: () => state.product && (window.location.href = "/api/products/" + state.product.id + "/export") },
  ];
  document.querySelectorAll(".history-item").forEach((item, i) => {
    const name = item.querySelector("b").textContent;
    cmds.push({ icon: "📦", label: "切换到「" + name + "」", hint: "历史商品 " + (i + 1), run: () => item.click() });
  });
  return cmds;
}
function openPalette() {
  if (document.querySelector(".palette-mask")) return;
  const mask = el("div", "palette-mask",
    '<div class="palette" role="dialog" aria-label="命令面板">'
    + '<input type="text" placeholder="搜索步骤 / 商品 / 操作…" aria-label="命令搜索"><div class="pal-list"></div></div>');
  const input = mask.querySelector("input"), list = mask.querySelector(".pal-list");
  const render = q => {
    palItems = paletteCommands().filter(c => !q || (c.label + c.hint).toLowerCase().includes(q.toLowerCase()));
    palSel = 0;
    list.innerHTML = palItems.length
      ? palItems.map((c, i) => '<div class="pal-item' + (i === 0 ? " sel" : "") + '" data-i="' + i
        + '"><span class="pal-icon">' + c.icon + '</span><span>' + esc(c.label)
        + '</span><small>' + esc(c.hint) + "</small></div>").join("")
      : '<div class="pal-empty">没有匹配的命令</div>';
  };
  const close = () => mask.remove();
  const exec = i => { close(); if (palItems[i]) palItems[i].run(); };
  input.addEventListener("input", () => render(input.value));
  input.addEventListener("keydown", e => {
    const items = list.querySelectorAll(".pal-item");
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      palSel = (palSel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(1, items.length);
      items.forEach((n, i) => n.classList.toggle("sel", i === palSel));
      items[palSel] && items[palSel].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") exec(palSel);
  });
  list.addEventListener("click", e => { const it = e.target.closest(".pal-item"); if (it) exec(+it.dataset.i); });
  mask.addEventListener("click", e => { if (e.target === mask) close(); });
  document.body.appendChild(mask);
  input.focus();
  render("");
}

/* ---- 键盘快捷键（输入聚焦时忽略） ---- */
function initShortcuts() {
  document.addEventListener("keydown", e => {
    const tag = (e.target.tagName || "").toLowerCase();
    const typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key >= "1" && e.key <= "6") goto(+e.key);
    else if (e.key.toLowerCase() === "d") toggleTheme();
    else if (e.key === "?") toast("快捷键：1-6 切换步骤 · Ctrl/⌘+K 命令面板 · D 切换主题");
  });
}

/* ---- 顶部进度条 ---- */
function updateProgress() {
  const bar = $("#topProgress");
  if (bar) bar.style.width = ((maxStep() - 1) / 5 * 100) + "%";
}

function showSkeleton(sel, on) {
  const node = $(sel);
  if (node) node.classList.toggle("hidden", !on);
}

/* ---------------- 步骤导航 ---------------- */
function maxStep() {
  if (state.tasks.length) return 6;
  if (state.listings.some(l => l.status === "approved")) return 6;
  if (state.listings.length) return 5;
  if (state.product && state.product.pim) return 4;
  if (state.product) return 3;
  return 1;
}

function goto(step) {
  if (step > maxStep()) { toast("请先完成前面的步骤", true); return; }
  state.step = step;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  $("#panel-" + step).classList.add("active");
  document.querySelectorAll("#steps li").forEach(li => {
    const s = +li.dataset.step;
    li.classList.toggle("active", s === step);
    li.classList.toggle("done", s < step);
    li.classList.toggle("locked", s > maxStep());
  });
  updateProgress();
  if (step === 2) renderStructure();
  if (step === 4) renderReport();
  if (step === 5) renderReview();
  if (step === 6) {
    $("#btnExportCsv").style.display = state.listings.length ? "" : "none";
    if (state.tasks.length) renderTasks();
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------------- 商品卡片（侧栏） ---------------- */
function renderProductCard() {
  const p = state.product;
  if (!p) return;
  $("#pcImg").src = p.image_path ? "/data/uploads/raw/" + p.image_path.split(/[\\/]/).pop() : "/static/placeholder.svg";
  $("#pcName").textContent = p.name;
  const c = p.counts;
  $("#pcMeta").innerHTML = `类目 ${p.category || "-"} · $${p.price}<br>状态：${statusText(p.status)} · ID #${p.id}`
    + (c && c.listings ? `<br>物料 ${c.listings} 条 · 已放行 ${c.approved}` : "");
  $("#btnDeleteProduct").style.display = "";
}

/* ---------------- 会话恢复 / 历史商品切换 ---------------- */
async function restoreSession() {
  const ps = await api("/api/products");
  renderHistory(ps, null);
  if (ps.length) await switchProduct(ps[0].id, { silent: true });
}

async function switchProduct(pid, opts = {}) {
  if (state.product && state.product.id === pid && !opts.force) return;
  try {
    const p = await api(`/api/products/${pid}`);
    state.product = p;
    state.images = p.images || null;
    state.listings = await api(`/api/products/${pid}/listings`);
    state.tasks = await api(`/api/products/${pid}/tasks`);
    renderProductCard();
    renderHistory(await api("/api/products"), pid);
    if (state.step >= 2) renderStructure();
    if (!opts.silent) {
      toast(`已切换到「${p.name}」`);
      goto(maxStep());
    }
  } catch (e) { toast(e.message, true); }
}

async function renderHistory(ps, activeId) {
  if (!ps.length) { $("#historyCard").style.display = "none"; return; }
  $("#historyCard").style.display = "";
  const box = $("#historyList");
  box.innerHTML = "";
  ps.slice(0, 8).forEach(p => {
    const row = el("div", "history-item" + (p.id === activeId || (activeId === null && state.product && p.id === state.product.id) ? " on" : ""));
    row.innerHTML = `<span class="hi-dot ${p.status}"></span><div class="hi-body"><b>${esc(p.name)}</b>
      <small>#${p.id} · ${statusText(p.status)}</small></div>`;
    row.onclick = () => switchProduct(p.id);
    box.appendChild(row);
  });
}

function statusText(s) {
  return { created: "已录入", structured: "已结构化", generated: "已生成", published: "已上架" }[s] || s;
}

/* ---------------- Step 1 样例与自建 ---------------- */
async function loadSamples() {
  const samples = await api("/api/samples");
  const grid = $("#sampleGrid");
  grid.innerHTML = "";
  samples.forEach(s => {
    const card = el("div", "sample-card");
    card.innerHTML = `<img src="/assets/${s.image}" alt="">
      <div class="body"><b>${s.name}</b>
      <div class="feat">${s.features.join(" · ")}</div>
      <div class="price">$${s.price.toFixed(2)} · ${s.target_market}</div></div>`;
    card.onclick = () => createSample(s.key);
    grid.appendChild(card);
  });
}

async function createSample(key) {
  try {
    toast("正在创建商品…");
    state.product = await api(`/api/products/sample/${key}`, { method: "POST" });
    state.images = null; state.listings = []; state.tasks = [];
    renderProductCard(); refreshHistoryMeta(); toast("商品已创建，进入 AI 结构化");
    goto(2);
  } catch (e) { toast(e.message, true); }
}

async function createCustom() {
  try {
    const fd = new FormData();
    fd.append("name", $("#fName").value || "未命名商品");
    fd.append("category", $("#fCat").value);
    fd.append("features", $("#fFeat").value);
    fd.append("price", $("#fPrice").value || "0");
    fd.append("target_market", $("#fMarket").value);
    const img = $("#fImg").files[0];
    if (img) fd.append("image", img);
    toast("正在创建商品…");
    state.product = await api("/api/products", { method: "POST", body: fd });
    state.images = null; state.listings = []; state.tasks = [];
    renderProductCard(); refreshHistoryMeta(); goto(2);
  } catch (e) { toast(e.message, true); }
}

/* ---------------- Step 2 结构化 ---------------- */
async function doStructure() {
  if (!state.product) return;
  $("#btnStructure").disabled = true; $("#btnStructure").textContent = "⏳ AI 识别与结构化中…";
  showSkeleton("#structureSkeleton", true);
  try {
    const r = await api(`/api/products/${state.product.id}/structure`, { method: "POST" });
    state.product = { ...r.product, images: r.images }; state.images = r.images;
    renderProductCard(); renderStructure(); refreshHistoryMeta();
  } catch (e) { toast(e.message, true); }
  showSkeleton("#structureSkeleton", false);
  $("#btnStructure").disabled = false; $("#btnStructure").textContent = "🧠 开始 AI 结构化 + 图片管线";
}

function renderStructure() {
  const pim = state.product.pim;
  if (!pim) return;
  $("#structureResult").classList.remove("hidden");
  $("#pimSource").textContent = "来源: " + (pim.source || "mock");
  $("#pimAttrs").innerHTML = Object.entries(pim.attributes || {})
    .map(([k, v]) => `<div class="kv"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("")
    + `<div class="kv"><b>目标人群</b><span>${esc(pim.target_audience || "-")}</span></div>`
    + `<div class="kv"><b>类目(EN)</b><span>${esc(pim.category_en || "-")}</span></div>`;
  $("#pimPoints").innerHTML = (pim.selling_points || []).map(s => `<li>${esc(s)}</li>`).join("");
  $("#pimKeywords").innerHTML = (pim.keywords || []).map(k => `<span class="chip">${esc(k)}</span>`).join("");
  if (state.images) {
    $("#imgMain").src = toWeb(state.images.main);
    const v = $("#imgVariants"); v.innerHTML = "";
    Object.entries(state.images.variants).forEach(([k, path]) => {
      const d = el("div", "v");
      d.innerHTML = `<img src="${toWeb(path)}"><small>${k.replace("x", ":")}</small>`;
      v.appendChild(d);
    });
    const scene = el("div", "v");
    scene.innerHTML = `<img src="${toWeb(state.images.scene)}"><small>场景图</small>`;
    v.appendChild(scene);
  }
}

/* ---------------- Step 3 生成 ---------------- */
function renderPicks() {
  const m = state.meta;
  const pp = $("#pickPlatforms"), pl = $("#pickLanguages");
  pp.innerHTML = ""; pl.innerHTML = "";
  m.platforms.forEach(p => {
    const c = el("span", "chip on", `${p.label} <small>(${p.rule_count}条规则)</small>`);
    c.dataset.key = p.key; c.onclick = () => c.classList.toggle("on");
    pp.appendChild(c);
  });
  m.languages.forEach(l => {
    const c = el("span", "chip" + (l.key === "en" ? " on" : ""), l.label);
    c.dataset.key = l.key; c.onclick = () => c.classList.toggle("on");
    pl.appendChild(c);
  });
}

async function doGenerate() {
  const platforms = [...document.querySelectorAll("#pickPlatforms .chip.on")].map(c => c.dataset.key);
  const languages = [...document.querySelectorAll("#pickLanguages .chip.on")].map(c => c.dataset.key);
  if (!platforms.length || !languages.length) { toast("请至少选择一个平台与一种语言", true); return; }
  if (state.listings.some(l => ["approved", "published"].includes(l.status))
      && !(await uiConfirm("重新生成将清除当前已放行/已上架的旧物料，并重新校验放行状态。", "重新生成？"))) {
    return;  // 重建式生成会重置审核状态，需用户确认
  }
  $("#btnGenerate").disabled = true; $("#btnGenerate").textContent = "⏳ 多平台文案链生成中…";
  showSkeleton("#genSkeleton", true);
  try {
    const r = await formPost(`/api/products/${state.product.id}/generate`, { platforms, languages });
    state.listings = await api(`/api/products/${state.product.id}/listings`);
    $("#generateResult").classList.remove("hidden");
    $("#genStats").innerHTML = `
      <div class="stat"><b data-count="${state.listings.length}">0</b><span>Listing 物料</span></div>
      <div class="stat"><b>${platforms.length} × ${languages.length}</b><span>平台 × 语言</span></div>
      <div class="stat"><b data-count="${new Set(state.listings.map(l => l.language)).size}">0</b><span>覆盖语言</span></div>`;
    document.querySelectorAll("#genStats b[data-count]").forEach(b => countUp(b, +b.dataset.count));
    const prev = $("#genPreview"); prev.innerHTML = "";
    const sorted = [...state.listings].sort((a, b) => (a.language === "en" ? -1 : 1) - (b.language === "en" ? -1 : 1));
    sorted.slice(0, 3).forEach(l => prev.appendChild(listingCard(l, false)));
    const expand = $("#btnExpandAll");
    if (state.listings.length > 3) {
      expand.classList.remove("hidden");
      expand.textContent = `展开全部 ${state.listings.length} 条物料 ▾`;
      expand.onclick = () => {
        const showing = prev.children.length;
        if (showing < state.listings.length) {
          prev.innerHTML = "";
          sorted.forEach(l => prev.appendChild(listingCard(l, false)));
          expand.textContent = "收起 ▴";
        } else {
          prev.innerHTML = "";
          sorted.slice(0, 3).forEach(l => prev.appendChild(listingCard(l, false)));
          expand.textContent = `展开全部 ${state.listings.length} 条物料 ▾`;
        }
      };
    } else {
      expand.classList.add("hidden");
    }
    state.product.status = "generated"; renderProductCard(); refreshHistoryMeta();
    toast(`已生成 ${state.listings.length} 条 Listing`);
  } catch (e) { toast(e.message, true); }
  showSkeleton("#genSkeleton", false);
  $("#btnGenerate").disabled = false; $("#btnGenerate").textContent = "✨ 一键生成全套 Listing";
}

function listingCard(l, editable) {
  const c = el("div", "card listing-card");
  const rtl = l.language === "ar" ? ' dir="rtl" style="text-align:right"' : "";  // 阿语从右向左排版
  const statusBadge = `<span class="badge ${l.status}">${{ draft: "草稿", approved: "已放行", rejected: "已驳回", published: "已上架" }[l.status] || l.status}</span>`;
  const copyBtn = text => `<button class="copy-btn" data-copy="${encodeURIComponent(text)}" aria-label="复制内容">复制</button>`;
  c.innerHTML = `<div class="lc-head"><b>${PLATFORM_LABEL[l.platform]} · ${LANG_LABEL[l.language] || l.language}</b>${statusBadge}</div>
    <div class="lc-field"><label>标题 (${l.title.length} 字符)</label>${editable ? `<input class="ed-title" value=""${rtl}>` : `${copyBtn(l.title)}<div${rtl}>${esc(l.title)}</div>`}</div>
    <div class="lc-field"><label>五点描述</label>${editable ? `<textarea class="ed-bullets" rows="5"${rtl}></textarea>` : `${copyBtn(l.bullets.join("\n"))}<ul class="sp-list"${rtl}>${l.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul>`}</div>
    <div class="lc-field"><label>长描述 (${l.description.length} 字符)</label>${editable ? `<textarea class="ed-desc" rows="4"${rtl}></textarea>` : `${copyBtn(l.description)}<div${rtl}>${esc(l.description)}</div>`}</div>`;
  if (editable) {
    c.querySelector(".ed-title").value = l.title;
    c.querySelector(".ed-bullets").value = l.bullets.join("\n");
    c.querySelector(".ed-desc").value = l.description;
  }
  return c;
}

function esc(s) { const d = el("div"); d.textContent = s || ""; return d.innerHTML; }

/* ---------------- Step 4 校验 ---------------- */
function currentListing(selectId) {
  const v = $(selectId).value;
  return state.listings.find(l => String(l.id) === v);
}

async function validateAll() {
  const btn = $("#btnValidateAll");
  btn.disabled = true; btn.textContent = "⏳ 校验中…";
  $("#matrixArea").innerHTML = Array(5).fill('<div class="skeleton sk-line" style="height:30px"></div>').join("");
  try {
    const r = await api(`/api/products/${state.product.id}/validate_all`, { method: "POST" });
    renderMatrix(r.items);
    if (currentListing("#reportListing")) renderReport();
    toast(`批量校验完成：${r.items.filter(i => i.passed).length}/${r.items.length} 通过`);
  } catch (e) { toast(e.message, true); }
  btn.disabled = false; btn.textContent = "🔄 批量校验全部";
}

function renderMatrix(items) {
  const area = $("#matrixArea");
  area.innerHTML = "";
  area.appendChild(el("div", "matrix-row matrix-head",
    `<span>ID</span><span>平台 / 语言</span><span>状态</span><span>校验结果</span><span></span>`));
  items.forEach(it => {
    const row = el("div", "matrix-row");
    row.innerHTML = `<span>#${it.id}</span>
      <span>${PLATFORM_LABEL[it.platform]} · ${LANG_LABEL[it.language] || it.language}</span>
      <span><span class="badge ${it.status}">${({ draft: "草稿", approved: "已放行", rejected: "已驳回", published: "已上架" }[it.status]) || it.status}</span></span>
      <span><span class="status-chip ${it.passed ? "pass" : "fail"}">${it.passed ? "✓ 通过" : "✗ 违规"}</span> <small class="dim">${esc(it.summary)}</small></span>
      <span class="matrix-act">查看 →</span>`;
    row.onclick = () => { $("#reportListing").value = it.id; renderReport(); };
    area.appendChild(row);
  });
}

function fillListingSelect(selectId, filterEnFirst = false) {
  const sel = $(selectId);
  sel.innerHTML = "";
  let list = [...state.listings];
  if (filterEnFirst) list.sort((a, b) => (a.language === "en" ? -1 : 1) - (b.language === "en" ? -1 : 1));
  list.forEach(l => {
    const o = el("option", "", `#${l.id} ${PLATFORM_LABEL[l.platform]} · ${LANG_LABEL[l.language] || l.language} · ${({ draft: "草稿", approved: "已放行", rejected: "已驳回", published: "已上架" }[l.status])}`);
    o.value = l.id; sel.appendChild(o);
  });
}

async function renderReport() {
  if (!state.listings.length) return;
  fillListingSelect("#reportListing");
  const l = currentListing("#reportListing");
  if (!l) return;
  const r = await api(`/api/listings/${l.id}/validate`);
  const idx = state.listings.findIndex(x => x.id === l.id);
  state.listings[idx] = { ...state.listings[idx], validation: r };
  const area = $("#reportArea");
  area.innerHTML = "";
  const sum = el("div", "report-summary " + (r.passed ? "ok" : "bad"),
    `${r.platform_label} · 规则库 ${r.ruleset_version} — ${r.summary} ${r.passed ? "✅ 可提交审核" : "❌ 存在不合规项，请自动改写"}`);
  area.appendChild(sum);
  if (r.validated_at) {
    area.appendChild(el("p", "hint", `🕐 校验时间 ${r.validated_at.replace("T", " ")}`));
  }
  if (r.last_autofix && r.last_autofix.fixed && r.last_autofix.fixed.length) {
    const names = r.last_autofix.fixed.map(f => f.name).join("、");
    area.appendChild(el("div", "check-row",
      `<div class="left"><b>🧾 上次自动改写：${r.last_autofix.fixed.length} 项</b>
       <small>${esc(names)} · ${esc(String(r.last_autofix.at || "").replace("T", " "))}</small></div>
       <span class="status-chip warn">已留痕</span>`));
  }
  r.checks.forEach(c => {
    const row = el("div", "check-row");
    row.innerHTML = `<div class="left"><b>${c.name}</b><small>${c.detail} · 实测: ${esc(c.observed)}${c.fixable ? " · 支持自动修复" : ""}</small></div>
      <span class="status-chip ${c.status}">${{ pass: "通过", fail: "不合规", warn: "建议" }[c.status]}</span>`;
    area.appendChild(row);
  });
}

async function doAutofix() {
  const l = currentListing("#reportListing");
  if (!l) return;
  try {
    const r = await api(`/api/listings/${l.id}/autofix`, { method: "POST" });
    const idx = state.listings.findIndex(x => x.id === l.id);
    state.listings[idx] = r.listing;
    toast(`已按规则自动改写 ${r.fix_log.fixed.length} 项`);
    renderReport();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- Step 5 审核 ---------------- */
async function renderReview() {
  if (!state.listings.length) return;
  fillListingSelect("#reviewListing", true);
  showReviewCard();
}

async function showReviewCard() {
  const l = currentListing("#reviewListing");
  if (!l) return;
  const fresh = await api(`/api/products/${state.product.id}/listings`);
  Object.assign(state.listings, fresh.filter(f => state.listings.some(s => s.id === f.id)));
  const target = fresh.find(x => x.id === l.id);
  const area = $("#reviewArea");
  area.innerHTML = "";
  area.appendChild(listingCard(target, true));
}

async function saveReviewEdits(l) {
  const card = $("#reviewArea .listing-card");
  await api(`/api/listings/${l.id}`, {
    method: "PUT",
    body: (() => { const fd = new FormData();
      fd.append("title", card.querySelector(".ed-title").value);
      fd.append("bullets", card.querySelector(".ed-bullets").value);
      fd.append("description", card.querySelector(".ed-desc").value);
      return fd; })(),
  });
}

async function doSaveDraft() {
  const l = currentListing("#reviewListing");
  if (!l) return;
  try {
    await saveReviewEdits(l);
    toast("修改已保存（草稿）");
    await refreshListings();
  } catch (e) { toast(e.message, true); }
}

async function doDeleteProduct() {
  if (!state.product) return;
  if (!(await uiConfirm(`将删除「${state.product.name}」及其全部物料与任务，不可恢复。`, "删除当前商品？"))) return;
  try {
    await api(`/api/products/${state.product.id}`, { method: "DELETE" });
    toast("商品已删除");
    const ps = await api("/api/products");
    renderHistory(ps, null);
    if (ps.length) {
      await switchProduct(ps[0].id, { force: true, silent: true });
      goto(maxStep());
    } else {
      state.product = null; state.listings = []; state.tasks = []; state.images = null;
      $("#pcName").textContent = "尚未选择商品";
      $("#pcMeta").textContent = "请从第 1 步开始";
      $("#pcImg").src = "/static/placeholder.svg";
      $("#historyCard").style.display = "none";
      $("#btnDeleteProduct").style.display = "none";
      goto(1);
    }
  } catch (e) { toast(e.message, true); }
}

async function doApprove(reject = false) {
  const l = currentListing("#reviewListing");
  if (!l) return;
  try {
    await saveReviewEdits(l);
    await api(`/api/listings/${l.id}/${reject ? "reject" : "approve"}`, { method: "POST" });
    toast(reject ? "已驳回" : "已放行，可进入上架环节");
    await refreshListings();
    fillListingSelect("#reviewListing", true);
    $("#reviewListing").value = l.id;
    showReviewCard();
  } catch (e) { toast(e.message, true); }
}

async function doApproveAll() {
  try {
    const ens = state.listings.filter(l => l.language === "en" && l.status !== "published");
    for (const l of ens) await api(`/api/listings/${l.id}/approve`, { method: "POST" });
    await refreshListings();
    toast(`已批量放行 ${ens.length} 条主语言 Listing`);
    renderReview();
  } catch (e) { toast(e.message, true); }
}

async function refreshListings() {
  state.listings = await api(`/api/products/${state.product.id}/listings`);
}

function refreshHistoryMeta() {
  api("/api/products").then(ps => {
    const cur = ps.find(p => state.product && p.id === state.product.id);
    if (cur) { state.product = { ...state.product, ...cur, images: state.images || cur.images }; renderProductCard(); }
    renderHistory(ps, state.product && state.product.id);
  }).catch(() => {});
}

/* ---------------- Step 6 上架 ---------------- */
async function doPublish() {
  try {
    $("#btnPublish").disabled = true; $("#btnPublish").textContent = "⏳ 正在调用平台适配器…";
    const r = await api(`/api/products/${state.product.id}/publish`, { method: "POST" });
    state.tasks = r.tasks;
    $("#publishResult").classList.remove("hidden");
    renderTasks(); refreshHistoryMeta();
    if (state.tasks.every(t => t.status === "success")) fireConfetti();
    toast(`已提交 ${state.tasks.length} 个平台任务`);
  } catch (e) { toast(e.message, true); }
  $("#btnPublish").disabled = false; $("#btnPublish").textContent = "🚀 将已放行 Listing 批量上架";
}

function renderTasks() {
  const area = $("#taskList");
  area.innerHTML = "";
  state.tasks.forEach(t => {
    const row = el("div", "task-row");
    row.innerHTML = `<span class="dot ${t.status === "queued" ? "q" : t.status === "failed" ? "f" : ""}"></span>
      <div><b>${PLATFORM_LABEL[t.platform]} · ${LANG_LABEL[t.language] || t.language}</b>
      <small>${{ success: "上架成功", failed: "上架失败", queued: "排队中" }[t.status] || t.status}</small></div>
      <div class="msg">${esc(t.message)}</div>`;
    area.appendChild(row);
  });
}

/* ---------------- 初始化 ---------------- */
async function init() {
  state.meta = await api("/api/meta");
  $("#modeBadge").textContent = state.meta.mode === "qwen" ? "⚡ 百炼实时模式" : "🧪 本地模拟模式";
  await loadSamples();
  renderPicks();
  document.querySelectorAll("#steps li").forEach(li => li.onclick = () => goto(+li.dataset.step));
  $("#btnCustom").onclick = createCustom;
  $("#btnStructure").onclick = doStructure;
  $("#goto3").onclick = () => goto(3);
  $("#btnGenerate").onclick = doGenerate;
  $("#goto4").onclick = () => goto(4);
  $("#btnValidateAll").onclick = validateAll;
  $("#btnAutofix").onclick = doAutofix;
  $("#btnRevalidate").onclick = renderReport;
  $("#reportListing").onchange = renderReport;
  $("#goto5").onclick = () => goto(5);
  $("#reviewListing").onchange = showReviewCard;
  $("#btnSaveDraft").onclick = doSaveDraft;
  $("#btnApprove").onclick = () => doApprove(false);
  $("#btnReject").onclick = () => doApprove(true);
  $("#btnApproveAll").onclick = doApproveAll;
  $("#goto6").onclick = () => goto(6);
  $("#btnPublish").onclick = doPublish;
  $("#btnDeleteProduct").onclick = doDeleteProduct;
  $("#btnExportCsv").onclick = () => {
    window.location.href = `/api/products/${state.product.id}/export`;
  };
  applyTheme(localStorage.getItem("lf-theme")
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  $("#themeToggle").onclick = toggleTheme;
  initShortcuts(); initLightbox(); initCopyButtons();
  await restoreSession();   // 刷新后从数据库恢复上次进度
  goto(state.product ? maxStep() : 1);
  updateProgress();
}
init().catch(e => toast("初始化失败: " + e.message, true));
