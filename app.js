const SUPABASE_URL = "https://YOUR-PROJECT.supabase.co";
const SUPABASE_ANON_KEY = "YOUR-ANON-KEY";   // the anon key only. Never the service key.
const sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const FORMATS = ["feed", "carousel", "reel", "story"];
const FMT = { feed: "Feed", carousel: "Carousel", reel: "Reel", story: "Story" };
const CLAIMS = ["confirmed", "unverified", "speculation"];
const LABEL = { confirmed: "Confirmed", unverified: "Unconfirmed", speculation: "Speculation" };
const FILTERS = [["pending", "Pending"], ["approved", "Approved"], ["publishing", "Posting"], ["published", "Posted"], ["failed", "Failed"], ["rejected", "Rejected"]];
const CHEV = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0A2A1F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>`;
const mark = px => `<svg width="${px}" height="${px}" viewBox="0 0 512 512" aria-hidden="true"><use href="#mk"/></svg>`;
const ago = t => {
  const m = Math.max(1, Math.round((Date.now() - new Date(t)) / 60000));
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};
const claim = c => `<span class="cl cl-${esc(c)}">${esc(LABEL[c] || c)}</span>`;
const pill = n => `<span class="p ${n >= 85 ? "u" : ""}">${n}</span>`;

let filter = "pending", cur = null, feed = null;

const row = i => `
<a class="c" href="#item=${esc(i.id)}">
  <div class="r">${pill(i.priority_score)}<span class="tp">${esc(i.topic)}${i.risk === "low" ? "" : `, ${esc(i.risk)} risk`}</span>${claim(i.claim_status)}</div>
  <h2 class="h">${esc(i.headline || i.original_title)}</h2>
  <p class="x">${esc((i.rewritten_text || i.original_text || "").slice(0, 140))}</p>
  <div class="ft"><span>${esc(i.source_name)}, ${ago(i.fetched_at)}</span><span>${esc(FMT[i.suggested_format] || "")}</span></div>
</a>`;

function loginView(msg = "") {
  $("#app").innerHTML = `
    <section class="login">
      ${mark(72)}
      <h1>Tri News</h1>
      <p class="mut">Review queue</p>
      ${msg ? `<p class="err">${esc(msg)}</p>` : ""}
      <label class="lb" style="width:100%">Email<input class="in" id="em" type="email" autocomplete="username"></label>
      <label class="lb" style="width:100%">Password<input class="in" id="pw" type="password" autocomplete="current-password"></label>
      <button class="bt go" id="go">Sign in</button>
      <p class="mut small">A TriBridge Services company</p>
    </section>`;
  $("#go").onclick = async () => {
    const { error } = await sb.auth.signInWithPassword({ email: $("#em").value.trim(), password: $("#pw").value });
    error ? loginView(error.message) : start();
  };
}

async function showQueue() {
  const [{ data, error }, all] = await Promise.all([
    sb.from("items").select("id,topic,risk,claim_status,priority_score,headline,original_title,rewritten_text,original_text,source_name,fetched_at,suggested_format")
      .eq("status", filter).order("priority_score", { ascending: false }).order("fetched_at", { ascending: false }).limit(40),
    sb.from("items").select("status,priority_score").limit(1000),
  ]);
  const counts = {};
  let waiting = 0, urgent = 0;
  (all.data || []).forEach(r => {
    counts[r.status] = (counts[r.status] || 0) + 1;
    if (r.status === "pending") { waiting++; if (r.priority_score >= 85) urgent++; }
  });
  $("#app").innerHTML = `
    <header class="top">${mark(36)}<h1>Review queue</h1><button class="ghost" data-out>Sign out</button></header>
    <p class="mut">${waiting ? `${waiting} waiting. ${urgent} ${urgent === 1 ? "is" : "are"} urgent.` : "Nothing waiting."}</p>
    <nav class="chips">${FILTERS.map(([v, t]) => `<button class="ch ${v === filter ? "on" : ""}" data-f="${v}">${t}${counts[v] ? " " + counts[v] : ""}</button>`).join("")}</nav>
    ${error ? `<p class="err">Could not load items: ${esc(error.message)}. Sign in with the admin email set in the SQL policy.</p>`
      : (data.map(row).join("") || `<p class="mut">Nothing here. New items appear when the next fetch runs.</p>`)}`;
}

const seg = (key, label, vals, now) => `
  <div class="lb">${label}<div class="sg" role="group" aria-label="${label}">
    ${vals.map(v => `<button type="button" data-seg="${key}" data-v="${v}" class="${v === now ? "on" : ""}">${esc(key === "fmt" ? FMT[v] : LABEL[v])}</button>`).join("")}
  </div></div>`;

async function showReview(id) {
  const { data: it, error } = await sb.from("items").select("*").eq("id", id).single();
  const top = `<header class="top"><button class="back" data-back aria-label="Back to the queue">${CHEV}</button><h1>Review</h1>${it ? pill(it.priority_score) : ""}</header>`;
  if (error || !it) {
    $("#app").innerHTML = `${top}<p class="err">Could not load this item${error ? ": " + esc(error.message) : ""}.</p>`;
    return;
  }
  cur = { ...it, fmt: it.suggested_format, claim: it.claim_status };
  const canAct = ["pending", "failed", "rejected"].includes(it.status);
  $("#app").innerHTML = `
    ${top}
    ${it.media_url ? `<img class="pv" src="${esc(it.media_url)}" alt="Preview of the post image">
      <p class="mut">Draft preview. The final image is drawn again from your edited text when it posts.</p>` : ""}
    <div class="src"><span>${esc(it.source_name)}</span><a href="${esc(it.source_url)}" target="_blank" rel="noopener">Open source</a></div>
    <details><summary>Original text</summary><p class="orig">${esc((it.original_text || "").slice(0, 1500))}</p></details>
    ${it.deadline ? `<p class="mut">Deadline in the text: ${esc(new Date(it.deadline).toLocaleString())}</p>` : ""}
    ${it.note ? `<p class="err">${esc(it.note)}</p>` : ""}
    <label class="lb">Headline<input class="in hl" id="f-headline" value="${esc(it.headline)}"></label>
    <label class="lb">Rewritten text<textarea class="in" id="f-text" rows="5">${esc(it.rewritten_text)}</textarea></label>
    <label class="lb">Caption<textarea class="in" id="f-caption" rows="5">${esc(it.caption)}</textarea></label>
    <label class="lb">Carousel slides, one per line<textarea class="in" id="f-slides" rows="4">${esc((it.slides || []).join("\n"))}</textarea></label>
    <label class="lb">Hashtags<input class="in" id="f-tags" value="${esc((it.hashtags || []).join(" "))}"></label>
    ${seg("fmt", "Format", FORMATS, cur.fmt)}
    ${seg("claim", "Claim", CLAIMS, cur.claim)}
    <div class="lb">Post to
      <label class="ck"><input type="checkbox" id="c-ig" ${(it.channels || []).includes("instagram") ? "checked" : ""}>Instagram</label>
      <label class="ck"><input type="checkbox" id="c-wa" ${(it.channels || []).includes("whatsapp") ? "checked" : ""}>WhatsApp</label>
    </div>
    <p class="mut">Media idea: ${esc(it.media_suggestion)}</p>
    ${canAct ? `<div class="acts"><button class="bt no" data-act="reject">Reject</button><button class="bt" data-act="save">Save</button><button class="bt go" data-act="approve">Approve and queue</button></div>`
      : `<p class="mut">Status: ${esc(it.status)}</p>`}`;
}

async function act(a, btn) {
  const v = n => $("#" + n).value.trim();
  const u = {
    headline: v("f-headline"),
    rewritten_text: v("f-text"),
    caption: v("f-caption"),
    slides: v("f-slides").split("\n").map(s => s.trim()).filter(Boolean).slice(0, 8),
    hashtags: v("f-tags").split(/[\s,]+/).filter(Boolean).map(t => t.startsWith("#") ? t : "#" + t),
    suggested_format: cur.fmt,
    claim_status: cur.claim,
    channels: [$("#c-ig").checked && "instagram", $("#c-wa").checked && "whatsapp"].filter(Boolean),
  };
  u.edited_by_admin = cur.edited_by_admin || ["headline", "rewritten_text", "caption"].some(k => u[k] !== (cur[k] || ""));
  if (a === "approve") {
    if (!u.headline || !u.rewritten_text) return alert("Add a headline and text before approving.");
    if (!u.channels.length) return alert("Choose at least one channel.");
    if (u.claim_status !== "confirmed" && !/unconfirmed|speculation|rumou?r|reportedly|allegedly/i.test(`${u.rewritten_text} ${u.caption}`))
      return alert("This is not marked Confirmed, but the text does not say so. Start it with “Unconfirmed:” or “Speculation:”.");
    if (!confirm("Approve and queue for posting?")) return;
    Object.assign(u, { status: "approved", approved_at: new Date().toISOString(), note: null });
  } else if (a === "reject") {
    if (!confirm("Reject this item?")) return;
    u.status = "rejected";
  }
  const { error } = await sb.from("items").update(u).eq("id", cur.id);
  if (error) return alert(`Could not save: ${error.message}`);
  await sb.from("audit_log").insert({ item_id: cur.id, action: a });
  if (a === "save") {
    Object.assign(cur, u);
    btn.textContent = "Saved";
    setTimeout(() => { btn.textContent = "Save"; }, 1500);
  } else {
    location.hash = "";
  }
}

document.addEventListener("click", async e => {
  const t = e.target.closest("[data-f],[data-out],[data-back],[data-seg],[data-act]");
  if (!t) return;
  if (t.dataset.f) { filter = t.dataset.f; return showQueue(); }
  if (t.hasAttribute("data-out")) { await sb.auth.signOut(); return loginView(); }
  if (t.hasAttribute("data-back")) { location.hash = ""; return; }
  if (t.dataset.seg) {
    cur[t.dataset.seg] = t.dataset.v;
    t.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === t));
    return;
  }
  if (t.dataset.act) return act(t.dataset.act, t);
});

const itemId = () => new URLSearchParams(location.hash.slice(1)).get("item");
const route = () => (itemId() ? showReview(itemId()) : showQueue());
window.addEventListener("hashchange", async () => {
  const { data: { session } } = await sb.auth.getSession();
  if (session) route();
});

async function start() {
  const { data: { session } } = await sb.auth.getSession();
  if (!session) return loginView();
  if (!feed) feed = sb.channel("items-feed").on("postgres_changes", { event: "INSERT", schema: "public", table: "items" }, () => { if (!itemId()) showQueue(); }).subscribe();
  route();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
start();
