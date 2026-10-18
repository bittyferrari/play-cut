"""English translation. Keys are the original Traditional Chinese strings in the code."""
# flake8: noqa

T = {
    # ---- 啟動 ----
    "詳細內容已存到：\n{path}": "Details were saved to:\n{path}",
    "PlayCut 啟動失敗": "PlayCut failed to start",
    "找不到 PySide6 套件。": "The PySide6 package was not found.",
    "請重新執行 {script}。": "Please run {script} again.",

    # ---- 匯出對話框 ----
    "起點所在的那一小段重新編碼，其餘直接複製。起點完全精準、不會像 LosslessCut 那樣往前偏移，速度也接近無損剪輯。":
        "Only the short stretch around the start point is re-encoded; the rest is copied as-is. "
        "The start is frame-accurate (no backward shift like LosslessCut) and it's nearly as fast as a lossless cut.",
    "整段重新編碼。最精準、相容性最好，但最慢，而且畫質會依 CRF 略有損失。":
        "Re-encodes the whole clip. Most accurate and most compatible, but slowest, with slight quality loss depending on CRF.",
    "完全不重新編碼，最快也完全無損 —— 但起點會被拉到前一個關鍵影格（也就是 LosslessCut 的偏移問題），最多可能早好幾秒。":
        "No re-encoding at all: fastest and fully lossless — but the start snaps back to the previous keyframe "
        "(the LosslessCut offset problem) and can be several seconds early.",
    "匯出片段": "Export Clips",
    "剪輯方式": "Cutting method",
    "模式": "Mode",
    '重新編碼的畫質，數字越小畫質越好、檔案越大。\n22 一般人看不出差別；16 接近無損但檔案約大一倍；每 +6 檔案約小一半。':
        'Re-encoding quality: lower = better quality and bigger files.\n22 looks the same to most people; 16 is near-lossless but about twice the size; every +6 roughly halves the size.',
    '越慢壓縮效率越好：同樣畫質下 slow 的檔案會比 medium 小一些':
        'Slower presets compress better: at the same quality, slow gives a somewhat smaller file than medium',
    '壓縮（讓檔案變小）':
        'Compression (smaller files)',
    '影片編碼':
        'Video codec',
    'H.264（相容性最好）':
        'H.264 (most compatible)',
    'H.265 / HEVC（檔案更小、較慢）':
        'H.265 / HEVC (smaller, slower)',
    'H.265 同樣畫質下檔案約小 30～50%，但編碼較慢，部分舊裝置或網站可能無法播放':
        'At the same quality H.265 files are about 30–50% smaller, but encoding is slower and some older devices or sites may not play them',
    '解析度上限':
        'Max resolution',
    '原始解析度':
        'Original resolution',
    '以短邊計算（直式影片也適用），只會縮小、不會放大':
        'Measured on the short side (works for vertical video too); only scales down, never up',
    '聲音位元率':
        'Audio bitrate',
    '自動（雙聲道最多 160 kbps）':
        'Auto (stereo up to 160 kbps)',
    '目標大小':
        'Target size',
    '指定檔案大小':
        'Set file size',
    '依片段長度自動算出位元率，用 CPU 兩階段編碼，輸出大小會很接近設定值（會略小一點）。\n不分段時是每個輸出檔的大小；合併時是整個檔案的大小。':
        "The bitrate is calculated from the clip length and encoded in two passes on the CPU, so the output lands very close to (slightly under) this size.\nWithout merging it's the size of each output file; when merging it's the size of the whole file.",
    '來源：{desc}':
        'Source: {desc}',
    '預估影片位元率約 {k} kbps（用 CPU 兩階段編碼）':
        'Estimated video bitrate: about {k} kbps (two-pass CPU encoding)',
    '位元率很低，畫質可能會很差：可以調大目標大小、降低解析度，或把片段剪短':
        'The bitrate is very low and quality may be poor: raise the target size, lower the resolution, or shorten the clip',
    '壓縮':
        'compression',
    '兩階段編碼：第 1 階段（分析畫面）…':
        'Two-pass encoding: pass 1 (analyzing)…',
    '兩階段編碼：第 2 階段（輸出，約 {k} kbps）…':
        'Two-pass encoding: pass 2 (writing, about {k} kbps)…',
    "重編碼畫質 CRF": "Re-encode quality (CRF)",
    "編碼速度": "Encoder preset",
    "使用顯卡加速（NVIDIA / Intel / AMD，失敗會自動改用 CPU）":
        "Use GPU acceleration (NVIDIA / Intel / AMD; falls back to CPU on failure)",
    "「全部重新編碼」和「燒錄字幕」時用顯卡編碼，速度快很多。\n智慧剪輯開頭那一小段仍用 CPU，確保跟直接複製的部分接得起來。\n用顯卡時 CRF 會當成對應的品質值（NVENC 的 CQ 等），檔案可能稍大。":
        "Uses the GPU encoder for \"Re-encode all\" and burned-in subtitles — much faster.\n"
        "Smart cut still encodes its short head on the CPU so it joins cleanly with the copied part.\n"
        "With the GPU, CRF is mapped to the matching quality value (e.g. NVENC CQ); files may be slightly larger.",
    "聲音": "Audio",
    "把目前的聲音延遲 {ms:+.0f} ms 套用到輸出檔": "Apply the current audio delay of {ms:+.0f} ms to the output",
    "套用延遲時聲音會重新編碼（畫面仍維持原樣），輸出檔就會跟你在播放器裡聽到的完全一致。":
        "When the delay is applied, audio is re-encoded (video stays untouched), so the output sounds exactly like it does in the player.",
    "速度與短影音裁切": "Speed & short-video crop",
    "套用播放速度": "Apply playback speed",
    "輸出影片的速度：2 = 兩倍速（長度減半），0.5 = 慢動作。\n聲音用 atempo 變速，音高不變。":
        "Output speed: 2 = double speed (half the length), 0.5 = slow motion.\nAudio is time-stretched with atempo, keeping the pitch.",
    "預設帶入目前播放器的速度 {s:g}×，可以直接改數字":
        "Defaults to the player's current speed ({s:g}×); you can type any value",
    "速度": "Speed",
    "不裁切": "No crop",
    "裁切比例": "Crop ratio",
    "橫式影片裁成直式時，取畫面的哪一邊": "Which part of the frame to keep when cropping landscape to portrait",
    "裁切位置": "Crop position",
    "縮放到上面標示的解析度（不勾 = 保留裁切後的原始解析度）":
        "Scale to the resolution shown above (unchecked = keep the cropped resolution)",
    "套用速度或裁切時，會改用「全部重新編碼」。輸出檔名會自動加上 _2x、_4x5 之類的後綴。":
        "Speed or crop forces \"Re-encode all\". Output names get suffixes such as _2x or _4x5.",
    "字幕": "Subtitles",
    "每個輸出檔旁邊另存對應的 .srt 字幕（時間自動對齊片段）":
        "Save a matching .srt next to each output (timings aligned to the clip)",
    "把字幕燒進畫面（硬字幕，一律整段重新編碼）":
        "Burn subtitles into the video (hard subs; always re-encodes the whole clip)",
    "輸出": "Output",
    "瀏覽…": "Browse…",
    "資料夾": "Folder",
    "跟來源相同": "Same as source",
    "容器格式": "Container",
    "把所有片段接成一個檔案": "Join all clips into a single file",
    "開始匯出": "Export",
    "關閉": "Close",
    "選擇輸出資料夾": "Choose Output Folder",
    "取消": "Cancel",
    "準備中…": "Preparing…",
    "完成，共 {n} 個檔案": "Done — {n} file(s)",
    "匯出完成": "Export Complete",
    "失敗": "Failed",
    "已取消": "Cancelled",
    "目前沒有開啟字幕（字幕 → 載入字幕檔…，或切換到內嵌字幕軌）":
        "No subtitles are active (Subtitles → Load Subtitle File…, or switch to an embedded track)",
    "，字幕延遲 {ms:+.0f} ms 會一起套用": "; the subtitle delay of {ms:+.0f} ms will be applied too",
    "圖像字幕（PGS / VobSub）無法轉成 .srt": "Image-based subtitles (PGS / VobSub) can't be converted to .srt",
    "圖像字幕（PGS / VobSub）目前不支援燒錄": "Burning image-based subtitles (PGS / VobSub) isn't supported yet",
    "共 {n} 段": "{n} clip(s)",
    "燒錄字幕": "burned-in subtitles",
    "已設定{what}：這次會改用「全部重新編碼」。": "{what} selected: this export will use \"Re-encode all\".",
    "已輸出到：": "Saved to:",
    "匯出失敗": "Export Failed",
    "取消中…": "Cancelling…",
    "目前字幕：{name}": "Current subtitles: {name}",
    "({sec:.3f} 秒)": "({sec:.3f} s)",
    "… 還有 {n} 段": "… and {n} more",
    "{s:g}× 速度": "{s:g}× speed",
    "{ratio} 裁切": "{ratio} crop",
    "輸出資料夾有問題": "Output Folder Problem",
    "來源：": "Source: ",
    "片段：": "Clips: ",
    "、": ", ",

    # ---- 匯出引擎 ----
    "智慧剪輯（起點精準 · 快）": "Smart cut (accurate start · fast)",
    "全部重新編碼（最精準 · 慢）": "Re-encode all (most accurate · slow)",
    "純無損複製（最快 · 起點會偏移）": "Lossless copy (fastest · start may shift)",
    "1:1 正方形（1080×1080）": "1:1 Square (1080×1080)",
    "4:5 直式（1080×1350）": "4:5 Portrait (1080×1350)",
    "9:16 直式全螢幕（1080×1920）": "9:16 Full-screen portrait (1080×1920)",
    "16:9 橫式（1920×1080）": "16:9 Landscape (1920×1080)",
    "置中": "Center",
    "靠左 / 靠上": "Left / Top",
    "靠右 / 靠下": "Right / Bottom",
    "重新編碼中（顯卡 {name}）…": "Re-encoding (GPU {name})…",
    "重新編碼中（CPU）…": "Re-encoding (CPU)…",
    "重新編碼中…": "Re-encoding…",
    "重新編碼 {a:.3f}s–{b:.3f}s（{d:.3f}s），其餘串流複製":
        "Re-encoding {a:.3f}s–{b:.3f}s ({d:.3f}s), stream-copying the rest",
    "掃描關鍵影格…": "Scanning keyframes…",
    "起點剛好落在關鍵影格，整段串流複製": "Start is exactly on a keyframe — stream-copying the whole clip",
    "起點到終點之間沒有關鍵影格，整段重新編碼": "No keyframe between start and end — re-encoding the whole clip",
    "片段長度必須大於 0": "Clip length must be greater than 0",
    "串流複製中…": "Stream copying…",
    "完成": "Done",
    "重新編碼開頭 {sec:.3f} 秒…": "Re-encoding the first {sec:.3f} s…",
    "串流複製其餘部分…": "Stream-copying the rest…",
    "接合片段…": "Joining parts…",
    "沒有可匯出的片段": "There are no clips to export",
    "關鍵影格掃描失敗（{err}），改為整段重新編碼": "Keyframe scan failed ({err}); re-encoding the whole clip",
    "顯卡編碼失敗，改用 CPU 重新編碼…": "GPU encoding failed; re-encoding on the CPU…",
    "ffmpeg 失敗：\n": "ffmpeg failed:\n",
    "重新編碼開頭…": "Re-encoding the head…",
    "接合失敗，改用全部重新編碼…": "Joining failed; re-encoding everything…",
    "準備字幕…": "Preparing subtitles…",
    "接合所有片段…": "Joining all clips…",
    "ffprobe 失敗": "ffprobe failed",

    # ---- 主視窗 ----
    "影片檔 (*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm *.ts *.m2ts *.mpg *.mpeg *.m4v *.rmvb *.3gp *.vob *.ogv);;所有檔案 (*.*)":
        "Video files (*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm *.ts *.m2ts *.mpg *.mpeg *.m4v *.rmvb *.3gp *.vob *.ogv);;All files (*.*)",
    "<b>觸控手勢（觸控螢幕 / 滑鼠皆可）</b><br>\n• 左右滑 —— 拉進度條（滑動中即時預覽，放開才真的跳過去）<br>\n• 上下滑 —— 音量<br>\n• 觸控單指點（點哪裡都一樣）/ 滑鼠單擊 —— 播放 / 暫停<br>\n• 觸控兩指點 —— 切換全螢幕<br>\n• 滑鼠雙擊左 1/3 —— 倒退 10 秒；右 1/3 —— 快轉 10 秒；中間 —— 全螢幕<br>\n• 滑鼠中鍵 —— 切換全螢幕<br>\n• 長按 —— 兩倍速播放，放開恢復<br>\n• 觸控板兩指左右滑 / 滾輪 —— 拉進度、上下 —— 音量<br>\n":
        "<b>Touch gestures (touchscreen or mouse)</b><br>\n"
        "• Swipe left/right — scrub (live preview; jumps when you let go)<br>\n"
        "• Swipe up/down — volume<br>\n"
        "• One-finger tap (anywhere) / mouse click — play / pause<br>\n"
        "• Two-finger tap — toggle full screen<br>\n"
        "• Mouse double-click left third — back 10 s; right third — forward 10 s; center — full screen<br>\n"
        "• Middle mouse button — toggle full screen<br>\n"
        "• Long press — 2× speed until released<br>\n"
        "• Two-finger trackpad swipe / scroll wheel — left/right scrubs, up/down changes volume<br>\n",
    "<br><b>旗標怎麼用</b><br>\n第 1 個旗標是起點、第 2 個是終點、第 3 個又是起點…<br>\n例如在 01:00 和 02:00 各插一個，就會匯出 01:00–02:00 這一段。<br>\n在旗標面板可以把某個旗標固定成起點或終點。\n":
        "<br><b>Using flags</b><br>\n"
        "Flag 1 is a start, flag 2 is an end, flag 3 is a start again…<br>\n"
        "For example, flags at 01:00 and 02:00 export the 01:00–02:00 clip.<br>\n"
        "In the Flags panel you can pin any flag as a start or an end.\n",
    "<br><b>字幕</b><br>\n• 跟影片同名的字幕（abc.mp4 → abc.srt / abc.zh-TW.srt）會自動載入<br>\n• 其他字幕檔：直接拖進視窗，或 字幕 → 載入字幕檔…（srt / ass / vtt / sup…）<br>\n• 影片跟字幕可以一起拖進來<br>\n• 匯出時可以另存對齊片段的 .srt，或把字幕燒進畫面；字幕延遲也會一起套用\n":
        "<br><b>Subtitles</b><br>\n"
        "• Subtitles with the same name as the video (abc.mp4 → abc.srt / abc.en.srt) load automatically<br>\n"
        "• Other subtitle files: drag them into the window, or Subtitles → Load Subtitle File… (srt / ass / vtt / sup…)<br>\n"
        "• You can drag a video and its subtitles in together<br>\n"
        "• When exporting you can save a clip-aligned .srt or burn subtitles into the picture; the subtitle delay is applied too\n",
    "<b>PlayCut</b><br>\n一個給 Windows / macOS 用的影片播放 / 標記 / 剪輯工具。<br><br>\n• 不會跳出更新通知<br>\n• 播放核心 libmpv，剪輯核心 ffmpeg<br>\n• 智慧剪輯模式讓起點<b>完全精準</b>，沒有 LosslessCut 的關鍵影格偏移問題<br>\n• 聲音延遲校正可以直接烘焙進輸出檔\n":
        "<b>PlayCut</b><br>\n"
        "A video player / marker / cutter for Windows and macOS.<br><br>\n"
        "• No update pop-ups<br>\n"
        "• Playback by libmpv, cutting by ffmpeg<br>\n"
        "• Smart cut makes the start <b>frame-accurate</b> — no LosslessCut keyframe offset<br>\n"
        "• Audio delay correction can be baked into the output\n",
    "檔案": "File",
    "播放": "Playback",
    "旗標": "Flags",
    "檢視": "View",
    "說明": "Help",
    "語言": "Language",
    "介面語言會在重新啟動 PlayCut 後切換。要現在重新啟動嗎？":
        "The interface language will change after PlayCut restarts. Restart now?",
    "控制列": "Controls",
    "拖一個影片檔進來，或按 Ctrl+O 開啟": "Drop a video file here, or press Ctrl+O to open one",
    "播放 / 暫停": "Play / Pause",
    "播放速度": "Playback speed",
    "降速": "Slower",
    "加速": "Faster",
    "恢復正常速度": "Normal speed",
    "延遲": "Delay",
    "聲音延遲校正": "Audio delay correction",
    "聲音延遲歸零": "Reset audio delay",
    "字幕軌": "Subtitle Track",
    "選擇字幕軌 / 載入字幕檔": "Choose a subtitle track / load a subtitle file",
    "🚩 旗標": "🚩 Flag",
    "在目前位置插入旗標": "Add a flag at the current position",
    "匯出": "Export",
    "依旗標匯出片段": "Export clips defined by the flags",
    "全螢幕（播放畫面按滑鼠中鍵也可以）": "Full screen (or middle-click the video)",
    "尚無片段": "No clips yet",
    "自動存檔旗標（影片旁的 .playcut.json）": "Auto-save flags (.playcut.json next to the video)",
    "檔案(&F)": "&File",
    "開啟影片…": "Open Video…",
    "載入旗標檔…": "Load Flags File…",
    "另存旗標檔…": "Save Flags As…",
    "匯出旗標為 CSV…": "Export Flags as CSV…",
    "匯出片段…": "Export Clips…",
    "離開": "Quit",
    "播放(&P)": "&Playback",
    "上一格": "Previous frame",
    "下一格": "Next frame",
    "恢復 1×": "Reset to 1×",
    "靜音": "Mute",
    "全螢幕": "Full Screen",
    "離開全螢幕": "Exit Full Screen",
    "字幕(&S)": "&Subtitles",
    "載入字幕檔…": "Load Subtitle File…",
    "切換字幕軌": "Next Subtitle Track",
    "顯示 / 隱藏字幕": "Show / Hide Subtitles",
    "字幕延遲歸零": "Reset subtitle delay",
    "字幕放大": "Larger subtitles",
    "字幕縮小": "Smaller subtitles",
    "字幕位置上移": "Move subtitles up",
    "字幕位置下移": "Move subtitles down",
    "字幕大小 / 位置恢復預設": "Reset subtitle size / position",
    "旗標(&M)": "Fla&gs",
    "插入旗標": "Add Flag",
    "設為起點": "Set as Start",
    "設為終點": "Set as End",
    "跳到上一個旗標": "Go to Previous Flag",
    "跳到下一個旗標": "Go to Next Flag",
    "刪除選取旗標": "Delete Selected Flags",
    "復原：移除最後放置的旗標": "Undo: Remove Last Placed Flag",
    "↶ 已移除旗標 {t}": "↶ Removed flag {t}",
    "沒有可以復原的旗標": "No flag to undo",
    "檢視(&V)": "&View",
    "顯示旗標面板": "Show Flags Panel",
    "觸控滑動靈敏度（整個螢幕寬 = ？秒）": "Swipe Sensitivity (full screen width = ? seconds)",
    "暫停時左上角顯示「已暫停」": "Show \"Paused\" in the Top-Left Corner",
    "加速 / 降速間隔": "Speed Step",
    "自訂快捷鍵…": "Customize Shortcuts…",
    "說明(&H)": "&Help",
    "快速鍵與手勢": "Shortcuts & Gestures",
    "關於": "About",
    "開啟影片": "Open Video",
    "載入字幕檔": "Load Subtitle File",
    "字幕延遲 {ms:+.0f} ms": "Subtitle delay {ms:+.0f} ms",
    "正值 = 字幕晚出現": "Positive = subtitles appear later",
    "字幕大小 {pct:.0f}%": "Subtitle size {pct:.0f}%",
    "字幕位置 {pos}": "Subtitle position {pos}",
    "100 = 畫面最下方": "100 = bottom of the frame",
    "字幕大小 / 位置已恢復預設": "Subtitle size / position reset",
    "關閉字幕": "Subtitles Off",
    "顯示字幕": "Show Subtitles",
    "聲音延遲 {ms:+.0f} ms": "Audio delay {ms:+.0f} ms",
    "另存旗標檔": "Save Flags As",
    "已儲存 {path}": "Saved {path}",
    "載入旗標檔": "Load Flags File",
    "已載入 {n} 個旗標": "Loaded {n} flag(s)",
    "匯出 CSV": "Export CSV",
    "找不到 ffmpeg": "ffmpeg Not Found",
    "加速 / 降速每次 ± {s:g}×": "Speed changes by ± {s:g}× per step",
    "整個螢幕寬的滑動 = {n} 秒": "A full-width swipe = {n} seconds",
    "關於 PlayCut": "About PlayCut",
    "角色": "Role",
    "時間": "Time",
    "備註": "Note",
    "＋旗標": "+ Flag",
    "起點": "Start",
    "把目前位置設成片段起點": "Set the current position as a clip start",
    "終點": "End",
    "把目前位置設成片段終點": "Set the current position as a clip end",
    "跳到": "Go to",
    "跳到選取的旗標": "Jump to the selected flag",
    "刪除": "Delete",
    "刪除選取的旗標": "Delete the selected flags",
    "切換角色": "Toggle role",
    "在 起點 / 終點 / 自動 之間切換": "Cycle between Start / End / Auto",
    "清空": "Clear",
    "刪除全部旗標": "Delete all flags",
    "{n} 秒": "{n} s",
    "語言設定已儲存": "Language setting saved",
    "立即重新啟動": "Restart now",
    "稍後": "Later",
    "無法自動重新啟動，請手動重新開啟 PlayCut。": "Couldn't restart automatically. Please reopen PlayCut yourself.",
    "找不到檔案": "File Not Found",
    "已載入 {n} 個先前存下的旗標": "Loaded {n} previously saved flag(s)",
    "還沒開啟影片": "No Video Open",
    "請先開啟影片，再載入字幕檔。": "Open a video first, then load the subtitle file.",
    "請先開啟影片，再把字幕檔拖進來。": "Open a video first, then drag the subtitle file in.",
    "已載入字幕：{name}": "Loaded subtitles: {name}",
    "沒有字幕": "No subtitles",
    "字幕 → 載入字幕檔…": "Subtitles → Load Subtitle File…",
    "字幕：": "Subtitles: ",
    "字幕：顯示": "Subtitles: on",
    "字幕：隱藏": "Subtitles: hidden",
    "字幕 ✓": "Subtitles ✓",
    "正值 = 聲音延後": "Positive = audio later",
    "請先開啟影片": "Open a video first",
    "這裡已經有旗標了": "There's already a flag here",
    "清空旗標": "Clear Flags",
    "確定要刪除全部 {n} 個旗標嗎？": "Delete all {n} flags?",
    "尚無片段。\n插入第 1 個旗標 = 起點，第 2 個 = 終點，第 3 個又是起點…依此類推。":
        "No clips yet.\nFlag 1 = start, flag 2 = end, flag 3 = start again… and so on.",
    "已匯出 {path}": "Exported {path}",
    "尚未開啟影片": "No Video Open",
    "請先開啟一個影片檔。": "Please open a video file first.",
    "請至少插入兩個旗標：第 1 個是起點、第 2 個是終點。\n（在想要的位置按 M 就可以插旗標）":
        "Add at least two flags: the first is the start, the second is the end.\n(Press M at the position you want to add a flag.)",
    "（播放功能不受影響，仍可正常使用。）": "(Playback is not affected and works normally.)",
    "要改按鍵：檢視 → 自訂快捷鍵…": "To change keys: View → Customize Shortcuts…",
    "跟隨系統": "System default",
    "（固定）": " (pinned)",
    "旗標自動存檔失敗：{err}": "Auto-saving flags failed: {err}",
    "載入失敗": "Load Failed",
    "匯出功能需要 ffmpeg。\n\n": "Exporting requires ffmpeg.\n\n",
    "正值 = 聲音延後播放。": "Positive = audio plays later. ",
    "將匯出 {n} 段，共 {sec:.3f} 秒": "{n} clip(s) to export, {sec:.3f} s total",
    "請在終端機執行：brew install ffmpeg\n（或執行專案資料夾裡的 setup_mac.command）\n":
        "Run this in Terminal: brew install ffmpeg\n(or run setup_mac.command in the project folder)\n",
    "請執行專案資料夾裡的 setup.bat，它會自動把 ffmpeg.exe 下載到 bin\\。\n":
        "Run setup.bat in the project folder; it downloads ffmpeg.exe into bin\\ automatically.\n",
    "鍵盤": "Keyboard",
    "（未設定）": "(not set)",

    # ---- 播放核心 ----
    "找不到 libmpv。請用套件管理員安裝 libmpv（例如 libmpv2 / mpv-libs）。":
        "libmpv was not found. Install it with your package manager (e.g. libmpv2 / mpv-libs).",
    "找不到 libmpv。請先執行 setup_mac.command，或在終端機輸入：brew install mpv":
        "libmpv was not found. Run setup_mac.command first, or run in Terminal: brew install mpv",
    "找不到 libmpv。請先執行 setup.bat（會自動下載 libmpv-2.dll）。":
        "libmpv was not found. Run setup.bat first (it downloads libmpv-2.dll automatically).",
    "python-mpv 版本過舊，缺少 render API。": "python-mpv is too old and lacks the render API.",
    "（外掛）": " (external)",
    "原始錯誤：{err}": "Original error: {err}",
    "OpenGL 繪圖初始化失敗：{err}": "OpenGL rendering failed to initialize: {err}",
    "字幕載入失敗：{err}": "Failed to load subtitles: {err}",
    "畫面繪製錯誤：{err}": "Rendering error: {err}",

    # ---- 自訂快捷鍵 ----
    "自訂快捷鍵": "Customize Shortcuts",
    "點一下「快捷鍵」欄位，直接按下想要的按鍵組合即可。清空 = 不指定快捷鍵。重複的按鍵會標成紅色。":
        "Click a Shortcut cell and press the key combination you want. Clear it for no shortcut. Duplicate keys are shown in red.",
    "搜尋功能或按鍵…": "Search actions or keys…",
    "此項恢復預設": "Reset This One",
    "全部恢復預設": "Reset All",
    "套用": "Apply",
    "分類": "Category",
    "功能": "Action",
    "快捷鍵": "Shortcut",
    "預設": "Default",
    "快捷鍵重複": "Duplicate Shortcuts",
    "有功能用了同一個按鍵，請先修正紅色標示的項目。":
        "Some actions share the same key. Please fix the items marked in red first.",
    "按下按鍵…": "Press a key…",
    "按鍵重複：\n": "Duplicate keys:\n",
    "：": ": ",

    # ---- 字幕 ----
    "字幕檔 (*.srt *.ass *.ssa *.vtt *.sub *.idx *.sup *.smi *.lrc *.mks);;所有檔案 (*.*)":
        "Subtitle files (*.srt *.ass *.ssa *.vtt *.sub *.idx *.sup *.smi *.lrc *.mks);;All files (*.*)",
    "內嵌字幕 #{n}": "Embedded subtitles #{n}",
    "這是圖像字幕（PGS / VobSub），無法轉成 .srt。":
        "These are image-based subtitles (PGS / VobSub) and can't be converted to .srt.",
    "沒有可用的字幕軌。": "No usable subtitle track.",
    "圖像字幕（PGS / VobSub）目前不支援燒錄，請改用文字字幕。":
        "Burning image-based subtitles (PGS / VobSub) isn't supported yet. Please use text subtitles.",
    "字幕轉換失敗：\n": "Subtitle conversion failed:\n",

    # ---- 畫面提示 ----
    "已暫停": "Paused",
    "放開恢復": "Release to restore",
    "{s:+.1f} 秒": "{s:+.1f} s",
    "⏪ 10 秒": "⏪ 10 s",
    "⏸ 暫停": "⏸ Pause",
    "▶ 播放": "▶ Play",
    "⏩ 10 秒": "⏩ 10 s",

    # ---- 系統匣 ----
    '開啟 PlayCut': 'Open PlayCut',
    '完全結束': 'Quit completely',
    '關閉視窗時縮到系統匣（開啟更快）': 'Minimize to system tray on close (faster start-up)',
    'PlayCut 已縮到系統匣，下次開啟會更快。\n{n} 分鐘內沒再使用就會自動結束。': 'PlayCut is still running in the system tray, so it will open faster next time.\nIt quits automatically after {n} minutes of inactivity.',

    # ---- 截圖 ----
    '截圖': 'Screenshot',
    '截圖(&C)': 'S&creenshot',
    '截圖（含字幕）。按右邊的箭頭可以只截影片畫面': 'Screenshot (with subtitles). Use the arrow on the right for the video frame only',
    '截圖（含字幕）': 'Screenshot (with subtitles)',
    '截圖（只有影片畫面）': 'Screenshot (video only)',
    '截圖後同時複製到剪貼簿': 'Also copy screenshots to the clipboard',
    '圖檔格式': 'Image format',
    '存到影片所在的資料夾': 'Save next to the video',
    '選擇截圖資料夾…': 'Choose screenshot folder…',
    '開啟截圖資料夾': 'Open screenshot folder',
    '無法寫入檔案': 'Could not write the file',
    '截圖失敗': 'Screenshot failed',
    '截圖失敗：{err}': 'Screenshot failed: {err}',
    '含字幕': 'with subtitles',
    '影片畫面': 'video only',
    '目前沒有顯示字幕，所以跟影片畫面一樣': "No subtitles are showing, so it's the same as the video frame",
    '📷 已截圖（{kind}）': '📷 Screenshot saved ({kind})',
    '截圖已存到 {path}': 'Screenshot saved to {path}',
    '選擇截圖資料夾': 'Choose Screenshot Folder',
    '截圖會存到 {path}': 'Screenshots will be saved to {path}',
    '截圖會存到影片所在的資料夾': 'Screenshots will be saved next to the video',
    '截圖資料夾：{name}…': 'Screenshot folder: {name}…',

    # ---- HDR ----
    "HDR 影片色調映射": "HDR Tone Mapping",
    "Hable（柔和，最不易過曝，推薦）": "Hable (soft, least likely to blow out — recommended)",
    "Mobius（保留中間調，較亮）": "Mobius (keeps mid-tones, brighter)",
    "Reinhard（簡單壓縮亮部）": "Reinhard (simple highlight compression)",
    "BT.2390（mpv 預設，較亮）": "BT.2390 (mpv default, brighter)",
    "不轉換（直接裁切，會過曝）": "None (hard clip, will look blown out)",
    "動態峰值偵測（依畫面亮度自動調整）": "Dynamic peak detection (adapts to scene brightness)",
    "HDR 影片（{kind}）→ 已轉換為 SDR 顯示（{mode}）": "HDR video ({kind}) → shown as SDR ({mode})",
    "HDR 色彩增強（補回飽和度與對比，較接近 PotPlayer）": "HDR color boost (restores saturation and contrast, closer to PotPlayer)",

    # ---- 設定視窗 ----
    '設定…': 'Settings…',
    '設定已套用': 'Settings applied',
    '聲音提早 {ms}ms': 'Audio {ms} ms earlier',
    '聲音延後 {ms}ms': 'Audio {ms} ms later',
    '音量 +{n}': 'Volume +{n}',
    '音量 −{n}': 'Volume −{n}',
    '字幕提早 {ms}ms': 'Subtitles {ms} ms earlier',
    '字幕延後 {ms}ms': 'Subtitles {ms} ms later',
    '倒退 {s} 秒': 'Back {s} s',
    '快轉 {s} 秒': 'Forward {s} s',
    '{a} / {b} 可快速調整 ±{ms}ms': '{a} / {b} adjust it by ±{ms} ms',
    ' 秒': ' s',
    '設定': 'Settings',
    '畫面': 'Display',
    '一般': 'General',
    '恢復本頁預設': 'Restore Page Defaults',
    '確定': 'OK',
    '倒退 / 快轉的秒數': 'Seek distances',
    '小（預設 Shift+← / →）': 'Small (default Shift+← / →)',
    '中（預設 ← / →）': 'Medium (default ← / →)',
    '大（預設不指定按鍵）': 'Large (no key by default)',
    '觸控與畫面': 'Touch & on-screen',
    '觸控滑動靈敏度': 'Touch swipe sensitivity',
    '微調間隔': 'Adjustment steps',
    '聲音延遲每次調整': 'Audio delay step',
    '音量每次調整': 'Volume step',
    '字幕延遲每次調整': 'Subtitle delay step',
    '存放位置': 'Save location',
    '存到這個資料夾：': 'Save to this folder:',
    '映射方式': 'Method',
    '介面語言': 'Interface language',
    '視窗': 'Window',
    '選單與快捷鍵的名稱會跟著這裡的秒數變。': 'Menu and shortcut names follow the values set here.',
    '手指從螢幕最左滑到最右 = 移動幾秒。數字越小越好微調。': 'How many seconds a swipe across the full screen width moves. Smaller = finer control.',
    '按「聲音提早 / 延後」快捷鍵，或控制列延遲欄旁邊的 − / + 時，每次調整的量。正值 = 聲音延後播放。': 'How much each press of the "Audio earlier / later" shortcuts, or the − / + buttons next to the delay box, changes the delay. Positive = audio plays later.',
    '按「字幕提早 / 延後」快捷鍵時每次調整的量。': 'How much each press of the "Subtitles earlier / later" shortcuts changes the delay.',
    '切換語言需要重新啟動 PlayCut。': 'Changing the language requires restarting PlayCut.',
}
