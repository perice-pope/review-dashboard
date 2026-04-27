import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";
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
  rationale: string;
};

async function proposeRevisionWithClaude(
  shot: Record<string, unknown>,
  run: Record<string, unknown>,
  feedback: string,
  validCharacters: string[],
): Promise<ProposedRevision> {
  if (!ANTHROPIC_API_KEY) {
    throw new Error(
      "ANTHROPIC_API_KEY not set in edge function secrets — cannot propose revision",
    );
  }

  const systemPrompt = [
    "You are a prompt engineer for the Runway Gen-4 References video model. Your job is to revise a shot's runway_prompt to address reviewer feedback WHILE strictly following Runway's official prompting rules.",
    "",
    "RUNWAY GEN-4 PROMPTING RULES (CRITICAL — apply these even when the feedback doesn't mention them):",
    "",
    "1. REFERENCES HANDLE IDENTITY. Each @-tagged character has a reference image that defines face, hair, build, age, clothing, and accessories. The PROMPT MUST NOT redescribe any of these. Forbidden in the prompt text: hair color, hair style, age, build, race, clothing item, clothing color, accessories, facial features, jewelry. If the prior prompt contains any of these, STRIP them out — this is opportunistic cleanup you do every time, not just when the feedback asks for it.",
    "",
    "2. PROMPTS HANDLE ACTION + ENVIRONMENT + CAMERA + MOOD. Keep only what describes what the characters DO (verbs, motion, gestures), WHERE they are (location, lighting, atmosphere, weather), how the CAMERA moves (push, pull, pan, eye level, framing, lens), and what the scene FEELS like (mood, audio cues that drive action).",
    "",
    "3. PRESERVE EXPLICIT NEGATIVE-PROMPT INSTRUCTIONS. Phrases like 'no breath vapor', 'no eye contact', 'NOT choreography', 'NOT 3D', 'do not show X' are deliberate constraints, often added in response to prior reviewer feedback. KEEP them intact — negative guidance is NOT bloat.",
    "",
    "4. KEEP IT REASONABLY CONCISE. Cut decorative redundancy, but never at the cost of Rule 3 caveats. There is no hard length limit — clarity beats brevity.",
    "",
    "5. CHARACTERS ARE @-TAGGED. Format: @Name (e.g. @Noah). The reference image bound to that name supplies their look. Just say what @Name does — never describe how they look.",
    "",
    "6. PRESERVE the global visual-style line if present (e.g. 'Roommates visual style: warm flat illustration, subtle gradients...') — that is rendering style, not character identity. Keep it intact.",
    "",
    "Use only character names from the provided valid list. Respond via the propose_revision tool. In the rationale, briefly note (a) what feedback you addressed and (b) what Rule 1 cleanup you performed.",
  ].join("\n");

  const userMessage = [
    `SHOT NAME: ${shot.shot_name ?? ""}`,
    `CURRENT runway_prompt:\n${shot.runway_prompt ?? ""}`,
    `CURRENT characters_used: ${shot.characters_used ?? ""}`,
    `VALID CHARACTER NAMES: ${validCharacters.join(", ")}`,
    `PRIOR TAKE'S character_name field: ${run.character_name ?? "(unknown)"}`,
    `PRIOR TAKE'S drive_filename: ${run.drive_filename ?? "(unknown)"}`,
    "",
    "REVIEWER FEEDBACK ON THE PRIOR TAKE:",
    feedback,
    "",
    "Propose an updated runway_prompt and characters_used. Address the feedback, AND strip any Rule-1 identity descriptors you find in the current prompt.",
  ].join("\n");

  const tool = {
    name: "propose_revision",
    description:
      "Submit the proposed updates for the shot's runway_prompt and characters_used.",
    input_schema: {
      type: "object",
      properties: {
        runway_prompt: {
          type: "string",
          description:
            "The full updated prompt to send to Runway. Include all context — this replaces the prior prompt, it does not append.",
        },
        characters_used: {
          type: "string",
          description:
            "Comma-separated character names. Must be drawn from the valid list.",
        },
        rationale: {
          type: "string",
          description:
            "1-3 sentences describing what you changed and why, addressing the feedback.",
        },
      },
      required: ["runway_prompt", "characters_used", "rationale"],
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
      const allowed = ["queued", "generating", "generated", "review_pending", "revision_needed", "approved", "rejected", "in_assembly", "in_post", "final_review", "complete", "shipped"];
      const newStatus = body.status as string;
      if (!allowed.includes(newStatus)) throw new Error("Invalid status: " + newStatus);
      const { error } = await client
        .from("production_queue")
        .update({ status: newStatus, updated_at: new Date().toISOString() })
        .eq("id", body.shot_id as string);
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

      const validCharacters = await fetchValidCharacters();
      const proposal = await proposeRevisionWithClaude(
        shot as Record<string, unknown>,
        run as Record<string, unknown>,
        feedback,
        validCharacters,
      );

      return {
        success: true,
        shot_id: shotId,
        run_id: runId,
        feedback,
        current: {
          runway_prompt: (shot as { runway_prompt: string | null }).runway_prompt || "",
          characters_used: (shot as { characters_used: string | null }).characters_used || "",
        },
        proposed: proposal,
      };
    }
    case "apply_revision": {
      const shotId = body.shot_id as string;
      const runId = body.run_id as string;
      const newPrompt = body.runway_prompt as string;
      const newCharacters = body.characters_used as string;
      const feedback = (body.feedback as string) || "";
      if (!shotId || !runId) throw new Error("shot_id and run_id required");

      const { data: shot, error: shotErr } = await client
        .from("production_queue")
        .select("runway_prompt, characters_used")
        .eq("id", shotId)
        .single();
      if (shotErr) throw shotErr;

      const { error: updErr } = await client
        .from("production_queue")
        .update({
          runway_prompt: newPrompt,
          characters_used: newCharacters,
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

      return { success: true };
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
