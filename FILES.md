# File Guide

## Overview

Complete Supabase Edge Function for The Roommates video review dashboard.

**Location**: `/mnt/Rommates Manager/supabase-functions/review-dashboard/`

## Files

### 1. **index.ts** (838 lines)
**The main function code - this is what gets deployed to Supabase**

Contains:
- TypeScript interfaces for database types
- `getDashboardData()` - Query generation_runs with production_queue join
- `updateVideoStatus()` - Update DB when user approves/rejects
- `generateHTML()` - Generate the complete HTML dashboard with embedded JS
- `Deno.serve()` handler for GET (return dashboard) and POST (update status)

Key features:
- Queries all videos sorted by created_at DESC
- Calculates approved/pending/rejected counts
- Embeds Supabase JS client in HTML
- Handles approve/reject with optional notes
- Full responsive styling with The Roommates brand colors

**To deploy**: `supabase functions deploy review-dashboard`

---

### 2. **deno.json** (7 lines)
**Deno configuration with dependencies**

Specifies:
- @supabase/functions-js v2.4.1 (edge runtime types)
- @supabase/supabase-js v2.45.0 (database client)
- @supabase/edge-runtime v1.3.0 (CORS headers)

No modifications needed unless you want different versions.

---

### 3. **README.md** (306 lines)
**Feature overview and quick usage guide**

Read this first for:
- Quick start deployment (2 commands)
- What the dashboard does
- How it works (architecture diagram)
- Database tables summary
- Styling/brand colors
- All features explained
- Customization tips
- Troubleshooting basics

**For**: Getting started quickly, understanding features

---

### 4. **QUICK_DEPLOY.md** (87 lines)
**2-minute deployment instructions**

Contains:
- Copy-paste deployment commands
- What you're deploying
- Next steps after deployment
- Quick FAQ
- Redeploy instructions

**For**: Fast deployment without reading full docs

---

### 5. **DEPLOYMENT.md** (306 lines)
**Detailed setup, configuration, and troubleshooting**

Read this for:
- Full prerequisites and setup
- Environment variables (how they work)
- Local testing with `supabase start`
- Step-by-step deployment (CLI or dashboard)
- Accessing the live dashboard
- How the function works (GET/POST)
- Database access and RLS policy examples
- Detailed customization (colors, fields, grid layout)
- Full troubleshooting guide
- Monitoring and logs
- Updates and rollback
- Performance tips
- Security notes

**For**: Deep understanding of deployment and configuration

---

### 6. **IMPLEMENTATION_NOTES.md** (333 lines)
**Technical architecture and development details**

Read this for:
- Code structure breakdown
- Backend functions explained
- Frontend JavaScript features
- Database schema requirements
- RLS policy examples
- Styling system and colors
- Performance considerations
- Security architecture
- Error handling
- Future enhancement ideas
- Testing notes
- Deployment checklist
- Debugging tips

**For**: Developers, code review, modifications, extending functionality

---

### 7. **FILES.md** (this file)
**Quick reference guide to all files**

---

## Quick Navigation

**Just want to deploy?**
→ Read QUICK_DEPLOY.md (2 min)

**Need to understand what it does?**
→ Read README.md (5 min)

**Want full deployment details?**
→ Read DEPLOYMENT.md (10 min)

**Need to modify the code?**
→ Read IMPLEMENTATION_NOTES.md (15 min)

**Want everything you need?**
→ This file is the roadmap

---

## File Sizes

```
index.ts                 21 KB   (Main function)
IMPLEMENTATION_NOTES.md  8.7 KB  (Technical details)
DEPLOYMENT.md           8.3 KB  (Setup & troubleshooting)
README.md               7.7 KB  (Features & usage)
QUICK_DEPLOY.md         2.4 KB  (Fast setup)
deno.json               269 B   (Dependency config)
FILES.md                (this)
---
Total: ~50 KB across 6 production files + docs
```

---

## What Each File Contains

### Production Code
- **index.ts** ← Deploy this

### Configuration
- **deno.json** ← Required for Deno runtime

### Documentation
- **README.md** ← Start here
- **QUICK_DEPLOY.md** ← Fast path
- **DEPLOYMENT.md** ← Complete setup guide
- **IMPLEMENTATION_NOTES.md** ← Developer details
- **FILES.md** ← This file

---

## Key Sections by Document

### To Deploy
1. QUICK_DEPLOY.md (copy-paste commands)
2. README.md → Deployment section
3. DEPLOYMENT.md → Deployment Steps

### To Use
1. README.md → How It Works, Features
2. Dashboard at: https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard

### To Customize
1. DEPLOYMENT.md → Customization section
2. IMPLEMENTATION_NOTES.md → Code Structure
3. index.ts → Make changes

### To Troubleshoot
1. README.md → Troubleshooting section
2. DEPLOYMENT.md → Full Troubleshooting section
3. IMPLEMENTATION_NOTES.md → Debugging Tips

### To Understand
1. README.md → Overview
2. IMPLEMENTATION_NOTES.md → Technical details
3. index.ts → Source code

---

## File Dependencies

```
index.ts ← deno.json (specifies deps)
index.ts → DEPLOYMENT.md (to deploy)
index.ts → README.md (to understand)

Everything → IMPLEMENTATION_NOTES.md (technical reference)
```

---

## Next Steps

1. **Deploy**
   ```bash
   supabase link --project-ref xrtyllishxovdpazjdco
   supabase functions deploy review-dashboard
   ```
   See: QUICK_DEPLOY.md

2. **Access**
   ```
   https://xrtyllishxovdpazjdco.supabase.co/functions/v1/review-dashboard
   ```

3. **Test**
   - Watch videos
   - Click approve/reject
   - Check database updates

4. **Customize** (if needed)
   - Edit index.ts
   - Redeploy: `supabase functions deploy review-dashboard`
   See: DEPLOYMENT.md → Customization

---

## Support

**Can't find something?**

| Question | File |
|----------|------|
| How do I deploy? | QUICK_DEPLOY.md |
| What does it do? | README.md |
| How do I customize it? | DEPLOYMENT.md |
| What's the code doing? | IMPLEMENTATION_NOTES.md |
| Something's not working | DEPLOYMENT.md (Troubleshooting) |
| I want to modify the code | IMPLEMENTATION_NOTES.md |

---

## Summary

You have everything needed to:
- ✅ Deploy the function
- ✅ Use the dashboard
- ✅ Customize the design/features
- ✅ Troubleshoot issues
- ✅ Understand the architecture
- ✅ Extend with new features

Start with QUICK_DEPLOY.md or README.md based on your needs.

---

**All files are in**:
`/mnt/Rommates Manager/supabase-functions/review-dashboard/`

**Latest update**: April 2026
**Version**: 1.0
