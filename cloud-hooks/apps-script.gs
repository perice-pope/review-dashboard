/**
 * apps-script.gs — Self-contained Drive webapp for the Roommates pipeline.
 *
 * REPLACES your existing webapp entirely. Handles BOTH the new hook-pipeline
 * actions AND the legacy video-save action that run_batch.py / run_batch_runway.py
 * already use, so dropping this in at the same deployment URL is a clean swap.
 *
 * Endpoints:
 *
 *   GET  ?action=list&folder=<name>
 *        → { folder, folderUrl, files: [{ id, name, mimeType, modifiedTime, size }] }
 *
 *   GET  ?action=download&fileId=<id>
 *        → { id, name, mimeType, contentBase64 }
 *
 *   POST { action: 'upload', folder, filename, contentBase64, mimeType? }
 *        → { fileId, fileUrl, folder, folderUrl }
 *
 *   POST { folderName, videos: [[filename, url], ...] }   (legacy)
 *        → { status: 'ok', folderUrl, saved, total }
 *        Downloads each video URL and saves it to the named folder.
 *        run_batch.py and run_batch_runway.py rely on this exact shape.
 *
 * DEPLOYMENT (one-time, ~3 minutes):
 *   1. Open script.google.com → your existing Drive webapp project
 *   2. Replace the whole script with this file's contents
 *   3. Deploy → Manage deployments → Edit (pencil icon) → New version → Deploy
 *   4. The DRIVE_WEBAPP_URL stays the same — no env var changes needed
 *
 * If your existing script does anything beyond the legacy video-save above
 * (custom email sending, calendar integration, etc.), preserve those pieces
 * by pasting them in *above* the dispatchers and routing to them from doPost.
 */


// HOOK_PARENT_FOLDER_ID applies ONLY to the new hook pipeline actions
// (list / download / upload). The legacy video-save endpoint keeps using
// the root of My Drive so existing folders like "Spring Thaw - Generated
// Shots" don't get duplicated. Set this to the Drive folder ID where you
// want the hook pipeline (Full Songs / Hooks subfolders) to live.
var HOOK_PARENT_FOLDER_ID = '1b26Gavhh8JcEUDppDIG3acKXSBGSjmCL';


// ─── New endpoints (cloud hook pipeline) ───────────────────────────────────

function listFolderContents(folderName) {
  var folder = getOrCreateHookFolder(folderName);
  var iter = folder.getFiles();
  var files = [];
  while (iter.hasNext()) {
    var f = iter.next();
    files.push({
      id:           f.getId(),
      name:         f.getName(),
      mimeType:     f.getMimeType(),
      modifiedTime: f.getLastUpdated().toISOString(),
      size:         f.getSize(),
    });
  }
  return jsonResponse({ folder: folder.getName(), folderUrl: folder.getUrl(), files: files });
}

function downloadFileAsBase64(fileId) {
  var file = DriveApp.getFileById(fileId);
  var blob = file.getBlob();
  return jsonResponse({
    id:            file.getId(),
    name:          file.getName(),
    mimeType:      file.getMimeType(),
    contentBase64: Utilities.base64Encode(blob.getBytes()),
  });
}

function uploadBase64File(folderName, filename, contentBase64, mimeType) {
  var folder = getOrCreateHookFolder(folderName);
  var bytes = Utilities.base64Decode(contentBase64);
  var blob = Utilities.newBlob(bytes, mimeType || 'application/octet-stream', filename);

  // Replace existing file with the same name
  var existing = folder.getFilesByName(filename);
  while (existing.hasNext()) existing.next().setTrashed(true);

  var file = folder.createFile(blob);
  return jsonResponse({
    fileId:    file.getId(),
    fileUrl:   file.getUrl(),
    folder:    folder.getName(),
    folderUrl: folder.getUrl(),
  });
}


// ─── Legacy endpoint (preserved for run_batch_runway.py compatibility) ─────
// Saves to the root of My Drive — same as before — so existing folders like
// "Spring Thaw - Generated Shots" stay where they are.

function saveVideosFromUrls(folderName, videos) {
  var folder = getOrCreateRootFolder(folderName);
  var saved = 0;
  for (var i = 0; i < videos.length; i++) {
    var pair = videos[i];
    if (!pair || pair.length < 2) continue;
    var filename = pair[0];
    var url = pair[1];
    try {
      var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
      if (resp.getResponseCode() >= 400) {
        Logger.log('skip ' + filename + ' (HTTP ' + resp.getResponseCode() + ')');
        continue;
      }
      var blob = resp.getBlob().setName(filename);

      // Replace existing file with the same name
      var existing = folder.getFilesByName(filename);
      while (existing.hasNext()) existing.next().setTrashed(true);

      folder.createFile(blob);
      saved++;
    } catch (err) {
      Logger.log('failed ' + filename + ': ' + err);
    }
  }
  return jsonResponse({
    status:    'ok',
    folderUrl: folder.getUrl(),
    saved:     saved,
    total:     videos.length,
  });
}


// ─── Helpers ───────────────────────────────────────────────────────────────

// For the new hook pipeline — resolves under HOOK_PARENT_FOLDER_ID.
function getOrCreateHookFolder(name) {
  var parent = HOOK_PARENT_FOLDER_ID
    ? DriveApp.getFolderById(HOOK_PARENT_FOLDER_ID)
    : DriveApp.getRootFolder();
  var iter = parent.getFoldersByName(name);
  if (iter.hasNext()) return iter.next();
  return parent.createFolder(name);
}

// For the legacy video-save endpoint — always resolves at the root of My Drive
// so existing run_batch_runway.py output folders ("Spring Thaw - Generated
// Shots", etc.) keep working without migration.
function getOrCreateRootFolder(name) {
  var parent = DriveApp.getRootFolder();
  var iter = parent.getFoldersByName(name);
  if (iter.hasNext()) return iter.next();
  return parent.createFolder(name);
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ─── Dispatchers ───────────────────────────────────────────────────────────

function doGet(e) {
  try {
    var action = (e && e.parameter && e.parameter.action) || '';
    if (action === 'list') {
      var folder = e.parameter.folder;
      if (!folder) return jsonResponse({ error: 'missing folder param' });
      return listFolderContents(folder);
    }
    if (action === 'download') {
      var fileId = e.parameter.fileId;
      if (!fileId) return jsonResponse({ error: 'missing fileId param' });
      return downloadFileAsBase64(fileId);
    }
    return jsonResponse({ error: 'unknown action: ' + action });
  } catch (err) {
    return jsonResponse({ error: String(err) });
  }
}

function doPost(e) {
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');

    // New: explicit upload action
    if (body.action === 'upload') {
      if (!body.folder || !body.filename || !body.contentBase64) {
        return jsonResponse({ error: 'upload requires folder, filename, contentBase64' });
      }
      return uploadBase64File(body.folder, body.filename, body.contentBase64, body.mimeType);
    }

    // Legacy: video-save by URL
    if (body.folderName && body.videos) {
      return saveVideosFromUrls(body.folderName, body.videos);
    }

    return jsonResponse({ error: 'unknown POST shape' });
  } catch (err) {
    return jsonResponse({ error: String(err) });
  }
}
