# Review Dashboard Edge Function - Deployment Guide

## Overview

This is a Supabase Edge Function that serves a professional review dashboard for video approval/rejection workflows. The function is built with Deno and uses Supabase's JavaScript client library for database operations.

### Features

- Displays all videos from `generation_runs` joined with `production_queue` data
- Embedded video players with approve/reject buttons
- Summary statistics (approved, pending, rejected counts)
- Responsive design with The Roommates brand colors
- Filter videos by status
- Client-side state management with real-time UI updates
- The Roommates brand styling: burnt orange (#C45A2C), deep navy (#1E2A3A), cream (#F5E6C8), teal (#5B8A7A)

## Prerequisites

Before deploying, ensure you have:

1. **Supabase CLI** installed:
   ```bash
   npm install -g supabase
   ```

2. **Access to the Supabase project**: xrtyllishxovdpazjdco

3. **Project structure**: The function files should be in:
   ```
   supabase/functions/review-dashboard/
   ├── index.ts
   ├── deno.json
   └── DEPLOYMENT.md (this file)
   ```

## Environment Variables

The function automatically reads these from your Supabase project:

- `SUPABASE_URL`: Your Supabase project URL (automatically set)
- `SUPABASE_ANON_KEY`: Your Supabase anonymous/publishable key (automatically set)

These are injected by Supabase at runtime, so no manual configuration is needed.

## Local Testing (Optional)

You can test the function locally before deploying:

```bash
# Start the Supabase local development stack
supabase start

# In another terminal, serve the function locally
supabase functions serve

# Access the function at http://localhost:54321/functions/v1/review-dashboard
```

## Deployment Steps

### Option 1: Using Supabase CLI (Recommended)

1. **Link your local project to Supabase**:
   ```bash
   supabase link --project-ref xrtyllishxovdpazjdco
   ```

2. **Deploy the function**:
   ```bash
   supabase functions deploy review-dashboard
   ```

3. **Verify deployment**:
   ```bash
   supabase functions list
   ```

### Option 2: Using Supabase Dashboard

1. Navigate to your Supabase project dashboard
2. Go to **Edge Functions** in the left sidebar
3. Click **Create a new function**
4. Name it `review-dashboard`
5. Copy the entire contents of `index.ts` into the editor
6. Click **Deploy**

## Accessing the Dashboard

Once deployed, access the dashboard at:

```
https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
```

## How It Works

### GET Request (Load Dashboard)

When you visit the function URL, it:

1. Fetches all `generation_runs` with joined `production_queue` data
2. Calculates summary statistics (approved, pending, rejected counts)
3. Generates HTML with embedded Supabase client
4. Renders the dashboard with all videos

### POST Request (Update Video Status)

When you click approve/reject in the dashboard:

1. JavaScript sends a POST request with:
   - `generation_run_id`: The video's generation run ID
   - `production_queue_id`: The parent production queue ID
   - `status`: "approve" or "reject"
   - `notes`: Optional rejection notes

2. The function updates two tables:
   - **generation_runs**: Sets `fal_status` to "approved" or "rejected"
   - **production_queue**: Sets `status` to "approved" or "rejected", and stores rejection notes in `capcut_notes.rejection_reason`

## Database Access

The function uses the Supabase anonymous/publishable key. Ensure your Supabase Row Level Security (RLS) policies allow:

### Required RLS Policies

**For generation_runs table:**
- Read access: SELECT (public or authenticated)
- Write access: UPDATE (authenticated users only, or via service role)

**For production_queue table:**
- Read access: SELECT (public or authenticated)
- Write access: UPDATE (authenticated users only, or via service role)

**Example RLS Policy** (if using authentication):

```sql
-- Allow authenticated users to read generation_runs
CREATE POLICY "Allow authenticated users to read generation_runs"
ON generation_runs
FOR SELECT
USING (auth.role() = 'authenticated');

-- Allow authenticated users to update their own records
CREATE POLICY "Allow updates to generation_runs"
ON generation_runs
FOR UPDATE
USING (auth.role() = 'authenticated');
```

If you want to allow unauthenticated access, modify the policies accordingly:

```sql
-- Allow anonymous users to read
CREATE POLICY "Allow anonymous read"
ON generation_runs
FOR SELECT
USING (true);

-- Allow anonymous updates (less secure, use with caution)
CREATE POLICY "Allow anonymous updates"
ON generation_runs
FOR UPDATE
USING (true);
```

## Customization

### Styling

The brand colors are defined in the CSS:
- **Burnt Orange**: #C45A2C (primary action buttons)
- **Deep Navy**: #1E2A3A (text, headers)
- **Cream**: #F5E6C8 (accent background)
- **Teal**: #5B8A7A (approved status, secondary buttons)

To modify colors, edit the `<style>` section in the `generateHTML()` function.

### Adding More Metadata

To display additional fields from the database:

1. Update the `.select()` query to include new fields
2. Update the TypeScript interfaces (`GenerationRun`, `ProductionQueueItem`)
3. Add new HTML elements in the `card.innerHTML` template

Example:
```typescript
// In getDashboardData()
.select(`
  id,
  production_queue_id,
  song_title,  // Add new field
  ...
`)
```

### Adjusting the Grid Layout

Modify the `videos-grid` CSS:
```css
.videos-grid {
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  /* Change minmax value for different card sizes */
}
```

## Troubleshooting

### "Unauthorized" or "403" Errors

**Issue**: RLS policies are blocking access

**Solution**:
- Check RLS policies on `generation_runs` and `production_queue` tables
- Ensure anonymous access is enabled if not using authentication
- Verify the SUPABASE_ANON_KEY is correct

### Videos Not Loading

**Issue**: Video URLs are invalid or CORS-blocked

**Solution**:
- Verify `video_url` values in the database are valid and accessible
- Check that the video hosting service allows cross-origin requests
- Use a proxy or CDN if needed

### Function Returns 500 Error

**Issue**: Database query or processing error

**Solution**:
- Check Edge Function logs: `supabase functions logs review-dashboard`
- Verify table names and column names match your schema
- Ensure all required columns exist in the database

### Dashboard Shows No Videos

**Issue**: Database query returns empty result

**Solution**:
- Verify data exists in `generation_runs` and `production_queue` tables
- Check that the join is working correctly (production_queue_id exists)
- Review RLS policies to ensure SELECT access is granted

## Monitoring

### View Function Logs

```bash
supabase functions logs review-dashboard --limit 100
```

### Check Function Invocations

In the Supabase dashboard:
1. Navigate to **Edge Functions**
2. Click on **review-dashboard**
3. View recent invocations and their status

## Updates and Maintenance

### Deploying Updates

After making changes to `index.ts`:

```bash
supabase functions deploy review-dashboard
```

The function will be updated immediately.

### Rollback

If you need to revert to a previous version:

```bash
# Check function version history in the dashboard
# Or redeploy an earlier version of index.ts
supabase functions deploy review-dashboard
```

## Performance Considerations

- **Video Count**: The function loads all videos into memory. For 100+ videos, consider adding pagination.
- **Large Video Files**: Streaming from direct URLs is handled by the browser; very large files may buffer.
- **Database Queries**: The initial load makes one query with a join. This is optimized for typical use cases.

## Security Notes

1. **Anonymous Key**: The function uses the SUPABASE_ANON_KEY (publishable key), which is safe to embed in HTML.
2. **Service Role Key**: Never use the service_role key in client-facing code.
3. **RLS Policies**: Implement strict RLS policies to control who can view/edit video data.
4. **CORS**: The function includes CORS headers for cross-origin requests.

## Support

For issues or questions:

1. Check Supabase documentation: https://supabase.com/docs
2. Review Edge Functions guide: https://supabase.com/docs/guides/functions
3. Check function logs for errors

---

**Last Updated**: April 2026
**Function Version**: 1.0
