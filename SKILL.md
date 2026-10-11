---
name: 小程序分包视频压缩
description: >-
  【小程序分包视频压缩】>- 【小程序分包视频压缩】"Compress and package tutorial or teaching videos into a WeChat Mini Program subpackage while respecting the hard 2MB per-package limit. Use this skill whenever a mini program needs to ship local video instead of a CDN, such as adding a brand or device tutorial video to a course page, or when upload size must stay under 2MB. Covers PyAV 18 transcode quirks such as AudioResampler and even yuv420p dimensions, CRF budget scanning, first-frame poster extraction, and wiring the subpackage into app.json, courses.js and tutorial.js."
agent_created: true
---

# Mini Program Subpackage Video Packager

## Overview

WeChat Mini Programs have a **hard 2MB limit per package** (main package AND each
subpackage separately; whole app ≤ 20MB). Video stored as a local resource blows
this budget instantly, so tutorial videos must be (a) aggressively compressed and
(b) parked in a **subpackage** so they don't eat the main package's 2MB.

This skill packages one or more source videos into a new subpackage:
transcode to a small resolution/CRF that fits the budget, extract a first-frame
poster, drop in a copied `player` page, and report the per-package total so the
2MB gate can be verified.

## When to use

- Adding local tutorial videos to a WeChat mini program (no CDN dependency).
- "视频上传时大小不能大于 2MB" type constraints.
- Splitting a new brand/device's videos into their own subpackage so they don't
  crowd another brand's 2MB allowance.

## Workflow

### Step 1 — Budget the package

Per-package budget = 2048 KB total. Reserve ~70 KB for the `player` page
(.js/.json/.wxml/.wxss). That leaves ~1950 KB for video. **Posters do NOT count
against the subpackage** — they must live in the MAIN package (see iron rule 1).

If multiple videos share one package, split the budget:
`TARGET_KB = (1950 - 70) // N` per video (N = number of videos). For two ~30s
videos, 950 KB each (default) works.

Also check the MAIN package headroom: each poster (~34 KB) moves into the main
package, so confirm the main package stays below 2MB after adding them.

### Step 2 — Run the build script

The bundled `scripts/build_subpkg_video.py` does the transcode + poster + player
copy. Configure via constants at the top or env vars:

```bash
# defaults point at the 演唱会小程序 project; override for other projects
MINIAPP="D:/workbuddy/Claw/演唱会小程序/miniapp" \
SRC_DIR="D:/workbuddy/2026-09-06-15-05-46/vivo_src" \
python "C:/Users/Administrator/.workbuddy/skills/miniprogram-subpkg-video/scripts/build_subpkg_video.py"
```

Edit `PLAN` (source filename → output mp4 name → label) and `OUT_PKG`/`REF_PKG`
before running. The script prints each video's KB + duration and the package total.
**The script writes posters into the MAIN package at `images/<brand>/`** (same
place the player page will read them from via the shared `poster` field).

### Step 3 — Wire into the app

1. **app.json** — add a `subPackages` entry for `OUT_PKG` (root + `pages/player/player`).
2. **app.json `preloadRule`** — add the new package name ONLY IF the total of ALL
   packages listed together stays at or below 2048 KB. **WeChat hard-fails the
   whole preload with error 80058 when the combined preload exceeds 2MB.** With two
   ~1.4-1.7MB subpackages you can only preload ONE; the other downloads on first
   open of its player page. Set `network: "wifi"` so 4G users are not forced to
   download.
3. **utils/courses.js** — add course objects with `videoUrl: /OUT_PKG/videos/xxx.mp4`
   and **`poster: /images/<brand>/xxx_poster.jpg` (MAIN package path — see iron
   rule 1)**, keyed in `COURSES_BY_MODEL`.
4. **pages/tutorial/tutorial.js** — add the device card (`ready: true`), a `PICKERS`
   entry, and make `goCourse` route to the right subpackage's player based on the
   `videoUrl` prefix (vivo → `/packageVivo/...`, others → `/packageVideo/...`).
   The course list cover is derived as `cover = poster || pages[0].img ||
   /images/covers/{id}.jpg`, so keeping `poster` in the main package makes covers
   show everywhere.

### Step 4 — Verify

Run `audit_miniapp.py` (the project's health-check script) — it enforces a per-
package 2MB gate and reports sizes. Confirm the new subpackage total is below 2048 KB
and the main package still is too (posters were added there).

See `references/pyav_gotchas.md` for the PyAV 18 API traps that this script already
handles (read before modifying the script).

## Key constraints (will break the build if ignored)

- **IRON RULE 1 — main-package pages can NEVER display subpackage static resources
  (images), even with preloadRule set.** WeChat isolates package file spaces; a
  poster at `/packageVivo/videos/x.jpg` referenced from the main-package course
  list renders as a blank image on real devices. **Therefore: posters/covers go in
  the MAIN package `images/<brand>/`; only the .mp4 goes in the subpackage.**
  Subpackage pages CAN use main-package images (player's `<video poster>` reads
  the same main-package poster). Verified 2026-09-06 on real-device debug.
- **IRON RULE 2 — `preloadRule` combined package size ≤ 2MB.** Listing two ~1.5MB
  subpackages under one page's preload triggers error 80058
  (`preloadRule ... source size ... exceed max limit 2MB`) and blocks real-device
  debugging. Preload at most ONE subpackage; keep the rest on-demand.
- **yuv420p requires even width AND height.** Odd H (e.g. 405) → `avcodec_open2`
  error. Always use even W/H (default 720×404).
- **Subpackage video can only be used by a player page inside the same subpackage.**
  So the player page MUST be copied into the new subpackage too (done by the script).
- **A subpackage page cannot navigate to another subpackage's page.** Route by
  `videoUrl` prefix instead.
- **No duplicate page paths** across `pages` and `subPackages` in app.json.
- Prefer WXS/precomputed booleans in WXML — **WXML forbids method calls**.
