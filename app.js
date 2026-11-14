const DEFAULTS = { url: "https://YOUR-PROJECT.supabase.co", key: "YOUR-ANON-KEY" };   // optional: paste yours here, or in the app on first open
const SUPABASE_URL = localStorage.getItem("sb_url") || DEFAULTS.url;
const SUPABASE_ANON_KEY = localStorage.getItem("sb_key") || DEFAULTS.key;   // the anon key only. Never the service key.
const BRAND = "Tri News", HANDLE = "@_.trinews";
const READY = !SUPABASE_URL.includes("YOUR-PROJECT") && !SUPABASE_ANON_KEY.includes("YOUR-ANON-KEY");
const sb = READY ? supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const FORMATS = ["feed", "carousel", "reel", "story"];
const FMT = { feed: "Feed", carousel: "Carousel", reel: "Reel", story: "Story" };
const CLAIMS = ["confirmed", "unverified", "speculation"];
const LABEL = { confirmed: "Confirmed", unverified: "Unconfirmed", speculation: "Speculation" };
const FILTERS = [["pending", "Pending"], ["approved", "Approved"], ["publishing", "Posting"], ["published", "Posted"], ["failed", "Failed"], ["rejected", "Rejected"], ["deleted", "Bin"]];
const CHEV = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0A2A1F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>`;
const mark = (px, style = "") => `<svg width="${px}" height="${px}" viewBox="0 0 512 512" style="${style}" aria-hidden="true"><use href="#mk"/></svg>`;
const ago = t => {
  const m = Math.max(1, Math.round((Date.now() - new Date(t)) / 60000));
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};
const claim = c => `<span class="cl cl-${esc(c)}">${esc(LABEL[c] || c)}</span>`;
const pill = n => `<span class="p ${n >= 85 ? "u" : ""}">${n}</span>`;
const tags = v => v.split(/[\s,]+/).filter(Boolean).map(t => t.startsWith("#") ? t : "#" + t);
const lines = v => v.split("\n").map(s => s.trim()).filter(Boolean).slice(0, 8);
const plural = n => (n === 1 ? "" : "s");

let filter = "pending", cur = null, feed = null, selecting = false, shown = [], binDays = 34;
const picked = new Set();

const row = i => `
<a class="c" href="#item=${esc(i.id)}">
  <div class="r">${pill(i.priority_score)}<span class="tp">${esc(i.topic)}${i.risk === "low" ? "" : `, ${esc(i.risk)} risk`}</span>${claim(i.claim_status)}</div>
  <h2 class="h">${esc(i.headline || i.original_title)}</h2>
  <p class="x">${esc((i.rewritten_text || i.original_text || "").slice(0, 140))}</p>
  <div class="ft"><span>${esc(i.source_name)}, ${ago(i.source_published || i.fetched_at)}${i.source_published && Date.now() - new Date(i.source_published) > 864e5 ? ' <b class="err">old</b>' : ""}</span><span>${esc(FMT[i.suggested_format] || "")}</span></div>
</a>`;

const pickRow = i => `
<div class="c" data-pick="${esc(i.id)}" style="cursor:pointer;${picked.has(i.id) ? "outline:3px solid var(--leaf);" : ""}">
  <div class="r"><span data-box style="font-size:22px;line-height:1">${picked.has(i.id) ? "☑" : "☐"}</span>${pill(i.priority_score)}<span class="tp">${esc(i.topic)}</span>${claim(i.claim_status)}</div>
  <h2 class="h">${esc(i.headline || i.original_title)}</h2>
  <p class="x">${esc((i.rewritten_text || i.original_text || "").slice(0, 100))}</p>
</div>`;

async function uploadFile(file, key) {
  if (file.size > 50 * 1024 * 1024) throw new Error("That file is over 50 MB. Trim the video or pick a smaller one.");
  const ext = (file.name.split(".").pop() || "bin").toLowerCase().replace(/[^a-z0-9]/g, "");
  const path = `uploads/${key}-${Date.now()}.${ext}`;
  const { error } = await sb.storage.from("media").upload(path, file, { contentType: file.type });
  if (error) throw new Error(`Upload failed: ${error.message}`);
  return { url: sb.storage.from("media").getPublicUrl(path).data.publicUrl, isVideo: file.type.startsWith("video/") };
}

function setupView() {
  $("#app").innerHTML = `
    <section class="login">
      ${mark(72)}
      <h1>${esc(BRAND)}</h1>
      <p class="mut">First time on this device: connect to your Supabase project.</p>
      <label class="lb" style="width:100%">Project URL<input class="in" id="su" placeholder="https://xxxx.supabase.co" autocapitalize="off" autocomplete="off"></label>
      <label class="lb" style="width:100%">anon (publishable) key<input class="in" id="sk" autocapitalize="off" autocomplete="off"></label>
      <button class="bt go" id="ss">Save and open</button>
    </section>`;
  $("#ss").onclick = () => {
    localStorage.setItem("sb_url", $("#su").value.trim().replace(/\/+$/, ""));
    localStorage.setItem("sb_key", $("#sk").value.trim());
    location.reload();
  };
}

function loginView(msg = "") {
  $("#app").innerHTML = `
    <section class="login">
      ${mark(72)}
      <h1>${esc(BRAND)}</h1>
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

function renderBar() {
  const el = $("#barin");
  if (!el) return;
  el.innerHTML = `
    <div class="r" style="margin-bottom:8px"><b style="flex:1">${picked.size} selected</b><button class="ghost" data-bulk="all">All</button></div>
    <div class="acts" style="margin:0">${filter === "deleted"
      ? `<button class="bt" data-bulk="restore">Restore</button><button class="bt no" data-bulk="purge">Delete forever</button>`
      : `<button class="bt no" data-bulk="delete">Delete</button><button class="bt go" data-bulk="approve">Approve</button>`}</div>`;
}

function togglePick(el) {
  const id = el.dataset.pick;
  picked.has(id) ? picked.delete(id) : picked.add(id);
  el.style.outline = picked.has(id) ? "3px solid var(--leaf)" : "";
  const box = el.querySelector("[data-box]");
  if (box) box.textContent = picked.has(id) ? "☑" : "☐";
  renderBar();
}

async function showQueue() {
  const [{ data, error }, all, bd] = await Promise.all([
    sb.from("items").select("id,topic,risk,claim_status,priority_score,headline,original_title,rewritten_text,original_text,caption,channels,source_name,fetched_at,source_published,suggested_format")
      .eq("status", filter).order("priority_score", { ascending: false }).order("fetched_at", { ascending: false }).limit(100),
    sb.from("items").select("status,priority_score").limit(1000),
    sb.from("settings").select("value").eq("key", "bin_days"),
  ]);
  binDays = parseInt(bd.data && bd.data[0] && bd.data[0].value, 10) || 34;
  shown = data || [];
  const counts = {};
  let waiting = 0, urgent = 0;
  (all.data || []).forEach(r => {
    counts[r.status] = (counts[r.status] || 0) + 1;
    if (r.status === "pending") { waiting++; if (r.priority_score >= 85) urgent++; }
  });
  $("#app").innerHTML = `
    <header class="top">${mark(36)}<h1>Review queue</h1><button class="ghost" data-out>Sign out</button></header>
    <div class="acts" style="margin:0 0 12px">
      <a class="bt go" href="#new" style="display:flex;align-items:center;justify-content:center;text-decoration:none">New post</a>
      <button class="bt" data-select>${selecting ? "Done" : "Select"}</button>
      <a class="bt" href="#settings" style="display:flex;align-items:center;justify-content:center;text-decoration:none">Settings</a>
    </div>
    <p class="mut">${waiting ? `${waiting} waiting. ${urgent} ${urgent === 1 ? "is" : "are"} urgent.` : "Nothing waiting."}</p>
    <nav class="chips">${FILTERS.map(([v, t]) => `<button class="ch ${v === filter ? "on" : ""}" data-f="${v}">${t}${counts[v] ? " " + counts[v] : ""}</button>`).join("")}</nav>
    ${filter === "deleted" ? `<p class="mut">Deleted items stay here for ${binDays} days, then disappear for good.</p>` : ""}
    ${error ? `<p class="err">Could not load items: ${esc(error.message)}. Sign in with the admin email set in the SQL policy, and run the newest SQL files.</p>`
      : (shown.map(selecting ? pickRow : row).join("") || `<p class="mut">Nothing here. New items appear when the next fetch runs.</p>`)}
    ${selecting ? `<div style="height:150px"></div><div style="position:fixed;left:0;right:0;bottom:0;z-index:5;background:#fff;border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom))"><div id="barin" style="max-width:560px;margin:0 auto"></div></div>` : ""}`;
  renderBar();
}

async function bulk(kind) {
  if (kind === "all") {
    const every = shown.length > 0 && shown.every(i => picked.has(i.id));
    picked.clear();
    if (!every) shown.forEach(i => picked.add(i.id));
    return showQueue();
  }
  const ids = [...picked];
  if (!ids.length) return alert("Pick at least one item first.");
  const now = new Date().toISOString();
  let error = null;
  if (kind === "delete") {
    if (!confirm(`Move ${ids.length} item${plural(ids.length)} to the Bin? You can restore them for ${binDays} days.`)) return;
    ({ error } = await sb.from("items").update({ status: "deleted", deleted_at: now }).in("id", ids).neq("status", "publishing"));
  } else if (kind === "restore") {
    ({ error } = await sb.from("items").update({ status: "pending", deleted_at: null, note: null, fetched_at: now }).in("id", ids).eq("status", "deleted"));
  } else if (kind === "purge") {
    if (!confirm(`Delete ${ids.length} item${plural(ids.length)} forever? This cannot be undone.`)) return;
    ({ error } = await sb.from("items").delete().in("id", ids).eq("status", "deleted"));
  } else if (kind === "approve") {
    const chosen = shown.filter(i => picked.has(i.id));
    const bad = chosen.filter(i => !i.headline || !i.rewritten_text || !(i.channels || []).length);
    const good = chosen.filter(i => !bad.includes(i));
    if (!good.length) return alert("None of these can be approved yet. Each needs a headline, text and a place to post.");
    const unsure = good.filter(i => i.claim_status !== "confirmed").length;
    if (!confirm(`Approve ${good.length} item${plural(good.length)}?${unsure ? ` ${unsure} are tagged Unconfirmed or Speculation.` : ""}${bad.length ? ` ${bad.length} will be skipped (missing headline or text).` : ""}`)) return;
    ({ error } = await sb.from("items").update({ status: "approved", approved_at: now, publish_after: await undoAt(), auto_approved: false, note: null })
      .in("id", good.map(i => i.id)).in("status", ["pending", "failed", "rejected"]));
  }
  if (error) return alert(error.message);
  picked.clear();
  selecting = false;
  showQueue();
}

const seg = (key, label, vals, now) => `
  <div class="lb">${label}<div class="sg" role="group" aria-label="${label}">
    ${vals.map(v => `<button type="button" data-seg="${key}" data-v="${v}" class="${v === now ? "on" : ""}">${esc(key === "fmt" ? FMT[v] : LABEL[v])}</button>`).join("")}
  </div></div>`;

const channelsBlock = ch => `
  <div class="lb">Post to
    <label class="ck"><input type="checkbox" id="c-ig" ${ch.includes("instagram") && !ch.includes("manual") ? "checked" : ""}>Instagram, posts by itself</label>
    <label class="ck"><input type="checkbox" id="c-man" ${ch.includes("manual") ? "checked" : ""}>Send to me to post with Instagram audio</label>
    <label class="ck"><input type="checkbox" id="c-wa" ${ch.includes("whatsapp") ? "checked" : ""}>WhatsApp text for your Channel</label>
  </div>`;
const readChannels = () => [$("#c-ig").checked && "instagram", $("#c-man").checked && "manual", $("#c-wa").checked && "whatsapp"].filter(Boolean);

const mediaBlock = (it, canAct) => `
  <div class="lb">Photo or video
    ${it.video_url ? `<video src="${esc(it.video_url)}" style="width:100%;border-radius:12px;background:#000" controls muted playsinline preload="metadata"></video>` : ""}
    ${it.photo_url ? `<img class="pv" src="${esc(it.photo_url)}" alt="Photo for this post">` : ""}
    <span class="mut">${it.photo_credit ? `Free stock media: ${esc(it.photo_credit)}. ` : ""}${it.image_query ? `Search: ${esc(it.image_query)}. ` : ""}${!it.photo_url && !it.video_url ? "No photo or video yet, so the post uses the plain card. " : ""}Only add media you own or have permission to use.</span>
    ${canAct ? `<div class="acts" style="margin-top:8px"><label class="bt" style="display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer">Add your own<input type="file" id="f-media" accept="image/*,video/*" hidden></label><button class="bt" data-act="nomedia">Remove</button></div>
    <label class="ck"><input type="checkbox" id="c-raw" ${it.raw_media ? "checked" : ""}>Post my photo or video exactly as it is, with no Tri News card</label>
    <span class="mut">Add media first, then edit the text: the page reloads after an upload.</span>` : ""}
  </div>`;

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
      <p class="mut">Draft preview. The final image is drawn again from your edited text when it posts.</p>`
      : `<p class="mut">No preview yet. The picture is drawn from the template when it posts.</p>`}
    <div class="src"><span>${esc(it.source_name)}</span>${/^https?:/.test(it.source_url) ? `<a href="${esc(it.source_url)}" target="_blank" rel="noopener">Open source</a>` : ""}</div>
    <details><summary>Original text</summary><p class="orig">${esc((it.original_text || "").slice(0, 1500))}</p></details>
    ${it.deadline ? `<p class="mut">Deadline in the text: ${esc(new Date(it.deadline).toLocaleString())}</p>` : ""}
    ${it.status === "approved" && it.publish_after && new Date(it.publish_after) > new Date() ? `<p class="mut">${it.auto_approved ? "Auto-approved. " : ""}It posts around ${esc(new Date(it.publish_after).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}. Pull it back if you changed your mind.</p>` : ""}
    ${it.note ? `<p class="err">${esc(it.note)}</p>` : ""}
    <label class="lb">Headline<input class="in hl" id="f-headline" value="${esc(it.headline)}"></label>
    <label class="lb">Rewritten text<textarea class="in" id="f-text" rows="5">${esc(it.rewritten_text)}</textarea></label>
    <label class="lb">Caption<textarea class="in" id="f-caption" rows="5">${esc(it.caption)}</textarea></label>
    <label class="lb">Carousel slides, one per line<textarea class="in" id="f-slides" rows="4">${esc((it.slides || []).join("\n"))}</textarea></label>
    <label class="lb">Hashtags<input class="in" id="f-tags" value="${esc((it.hashtags || []).join(" "))}"></label>
    ${mediaBlock(it, canAct)}
    ${seg("fmt", "Format", FORMATS, cur.fmt)}
    ${seg("claim", "Your tag, never shown on the post", CLAIMS, cur.claim)}
    ${channelsBlock(it.channels || [])}
    ${it.audio_idea ? `<p class="mut">Audio idea: ${esc(it.audio_idea)}. Meta does not let apps add Instagram's own music, so tick "Send to me to post with Instagram audio" and add it yourself.</p>` : ""}
    <p class="mut">Media idea: ${esc(it.media_suggestion)}</p>
    ${canAct ? `<div class="acts"><button class="bt no" data-act="reject">Reject</button><button class="bt" data-act="save">Save</button><button class="bt go" data-act="approve">Approve and queue</button></div>`
      : it.status === "approved" ? `<div class="acts"><button class="bt" data-act="pullback">Pull back to pending</button></div>`
      : it.status === "deleted" ? `<div class="acts"><button class="bt go" data-act="restore">Restore to pending</button></div>`
      : it.status === "published" ? `<p class="mut">Instagram does not let any app edit or delete a post. Open it in Instagram, tap the three dots, then Edit (caption) or Delete. To fix the picture, make an editable copy here, post the new one, then delete the old one in Instagram.</p>
        <div class="acts">${it.ig_permalink ? `<a class="bt" href="${esc(it.ig_permalink)}" target="_blank" rel="noopener" style="display:flex;align-items:center;justify-content:center;text-decoration:none">Open on Instagram</a>` : ""}<button class="bt go" data-act="repost">Edit and repost</button></div>`
      : `<p class="mut">Status: ${esc(it.status)}</p>`}`;
}

async function undoAt() {
  const { data } = await sb.from("settings").select("value").eq("key", "undo_minutes");
  const n = parseInt(data && data[0] && data[0].value, 10) || 0;
  return n > 0 ? new Date(Date.now() + n * 60000).toISOString() : null;
}

async function act(a, btn) {
  if (a === "nomedia") {
    if (!confirm("Remove the photo or video? The post will use the plain card.")) return;
    const { error } = await sb.from("items").update({ photo_url: null, video_url: null, photo_credit: null, use_stock: false }).eq("id", cur.id);
    return error ? alert(error.message) : showReview(cur.id);
  }
  if (a === "restore") {
    const { error } = await sb.from("items").update({ status: "pending", deleted_at: null, note: null, fetched_at: new Date().toISOString() }).eq("id", cur.id);
    return error ? alert(error.message) : showReview(cur.id);
  }
  if (a === "repost") {
    if (!confirm("Make an editable copy? After the new post is live, delete the old one in Instagram.")) return;
    const now = new Date().toISOString();
    const copy = {
      source_name: cur.source_name, source_url: `copy://${cur.id}-${Date.now()}`, original_title: cur.original_title, original_text: cur.original_text,
      topic: cur.topic, risk: cur.risk || "low", claim_status: cur.claim_status, priority_score: cur.priority_score || 90,
      headline: cur.headline, rewritten_text: cur.rewritten_text, caption: cur.caption, hashtags: cur.hashtags || [], slides: cur.slides || [],
      suggested_format: cur.suggested_format || "feed", channels: cur.channels || ["instagram"], media_suggestion: cur.media_suggestion,
      media_url: cur.media_url, photo_url: cur.photo_url, photo_credit: cur.photo_credit, video_url: cur.video_url,
      image_query: cur.image_query, audio_idea: cur.audio_idea, use_stock: cur.use_stock ?? true, raw_media: !!cur.raw_media,
      status: "pending", edited_by_admin: true, fetched_at: now, source_published: now,
      note: "Copy of an earlier post. Delete the old post on Instagram once this one is live.",
    };
    const { data, error } = await sb.from("items").insert(copy).select("id").single();
    if (error) return alert(`Could not copy it: ${error.message}`);
    location.hash = `item=${data.id}`;
    return;
  }
  if (a === "pullback") {
    const { data, error } = await sb.from("items").update({ status: "pending", approved_at: null, publish_after: null, auto_approved: false }).eq("id", cur.id).eq("status", "approved").select();
    if (error) return alert(error.message);
    if (!data.length) return alert("Too late: it is already posting.");
    return showReview(cur.id);
  }
  const v = n => $("#" + n).value.trim();
  const u = {
    headline: v("f-headline"),
    rewritten_text: v("f-text"),
    caption: v("f-caption"),
    slides: lines(v("f-slides")),
    hashtags: tags(v("f-tags")),
    suggested_format: cur.fmt,
    claim_status: cur.claim,
    channels: readChannels(),
    raw_media: !!($("#c-raw") && $("#c-raw").checked),
  };
  u.edited_by_admin = cur.edited_by_admin || ["headline", "rewritten_text", "caption"].some(k => u[k] !== (cur[k] || ""));
  if (a === "approve") {
    if (!u.headline || !u.rewritten_text) return alert("Add a headline and text before approving.");
    if (!u.channels.length) return alert("Choose where to post it.");
    if (!confirm("Approve and queue for posting?")) return;
    Object.assign(u, { status: "approved", approved_at: new Date().toISOString(), publish_after: await undoAt(), auto_approved: false, note: null });
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

function showNew() {
  cur = { fmt: "feed", claim: "confirmed", preview: null };
  $("#app").innerHTML = `
    <header class="top"><button class="back" data-back aria-label="Back to the queue">${CHEV}</button><h1>New post</h1></header>
    <div id="prev"></div>
    <label class="lb">Headline<input class="in hl" id="n-headline" placeholder="Short and punchy"></label>
    <label class="lb">Text on the card<textarea class="in" id="n-text" rows="4"></textarea></label>
    <label class="lb">Caption (leave empty to reuse the text)<textarea class="in" id="n-caption" rows="4"></textarea></label>
    <label class="lb">Carousel slides, one per line<textarea class="in" id="n-slides" rows="3"></textarea></label>
    <label class="lb">Hashtags<input class="in" id="n-tags" value="#TriNews"></label>
    <label class="lb">Your photo or video<input class="in" id="n-file" type="file" accept="image/*,video/*"></label>
    <label class="ck"><input type="checkbox" id="n-raw">Post my photo or video exactly as it is, with no Tri News card</label>
    <label class="lb">Or a free stock photo search (optional)<input class="in" id="n-query" placeholder="stage lights"></label>
    <label class="lb">Audio idea for yourself (optional)<input class="in" id="n-audio" placeholder="upbeat gengetone beat"></label>
    ${seg("fmt", "Format", FORMATS, "feed")}
    ${seg("claim", "Your tag, never shown on the post", CLAIMS, "confirmed")}
    ${channelsBlock(["instagram", "whatsapp"])}
    <p class="mut">Only add media you own or have permission to use.</p>
    <div class="acts"><button class="bt" data-act="n-draft">Save draft</button><button class="bt go" data-act="n-approve">Approve and queue</button></div>`;
  previewCard();
}

function previewCard() {
  const box = $("#prev");
  if (!box) return;
  const tall = cur.fmt === "story" || cur.fmt === "reel";
  const h = $("#n-headline").value.trim() || "Your headline goes here";
  const b = $("#n-text").value.trim();
  const m = cur.preview;
  if (m && $("#n-raw") && $("#n-raw").checked) {
    box.innerHTML = `<div style="border-radius:16px;overflow:hidden;background:#000;max-height:540px;margin:0 auto 8px;display:flex;justify-content:center">
      ${m.isVideo ? `<video src="${esc(m.url)}" muted autoplay loop playsinline style="max-width:100%;max-height:540px"></video>` : `<img src="${esc(m.url)}" alt="" style="max-width:100%;max-height:540px">`}</div>
      <p class="mut">Your ${m.isVideo ? "video" : "picture"} will post as it is, with no card on it.</p>`;
    return;
  }
  const media = m ? (m.isVideo
    ? `<video src="${esc(m.url)}" muted autoplay loop playsinline style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover"></video>`
    : `<img src="${esc(m.url)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">`) : "";
  const fade = m ? `<div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(10,42,31,.6),rgba(10,42,31,0) 28%,rgba(10,42,31,.94) 82%)"></div>` : "";
  box.innerHTML = `
    <div style="position:relative;overflow:hidden;border-radius:16px;background:#0A2A1F;color:#fff;aspect-ratio:${tall ? "9/16" : "4/5"};max-height:540px;margin:0 auto 8px;border-top:6px solid #FF5A36">
      ${media}${fade}
      <div style="position:absolute;inset:0;padding:18px 20px;display:flex;flex-direction:column">
        <div style="display:flex;align-items:center;gap:8px;font-weight:800">${mark(30, "--b:#fff;--l:#0A2A1F")}${esc(BRAND)}</div>
        <div style="margin-top:auto">
          <div style="font:700 ${tall ? 26 : 24}px/1.15 Newsreader,Georgia,serif">${esc(h)}</div>
          ${b ? `<div style="font-size:13px;line-height:1.4;margin-top:8px;color:#E5ECE8">${esc(b.slice(0, tall ? 160 : 200))}</div>` : ""}
          <div style="display:flex;justify-content:space-between;margin-top:14px;font-size:11px;color:#C9D6CF"><span>${esc(HANDLE)}</span><span>A TriBridge Services company</span></div>
        </div>
      </div>
    </div>
    <p class="mut">Approximate preview. The final image is drawn from the same template when it posts.</p>`;
}

async function saveNew(approve) {
  const v = id => $("#" + id).value.trim();
  const headline = v("n-headline"), text = v("n-text");
  if (!headline) return alert("Add a headline first.");
  const caption = v("n-caption") || text || headline;
  const channels = readChannels();
  if (!channels.length) return alert("Choose where to post it.");
  if (approve && !confirm("Approve and queue for posting?")) return;
  const now = new Date().toISOString();
  const rowData = {
    source_name: `${BRAND} (own post)`, source_url: `own://${Date.now()}`,
    original_title: headline, original_text: text, topic: "OWN POST",
    claim_status: cur.claim, risk: "low", priority_score: 95,
    headline, rewritten_text: text, caption, hashtags: tags(v("n-tags")), slides: lines(v("n-slides")),
    suggested_format: cur.fmt, channels, image_query: v("n-query") || null, audio_idea: v("n-audio") || null,
    use_stock: true, raw_media: $("#n-raw").checked, edited_by_admin: true, status: approve ? "approved" : "pending",
    approved_at: approve ? now : null, fetched_at: now, source_published: now,
  };
  if (approve) rowData.publish_after = await undoAt();
  const file = $("#n-file").files[0];
  try {
    if (file) {
      const up = await uploadFile(file, "own");
      rowData.photo_url = up.isVideo ? null : up.url;
      rowData.video_url = up.isVideo ? up.url : null;
      rowData.use_stock = false;
    }
  } catch (err) { return alert(err.message); }
  const { error } = await sb.from("items").insert(rowData);
  if (error) return alert(`Could not save: ${error.message}. Have you run the newest SQL files?`);
  location.hash = "";
}

async function showSettings() {
  const { data, error } = await sb.from("settings").select("key,value");
  const s = Object.fromEntries((data || []).map(r => [r.key, r.value]));
  const g = (k, d) => esc(s[k] ?? d);
  $("#app").innerHTML = `
    <header class="top"><button class="back" data-back aria-label="Back to the queue">${CHEV}</button><h1>Settings</h1></header>
    ${error ? `<p class="err">Could not load settings: ${esc(error.message)}. Run the 004 SQL first.</p>` : ""}
    <a class="bt" href="#sources" style="display:flex;align-items:center;justify-content:center;text-decoration:none">Manage news sources</a>
    <div class="lb">Auto-publish confirmed news
      <label class="ck"><input type="checkbox" id="s-on" ${s.auto_publish === "on" ? "checked" : ""}>Let safe, confirmed stories post without my approval</label>
    </div>
    <p class="mut">Only stories the AI marked Confirmed and low risk can post themselves. Your own tips, celebrity and relationship gossip, viral trends and sensitive topics never do. Each one waits for the delay below, you get a Telegram message, and you can pull it back from its review screen.</p>
    <label class="lb">Minimum score<input class="in" id="s-score" inputmode="numeric" value="${g("auto_min_score", 70)}"></label>
    <label class="lb">Minimum source trust, 1 to 5<input class="in" id="s-trust" inputmode="numeric" value="${g("auto_min_trust", 3)}"></label>
    <label class="lb">Most auto-posts per day<input class="in" id="s-cap" inputmode="numeric" value="${g("auto_daily_cap", 6)}"></label>
    <label class="lb">Minutes to wait before posting<input class="in" id="s-delay" inputmode="numeric" value="${g("auto_delay_min", 10)}"></label>
    <label class="lb">Undo window after you approve, in minutes (0 posts straight away)<input class="in" id="s-undo" inputmode="numeric" value="${g("undo_minutes", 0)}"></label>
    <label class="lb">Days to keep deleted items in the Bin<input class="in" id="s-bin" inputmode="numeric" value="${g("bin_days", 34)}"></label>
    <div class="acts"><button class="bt go" data-act="save-settings">Save settings</button></div>`;
}

async function saveSettings() {
  const num = (id, lo, hi, d) => String(Math.min(hi, Math.max(lo, parseInt($("#" + id).value, 10) || d)));
  const rowsData = [
    { key: "auto_publish", value: $("#s-on").checked ? "on" : "off" },
    { key: "auto_min_score", value: num("s-score", 0, 100, 70) },
    { key: "auto_min_trust", value: num("s-trust", 1, 5, 3) },
    { key: "auto_daily_cap", value: num("s-cap", 0, 50, 6) },
    { key: "auto_delay_min", value: num("s-delay", 1, 120, 10) },
    { key: "bin_days", value: num("s-bin", 1, 365, 34) },
    { key: "undo_minutes", value: num("s-undo", 0, 60, 0) },
  ];
  const { error } = await sb.from("settings").upsert(rowsData, { onConflict: "key" });
  if (error) return alert(`Could not save: ${error.message}`);
  alert($("#s-on").checked ? "Saved. Auto-publish is ON." : "Saved. Auto-publish is OFF.");
  location.hash = "";
}

async function showSources() {
  cur = { kind: "youtube" };
  const { data, error } = await sb.from("sources").select("id,name,url,type,active").order("type").order("name");
  $("#app").innerHTML = `
    <header class="top"><button class="back" data-back aria-label="Back to the queue">${CHEV}</button><h1>Sources</h1></header>
    ${error ? `<p class="err">Could not load sources: ${esc(error.message)}. Run the 005 SQL first.</p>` : ""}
    <p class="mut">Where Tri News looks for stories. Instagram, Facebook and TikTok pages cannot be added, because they block automatic reading. For those, send a screenshot of the story to your Telegram bot.</p>
    <div class="lb">Add a source
      <input class="in" id="a-name" placeholder="Name, for example Bahati on YouTube">
      <input class="in" id="a-url" placeholder="Channel link, @handle, or feed link" autocapitalize="off" style="margin-top:8px">
      <div class="sg" style="margin-top:8px"><button type="button" data-kind="youtube" class="on">YouTube channel</button><button type="button" data-kind="rss">News feed</button></div>
      <button class="bt go" data-act="add-source" style="margin-top:8px">Add</button>
    </div>
    ${(data || []).map(s => `
      <div class="c" style="gap:6px">
        <div class="r"><b style="flex:1">${esc(s.name)}</b><span class="tp" style="flex:none">${esc(s.type)}</span></div>
        <span class="mut" style="word-break:break-all">${esc(s.url.slice(0, 90))}</span>
        <div class="acts" style="margin-top:4px"><button class="bt" data-src="${esc(s.id)}" data-active="${s.active}">${s.active ? "On, tap to switch off" : "Off, tap to switch on"}</button><button class="bt no" data-del-src="${esc(s.id)}">Remove</button></div>
      </div>`).join("")}`;
}

async function addSource() {
  const name = $("#a-name").value.trim();
  let url = $("#a-url").value.trim();
  if (!name || !url) return alert("Add a name and a link.");
  if (cur.kind === "youtube") {
    if (/^UC[\w-]{22}$/.test(url)) url = `https://www.youtube.com/channel/${url}`;
    else if (!/^https?:/.test(url)) url = `https://www.youtube.com/@${url.replace(/^@/, "")}`;
  } else if (!/^https?:/.test(url)) return alert("Paste the full feed link, starting with https.");
  const { error } = await sb.from("sources").insert({ name, url, type: cur.kind, category: cur.kind === "youtube" ? "youtube" : "custom", trust_level: 3 });
  if (error) return alert(`Could not add it: ${error.message}`);
  showSources();
}

document.addEventListener("click", async e => {
  const t = e.target.closest("[data-f],[data-out],[data-back],[data-seg],[data-act],[data-pick],[data-bulk],[data-select],[data-kind],[data-src],[data-del-src]");
  if (!t) return;
  if (t.dataset.f) { filter = t.dataset.f; picked.clear(); return showQueue(); }
  if (t.hasAttribute("data-out")) { await sb.auth.signOut(); return loginView(); }
  if (t.hasAttribute("data-back")) { location.hash = ""; return; }
  if (t.dataset.pick) return togglePick(t);
  if (t.dataset.bulk) return bulk(t.dataset.bulk);
  if (t.hasAttribute("data-select")) { selecting = !selecting; picked.clear(); return showQueue(); }
  if (t.dataset.kind) {
    cur.kind = t.dataset.kind;
    t.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === t));
    return;
  }
  if (t.dataset.src) {
    const { error } = await sb.from("sources").update({ active: t.dataset.active !== "true" }).eq("id", t.dataset.src);
    return error ? alert(error.message) : showSources();
  }
  if (t.dataset.delSrc) {
    if (!confirm("Remove this source? Its past stories stay in the app.")) return;
    const { error } = await sb.from("sources").delete().eq("id", t.dataset.delSrc);
    return error ? alert(error.message) : showSources();
  }
  if (t.dataset.seg) {
    cur[t.dataset.seg] = t.dataset.v;
    t.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === t));
    if ($("#prev")) previewCard();
    return;
  }
  const a = t.dataset.act;
  if (a === "n-draft" || a === "n-approve") return saveNew(a === "n-approve");
  if (a === "save-settings") return saveSettings();
  if (a === "add-source") return addSource();
  return act(a, t);
});

document.addEventListener("change", async e => {
  const el = e.target;
  if (el.id === "c-ig" && el.checked && $("#c-man")) $("#c-man").checked = false;
  if (el.id === "c-man" && el.checked && $("#c-ig")) $("#c-ig").checked = false;
  if (el.id === "n-file") {
    const f = el.files[0];
    cur.preview = f ? { url: URL.createObjectURL(f), isVideo: f.type.startsWith("video/") } : null;
    return previewCard();
  }
  if (el.id !== "f-media" || !el.files[0]) return;
  try {
    const up = await uploadFile(el.files[0], cur.id);
    const { error } = await sb.from("items").update({ photo_url: up.isVideo ? null : up.url, video_url: up.isVideo ? up.url : null, photo_credit: null, use_stock: false }).eq("id", cur.id);
    if (error) throw new Error(`Could not save: ${error.message}`);
    showReview(cur.id);
  } catch (err) { alert(err.message); }
});

document.addEventListener("input", e => { if ($("#prev") && e.target.id && e.target.id.startsWith("n-")) previewCard(); });

const itemId = () => new URLSearchParams(location.hash.slice(1)).get("item");
const onQueue = () => !location.hash || location.hash === "#";
const route = () => {
  if (itemId()) return showReview(itemId());
  if (location.hash === "#new") return showNew();
  if (location.hash === "#settings") return showSettings();
  if (location.hash === "#sources") return showSources();
  return showQueue();
};
window.addEventListener("hashchange", async () => {
  if (!READY) return;
  const { data: { session } } = await sb.auth.getSession();
  if (session) route();
});

async function start() {
  if (!READY) return setupView();
  const { data: { session } } = await sb.auth.getSession();
  if (!session) return loginView();
  if (!feed) feed = sb.channel("items-feed").on("postgres_changes", { event: "INSERT", schema: "public", table: "items" }, () => { if (onQueue() && !selecting) showQueue(); }).subscribe();
  route();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
start();
