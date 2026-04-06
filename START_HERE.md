# START HERE - Review Dashboard

Welcome to your Supabase Edge Function for the video review dashboard!

## What You Have

A complete, production-ready video review dashboard with:
- ✅ Professional UI with The Roommates branding
- ✅ Video gallery with embedded players
- ✅ Approve/reject workflow
- ✅ Real-time statistics
- ✅ Database integration
- ✅ Responsive design

## 30 Second Setup

```bash
npm install -g supabase
supabase link --project-ref xrtyllishxovdpazjdco
supabase functions deploy review-dashboard
```

Then open: **https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard**

That's it!

## What's In This Directory

```
review-dashboard/
├── START_HERE.md ← You are here
├── QUICK_DEPLOY.md ← Deploy in 2 minutes
├── README.md ← Understand the features
├── DEPLOYMENT.md ← Full setup guide
├── IMPLEMENTATION_NOTES.md ← Technical details
├── FILES.md ← File reference
├── index.ts ← The actual function (deploy this!)
└── deno.json ← Deno configuration
```

## Choose Your Path

### I just want to deploy it
→ **QUICK_DEPLOY.md** (2 minutes)

### I want to understand what it does
→ **README.md** (5 minutes)

### I need full setup and customization help
→ **DEPLOYMENT.md** (10 minutes)

### I want to modify the code
→ **IMPLEMENTATION_NOTES.md** (15 minutes)

### I'm lost
→ **FILES.md** (file reference guide)

## How It Works

```
You visit the dashboard URL
        ↓
Function queries your database
    (generation_runs + production_queue)
        ↓
Dashboard loads with all your videos
        ↓
You click approve/reject
        ↓
Function updates the database
        ↓
Dashboard updates instantly
```

## What Gets Deployed

Just the `index.ts` file. That's the entire function - 838 lines of TypeScript that:
- Serves the HTML dashboard
- Queries your videos from the database
- Handles approve/reject actions
- Updates your database

Everything is self-contained. No dependencies to install, no build step needed.

## Key Features

### Video Gallery
- Embedded MP4 player for each video
- Shows shot name, character, duration, resolution
- Color-coded status badges
- Hover effects for interactivity

### Approval Workflow
- **Approve button** - One click to approve
- **Reject button** - Opens modal for optional notes
- Status updates instantly
- Database is updated automatically

### Dashboard Statistics
- **Approved count** - How many you've approved
- **Pending count** - How many need review
- **Rejected count** - How many you've rejected
- Updates in real-time as you approve/reject

### Filtering
- **All Videos** - See everything
- **Pending Review** - Only needs action
- **Approved** - Already approved videos
- **Rejected** - Rejected videos

### Styling
Professional design with The Roommates brand colors:
- **Burnt Orange** (#C45A2C) - Primary, pending status
- **Deep Navy** (#1E2A3A) - Text, headers
- **Cream** (#F5E6C8) - Accents
- **Teal** (#5B8A7A) - Approved status

Fully responsive - works on desktop, tablet, mobile.

## Database Tables Used

### generation_runs
```
id, production_queue_id, shot_name, character_name,
tool_used, video_url, drive_filename, drive_folder,
duration_seconds, resolution, fal_status, created_at
```

The dashboard updates `fal_status` when you approve/reject.

### production_queue
```
id, shot_name, status, concept_tag, characters_used,
song_title, capcut_notes
```

The dashboard updates `status` and stores rejection notes in `capcut_notes`.

## Environment Variables

The function automatically reads:
- `SUPABASE_URL` - Your project URL
- `SUPABASE_ANON_KEY` - Your publishable key

No manual setup needed - Supabase provides these.

## RLS Policies

Your database needs to allow reads and updates. Quick setup:

```sql
-- Allow all to read and update (simple)
CREATE POLICY "public_read" ON generation_runs FOR SELECT USING (true);
CREATE POLICY "public_update" ON generation_runs FOR UPDATE USING (true);

-- Same for production_queue
CREATE POLICY "public_read" ON production_queue FOR SELECT USING (true);
CREATE POLICY "public_update" ON production_queue FOR UPDATE USING (true);
```

For production, use stricter policies (see DEPLOYMENT.md).

## Common Questions

**Q: Is it safe to use the anonymous key?**
A: Yes! The anon/publishable key is designed for client-side use. RLS policies control access.

**Q: Can I change the colors?**
A: Yes! Edit the `<style>` section in index.ts and redeploy.

**Q: How many videos can it handle?**
A: Works great for 50-200 videos. For 200+, add pagination (see DEPLOYMENT.md).

**Q: Can I add more fields?**
A: Yes! Modify the query and HTML template (see IMPLEMENTATION_NOTES.md).

**Q: Does it need authentication?**
A: No, but you can add it via RLS policies.

## Deployment Checklist

- [ ] Have Supabase CLI installed
- [ ] Know your project ID: `xrtyllishxovdpazjdco`
- [ ] Have data in your tables (or add test data)
- [ ] Run `supabase link --project-ref xrtyllishxovdpazjdco`
- [ ] Run `supabase functions deploy review-dashboard`
- [ ] Visit the dashboard URL
- [ ] Test approve/reject
- [ ] Check database for updates

## What Happens When You Deploy

1. Supabase creates a new Edge Function
2. Your code is deployed to the edge (Deno runtime)
3. Function is instantly available at the public URL
4. Returns HTML on GET requests
5. Handles database updates on POST requests
6. Scales automatically

## Next Steps

### Right Now
1. Choose a guide above (Quick Deploy if unsure)
2. Follow the 30-second setup
3. Visit your dashboard

### After Deployment
1. Test with your actual videos
2. Try approve/reject buttons
3. Verify database updates
4. Share URL with your team

### Customization
1. Change colors (in index.ts)
2. Add more fields (in index.ts)
3. Adjust layout (in index.ts CSS)
4. Redeploy: `supabase functions deploy review-dashboard`

## Troubleshooting

**Videos don't appear?**
- Check that data exists in your tables
- Verify RLS policies allow SELECT
- Check browser console for errors (F12)

**Approve/Reject doesn't work?**
- Check RLS policies allow UPDATE
- Check browser console for errors
- Check function logs: `supabase functions logs review-dashboard`

**Styling looks broken?**
- Clear browser cache (Ctrl+Shift+Del)
- Try a different browser
- Check for console errors

See DEPLOYMENT.md for detailed troubleshooting.

## Files At A Glance

| File | Purpose | Size |
|------|---------|------|
| **index.ts** | The edge function (deploy this!) | 21 KB |
| **deno.json** | Dependencies config | 269 B |
| **QUICK_DEPLOY.md** | Fast setup guide | 2.4 KB |
| **README.md** | Feature overview | 7.7 KB |
| **DEPLOYMENT.md** | Complete setup guide | 8.3 KB |
| **IMPLEMENTATION_NOTES.md** | Technical reference | 8.7 KB |
| **FILES.md** | File reference guide | 6.4 KB |

## You're All Set!

Everything you need is in this directory. Follow one of the guides above and you'll have your dashboard running in minutes.

**Questions?** Each guide has a troubleshooting section.

**Ready?** → Go to QUICK_DEPLOY.md

---

**Project**: The Roommates Video Review Dashboard
**Version**: 1.0
**Created**: April 2026
**Status**: Ready to deploy
