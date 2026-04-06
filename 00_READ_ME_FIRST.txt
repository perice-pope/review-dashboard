================================================================================
                    REVIEW DASHBOARD - READ ME FIRST
================================================================================

Welcome! You have a complete Supabase Edge Function ready to deploy.

LOCATION: /mnt/Rommates Manager/supabase-functions/review-dashboard/

================================================================================
                            WHAT YOU HAVE
================================================================================

A professional video review dashboard with:
  ✓ Video gallery with embedded players
  ✓ Approve/reject workflow with optional notes
  ✓ Real-time statistics (approved/pending/rejected)
  ✓ Status filtering
  ✓ The Roommates brand styling
  ✓ Responsive design (mobile, tablet, desktop)
  ✓ Complete database integration
  ✓ Ready to deploy - no modifications needed!

================================================================================
                        FASTEST DEPLOYMENT (30 seconds)
================================================================================

npm install -g supabase
supabase link --project-ref xrtyllishxovdpazjdco
supabase functions deploy review-dashboard

Then visit:
https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard

That's it!

================================================================================
                          WHICH FILE TO READ?
================================================================================

START_HERE.md
  → Quick overview and navigation guide (2 min read)
  → Read this first if you're lost

QUICK_DEPLOY.md
  → Step-by-step deployment instructions (2 min)
  → Follow this to deploy immediately

README.md
  → Feature overview and usage guide (5 min)
  → Read this to understand what it does

DEPLOYMENT.md
  → Complete setup, customization, troubleshooting (15 min)
  → Read this for customization options and full details

IMPLEMENTATION_NOTES.md
  → Technical architecture and code details (15 min)
  → Read this if you want to modify the code

FILES.md
  → Reference guide to all files
  → Read this to understand the file structure

index.ts
  → The actual edge function code (838 lines)
  → This is what gets deployed - no modifications needed!

deno.json
  → Deno dependencies configuration
  → Leave this as-is

================================================================================
                            QUICK FACTS
================================================================================

Project ID:     xrtyllishxovdpazjdco
Function URL:   https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
Runtime:        Deno (TypeScript)
Files Needed:   Just index.ts (Supabase CLI handles dependencies)

Database Tables:
  - generation_runs (queries + updates fal_status)
  - production_queue (updates status + capcut_notes)

Brand Colors:
  - Burnt Orange (#C45A2C) - Primary, pending status
  - Deep Navy (#1E2A3A) - Text, headers
  - Cream (#F5E6C8) - Accents
  - Teal (#5B8A7A) - Approved status

================================================================================
                            I JUST WANT TO...
================================================================================

"Deploy it now"
→ Copy-paste the 3 commands above, then visit the URL

"Understand what it does"
→ Read README.md

"Deploy it with full details"
→ Follow DEPLOYMENT.md step-by-step

"Change the colors/styling"
→ Read DEPLOYMENT.md → Customization section
→ Edit index.ts → Redeploy

"Modify the code"
→ Read IMPLEMENTATION_NOTES.md for architecture
→ Edit index.ts
→ Run: supabase functions deploy review-dashboard

"Troubleshoot an issue"
→ See DEPLOYMENT.md → Troubleshooting section

"Understand the code"
→ Read IMPLEMENTATION_NOTES.md

================================================================================
                         DEPLOYMENT CHECKLIST
================================================================================

Before deploying, ensure:

  [ ] You have Supabase CLI installed
      npm install -g supabase

  [ ] You know your project ID
      xrtyllishxovdpazjdco

  [ ] Your database has:
      - generation_runs table with required columns
      - production_queue table with required columns
      - Some test data (or data to review)

  [ ] RLS policies allow:
      - SELECT on both tables
      - UPDATE on both tables

Then:
  [ ] Run: supabase link --project-ref xrtyllishxovdpazjdco
  [ ] Run: supabase functions deploy review-dashboard
  [ ] Visit: https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
  [ ] Test the approve/reject buttons
  [ ] Check your database for updates

================================================================================
                           WHAT GETS DEPLOYED
================================================================================

Just the index.ts file!

That one file contains:
  - HTML dashboard (complete with CSS and JavaScript)
  - Database query logic
  - Approve/reject handler
  - Everything needed

No separate builds, dependencies, or configuration needed.
Supabase CLI handles the rest automatically.

================================================================================
                          HOW IT WORKS (30 second version)
================================================================================

1. You visit the dashboard URL
2. Function queries generation_runs + production_queue from your database
3. Dashboard loads with all your videos
4. You click approve or reject
5. JavaScript sends the action to the function
6. Function updates your database
7. Dashboard updates instantly

That's it!

================================================================================
                           KEY FEATURES
================================================================================

VIDEO GALLERY
  - Embedded MP4 player for each video (click play to watch)
  - Shows shot name, character, duration, resolution
  - Color-coded status (pending, approved, rejected)

APPROVAL WORKFLOW
  - "Approve" button - one click to approve
  - "Reject" button - opens form for optional notes
  - Status updates instantly
  - Database is updated automatically

STATISTICS
  - Shows total approved count
  - Shows pending review count
  - Shows rejected count
  - Updates as you approve/reject

FILTERING
  - "All Videos" - see everything
  - "Pending Review" - only videos needing action
  - "Approved" - see approved videos
  - "Rejected" - see rejected videos

STYLING
  - Professional design with The Roommates brand colors
  - Hover effects and smooth transitions
  - Fully responsive (desktop, tablet, mobile)
  - Clean, modern UI

================================================================================
                        ENVIRONMENT VARIABLES
================================================================================

The function automatically uses:
  - SUPABASE_URL (automatically provided by Supabase)
  - SUPABASE_ANON_KEY (automatically provided by Supabase)

You don't need to set these manually!
Supabase injects them at runtime.

================================================================================
                         DATABASE REQUIREMENTS
================================================================================

Your database must have these tables:

generation_runs
  - id (uuid)
  - production_queue_id (uuid) - foreign key to production_queue
  - shot_name (text)
  - character_name (text)
  - tool_used (text)
  - video_url (text) - URL to video file (important!)
  - drive_filename (text)
  - drive_folder (text)
  - duration_seconds (integer)
  - resolution (text)
  - fal_status (text) - will be updated by dashboard
  - created_at (timestamp)

production_queue
  - id (uuid)
  - shot_name (text)
  - status (text) - will be updated by dashboard
  - concept_tag (text)
  - characters_used (array or jsonb)
  - song_title (text)
  - capcut_notes (jsonb) - will store rejection_reason

RLS Policies needed:
  - Allow SELECT on both tables
  - Allow UPDATE on both tables

Quick RLS setup (simple version - see DEPLOYMENT.md for secure version):
  CREATE POLICY "all_select" ON generation_runs FOR SELECT USING (true);
  CREATE POLICY "all_update" ON generation_runs FOR UPDATE USING (true);
  CREATE POLICY "all_select" ON production_queue FOR SELECT USING (true);
  CREATE POLICY "all_update" ON production_queue FOR UPDATE USING (true);

================================================================================
                         COMMON QUESTIONS
================================================================================

Q: Do I need to modify any code?
A: No! Deploy as-is. You can customize later if needed.

Q: Is it safe to use the anonymous key?
A: Yes! The anon/publishable key is designed for client use.
   RLS policies control what data users can access.

Q: Can I change the colors?
A: Yes! Edit the <style> section in index.ts, then redeploy.

Q: How many videos can it handle?
A: Works great for 50-200 videos. For 200+, see DEPLOYMENT.md
   for pagination tips.

Q: Can I add more fields to display?
A: Yes! Modify the .select() query in index.ts and the HTML
   template. See IMPLEMENTATION_NOTES.md for details.

Q: Does this need authentication?
A: No, but you can add it via RLS policies.
   See DEPLOYMENT.md for examples.

Q: What happens if I refresh the page?
A: The dashboard reloads fresh data from your database.

Q: Can I use this on a phone?
A: Yes! Full responsive design works on phones/tablets/desktops.

Q: How do I update the code?
A: Edit index.ts, then run: supabase functions deploy review-dashboard

================================================================================
                              SUPPORT
================================================================================

If something isn't working:

1. Check DEPLOYMENT.md → Troubleshooting section

2. Check function logs:
   supabase functions logs review-dashboard

3. Check browser console:
   Open dashboard → Press F12 → Look for errors

4. Verify RLS policies allow access:
   Check in Supabase dashboard

5. Verify data exists in your tables:
   Check in Supabase dashboard

================================================================================
                            NEXT STEPS
================================================================================

1. If you're new here:
   → Read START_HERE.md

2. If you want to deploy immediately:
   → Copy-paste the 3 commands at the top of this file
   → Visit the URL that appears
   → Done!

3. If you want more details:
   → Read QUICK_DEPLOY.md (2 minutes)
   → Or README.md (5 minutes)
   → Or DEPLOYMENT.md (full guide)

4. After deploying:
   → Test with your videos
   → Try approve/reject
   → Check your database for updates
   → Share the URL with your team

================================================================================

You have everything you need. Just deploy and start using it!

Questions? See the file you need in the list above.
Ready? Copy-paste the 3 deployment commands and you're done!

================================================================================
