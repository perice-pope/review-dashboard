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
    case "change_status": {
      const allowed = ["queued", "generating", "generated", "review_pending", "revision_needed", "approved", "rejected", "in_assembly", "in_post", "final_review", "complete", "shipped"];
      const newStatus = body.status as string;
      if (!allowed.includes(newStatus)) throw new Error("Invalid status: " + newStatus);
      const { error } = await client
        .from("production_queue")
        .update({ status: newStatus, updated_at: new Date().toISOString() })
        .eq("id", body.shot_id as string);
      if (error) throw error;
      break;
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
      await handleAction(body);
      return json({ success: true });
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
