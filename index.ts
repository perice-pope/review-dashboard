import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const corsHeaders: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

/* ── Types ───────────────────────────────────────────────────────── */

interface Song {
  id: string;
  title: string;
}

interface GenerationRun {
  id: string;
  production_queue_id: string;
  shot_name: string;
  character_name: string;
  tool_used: string;
  video_url: string;
  drive_filename: string;
  drive_folder: string;
  duration_seconds: number;
  resolution: string;
  fal_status: string;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

interface ProductionQueueItem {
  id: string;
  song_id: string;
  shot_name: string;
  character: string;
  concept_tag: string;
  status: string;
  capcut_notes: Record<string, unknown> | null;
  director_signoff: Record<string, unknown> | null;
  director_signoff_status: string | null;
  drive_folder_url: string | null;
  created_at: string;
  updated_at: string;
}

interface ShotWithRuns extends ProductionQueueItem {
  runs: GenerationRun[];
  song_title: string;
  estimated_cost: number;
}

interface DashboardData {
  songs: Song[];
  shots: ShotWithRuns[];
  counts: {
    approved: number;
    pending: number;
    rejected: number;
    in_post: number;
    total: number;
  };
}

/* ── Cost estimation ─────────────────────────────────────────────── */
// Kling ≈ $0.028/sec, OmniHuman ≈ $0.05/sec (rough estimates)

const COST_PER_SEC: Record<string, number> = {
  kling: 0.028,
  omnihuman: 0.05,
};

function estimateCost(runs: GenerationRun[]): number {
  let total = 0;
  for (const run of runs) {
    if (!run.duration_seconds || !run.tool_used) continue;
    const tool = run.tool_used.toLowerCase();
    const rate =
      Object.entries(COST_PER_SEC).find(([key]) => tool.includes(key))?.[1] ||
      0.03;
    total += run.duration_seconds * rate;
  }
  return Math.round(total * 100) / 100;
}

/* ── HTML helpers ────────────────────────────────────────────────── */

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ── Data fetching ───────────────────────────────────────────────── */

async function getDashboardData(): Promise<DashboardData> {
  const [songsResult, shotsResult, runsResult] = await Promise.all([
    client.from("songs").select("id, title").order("title"),
    client
      .from("production_queue")
      .select("*")
      .order("created_at", { ascending: true }),
    client
      .from("generation_runs")
      .select("*")
      .order("created_at", { ascending: true }),
  ]);

  const songs = (songsResult.data || []) as Song[];
  const shots = (shotsResult.data || []) as ProductionQueueItem[];
  const runs = (runsResult.data || []) as GenerationRun[];

  // Group runs by production_queue_id
  const runsByShot = new Map<string, GenerationRun[]>();
  for (const run of runs) {
    const list = runsByShot.get(run.production_queue_id) || [];
    list.push(run);
    runsByShot.set(run.production_queue_id, list);
  }

  // Song title lookup
  const songTitles = new Map<string, string>();
  for (const song of songs) songTitles.set(song.id, song.title);

  // Combine shots with their runs
  const shotsWithRuns: ShotWithRuns[] = shots.map((shot) => {
    const shotRuns = runsByShot.get(shot.id) || [];
    return {
      ...shot,
      runs: shotRuns,
      song_title: songTitles.get(shot.song_id) || "Unknown Song",
      estimated_cost: estimateCost(shotRuns),
    };
  });

  // Count statuses
  const counts = {
    approved: 0,
    pending: 0,
    rejected: 0,
    in_post: 0,
    total: shots.length,
  };
  for (const shot of shots) {
    if (shot.status === "approved") counts.approved++;
    else if (shot.status === "rejected") counts.rejected++;
    else if (shot.status === "in_post") counts.in_post++;
    else counts.pending++;
  }

  return { songs, shots: shotsWithRuns, counts };
}

/* ── Action handlers ─────────────────────────────────────────────── */

async function handleAction(body: Record<string, unknown>): Promise<void> {
  switch (body.action) {
    case "review_run": {
      const newStatus =
        body.status === "approve" ? "completed" : "failed";
      const updates: Record<string, unknown> = { fal_status: newStatus };
      if (body.status === "reject")
        updates.error_message = "Rejected in review";
      const { error } = await client
        .from("generation_runs")
        .update(updates)
        .eq("id", body.run_id as string);
      if (error) throw error;
      break;
    }
    case "update_shot": {
      const { error } = await client
        .from("production_queue")
        .update({
          status: body.status as string,
          updated_at: new Date().toISOString(),
        })
        .eq("id", body.shot_id as string);
      if (error) throw error;
      break;
    }
    case "approve_director": {
      const { error } = await client
        .from("production_queue")
        .update({
          director_signoff_status: "approved",
          updated_at: new Date().toISOString(),
        })
        .eq("id", body.shot_id as string);
      if (error) throw error;
      break;
    }
    default:
      throw new Error(`Unknown action: ${body.action}`);
  }
}

/* ── HTML generation ─────────────────────────────────────────────── */

function generateHTML(data: DashboardData): string {
  const dateStr = new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  const shotCards = data.shots
    .map((shot) => {
      const capcut = shot.capcut_notes
        ? JSON.stringify(shot.capcut_notes, null, 2)
        : "No CapCut notes yet.";
      const missingNote =
        shot.capcut_notes &&
        typeof shot.capcut_notes === "object"
          ? (shot.capcut_notes as Record<string, string>).missing_assets_note ||
            ""
          : "";
      const dirStatus = shot.director_signoff_status || "pending";
      const dirBadge =
        dirStatus === "approved" ? "Director approved" : "Awaiting director";
      const dirSignoff = shot.director_signoff
        ? JSON.stringify(shot.director_signoff, null, 2)
        : "No director signoff yet.";
      const driveFolderUrl = shot.drive_folder_url || "";

      const videoCards = shot.runs
        .map(
          (run) => `
        <div class="video-card" id="run-${run.id}"
          data-drive-folder-url="${escapeAttr(driveFolderUrl)}"
          data-drive-filename="${escapeAttr(run.drive_filename || "")}">
          ${
            run.video_url
              ? `<video src="${escapeAttr(run.video_url)}" controls preload="metadata" playsinline onerror="showExpiry(this)"></video>
                 <div class="expiry-warning" id="expiry-${run.id}">fal link expired — use Drive copy</div>`
              : `<div class="no-video">No video yet</div>`
          }
          <div class="char-name">${escapeHtml(run.character_name || "Unknown")}</div>
          <div class="tool-name">${escapeHtml(run.tool_used || "")}${run.duration_seconds ? ` (${run.duration_seconds}s)` : ""}</div>
          <div class="file-name">${escapeHtml(run.drive_filename || "")}</div>
          <div class="btn-row">
            <button class="btn btn-approve" onclick="reviewRun('${run.id}','approve',this)">Good</button>
            <button class="btn btn-reject" onclick="reviewRun('${run.id}','reject',this)">Redo</button>
            ${run.drive_filename ? `<button class="btn btn-copy" onclick="copyDriveInfo(this)">Drive URL</button>` : ""}
          </div>
        </div>`
        )
        .join("");

      return `
    <div class="shot-card" data-status="${shot.status}" data-song-id="${shot.song_id}" data-shot-id="${shot.id}">
      <div class="shot-header">
        <div class="shot-meta">
          <span class="shot-name">${escapeHtml(shot.shot_name)}</span>
          <span class="status-badge status-${shot.status}">${shot.status}</span>
          <span class="director-badge director-${dirStatus}">${dirBadge}</span>
          ${shot.estimated_cost > 0 ? `<span class="cost-tag">~$${shot.estimated_cost.toFixed(2)}</span>` : ""}
        </div>
        <div style="display:flex;gap:6px;align-items:center">
          ${shot.concept_tag ? `<span class="concept-tag">${escapeHtml(shot.concept_tag)}</span>` : ""}
          <span style="font-size:11px;color:#5b8a7a">${escapeHtml(shot.song_title)}</span>
        </div>
      </div>

      <div class="videos-row">${videoCards || '<div style="color:#5b8a7a;font-size:12px;padding:8px">No videos generated yet</div>'}</div>

      ${missingNote ? `<div class="missing-asset">${escapeHtml(missingNote)}</div>` : ""}

      <div class="capcut-section">
        <button class="section-toggle" onclick="this.nextElementSibling.classList.toggle('open')">CapCut Edit Guide</button>
        <pre class="toggle-notes">${escapeHtml(capcut)}</pre>
        ${
          shot.director_signoff
            ? `<button class="section-toggle" onclick="toggleDirector(this)">Director Notes</button>
               <pre class="toggle-notes director-notes">${escapeHtml(dirSignoff)}</pre>`
            : ""
        }
      </div>

      <div class="shot-actions">
        <button class="btn-shot btn-shot-approve" onclick="updateShot('${shot.id}','approved')" ${shot.status === "approved" ? "disabled" : ""}>Approve Shot</button>
        <button class="btn-shot btn-shot-in-post" onclick="updateShot('${shot.id}','in_post')" ${shot.status === "in_post" ? "disabled" : ""}>Send to Post</button>
        ${dirStatus !== "approved" ? `<button class="btn-shot btn-shot-director" onclick="approveDirector('${shot.id}')">Approve Director Signoff</button>` : ""}
      </div>
    </div>`;
    })
    .join("");

  const songOptions = data.songs
    .map((s) => `<option value="${s.id}">${escapeHtml(s.title)}</option>`)
    .join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Review Dashboard — The Roommates</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1419; color: #e8d5b0; padding: 24px; min-height: 100vh; }

  /* Header */
  header { margin-bottom: 28px; }
  h1 { color: #c45a2c; font-size: 28px; margin-bottom: 6px; letter-spacing: -0.5px; }
  .subtitle { color: #5b8a7a; font-size: 14px; margin-bottom: 20px; }

  /* Controls */
  .controls { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
  .song-select { background: #1a2535; color: #e8d5b0; border: 1px solid #2b3d52; padding: 8px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; }
  .song-select:focus { border-color: #5b8a7a; outline: none; }

  /* Summary */
  .summary-bar { display: flex; gap: 16px; flex-wrap: wrap; }
  .summary-item { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .summary-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot-approved { background: #2d8a4e; }
  .dot-pending { background: #d4a355; }
  .dot-rejected { background: #8b3a1f; }
  .dot-in-post { background: #5b8a7a; }

  .btn-download { background: #2b3d52; color: #e8d5b0; border: 1px solid #5b8a7a; padding: 8px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; font-weight: 600; transition: background 0.2s; }
  .btn-download:hover { background: #3a4d62; }

  /* Filter bar */
  .filter-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
  .filter-btn { background: #1a2535; color: #e8d5b0; border: 1px solid #2b3d52; padding: 7px 16px; border-radius: 20px; font-size: 12px; cursor: pointer; font-weight: 600; transition: all 0.2s; }
  .filter-btn:hover { border-color: #5b8a7a; }
  .filter-btn.active { background: #c45a2c; border-color: #c45a2c; color: white; }

  /* Shot cards */
  .shots-grid { display: grid; gap: 24px; }
  .shot-card { background: #1a2535; border-radius: 12px; padding: 20px; border: 1px solid #2b3d52; transition: border-color 0.2s; }
  .shot-card:hover { border-color: #5b8a7a; }
  .shot-card[data-status="approved"] { border-left: 3px solid #2d8a4e; }
  .shot-card[data-status="rejected"] { border-left: 3px solid #8b3a1f; }
  .shot-card[data-status="in_post"] { border-left: 3px solid #d4a355; }

  .shot-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; }
  .shot-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .shot-name { font-size: 17px; font-weight: 700; color: #f5e6c8; }
  .concept-tag { background: #c45a2c; color: white; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
  .cost-tag { background: #1a3a2a; color: #5b8a7a; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }

  .status-badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
  .status-generated, .status-review_pending, .status-queued, .status-generating { background: #2b3d52; color: #e8d5b0; }
  .status-approved { background: #2d8a4e; color: white; }
  .status-rejected, .status-failed { background: #8b3a1f; color: white; }
  .status-in_post { background: #d4a355; color: #1a2535; }

  .director-badge { font-size: 11px; padding: 3px 10px; border-radius: 20px; }
  .director-pending { background: #2a2000; color: #d4a355; border: 1px solid #d4a355; }
  .director-approved { background: #0a2a0a; color: #2d8a4e; border: 1px solid #2d8a4e; }

  /* Video cards */
  .videos-row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
  .video-card { background: #0f1419; border-radius: 8px; padding: 10px; border: 2px solid #2b3d52; width: 200px; transition: border-color 0.2s; position: relative; }
  .video-card video { width: 100%; border-radius: 5px; margin-bottom: 7px; display: block; background: #000; }
  .no-video { height: 90px; display: flex; align-items: center; justify-content: center; color: #5b8a7a; font-size: 12px; }
  .char-name { font-size: 12px; font-weight: 700; color: #d4a355; }
  .tool-name { font-size: 10px; color: #5b8a7a; margin-top: 1px; }
  .file-name { font-size: 10px; color: #5b8a7a; margin-top: 2px; word-break: break-all; line-height: 1.3; }
  .expiry-warning { display: none; background: #2a1a00; border: 1px solid #c45a2c; border-radius: 4px; padding: 4px 8px; font-size: 10px; color: #e8a060; margin-top: 4px; }
  .expiry-warning.show { display: block; }

  .btn-row { display: flex; gap: 4px; margin-top: 7px; flex-wrap: wrap; }
  .btn { padding: 5px 8px; border-radius: 5px; border: none; cursor: pointer; font-size: 10px; font-weight: 700; transition: opacity 0.15s; }
  .btn:hover { opacity: 0.82; }
  .btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .btn-approve { background: #2d8a4e; color: white; }
  .btn-reject { background: #8b3a1f; color: white; }
  .btn-copy { background: #2b3d52; color: #e8d5b0; }

  /* CapCut & Director sections */
  .capcut-section { margin-top: 14px; padding-top: 14px; border-top: 1px solid #2b3d52; }
  .section-toggle { background: #2b3d52; color: #e8d5b0; border: none; padding: 7px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; margin-right: 8px; }
  .section-toggle:hover { background: #3a4d62; }
  .toggle-notes { display: none; margin-top: 10px; background: #080d12; padding: 12px; border-radius: 7px; font-size: 11px; line-height: 1.65; max-height: 300px; overflow-y: auto; color: #8ab; font-family: 'Courier New', monospace; white-space: pre-wrap; word-break: break-word; }
  .toggle-notes.open { display: block; }

  .missing-asset { background: #2a1a00; border: 1px solid #c45a2c; border-radius: 6px; padding: 8px 12px; margin-top: 8px; font-size: 11px; color: #e8a060; }

  /* Shot actions */
  .shot-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .btn-shot { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; transition: opacity 0.15s; }
  .btn-shot:hover { opacity: 0.82; }
  .btn-shot:disabled { opacity: 0.35; cursor: not-allowed; }
  .btn-shot-approve { background: #2d8a4e; color: white; }
  .btn-shot-in-post { background: #d4a355; color: #1a2535; }
  .btn-shot-director { background: #5b8a7a; color: white; }

  /* Toast */
  .toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 600; z-index: 1000; transform: translateY(-20px); opacity: 0; transition: all 0.3s; pointer-events: none; }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast-success { background: #2d8a4e; color: white; }
  .toast-error { background: #8b3a1f; color: white; }

  .empty-state { text-align: center; padding: 60px; color: #5b8a7a; font-size: 14px; }

  @media (max-width: 768px) {
    body { padding: 16px; }
    h1 { font-size: 22px; }
    .video-card { width: 150px; }
    .controls { flex-direction: column; align-items: flex-start; }
  }
</style>
</head>
<body>

<header>
  <h1>THE ROOMMATES</h1>
  <p class="subtitle">Review Dashboard — ${dateStr}</p>
  <div class="controls">
    <select class="song-select" id="song-filter" onchange="filterBySong()">
      <option value="all">All Songs</option>
      ${songOptions}
    </select>
    <div class="summary-bar">
      <div class="summary-item"><span class="summary-dot dot-approved"></span> ${data.counts.approved} Approved</div>
      <div class="summary-item"><span class="summary-dot dot-pending"></span> ${data.counts.pending} Pending</div>
      <div class="summary-item"><span class="summary-dot dot-in-post"></span> ${data.counts.in_post} In Post</div>
      <div class="summary-item"><span class="summary-dot dot-rejected"></span> ${data.counts.rejected} Rejected</div>
    </div>
    <button class="btn-download" onclick="downloadApproved()">Download Approved Manifest</button>
  </div>
</header>

<div class="filter-bar">
  <button class="filter-btn active" data-filter="all" onclick="setFilter('all',this)">All (${data.counts.total})</button>
  <button class="filter-btn" data-filter="pending" onclick="setFilter('pending',this)">Pending</button>
  <button class="filter-btn" data-filter="approved" onclick="setFilter('approved',this)">Approved</button>
  <button class="filter-btn" data-filter="in_post" onclick="setFilter('in_post',this)">In Post</button>
  <button class="filter-btn" data-filter="rejected" onclick="setFilter('rejected',this)">Rejected</button>
</div>

<div id="toast" class="toast"></div>

<div class="shots-grid" id="grid">
${shotCards || '<div class="empty-state">No shots found in production_queue.</div>'}
</div>

<script>
  var BASE_URL = window.location.href.split('?')[0];
  var currentFilter = 'all';
  var currentSongId = 'all';

  /* ── Toast ── */
  function toast(msg, type) {
    var el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast toast-' + (type || 'success') + ' show';
    setTimeout(function() { el.classList.remove('show'); }, 3000);
  }

  /* ── Filtering ── */
  function setFilter(filter, btn) {
    currentFilter = filter;
    var btns = document.querySelectorAll('.filter-btn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
    btn.classList.add('active');
    applyFilters();
  }

  function filterBySong() {
    currentSongId = document.getElementById('song-filter').value;
    applyFilters();
  }

  function applyFilters() {
    var pendingStatuses = ['queued', 'generating', 'generated', 'review_pending'];
    var cards = document.querySelectorAll('.shot-card');
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var status = card.getAttribute('data-status');
      var songId = card.getAttribute('data-song-id');
      var matchesStatus = currentFilter === 'all'
        || (currentFilter === 'pending' && pendingStatuses.indexOf(status) !== -1)
        || status === currentFilter;
      var matchesSong = currentSongId === 'all' || songId === currentSongId;
      card.style.display = (matchesStatus && matchesSong) ? '' : 'none';
    }
  }

  /* ── API calls ── */
  function apiCall(body) {
    return fetch(BASE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function(res) {
      if (!res.ok) return res.json().catch(function() { return { error: 'Request failed' }; }).then(function(err) { throw new Error(err.error || 'Request failed'); });
      return res.json();
    });
  }

  function reviewRun(id, action, btn) {
    var card = document.getElementById('run-' + id);
    var btns = card.querySelectorAll('.btn');
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    apiCall({ action: 'review_run', run_id: id, status: action }).then(function() {
      card.style.borderColor = action === 'approve' ? '#2d8a4e' : '#8b3a1f';
      toast(action === 'approve' ? 'Run approved' : 'Run marked for redo');
    }).catch(function(err) {
      for (var i = 0; i < btns.length; i++) btns[i].disabled = false;
      toast(err.message, 'error');
    });
  }

  function updateShot(id, status) {
    apiCall({ action: 'update_shot', shot_id: id, status: status }).then(function() {
      var card = document.querySelector('[data-shot-id="' + id + '"]');
      if (card) {
        card.setAttribute('data-status', status);
        var badge = card.querySelector('.status-badge');
        if (badge) { badge.className = 'status-badge status-' + status; badge.textContent = status; }
      }
      toast('Shot updated to ' + status);
    }).catch(function(err) {
      toast(err.message, 'error');
    });
  }

  function approveDirector(id) {
    apiCall({ action: 'approve_director', shot_id: id }).then(function() {
      var card = document.querySelector('[data-shot-id="' + id + '"]');
      if (card) {
        var badge = card.querySelector('.director-badge');
        if (badge) { badge.className = 'director-badge director-approved'; badge.textContent = 'Director approved'; }
        var dirBtn = card.querySelector('.btn-shot-director');
        if (dirBtn) dirBtn.remove();
      }
      toast('Director signoff approved');
    }).catch(function(err) {
      toast(err.message, 'error');
    });
  }

  /* ── Video expiry detection ── */
  function showExpiry(videoEl) {
    var card = videoEl.closest('.video-card');
    var warning = card.querySelector('.expiry-warning');
    if (warning) warning.classList.add('show');
  }

  /* ── Copy Drive URL ── */
  function copyDriveInfo(btn) {
    var card = btn.closest('.video-card');
    var url = card.getAttribute('data-drive-folder-url');
    var filename = card.getAttribute('data-drive-filename');
    var text = url || filename || '';
    if (!text) { toast('No Drive info available', 'error'); return; }
    navigator.clipboard.writeText(text).then(
      function() { toast('Copied: ' + (url ? 'Drive folder URL' : filename)); },
      function() { toast('Copy failed', 'error'); }
    );
  }

  /* ── Toggle director notes ── */
  function toggleDirector(btn) {
    var notes = btn.nextElementSibling;
    if (notes) notes.classList.toggle('open');
  }

  /* ── Download approved manifest ── */
  function downloadApproved() {
    var approvedCards = document.querySelectorAll('.shot-card[data-status="approved"]');
    if (!approvedCards.length) { toast('No approved shots', 'error'); return; }
    var lines = ['APPROVED SHOTS MANIFEST', 'Generated: ' + new Date().toISOString(), ''];
    for (var i = 0; i < approvedCards.length; i++) {
      var card = approvedCards[i];
      var name = card.querySelector('.shot-name');
      lines.push((name ? name.textContent : 'Unknown') + ':');
      var files = card.querySelectorAll('.file-name');
      for (var j = 0; j < files.length; j++) {
        if (files[j].textContent) lines.push('  - ' + files[j].textContent);
      }
      lines.push('');
    }
    var blob = new Blob([lines.join('\\n')], { type: 'text/plain' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'approved-manifest.txt';
    a.click();
    URL.revokeObjectURL(a.href);
    toast('Manifest downloaded');
  }
</script>
</body>
</html>`;
}

/* ── HTTP handler ────────────────────────────────────────────────── */

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    if (req.method === "GET") {
      const data = await getDashboardData();
      const html = generateHTML(data);
      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8", ...corsHeaders },
      });
    }

    if (req.method === "POST") {
      const body = await req.json();
      await handleAction(body);
      return new Response(JSON.stringify({ success: true }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  } catch (error) {
    console.error("Error:", error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      }
    );
  }
});
