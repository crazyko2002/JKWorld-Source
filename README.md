# JK世界

JK世界有兩個 Windows 應用：

- `JK世界 冇撚腦ver.exe`：所有已啟用 Flow 會一齊執行。
- `JK世界 Studio.exe`：完整編輯器，但沒有 Publish。
- `JK世界 Studio Owner.exe`：私人版本，包含 Publish，不會公開發布。

## Source mode

- Player：開啟 `Start JK世界 冇撚腦ver.bat`
- Studio：開啟 `Start Advanced Flow.bat`

## Build EXE

```powershell
.\build_exe.ps1
```

輸出：

- `dist/JKWorldNoBrain/JK世界 冇撚腦ver.exe`
- `dist/JKWorldStudio/JK世界 Studio.exe`
- `dist/JKWorldStudioOwner/JK世界 Studio Owner.exe`

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

NoBrain also checks the latest GitHub Release for `JKWorld-NoBrain.zip`.
If a newer packaged app is available, it downloads the ZIP, restarts, and
updates engine/app files while keeping local flow data folders such as
`config.yaml`, `templates/`, `recordings/`, and `numpad/`.

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
