# Review Dashboard Edge Function

A professional video review dashboard for The Roommates, built as a Supabase Edge Function.

## Quick Start

### Deploy in 2 Minutes

```bash
# Install Supabase CLI (if not already installed)
npm install -g supabase

# Navigate to the supabase directory
cd your-project/supabase

# Link to your project
supabase link --project-ref xrtyllishxovdpazjdco

# Deploy the function
supabase functions deploy review-dashboard

# Access at: https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
```

## What It Does

This Edge Function provides a complete video review dashboard with:

- **Video Gallery**: All videos from `generation_runs` displayed with thumbnails
- **Approve/Reject**: One-click actions to approve or reject videos with optional notes
- **Live Statistics**: Real-time counts of approved, pending, and rejected videos
- **Filtering**: Sort videos by status (all, pending, approved, rejected)
- **Professional Styling**: The Roommates brand colors and responsive design
- **Database Integration**: Automatically updates `generation_runs` and `production_queue` tables

## File Structure

```
review-dashboard/
├── index.ts           # Main function code (this is all you need to deploy)
├── deno.json         # Deno configuration with dependencies
├── README.md         # This file
└── DEPLOYMENT.md     # Detailed deployment and customization guide
```

## How It Works

### Architecture

```
Browser Request
    ↓
Edge Function (Deno)
    ├─ GET: Returns HTML dashboard with embedded JS client
    └─ POST: Processes approve/reject actions and updates DB
        ↓
    Supabase Database
    ├─ generation_runs table (read/write)
    └─ production_queue table (read/write)
```

### Data Flow

1. **Load Dashboard (GET)**
   - Function queries `generation_runs` with `production_queue` join
   - Calculates statistics
   - Serves HTML with embedded Supabase client and video data

2. **User Action (POST)**
   - User clicks approve/reject button
   - JavaScript sends POST with video IDs and action
   - Function updates both tables
   - UI updates to reflect changes

## Database Tables

### generation_runs
```
- id (uuid)
- production_queue_id (uuid) - foreign key
- shot_name (text)
- character_name (text)
- tool_used (text)
- video_url (text) - URL to the video file
- drive_filename (text)
- drive_folder (text)
- duration_seconds (integer)
- resolution (text)
- fal_status (text) - updated by dashboard
- created_at (timestamp)
```

### production_queue
```
- id (uuid)
- shot_name (text)
- status (text) - updated by dashboard
- concept_tag (text)
- characters_used (text[])
- song_title (text)
- capcut_notes (jsonb) - stores rejection_reason
```

## Styling

The dashboard uses The Roommates brand colors:

- **Burnt Orange** (#C45A2C): Primary actions, pending status
- **Deep Navy** (#1E2A3A): Text, headers, primary elements
- **Cream** (#F5E6C8): Accents, tags
- **Teal** (#5B8A7A): Approved status, secondary buttons

Responsive design works on desktop, tablet, and mobile.

## Features

### Summary Bar
Shows live counts of approved, pending, and rejected videos at the top.

### Video Cards
Each video card displays:
- Embedded video player (controls included)
- Shot name
- Character name
- Duration and resolution
- Concept tag
- Current status badge
- Approve/Reject buttons (disabled for already-processed videos)

### Filtering
Filter videos by status:
- **All Videos**: Shows everything
- **Pending Review**: Only videos awaiting decision
- **Approved**: Shows approved videos
- **Rejected**: Shows rejected videos

### Status Indicators
- Color-coded borders on cards
- Status badges with appropriate colors
- Summary bar with counts

### Rejection Notes
Optional text field when rejecting videos. Notes are stored in the database for editor reference.

## Environment Variables

The function automatically uses:
- `SUPABASE_URL`: Your project URL
- `SUPABASE_ANON_KEY`: Your publishable key

These are injected by Supabase at runtime. No manual configuration needed.

## RLS Policies

For the dashboard to work, your tables need Row Level Security policies that allow:

1. **Read access** to `generation_runs` and `production_queue`
2. **Update access** to both tables

Quick setup (if using authentication):

```sql
-- Generate an anon user role if needed
-- Then set policies to allow authenticated access

-- For generation_runs
CREATE POLICY "allow_all_read" ON generation_runs FOR SELECT USING (true);
CREATE POLICY "allow_all_update" ON generation_runs FOR UPDATE USING (true);

-- For production_queue
CREATE POLICY "allow_all_read" ON production_queue FOR SELECT USING (true);
CREATE POLICY "allow_all_update" ON production_queue FOR UPDATE USING (true);
```

## Usage

### Step 1: Deploy
Follow the Quick Start section above.

### Step 2: Access
Open the function URL in your browser:
```
https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
```

### Step 3: Review Videos
- Watch embedded videos
- Click **Approve** to accept (updates `status` to "approved")
- Click **Reject** to reject with optional notes

## Customization

### Change Colors
Edit the `<style>` section in `index.ts`:
```css
/* Change these hex values */
#C45A2C /* Burnt orange */
#1E2A3A /* Deep navy */
#F5E6C8 /* Cream */
#5B8A7A /* Teal */
```

### Add More Fields
Update the `.select()` query and card HTML template to display additional data.

### Adjust Grid Layout
Change the grid columns in CSS:
```css
.videos-grid {
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  /* Adjust minmax value for wider/narrower cards */
}
```

See `DEPLOYMENT.md` for more customization options.

## Troubleshooting

### Videos not showing?
- Check that `generation_runs` table has data
- Verify `video_url` fields are valid URLs
- Check RLS policies allow SELECT

### Approve/Reject not working?
- Check browser console for errors (F12)
- Verify RLS policies allow UPDATE
- Check function logs: `supabase functions logs review-dashboard`

### Function returns error?
- Check that table names match your schema
- Verify all columns exist in your tables
- Check logs for specific error message

See `DEPLOYMENT.md` for detailed troubleshooting.

## Performance

- **Fast**: Single database query with join, results cached in browser
- **Scalable**: Works well with 50-200 videos
- **Responsive**: All updates are instant (client-side optimistic updates)

For 200+ videos, consider adding pagination (see `DEPLOYMENT.md`).

## Development

### Local Testing
```bash
supabase start
supabase functions serve
# Visit http://localhost:54321/functions/v1/review-dashboard
```

### Making Changes
1. Edit `index.ts`
2. Save
3. Run `supabase functions deploy review-dashboard`
4. Changes are live immediately

## API

The function exposes two endpoints:

### GET /functions/v1/review-dashboard
Returns HTML dashboard page.

**Response**: HTML document with embedded Supabase client

### POST /functions/v1/review-dashboard
Updates video status.

**Request Body**:
```json
{
  "action": "update_status",
  "generation_run_id": "uuid",
  "production_queue_id": "uuid",
  "status": "approve" | "reject",
  "notes": "optional rejection notes"
}
```

**Response**:
```json
{
  "success": true
}
```

## Security

- Uses Supabase anonymous key (safe for client-side)
- Never includes service_role key in client code
- RLS policies control data access
- CORS headers properly configured

## Next Steps

1. Deploy using the Quick Start above
2. Access your dashboard
3. Test approve/reject functionality
4. Check logs to verify everything works
5. See `DEPLOYMENT.md` for customization and advanced configuration

---

For detailed deployment, troubleshooting, and customization, see `DEPLOYMENT.md`.
