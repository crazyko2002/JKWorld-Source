# SightFlow

SightFlow 有兩個 Windows 應用：

- `SightFlowPlayer.exe`：簡化版，只選擇及執行已發布 Flow，啟動時自動檢查更新。
- `SightFlowStudio.exe`：完整 IF / ELSE 編輯器、Recorder、OCR 與 Flow 發布工具。

## Source mode

- Player：開啟 `Start SightFlow Player.bat`
- Studio：開啟 `Start Advanced Flow.bat`

## Build EXE

```powershell
.\build_exe.ps1
```

輸出：

- `dist/SightFlowPlayer/SightFlowPlayer.exe`
- `dist/SightFlowStudio/SightFlowStudio.exe`

兩個都係 portable folder，派發時要 zip 整個資料夾，唔可以只拎走 exe。

## Flow update

Player 會讀取 `update_settings.json`，下載 GitHub 上的
`published/manifest.json`，驗證每個檔案的 SHA-256 後更新：

- `config.yaml`
- `macro_config.yaml`
- `templates/`
- `recordings/`
- `numpad/`

Studio 的 `PUBLISH` 按鈕會整理以上資料、建立 manifest、commit 並 push。

手動準備 bundle：

```powershell
.\.venv\Scripts\python.exe flow_distribution.py --prepare
```

## GitHub build

每次 push 到 `main`，GitHub Actions 會 build Player 和 Studio ZIP。
建立例如 `v1.0.0` tag 時，Actions 亦會自動建立 GitHub Release。

## Keyboard Recorder

Press `RECORDER` in the Advanced Flow header.

1. Enter a recording name.
2. Press `START RECORDING`.
3. Wait for the 3-second countdown.
4. Perform the keyboard operation.
5. Press `F8` to finish.
6. The recording is saved under `recordings/`.

The recorder stores explicit key-down and key-up events with high-resolution
timestamps. It no longer captures frames, video, datasets, or trigger images.

`F9` stops test playback.

## Recordings in a Flow

Add a `play_record` action and select a file from `recordings/`.

Available playback backends are DirectInput and PyAutoGUI.
