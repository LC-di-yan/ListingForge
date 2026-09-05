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
  if (step === 2) renderStructure();
  if (step === 4) renderReport();
  if (step === 5) renderReview();
  if (step === 6 && state.tasks.length) renderTasks();
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
  try {
    const r = await api(`/api/products/${state.product.id}/structure`, { method: "POST" });
    state.product = { ...r.product, images: r.images }; state.images = r.images;
    renderProductCard(); renderStructure(); refreshHistoryMeta();
  } catch (e) { toast(e.message, true); }
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
  $("#btnGenerate").disabled = true; $("#btnGenerate").textContent = "⏳ 多平台文案链生成中…";
  try {
    const r = await formPost(`/api/products/${state.product.id}/generate`, { platforms, languages });
    state.listings = await api(`/api/products/${state.product.id}/listings`);
    $("#generateResult").classList.remove("hidden");
    $("#genStats").innerHTML = `
      <div class="stat"><b>${state.listings.length}</b><span>Listing 物料</span></div>
      <div class="stat"><b>${platforms.length} × ${languages.length}</b><span>平台 × 语言</span></div>
      <div class="stat"><b>${new Set(state.listings.map(l => l.language)).size}</b><span>覆盖语言</span></div>`;
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
  $("#btnGenerate").disabled = false; $("#btnGenerate").textContent = "✨ 一键生成全套 Listing";
}

function listingCard(l, editable) {
  const c = el("div", "card listing-card");
  const rtl = l.language === "ar" ? ' dir="rtl" style="text-align:right"' : "";  // 阿语从右向左排版
  const statusBadge = `<span class="badge ${l.status}">${{ draft: "草稿", approved: "已放行", rejected: "已驳回", published: "已上架" }[l.status] || l.status}</span>`;
  c.innerHTML = `<div class="lc-head"><b>${PLATFORM_LABEL[l.platform]} · ${LANG_LABEL[l.language] || l.language}</b>${statusBadge}</div>
    <div class="lc-field"><label>标题 (${l.title.length} 字符)</label>${editable ? `<input class="ed-title" value=""${rtl}>` : `<div${rtl}>${esc(l.title)}</div>`}</div>
    <div class="lc-field"><label>五点描述</label>${editable ? `<textarea class="ed-bullets" rows="5"${rtl}></textarea>` : `<ul class="sp-list"${rtl}>${l.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul>`}</div>
    <div class="lc-field"><label>长描述 (${l.description.length} 字符)</label>${editable ? `<textarea class="ed-desc" rows="4"${rtl}></textarea>` : `<div${rtl}>${esc(l.description)}</div>`}</div>`;
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
  if (!confirm(`确认删除「${state.product.name}」及其全部物料与任务？`)) return;
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
  await restoreSession();   // 刷新后从数据库恢复上次进度
  goto(state.product ? maxStep() : 1);
}
init().catch(e => toast("初始化失败: " + e.message, true));
