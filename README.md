# Auto Credit

在本機替影片加上作者 credit 與結尾來源資訊的 Windows 桌面工具。使用 Python、Qt for Python（PySide6）與 FFmpeg，不需要登入平台、上傳影片或啟動後端服務。

## 功能

- 選取或拖入單支影片，選擇／自訂原始平台，填入作者 ID 和原片網址。
- 原片播放期間，全程在右上角顯示 `Credit:平台名@創作者名`，例如 `Credit:YouTube@creator_name`，白字搭配半透明深色底。
- 自動附加結尾資訊卡，顯示平台、作者、完整網址與 QR Code；預設 4 秒，可調整為 1–30 秒。
- 結尾會依平台自動顯示 YouTube、Bilibili 或 TikTok logo，使用隨程式附帶的素材，預覽與輸出一致。其他平台維持文字標示。
- 中文字型、自動換行、依影片短邊縮放的字級（1.5–5%）。
- 可選擷取時間，預覽標註畫面及結尾卡；預覽與輸出共用版面程式。
- 背景輸出、進度、取消、完成後開啟影片或資料夾。
- 一鍵複製來源文字，方便貼到影片說明欄。
- 記住平台、樣式及上次選擇的資料夾；作者與連結不會存入設定。
- 不覆蓋原片或既有輸出；取消與失敗時清理本次暫存檔。

## 開發環境啟動（Windows PowerShell）

需要 Python 3.11 或以上，以及可執行的 `ffmpeg`、`ffprobe`。本專案以 Python 3.14、PySide6 6.12 與 FFmpeg 進行驗證。

```powershell
cd D:\project_credit\auto-credit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

若尚未安裝 FFmpeg，可以使用：

```powershell
winget install --id Gyan.FFmpeg -e
```

安裝後重新開啟終端機，確認兩個工具皆可使用：

```powershell
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python.exe -m auto_credit
```

也可執行 `.\.venv\Scripts\auto-credit.exe`。不需要啟用虛擬環境，也不需要更改 PowerShell 執行政策。

FFmpeg 必須支援 `libx264`、AAC、PNG、`overlay`、`concat`、`lavfi`。官方資訊：[FFmpeg 下載](https://ffmpeg.org/download.html)、[濾鏡文件](https://ffmpeg.org/ffmpeg-filters.html)。

若工具不在 PATH，可指定完整路徑：

```powershell
$env:AUTO_CREDIT_FFMPEG = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
$env:AUTO_CREDIT_FFPROBE = 'C:\tools\ffmpeg\bin\ffprobe.exe'
.\.venv\Scripts\python.exe -m auto_credit
```

搜尋順序為環境變數、應用程式內的 `bin/`、PATH。環境變數請填檔案路徑，不要填指令或參數。

## 使用方式

1. 按「選擇影片」或拖入檔案。讀取影片後會顯示尺寸、時長及幀率。
2. 選擇平台（也可以直接輸入名稱），填入作者 ID 與完整的 HTTP/HTTPS 原片網址。
3. 作者 ID 可填 `creator_name` 或 `@creator_name`，右上角會自動統一顯示單一 `@`。
4. 調整結尾秒數、字級與擷取時間，按「更新預覽」。切換頁籤檢查結尾卡。
5. 按「產生 MP4 影片」，選擇新的檔名。預設為原片旁的 `原檔名_credit.mp4`。
6. 完成後可開啟影片，並複製來源文字貼到發佈平台。

預覽是靜態畫面，不是影片播放器。一般 MP4 畫面中的文字網址無法點擊；結尾 QR Code 使用完整輸入連結，未使用短網址服務。連結只做格式檢查，不會連線確認內容、追蹤轉址或自動查詢作者。

平台 logo 支援選單中的 YouTube、Bilibili、TikTok，以及自訂輸入的 `YT`、`哔哩哔哩`、`嗶哩嗶哩`、`B站`、`Tik Tok`（忽略大小寫與空白）。素材放在 `auto_credit/assets/logos/`，會一併包含在安裝套件與 Windows 打包結果，不依賴 Downloads 資料夾。

## 輸出規格與範圍

| 項目 | 行為 |
| --- | --- |
| 輸出 | MP4／H.264，CRF 20，AAC 192 kbps／48 kHz 雙聲道 |
| 尺寸 | 保留顯示比例，處理旋轉資訊及非方形像素，必要時補為偶數尺寸 |
| 幀率 | 以原片平均幀率輸出固定幀率，最高 60 fps |
| 音訊 | 使用第一條音軌，保留原片聲音內容並重編碼；結尾為靜音 |
| 無音軌影片 | 補上靜音音軌，方便與結尾串接 |
| 支援尺寸 | 短邊至少 240、長邊最多 4096 像素 |
| 色彩 | 第一版支援 SDR；PQ／HLG HDR 會提示先轉成 SDR |
| 多軌內容 | 使用第一個非封面影片軌與第一條音軌；不保留字幕、章節及原始 metadata |
| 來源資料 | 平台最多 80 字元、作者 160 字元、網址 2048 字元 |

加入標註需要重新編碼，處理速度與畫質取決於原片和電腦效能。可變幀率會轉成固定幀率；目前不提供 HDR 色調映射、批次處理、多作者、影片下載或平台自動發佈。極長連結若無法在小尺寸結尾卡清楚排版，會提示縮短資料，不會截斷完整網址。

暫存圖層與編碼中的影片會放在輸出資料夾下的 `.auto-credit-*`，成功後驗證尺寸與長度，再發布完成檔；需要足夠的磁碟空間。若程式或系統被強制終止，可在確認沒有處理工作後，手動刪除殘留的 `.auto-credit-*` 資料夾。

關閉正在處理的視窗會先取消工作並清理暫存檔，再結束程式。正常設定由 Qt QSettings 存於目前使用者的 `AutoCredit/AutoCredit`（Windows 為登錄設定）。

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

測試使用 Qt offscreen 模式，不會開啟可見視窗。整合測試透過 FFmpeg 產生短測試片，驗證直橫式、中文與特殊字元路徑、無音軌、旋轉資訊、顯示比例、輸出時長、音訊延遲與靜音結尾、取消清理、防覆蓋，以及介面的匯入→預覽→輸出流程。找不到 FFmpeg／FFprobe 時，整合測試會明確顯示 skipped；這不代表影片輸出已驗證。

## 打包為 Windows 應用程式

```powershell
.\scripts\build.ps1
```

腳本使用虛擬環境的 Python、PyInstaller 與 PATH 中的 FFmpeg／FFprobe。打包期間會隔離其他軟體的 DLL 搜尋路徑，並以實際影片輸出及 Qt 預覽進行打包版自我檢查；成功後才顯示完成。報告位於 `build\packaged-check\report.json`。

結果位於 `dist\AutoCredit\AutoCredit.exe`，請保留及分發整個 `AutoCredit` 資料夾；目標電腦不需要安裝 Python 或另裝 FFmpeg。

可指定其他 Python：`.\scripts\build.ps1 -Python 'C:\path\to\python.exe'`。若本機政策禁止執行腳本，可開啟腳本並在終端機執行其中的打包指令。正式分發前應在乾淨的 Windows 電腦驗證，並依實際使用的 Qt／FFmpeg build 附上相應授權文字與所需來源資訊；此 repository 不收錄第三方執行檔。

若原路徑的程式正在執行，腳本會先停止打包並提示關閉。也可使用 `.\scripts\build.ps1 -OutputDirectory 'dist\new-version'` 產生獨立新版，執行檔會位於指定目錄下的 `AutoCredit\AutoCredit.exe`。

Qt 打包參考：[官方部署文件](https://doc.qt.io/qtforpython-6/deployment/index.html)。

打包後可執行完整自我檢查，產生一段測試影片、實際輸出、預覽截圖及 JSON 報告。下列命令不會開啟可見視窗；`report.json` 的 `ok` 應為 `true`，執行檔結束碼應為 0：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
Start-Process -FilePath '.\dist\AutoCredit\AutoCredit.exe' -ArgumentList '--self-check', 'work\packaged-check' -WindowStyle Hidden -Wait
Remove-Item Env:QT_QPA_PLATFORM
Get-Content work\packaged-check\report.json
```

此選項也可用於原始碼：`python -m auto_credit --self-check work\source-check`。每次建立新的 `check-*` 子資料夾，保留測試產物供人工檢查。

## 程式結構

```text
auto_credit/
  app.py         繁體中文介面、背景工作及使用者設定
  models.py      來源資料與輸入驗證
  artwork.py     共用標註、中文字型、結尾卡與 QR Code
  logos.py       平台 logo 載入與別名辨識
  engine.py      FFprobe、FFmpeg、進度、取消及輸出驗證
scripts/
  build.ps1      Windows onedir 打包，包含 FFmpeg／FFprobe
  entry.py       打包入口
tests/           版面、介面及實際編碼整合測試
```

來源資料透過 Qt 繪製成圖片；FFmpeg 以參數陣列啟動，不使用 shell 字串拼接，也不把作者名稱或網址插入濾鏡語法。
