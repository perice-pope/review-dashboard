# Quick Deploy Guide - 2 Minute Setup

## Copy-Paste Deployment

```bash
# 1. Install Supabase CLI (one time only)
npm install -g supabase

# 2. Navigate to your supabase directory
cd /path/to/your/project/supabase

# 3. Link to your project
supabase link --project-ref xrtyllishxovdpazjdco

# 4. Deploy the function
supabase functions deploy review-dashboard

# 5. Done! Access at:
# https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
```

## What You Just Deployed

A Deno edge function that serves a professional video review dashboard with:

- ✅ Video gallery with embedded players
- ✅ Approve/reject buttons with optional notes
- ✅ Real-time statistics (approved/pending/rejected counts)
- ✅ Status filtering
- ✅ The Roommates brand styling
- ✅ Automatic database updates

## Next Steps

1. **Access the dashboard** at the URL above
2. **Approve/reject videos** using the buttons
3. **Check your database** - updates are saved automatically
4. **Read DEPLOYMENT.md** for customization options

## Files

- **index.ts** - The complete edge function (this is what gets deployed)
- **deno.json** - Dependency configuration
- **README.md** - Feature overview and usage guide
- **DEPLOYMENT.md** - Detailed setup, customization, and troubleshooting

## Database Updates

When you approve/reject a video:

**generation_runs table:**
- `fal_status` → "approved" or "rejected"

**production_queue table:**
- `status` → "approved" or "rejected"
- `capcut_notes.rejection_reason` → any notes you added

## Need Help?

- **Won't deploy?** Check you have Supabase CLI installed
- **Videos not showing?** Verify data exists in your tables
- **Approve/reject failing?** Check RLS policies (see DEPLOYMENT.md)

See **DEPLOYMENT.md** for full troubleshooting guide.

## Common Questions

**Q: Does this need authentication?**
A: No, the function works with your anonymous/publishable key. If you want auth, add it to your RLS policies.

**Q: Can I change the colors?**
A: Yes! Edit the `<style>` section in index.ts, then redeploy.

**Q: How many videos can it handle?**
A: Works great with 50-200 videos. For 200+, add pagination (see DEPLOYMENT.md).

**Q: Is this secure?**
A: Yes! Uses only the anon/publishable key (never service_role). RLS policies control access.

## Redeploy After Changes

```bash
# After editing index.ts
supabase functions deploy review-dashboard
```

That's it! Changes are live immediately.
