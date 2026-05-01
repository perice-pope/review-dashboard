import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";
const DRIVE_WEBAPP_URL = Deno.env.get("DRIVE_WEBAPP_URL") || "";

// GitHub workflow_dispatch — fired after apply_revision so the runner kicks
// off immediately instead of waiting up to 5 min for the cron tick.
const GH_DISPATCH_TOKEN = Deno.env.get("GH_DISPATCH_TOKEN") || "";
const GH_DISPATCH_OWNER = Deno.env.get("GH_DISPATCH_OWNER") || "perice-pope";
const GH_DISPATCH_REPO = Deno.env.get("GH_DISPATCH_REPO") || "review-dashboard";
const GH_DISPATCH_WORKFLOW = Deno.env.get("GH_DISPATCH_WORKFLOW") || "render-shots.yml";
const GH_DISPATCH_REF = Deno.env.get("GH_DISPATCH_REF") || "main";
const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const corsHeaders: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
}

/* ── GET: return all dashboard data ──────────────────────────────── */

async function getDashboardData() {
  const [songsResult, shotsResult, runsResult] = await Promise.all([
    client.from("songs").select("id, song_title").order("song_title"),
    client
      .from("production_queue")
      .select("*")
      .order("created_at", { ascending: true }),
    client
      .from("generation_runs")
      .select("*")
      .order("created_at", { ascending: true }),
  ]);

  return {
    songs: songsResult.data || [],
    shots: shotsResult.data || [],
    runs: runsResult.data || [],
  };
}

/* ── Claude revision helper ──────────────────────────────────────── */

type ProposedRevision = {
  runway_prompt: string;
  characters_used: string;
  scene_ref: string;
  rationale: string;
};

async function proposeRevisionWithClaude(
  shot: Record<string, unknown>,
  run: Record<string, unknown>,
  feedback: string,
  validCharacters: string[],
  validScenes: string[],
): Promise<ProposedRevision> {
  if (!ANTHROPIC_API_KEY) {
    throw new Error(
      "ANTHROPIC_API_KEY not set in edge function secrets — cannot propose revision",
    );
  }

  const systemPrompt = [
    "You are a prompt engineer for the Roommates pipeline that runs Runway Gen-4 References as a TWO-STAGE call: (1) text_to_image with referenceImages → still keyframe, (2) image_to_video to animate. The same prompt drives both stages, so it must work as both a still composition AND a motion description.",
    "",
    "REFERENCE IMAGE BUDGET: 3 per call, hard limit. Characters first, then ONE scene reference if there is room. If a shot needs more than 3 character refs, only the first 3 (in characters_used order) get bound — the rest fall back to the prompt only.",
    "",
    "RUNWAY GEN-4 PROMPTING RULES (apply these even when the feedback doesn't mention them):",
    "",
    "1. REFERENCES HANDLE IDENTITY. Each @-tagged character has a reference image that defines face, hair, build, age, clothing, accessories. The PROMPT MUST NOT redescribe any of these. Forbidden: hair color/style, age, build, race, clothing item, clothing color, accessories, facial features, jewelry. If the prior prompt contains any of these, STRIP them — opportunistic cleanup every time.",
    "",
    "2. PROMPTS HANDLE ACTION + ENVIRONMENT + CAMERA + MOOD. Keep what characters DO, WHERE they are, how the CAMERA moves, and what the scene FEELS like. Audio cues that drive action are fine.",
    "",
    "3. PRESERVE EXPLICIT NEGATIVE-PROMPT INSTRUCTIONS. Phrases like 'no breath vapor', 'no eye contact', 'NOT choreography', 'NOT 3D', 'do not show X' are deliberate constraints from prior reviewer feedback. KEEP them intact — negative guidance is NOT bloat.",
    "",
    "4. KEEP IT TIGHT. Aim for under ~600 characters. Cut decorative redundancy. Never sacrifice Rule 3 caveats.",
    "",
    "5. CHARACTERS ARE @-TAGGED. Format: @Name. The reference image bound to that name supplies the look. Every character in characters_used MUST appear as @Name somewhere in the prompt — otherwise the reference is wasted.",
    "",
    "6. SCENES CAN BE @-TAGGED TOO. If scene_ref is set (e.g. scene_ref='kitchen_morning'), reference it in the prompt as @kitchen_morning (verbatim slug). The setting image will be bound. If scene_ref is empty, describe the location in plain prose instead.",
    "",
    "7. PRESERVE the global visual-style line if present ('Roommates visual style: warm flat illustration, subtle gradients...') — that is rendering style, not identity.",
    "",
    "Pick characters_used and scene_ref ONLY from the provided valid lists. Respond via the propose_revision tool. In the rationale, briefly note (a) what feedback you addressed and (b) what Rule 1 cleanup you did.",
  ].join("\n");

  const userMessage = [
    `SHOT NAME: ${shot.shot_name ?? ""}`,
    `CURRENT runway_prompt:\n${shot.runway_prompt ?? ""}`,
    `CURRENT characters_used: ${shot.characters_used ?? ""}`,
    `CURRENT scene_ref: ${shot.scene_ref ?? "(empty)"}`,
    `LOCATION (free text): ${shot.location ?? ""}`,
    `VALID CHARACTER NAMES: ${validCharacters.join(", ")}`,
    `VALID SCENE TAGS: ${validScenes.length ? validScenes.join(", ") : "(none registered yet — leave scene_ref empty)"}`,
    `PRIOR TAKE'S character_name field: ${run.character_name ?? "(unknown)"}`,
    `PRIOR TAKE'S drive_filename: ${run.drive_filename ?? "(unknown)"}`,
    "",
    "REVIEWER FEEDBACK ON THE PRIOR TAKE:",
    feedback,
    "",
    "Propose updated runway_prompt, characters_used, and scene_ref. Address the feedback, AND strip Rule-1 identity descriptors. Ensure every character in characters_used appears as @Name in the prompt; if scene_ref is non-empty, reference it as @<slug>.",
  ].join("\n");

  const tool = {
    name: "propose_revision",
    description:
      "Submit the proposed updates for the shot's runway_prompt, characters_used, and scene_ref.",
    input_schema: {
      type: "object",
      properties: {
        runway_prompt: {
          type: "string",
          description:
            "The full updated prompt to send to Runway. Replaces the prior prompt. Every character in characters_used must appear as @Name; if scene_ref is set, the slug must appear as @<slug>.",
        },
        characters_used: {
          type: "string",
          description:
            "Comma-separated character names from the valid list. Order matters — only the first 3 get reference-bound when more than 3 are listed.",
        },
        scene_ref: {
          type: "string",
          description:
            "Setting reference slug from the valid scene tags list, or empty string. Empty if no setting image fits or none registered.",
        },
        rationale: {
          type: "string",
          description:
            "1-3 sentences: (a) what feedback you addressed, (b) what Rule 1 cleanup you did.",
        },
      },
      required: ["runway_prompt", "characters_used", "scene_ref", "rationale"],
    },
  };

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 1024,
      system: systemPrompt,
      tools: [tool],
      tool_choice: { type: "tool", name: "propose_revision" },
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Anthropic API ${resp.status}: ${errText}`);
  }

  const result = await resp.json();
  const block = (result.content || []).find((b: { type: string }) =>
    b.type === "tool_use"
  );
  if (!block || !block.input) {
    throw new Error("Claude did not return a tool_use block");
  }
  return block.input as ProposedRevision;
}

/**
 * Fire-and-forget GitHub workflow_dispatch. Returns false on failure but never
 * throws — the user's revision must succeed even if the trigger fails (the
 * 5-min cron will pick the shot up as a fallback).
 */
async function triggerRenderWorkflow(): Promise<{ triggered: boolean; reason?: string }> {
  if (!GH_DISPATCH_TOKEN) {
    return { triggered: false, reason: "GH_DISPATCH_TOKEN not set" };
  }
  const url = `https://api.github.com/repos/${GH_DISPATCH_OWNER}/${GH_DISPATCH_REPO}` +
              `/actions/workflows/${GH_DISPATCH_WORKFLOW}/dispatches`;
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${GH_DISPATCH_TOKEN}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: GH_DISPATCH_REF }),
    });
    if (resp.status === 204) return { triggered: true };
    const text = await resp.text();
    return { triggered: false, reason: `GitHub returned ${resp.status}: ${text.slice(0, 200)}` };
  } catch (e) {
    return { triggered: false, reason: e instanceof Error ? e.message : String(e) };
  }
}

async function fetchValidCharacters(): Promise<string[]> {
  const { data, error } = await client
    .from("production_queue")
    .select("characters_used")
    .not("characters_used", "is", null);
  if (error) throw error;
  const set = new Set<string>();
  for (const row of data || []) {
    const raw = (row as { characters_used: string | null }).characters_used;
    if (!raw) continue;
    for (const name of raw.split(",")) {
      const trimmed = name.trim();
      if (trimmed) set.add(trimmed);
    }
  }
  return Array.from(set).sort();
}

async function fetchValidScenes(): Promise<string[]> {
  const { data, error } = await client
    .from("production_queue")
    .select("scene_ref")
    .not("scene_ref", "is", null);
  if (error) throw error;
  const set = new Set<string>();
  for (const row of data || []) {
    const raw = (row as { scene_ref: string | null }).scene_ref;
    if (raw && raw.trim()) set.add(raw.trim());
  }
  return Array.from(set).sort();
}

/* ── POST: handle actions ────────────────────────────────────────── */

async function handleAction(body: Record<string, unknown>) {
  switch (body.action) {
    case "review_run": {
      const newStatus = body.status === "approve" ? "completed" : "failed";
      const updates: Record<string, unknown> = { fal_status: newStatus };
      if (body.status === "reject")
        updates.error_message = "Rejected in review";
      const { error } = await client
        .from("generation_runs")
        .update(updates)
        .eq("id", body.run_id as string);
      if (error) throw error;
      return { success: true };
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
      return { success: true };
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
      return { success: true };
    }
    case "change_status": {
      const allowed = ["queued", "needs_keyframe", "generating", "generated", "review_pending", "revision_needed", "approved", "rejected", "in_assembly", "in_post", "final_review", "complete", "shipped"];
      const newStatus = body.status as string;
      if (!allowed.includes(newStatus)) throw new Error("Invalid status: " + newStatus);
      const { error } = await client
        .from("production_queue")
        .update({ status: newStatus, updated_at: new Date().toISOString() })
        .eq("id", body.shot_id as string);
      if (error) throw error;
      return { success: true };
    }
    case "set_keyframe": {
      // Path B handoff: dashboard wrote a keyframe URL/file ID. Save it,
      // flip status to revision_needed so the runner re-picks the shot,
      // and instant-trigger the workflow.
      const shotId = body.shot_id as string;
      const raw = (body.keyframe_image_url as string || "").trim();
      if (!shotId) throw new Error("shot_id required");
      if (!raw) throw new Error("keyframe_image_url required");

      // Server-side guard: Runway webpage URLs are HTML, not images. The
      // runner can't fetch them as promptImage. Reject up-front so we don't
      // burn 3 retries proving it.
      if (/app\.runwayml\.com\/(creation|video-tools|ai-tools|gen|tasks)\//.test(raw)) {
        throw new Error(
          "Runway creation/share URLs are webpages, not images. Save the image to Drive and paste the file ID instead.",
        );
      }

      const { error } = await client
        .from("production_queue")
        .update({
          keyframe_image_url: raw,
          status: "revision_needed",
          updated_at: new Date().toISOString(),
        })
        .eq("id", shotId);
      if (error) throw error;

      const dispatch = await triggerRenderWorkflow();
      return {
        success: true,
        render_triggered: dispatch.triggered,
        render_trigger_reason: dispatch.reason,
      };
    }
    case "upload_keyframe": {
      // Drag-and-drop upload: dashboard sends the PNG bytes (base64) directly,
      // we proxy to the Apps Script upload endpoint, save the resulting Drive
      // file ID as the keyframe_image_url, and instant-trigger the workflow.
      const shotId = body.shot_id as string;
      const filename = (body.filename as string || "").trim();
      const contentBase64 = body.content_base64 as string;
      const mimeType = (body.mime_type as string) || "image/png";
      if (!shotId) throw new Error("shot_id required");
      if (!filename) throw new Error("filename required");
      if (!contentBase64) throw new Error("content_base64 required");
      if (!DRIVE_WEBAPP_URL) {
        throw new Error("DRIVE_WEBAPP_URL not set in edge function secrets");
      }

      // Look up the song title to build a sensible folder name.
      const { data: shot, error: shotErr } = await client
        .from("production_queue")
        .select("song_id, shot_name")
        .eq("id", shotId)
        .single();
      if (shotErr) throw shotErr;
      const songId = (shot as { song_id: string }).song_id;
      const { data: song } = await client
        .from("songs")
        .select("song_title")
        .eq("id", songId)
        .single();
      const songTitle = (song as { song_title: string } | null)?.song_title || "Unknown Song";
      const folderName = `${songTitle} - Keyframes`;

      // POST to Apps Script upload endpoint
      const uploadResp = await fetch(DRIVE_WEBAPP_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "upload",
          folder: folderName,
          filename,
          contentBase64,
          mimeType,
        }),
      });
      if (!uploadResp.ok) {
        throw new Error(`Drive upload failed: ${uploadResp.status} ${await uploadResp.text()}`);
      }
      const driveResult = await uploadResp.json();
      if (driveResult.error) {
        throw new Error(`Drive upload error: ${driveResult.error}`);
      }
      const fileId = driveResult.fileId;
      if (!fileId) {
        throw new Error(`Drive upload returned no fileId: ${JSON.stringify(driveResult)}`);
      }

      // Save the file ID as the keyframe and flip status
      const { error: updErr } = await client
        .from("production_queue")
        .update({
          keyframe_image_url: fileId,
          status: "revision_needed",
          updated_at: new Date().toISOString(),
        })
        .eq("id", shotId);
      if (updErr) throw updErr;

      const dispatch = await triggerRenderWorkflow();
      return {
        success: true,
        file_id: fileId,
        folder_url: driveResult.folderUrl,
        render_triggered: dispatch.triggered,
        render_trigger_reason: dispatch.reason,
      };
    }
    case "clear_keyframe": {
      // "Recompose" path: clear the locked keyframe and force the shot back
      // to needs_keyframe so the user picks a new still in Runway.
      const shotId = body.shot_id as string;
      if (!shotId) throw new Error("shot_id required");

      const { error } = await client
        .from("production_queue")
        .update({
          keyframe_image_url: null,
          status: "needs_keyframe",
          updated_at: new Date().toISOString(),
        })
        .eq("id", shotId);
      if (error) throw error;
      return { success: true };
    }
    case "request_revision": {
      const runId = body.run_id as string;
      const feedback = (body.feedback as string || "").trim();
      if (!runId) throw new Error("run_id required");
      if (!feedback) throw new Error("feedback required");

      const { data: run, error: runErr } = await client
        .from("generation_runs")
        .select("*")
        .eq("id", runId)
        .single();
      if (runErr) throw runErr;
      if (!run) throw new Error("Run not found");

      const shotId = (run as { production_queue_id: string }).production_queue_id;
      const { data: shot, error: shotErr } = await client
        .from("production_queue")
        .select("*")
        .eq("id", shotId)
        .single();
      if (shotErr) throw shotErr;
      if (!shot) throw new Error("Shot not found");

      const [validCharacters, validScenes] = await Promise.all([
        fetchValidCharacters(),
        fetchValidScenes(),
      ]);
      const proposal = await proposeRevisionWithClaude(
        shot as Record<string, unknown>,
        run as Record<string, unknown>,
        feedback,
        validCharacters,
        validScenes,
      );

      return {
        success: true,
        shot_id: shotId,
        run_id: runId,
        feedback,
        current: {
          runway_prompt: (shot as { runway_prompt: string | null }).runway_prompt || "",
          characters_used: (shot as { characters_used: string | null }).characters_used || "",
          scene_ref: (shot as { scene_ref: string | null }).scene_ref || "",
          keyframe_image_url: (shot as { keyframe_image_url: string | null }).keyframe_image_url || "",
        },
        proposed: proposal,
      };
    }
    case "apply_revision": {
      const shotId = body.shot_id as string;
      const runId = body.run_id as string;
      const newPrompt = body.runway_prompt as string;
      const newCharacters = body.characters_used as string;
      const newSceneRef = (body.scene_ref as string) ?? "";
      const feedback = (body.feedback as string) || "";
      if (!shotId || !runId) throw new Error("shot_id and run_id required");

      const { data: shot, error: shotErr } = await client
        .from("production_queue")
        .select("runway_prompt, characters_used, scene_ref")
        .eq("id", shotId)
        .single();
      if (shotErr) throw shotErr;

      const { error: updErr } = await client
        .from("production_queue")
        .update({
          runway_prompt: newPrompt,
          characters_used: newCharacters,
          scene_ref: newSceneRef || null,
          previous_runway_prompt: (shot as { runway_prompt: string | null }).runway_prompt,
          previous_characters_used: (shot as { characters_used: string | null }).characters_used,
          reviewer_feedback: feedback,
          status: "revision_needed",
          updated_at: new Date().toISOString(),
        })
        .eq("id", shotId);
      if (updErr) throw updErr;

      const { error: runErr } = await client
        .from("generation_runs")
        .update({
          fal_status: "failed",
          error_message: "Rejected in review (AI revision queued)",
          reviewer_feedback: feedback,
        })
        .eq("id", runId);
      if (runErr) throw runErr;

      // Fire-and-forget: kick the renderer immediately so the user doesn't
      // wait for the 5-min cron tick. If this fails, the cron is the fallback.
      const dispatch = await triggerRenderWorkflow();
      return { success: true, render_triggered: dispatch.triggered, render_trigger_reason: dispatch.reason };
    }
    case "refresh_run": {
      // Re-resolve a generation_run's video URL from Drive when the original
      // Runway CDN link has expired (JWT 3-day expiry + Runway task retention).
      // Returns a Drive embed URL that the dashboard renders as an <iframe>.
      const runId = body.run_id as string;
      if (!runId) throw new Error("run_id required");
      if (!DRIVE_WEBAPP_URL) {
        throw new Error("DRIVE_WEBAPP_URL not set in edge function secrets");
      }

      const { data: run, error: runErr } = await client
        .from("generation_runs")
        .select("drive_filename, drive_folder")
        .eq("id", runId)
        .single();
      if (runErr) throw runErr;
      if (!run) throw new Error("Run not found");

      const filename = (run as { drive_filename: string | null }).drive_filename;
      const folderUrl = (run as { drive_folder: string | null }).drive_folder;
      if (!filename) throw new Error("run has no drive_filename — cannot refresh");
      if (!folderUrl) throw new Error("run has no drive_folder — cannot refresh");

      // drive_folder looks like https://drive.google.com/drive/folders/<ID>
      const idMatch = folderUrl.match(/\/folders\/([A-Za-z0-9_-]+)/);
      if (!idMatch) throw new Error(`Could not parse folder ID from ${folderUrl}`);
      const folderId = idMatch[1];

      const listUrl = `${DRIVE_WEBAPP_URL}?action=list&folderId=${encodeURIComponent(folderId)}`;
      const driveResp = await fetch(listUrl);
      if (!driveResp.ok) {
        throw new Error(`Drive list failed: ${driveResp.status} ${await driveResp.text()}`);
      }
      const driveData = await driveResp.json();
      if (driveData.error) throw new Error(`Drive list error: ${driveData.error}`);

      type DriveFile = { id: string; name: string };
      const files: DriveFile[] = driveData.files || [];
      const match = files.find((f) => f.name === filename);
      if (!match) {
        throw new Error(
          `File ${filename} not found in folder ${folderId} (${files.length} files there)`,
        );
      }

      return {
        success: true,
        file_id: match.id,
        preview_url: `https://drive.google.com/file/d/${match.id}/preview`,
        folder_url: folderUrl,
      };
    }
    default:
      throw new Error(`Unknown action: ${body.action}`);
  }
}

/* ── HTTP handler ────────────────────────────────────────────────── */

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    if (req.method === "GET") {
      const data = await getDashboardData();
      return json(data);
    }

    if (req.method === "POST") {
      const body = await req.json();
      const result = await handleAction(body);
      return json(result);
    }

    return json({ error: "Method not allowed" }, 405);
  } catch (error) {
    console.error("Error:", error);
    return json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      500
    );
  }
});
