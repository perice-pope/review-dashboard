# Implementation Notes

## Technical Architecture

This edge function is built with:

- **Runtime**: Deno (serverless JavaScript/TypeScript)
- **Database Client**: @supabase/supabase-js v2
- **Frontend**: HTML5, vanilla JavaScript (no framework)
- **Authentication**: Supabase anonymous/publishable key

## Code Structure

### Backend (index.ts)

#### Interfaces
```typescript
GenerationRun        // Fields from generation_runs table
ProductionQueueItem  // Fields from production_queue table
DashboardData        // Aggregated data for dashboard
```

#### Functions

**getDashboardData()** - Main query function
- Performs a single join query between tables
- Calculates statistics (approved, pending, rejected counts)
- Returns typed DashboardData object
- Sorted by created_at (newest first)

**updateVideoStatus()** - Handles approve/reject
- Updates generation_runs fal_status
- Updates production_queue status
- Stores rejection notes in capcut_notes.rejection_reason
- Both updates in a single request cycle

**generateHTML()** - Dynamic HTML generation
- Embeds all video data as JSON in script
- Includes Supabase JS client CDN link
- All styling done via CSS-in-JS (no external stylesheets)
- Responsive design with mobile-first approach

#### Request Handlers

**GET** requests:
- Return the HTML dashboard page
- CORS headers included
- Content-Type: text/html

**POST** requests:
- Expect JSON with action, IDs, and status
- Call updateVideoStatus()
- Return JSON response with success flag
- CORS headers included

### Frontend (Embedded in HTML)

#### HTML Structure
```html
<header>        <!-- Summary bar with counts -->
<main>          <!-- Filter buttons and video grid -->
<modal>         <!-- Rejection notes form -->
<script>        <!-- Supabase client and interactivity -->
```

#### JavaScript Features

**Data Management**
- allVideos array holds current video state
- Updated optimistically on client
- Filter logic separates approved/pending/rejected

**Supabase Integration**
- Creates client on page load
- Reads SUPABASE_URL and SUPABASE_ANON_KEY from HTML
- Handles POST requests via fetch

**UI Updates**
- renderVideos() regenerates grid when filter changes
- Message alerts show success/error
- Modal for rejection notes
- Optimistic UI updates before server confirmation

## Database Schema Requirements

### generation_runs
```sql
CREATE TABLE generation_runs (
  id uuid PRIMARY KEY,
  production_queue_id uuid REFERENCES production_queue(id),
  shot_name text,
  character_name text,
  tool_used text,
  video_url text,        -- Must be a valid video URL
  drive_filename text,
  drive_folder text,
  duration_seconds integer,
  resolution text,
  fal_status text,       -- Will be updated by dashboard
  created_at timestamp DEFAULT now()
);
```

### production_queue
```sql
CREATE TABLE production_queue (
  id uuid PRIMARY KEY,
  shot_name text,
  status text,           -- Will be updated by dashboard
  concept_tag text,
  characters_used text[] or jsonb,
  song_title text,
  capcut_notes jsonb     -- Will store rejection reasons
);
```

## RLS Policy Examples

For public/anonymous access:

```sql
-- Allow all to read
CREATE POLICY "public_read"
ON generation_runs
FOR SELECT
USING (true);

-- Allow all to update
CREATE POLICY "public_update"
ON generation_runs
FOR UPDATE
USING (true);

-- Same for production_queue
```

For authenticated-only access:

```sql
-- Allow authenticated to read
CREATE POLICY "auth_read"
ON generation_runs
FOR SELECT
USING (auth.role() = 'authenticated');

-- Allow authenticated to update
CREATE POLICY "auth_update"
ON generation_runs
FOR UPDATE
USING (auth.role() = 'authenticated');
```

## Styling System

### Color Scheme
```css
#C45A2C  /* Burnt Orange - Primary, pending status */
#1E2A3A  /* Deep Navy - Text, headers, dark elements */
#F5E6C8  /* Cream - Accents, light backgrounds */
#5B8A7A  /* Teal - Approved status, secondary buttons */
```

### Responsive Breakpoints
- Desktop: Grid with 3+ columns
- Tablet: Grid with 1-2 columns
- Mobile: Single column, adjusted margins

### Key Components

**Video Card**
- Aspect ratio 16:9 for video player
- Color-coded left border by status
- Hover effect with shadow and lift
- Action buttons only on pending videos

**Summary Bar**
- Flex layout for responsive stacking
- Large count numbers with small labels
- Color-coded to match statuses

**Filter Buttons**
- Toggle active state with color
- Hover effect for affordance
- Flexbox layout for wrapping

## Performance Considerations

### Query Optimization
- Single query with join (not N+1 queries)
- Data sorted at query time (created_at DESC)
- All filtering done client-side after load

### Frontend Optimization
- No external libraries (vanilla JS)
- CSS-in-JS avoids stylesheet overhead
- Inline SVG for icons (none currently, but option)
- Image/video files loaded as needed by browser

### Scalability
- Works well for 50-200 videos
- For 200+: Add pagination to getDashboardData()
- Consider caching if many concurrent users

## Security Considerations

### Key Protection
- SUPABASE_ANON_KEY is embedded in HTML (safe, designed for client-side)
- SUPABASE_URL is embedded in HTML (non-sensitive, public URL)
- Service role key is NOT used anywhere
- No API keys or secrets in client code

### Data Validation
- POST request body is validated before use
- IDs are passed through Supabase client (automatic validation)
- User input (rejection notes) is escaped by database

### CORS Configuration
- corsHeaders from @supabase/edge-runtime
- Included in all responses
- Allows cross-origin requests from browsers

### RLS Enforcement
- All data access goes through Supabase (which enforces RLS)
- Even with anon key, RLS policies control access
- Recommend implementing stricter policies for production

## Error Handling

### Backend
- Try-catch in main Deno.serve handler
- Console.error() for debugging
- JSON error responses with 400/500 status codes
- Descriptive error messages

### Frontend
- Try-catch in async functions
- User-friendly error messages in UI
- Toast-style alerts that auto-dismiss
- Console logs for developer debugging

## Future Enhancements

Possible additions:

1. **Pagination** - For 200+ videos
   - Add limit/offset to query
   - Load more button or pagination controls

2. **Search** - Filter by shot name or character
   - Client-side filter on allVideos array
   - Or server-side search with database query

3. **Sorting** - By date, duration, status
   - Update order by clause in query
   - Or client-side sort of allVideos

4. **Bulk Actions** - Approve/reject multiple videos
   - Checkbox selection on cards
   - Bulk action buttons
   - Update multiple records in loop

5. **Notifications** - Real-time updates
   - Use Supabase Realtime subscriptions
   - Listen for table changes
   - Update UI without page refresh

6. **User Attribution** - Track who approved/rejected
   - Add updated_by column to tables
   - Store user ID from auth context
   - Display in cards and history

7. **Revision History** - Show decision history
   - Create audit table
   - Log all approvals/rejections
   - Display decision timeline per video

8. **Comments** - Add discussion to videos
   - Separate comments table
   - Show comment count on card
   - Expand to view/add comments

## Testing Notes

### Manual Testing
1. Visit dashboard URL
2. Verify videos load and display correctly
3. Click approve - should update immediately
4. Click reject - should show modal
5. Add notes and submit
6. Verify database updates in Supabase console
7. Refresh page - verify persisted state

### Automated Testing (Future)
- Unit tests for query functions
- Integration tests for update operations
- E2E tests via Playwright or Cypress
- Load testing with 100+ concurrent users

## Deployment Checklist

- [ ] Verify table structure matches schema
- [ ] Set up RLS policies on both tables
- [ ] Test with sample data
- [ ] Run `supabase functions deploy review-dashboard`
- [ ] Access via browser
- [ ] Test approve/reject functionality
- [ ] Check logs for any errors
- [ ] Share dashboard URL with team

## Debugging Tips

1. **Check browser console** (F12) for JavaScript errors
2. **Check function logs**: `supabase functions logs review-dashboard`
3. **Verify database** has data: Check Supabase dashboard
4. **Check RLS policies**: Try disabling temporarily to test
5. **Test database queries** directly in Supabase SQL editor
6. **Inspect network requests** in browser DevTools

## Version History

- **v1.0** (April 2026) - Initial release
  - Video gallery with embedded players
  - Approve/reject functionality
  - Real-time statistics
  - Status filtering
  - Responsive design
  - The Roommates branding

---

For deployment instructions, see DEPLOYMENT.md
For quick setup, see QUICK_DEPLOY.md
For usage guide, see README.md
