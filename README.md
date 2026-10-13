# PlayCut

**English** | [繁體中文](README.zh-TW.md)

A video player / marker / clip-cutting tool for Windows and macOS. **No update nag pop-ups.**

Four reasons it exists:

| What you want | How PlayCut does it |
|---|---|
| Playback speed control | 0.25×–4× from the dropdown or `[` `]`, or type a number directly. Press and hold on the video = temporary 2× speed |
| Touch swipe to seek | Single-finger left/right swipe on a touchscreen; up/down = volume / brightness; two-finger touchpad gestures work too |
| Audio delay correction | ±ms box at the bottom, `Ctrl+←` `Ctrl+→` for 50 ms steps, **and it can be baked into the exported file** |
| Drop flags → export clips | Press `M` to drop a flag: the 1st is a start, the 2nd an end. Exports have a **frame-accurate start, without LosslessCut's offset problem** |

---

## Installation

1. If you don't have Python, install it first (3.10 or later): <https://www.python.org/downloads/>
   **Make sure to tick "Add Python to PATH"** during installation.
2. Double-click **`setup.bat`**.
   It creates an isolated environment, installs the packages, and automatically downloads `libmpv-2.dll` (playback engine)
   and `ffmpeg.exe` / `ffprobe.exe` (cutting engine) into the `bin\` folder.
3. Double-click **`run.bat`** to launch.

For a fully portable single executable you can copy to another PC,
run **`build.bat`** after setup. The result is `dist\PlayCut.exe`.

If start-up speed matters more, run **`build_folder.bat`** instead: the result is the whole `dist\PlayCut\` folder
(plus a `dist\PlayCut.zip`). Copy the entire folder to another PC and run the `PlayCut.exe` inside it.
Nothing is unpacked on each launch, so it opens faster and is less likely to be flagged by antivirus software.

If something goes wrong, launch with **`debug.bat`** instead. It keeps the console window open and prints detailed messages.

> If `setup.bat` fails to download something, it prints the manual download URLs and where to put the files — just follow them.

### macOS

1. Install [Homebrew](https://brew.sh) first (skip if you already have it).
2. Double-click **`setup_mac.command`** in Finder.
   It uses Homebrew to install `mpv` (playback engine) and `ffmpeg` (cutting engine),
   and creates a separate `.venv-mac` environment (kept apart from the Windows `.venv`, so both can share the same folder without conflict).
3. Double-click **`run_mac.command`** to launch. If something goes wrong, run `./run_mac.command --debug` in Terminal to see detailed messages.

For an app you can drag into the Applications folder, run **`build_mac.command`**.
The result is `dist/PlayCut.app`, plus `dist/PlayCut-mac.zip` for easy transfer to other Macs.

Notes:

- **Packaging only works on a Mac**, and the result only runs on Macs with the same chip type (Apple Silicon or Intel).
- The app is not notarized by Apple, so other Macs will block it the first time: right-click the app → **Open**;
  on macOS 15 and later, go to "System Settings → Privacy & Security" and click "Open Anyway".
- If double-clicking a `.command` file does nothing or says "permission denied", open Terminal in the project folder and run
  `chmod +x *.command` once.
- Macs have no touchscreen, so single-finger swipe gestures don't apply; two-finger touchpad left/right = seek, up/down = volume.
- `Ctrl` in the shortcuts is `⌘ Cmd` on a Mac (e.g. `⌘O` to open, `⌘E` to export, `⌘←` `⌘→` to adjust audio delay).
- The installed app supports Finder's "Open With → PlayCut" and dropping files onto its Dock icon.
- Errors are logged to `~/Library/Logs/PlayCut/playcut_error.log`.

---

## Basic usage

**Drag a video into the window**, or open one with `Ctrl+O`.

### Dropping flags and cutting clips

1. Play to the position you want (use `,` `.` to step frame by frame and land on exactly the right frame)
2. Press `M` to drop a flag
3. Play to where the clip should end and press `M` again
4. `Ctrl+E` → choose a mode → start the export

Flags alternate automatically: the 1st is a **start**, the 2nd an **end**, the 3rd a start again…
So dropping one at 01:00 and one at 02:00 gives you the 01:00–02:00 segment.
You can also **pin** a flag as a start or end in the panel on the right.

Flags are saved automatically next to the video as `<video file name>.mp4.playcut.json` and loaded back the next time you open the same video.

### Three export modes

| Mode | Start accuracy | Speed | Quality |
|---|---|---|---|
| **Smart cut** (default) | **Frame-accurate** | Close to lossless cutting | Only a short stretch at the start is re-encoded; the rest is untouched |
| Re-encode all | Frame-accurate | Slowest | Depends on the CRF setting (default 22, visually indistinguishable for most people; 16 is near-lossless but roughly doubles the file size) |
| Lossless copy | **Shifts earlier** (possibly by several seconds) | Fastest | Fully lossless |

**Smart cut** is what solves the LosslessCut problem:
lossless cutting can only start at a keyframe. If you pick 01:00 but the previous keyframe is at 00:58,
the output gets 2 extra seconds (or a corrupted first few frames).
Smart cut re-encodes only the stretch **from 01:00 to the next keyframe**
and stream-copies everything after it — a frame-accurate start at almost lossless speed.

### Making files smaller

Smart cut and lossless copy both copy the original frames directly, so file size ≈ source bitrate × duration and won't shrink.
To reduce file size, use the "Compression (smaller files)" settings in the export dialog (whenever any of them is active, the export automatically switches to full re-encoding):

- **Video codec**: H.265 / HEVC is about 30–50% smaller at the same quality (slower; `.mp4` output is automatically tagged `hvc1` so Apple devices can play it)
- **Max resolution**: 1080p / 720p / 480p…, measured on the short side so it works for vertical video too; only scales down, never up
- **Audio bitrate**: Auto uses up to 160 kbps for stereo
- **Target size**: enter a size in MB; the bitrate is calculated from the duration and encoded with two-pass CPU encoding, so the output comes out slightly under the target
  (per file when not merging, for the whole file when merging)

Measured on a 10-second 1080p clip: smart cut 16.3 MB → re-encode at CRF 22 8.4 MB → H.265 + 720p 3.4 MB; a 2 MB target produced 1.9 MB.

Measured (25 fps, a keyframe every 5 seconds, cut at 12.36 s):

```
Smart cut       first frame vs requested position  PSNR 46.3 dB  ✅ exact match, 0.8 s
Re-encode all   first frame vs requested position  PSNR 46.3 dB  ✅ exact match, 1.2 s
Lossless copy   first frame vs requested position  PSNR 14.9 dB  ❌ jumped to the keyframe at 10.0 s
A/V sync: smart cut 0–1 ms, no jump at the splice point
```

### Audio delay

When the audio is out of sync, adjust the "Delay" box at the bottom (positive = audio plays later, in ms).
`Ctrl+←` / `Ctrl+→` change it by ±50 ms; press "0" to reset.

When exporting, the dialog asks whether to **apply this delay to the output file**. If you tick it,
the exported audio matches exactly what you hear in the player (video taken from `[start, end]`, audio from `[start − delay, end − delay]`).
When the delay is applied, the audio is re-encoded while the video stays untouched.

### Subtitles

Supports external `.srt` / `.ass` / `.ssa` / `.vtt` / `.sub` / `.idx` / `.sup` / `.smi` subtitles as well as subtitle tracks embedded in the video.

- **Auto-load**: subtitles with the same name as the video (or starting with the same name) are attached automatically, e.g. `abc.mp4` → `abc.srt`, `abc.zh-TW.srt`.
  When there are several, Traditional Chinese is preferred.
- **Manual load**: drag a subtitle file into the window (you can drag it together with the video), or use "Subtitles → Load Subtitle File…" (`Ctrl+L`).
- **Switch / turn off**: pick a track with the "Subtitles" button at the bottom or the "Subtitles" menu; `J` cycles tracks, `V` shows / hides them.
- **Subtitle delay**: `Z` / `X` shift by ∓100 ms (positive = subtitles appear later), `Shift+Z` resets.
- **Size / position**: `Alt+↑` `Alt+↓` to enlarge / shrink, `Alt+Shift+↑` `Alt+Shift+↓` to move up / down (settings are remembered).
- **Encodings**: UTF-8, UTF-16, Big5 and GBK subtitles all display correctly.

When exporting, the "Subtitles" section of the dialog uses **the subtitle currently shown in the player** (including its subtitle delay):

- **Save a matching .srt**: a same-named `.srt` is written next to each output file, with timings aligned to the clip (placed consecutively when merging). Doesn't slow down cutting.
- **Burn subtitles into the video** (hard subs): subtitles are drawn into the picture; this option forces full re-encoding.

Image-based subtitles (PGS `.sup`, VobSub `.idx/.sub`) can be played but can't be saved as .srt or burned in.

---

### Screenshots

Saves the current frame as an image at the **video's original resolution** (independent of the window size; the seek bar and on-screen hints are never included).

- **With subtitles** (`S`, or the 📷 button at the bottom): the video plus the subtitles currently shown, just like on screen. If subtitles are hidden it's the same as the video-only shot.
- **Video only** (`Shift+S`, or the arrow next to 📷): no subtitles.
- File name: `video_HH-MM-SS.mmm.png`, with `_sub` added for the subtitled version; existing files are never overwritten — `(2)`, `(3)`… are added.
- Saved next to the video by default; the Screenshot menu lets you pick another folder, switch to JPG, or also copy each shot to the clipboard.
- If the video's folder isn't writable (e.g. a read-only disc), shots go to "Pictures/PlayCut" instead.

### Speed and short-video crop

The "Speed & short-video crop" section of the export dialog:

- **Apply playback speed**: pre-filled with the player's current speed; you can type any value (0.1×–10×). Video uses `setpts` and audio uses `atempo` (pitch preserved); saved .srt timings are scaled too.
- **Crop ratio**: 1:1 (1080×1080), 4:5 (1080×1350), 9:16 (1080×1920), 16:9 (1920×1080). Takes the largest area of that ratio from the frame, anchored center / top-left / bottom-right, then scales it to the listed resolution (scaling can be turned off). Equivalent to:

  ```
  ffmpeg -i 1.mp4 -vf "crop=ih*4/5:ih,scale=1080:1350" 1_short_4x5.mp4
  ```

Applying speed or cropping always re-encodes the whole clip; output file names automatically get suffixes such as `_2x` or `_4x5`.

### System tray (Windows)

Closing the window doesn't actually quit PlayCut — it minimizes to the system tray in the bottom-right corner, so the next launch (double-clicking the exe, a video file, or the tray icon) appears almost instantly.

- When minimized to the tray, playback stops and flags are saved, so it comes back as a clean window
- If it isn't brought back within **5 minutes**, it quits completely on its own and frees its memory
- Launching PlayCut again while it's in the background hands the file to the existing instance instead of opening a second window
- To really quit: right-click the tray icon → "Quit completely", or File → Quit (Ctrl+Q)
- Don't want this? Untick File → "Minimize to system tray on close"
- If you need two windows at once, use `PlayCut.exe --new-instance`

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Play / pause |
| `←` `→` | Back / forward 5 seconds |
| `Shift+←` `Shift+→` | 1 second |
| `,` `.` | Previous / next frame |
| `[` `]` | Slower / faster |
| `Backspace` | Reset to 1× |
| `Ctrl+←` `Ctrl+→` | Audio delay ±50 ms |
| `Ctrl+L` | Load subtitle file |
| `J` / `V` | Cycle subtitle tracks / show or hide subtitles |
| `Z` `X` / `Shift+Z` | Subtitle delay ∓100 ms / reset |
| `Alt+↑` `Alt+↓` | Larger / smaller subtitles |
| `Alt+Shift+↑` `Alt+Shift+↓` | Move subtitles up / down |
| `S` / `Shift+S` | Screenshot (with subtitles) / screenshot (video only) |
| `M` | Drop a flag |
| `I` / `O` | Set as start / end |
| `PgUp` `PgDn` | Jump to previous / next flag |
| `Delete` | Delete the selected flag |
| `Ctrl+O` | Open video |
| `Ctrl+E` | Export clips |
| `F` / `Esc` | Full screen / exit full screen (the progress bar and controls are hidden in full screen) |
| `F1` | Shortcut and gesture help |
| Middle mouse button (on the video) | Toggle full screen |

Single-key shortcuts are disabled automatically while you type in the note field, so there are no accidental triggers.

### Custom shortcuts

"View → Customize Shortcuts…" lets you change the key for every action: click the "Shortcut" cell and press the combination you want;
click ⓧ to clear it (= unassigned). Duplicate keys are highlighted in red and can't be applied.
A few extra actions with no default key are also available to assign: back / forward 10 seconds, volume ±5, mute.
Settings are remembered across launches, and button tooltips and the `F1` help show your customized keys.

### Interface language

Supports **Traditional Chinese, Simplified Chinese, English and Japanese**. On first launch it follows the system language
(Traditional Chinese / Hong Kong / Macau → Traditional Chinese, Simplified Chinese → Simplified Chinese, Japanese → Japanese, everything else → English).

To switch manually: "View → Language". After choosing, you'll be asked whether to restart now (the change takes effect after restarting;
the currently open video is reopened automatically and its flags are saved first). Choose "System default" to go back to automatic detection.
The menu title always includes the English word "Language", so you can find your way back even if you switch to a language you can't read.

When adding or changing UI text: write the Traditional Chinese source text directly in the code wrapped in `tr("…")`,
then add translations to `en.py`, `zh_CN.py` and `ja.py` in `playcut/locales/`.
Run `python tools/i18n_keys.py` to list strings that haven't been translated yet.

## Touch gestures

| Gesture | Action |
|---|---|
| Swipe left / right | Seek (live preview while swiping; the jump happens when you let go) |
| Swipe up / down on the right half | Volume |
| Swipe up / down on the left half | Screen brightness |
| Single tap | Play / pause |
| Double-tap left third · right third · middle | −10 s · +10 s · full screen |
| Middle mouse button | Toggle full screen |
| Long press | Temporary 2× speed, back to normal on release |
| Two-finger touchpad left-right / up-down | Seek / volume |

Swipe sensitivity can be adjusted under "View → Swipe Sensitivity" (default: full screen width = 120 seconds).

---

## Project structure

```
PlayCut\
  setup.bat          Setup (downloads libmpv and ffmpeg)
  run.bat            Launch
  debug.bat          Launch with error messages printed, for troubleshooting
  build.bat          Package as a single exe
  build_folder.bat   Package as a portable folder (onedir)
  bin\               libmpv-2.dll / ffmpeg.exe / ffprobe.exe (placed automatically by setup)
  playcut\
    __main__.py      Entry point
    mpvwidget.py     libmpv embedded in Qt (OpenGL render API)
    tray.py          System tray, single instance, idle auto-quit (Windows)
    videoview.py     Touch gestures + on-screen display (OSD)
    timeline.py      Progress bar with flags
    markers.py       Flag / clip data model
    exporter.py      Three cutting modes + audio delay baking
    subtitles.py     Subtitle parsing / encoding detection / .srt timing and burn-in on export
    exportdialog.py  Export dialog
    shortcuts.py     Custom shortcuts (settings storage + dialog)
    i18n.py          UI localization (tr(), system language detection)
    locales\         Translation tables (en / zh_CN / ja)
    mainwindow.py    Main window
  tests\             Verification tests (cut accuracy, A/V sync, UI)
```

## Troubleshooting

**Clicking run.bat does nothing / the window flashes and closes** — launch with `debug.bat` instead; error messages stay in the window.
If the program fails to start, it also writes `playcut_error.log` in the PlayCut folder.

**"libmpv not found" on launch** — `bin\libmpv-2.dll` wasn't downloaded. Rerun `setup.bat`,
or download it manually from the URL it prints and put it in `bin\`.

**Black screen, audio only** — a graphics driver / hardware decoding issue.
Add a line `set PLAYCUT_HWDEC=no` before the `start` line in `run.bat` and try again.

**Export says ffmpeg can't be found** — `bin\ffmpeg.exe` wasn't downloaded; same fix as above.

**Why are the .bat files in English?** — cmd.exe reads batch files by byte offset.
If a batch file switches code pages with `chcp` midway and contains UTF-8 Chinese text, cmd reads from the wrong position and aborts
(the window flashes and closes). So these .bat files are deliberately pure ASCII, and all Chinese messages are printed by Python.

**Passing extra mpv options** — set the `PLAYCUT_MPV_OPTS` environment variable,
e.g. `set PLAYCUT_MPV_OPTS=scale=bilinear,video_sync=display-resample`.

## Running tests

```
.venv\Scripts\python tests\test_cut_accuracy.py   Whether the cut start has zero offset
.venv\Scripts\python tests\test_av_sync.py        A/V sync and smooth splice points
.venv\Scripts\python tests\test_ui_smoke.py       UI / gestures / flag logic
.venv\Scripts\python tests\test_shortcuts.py      Custom shortcuts / middle-click full screen / hidden controls in full screen
.venv\Scripts\python tests\test_subtitles.py      Subtitle loading / switching / delay, .srt export and burn-in
.venv\Scripts\python tests\test_i18n.py           Localization: complete translation tables, UI builds in every language
.venv\Scripts\python tests\test_screenshot.py     Screenshots: video only / with subtitles, file names, clipboard, fallback folder
```
