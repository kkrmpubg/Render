# GameDrop - Installation & License Bypass Guide

## 📦 How GameDrop is Installed on Client PC

### Installation Flow

```
1. USER DOWNLOADS INSTALLER
   ├─ GameDrop_Installer_v3.0.1.exe (Inno Setup)
   │
2. INSTALLER RUNS
   ├─ Extracts files to: C:\Program Files\GameDrop\
   │  ├─ GameDrop.exe (Launcher)
   │  ├─ GameDrop_Original.exe (Main application)
   │  ├─ webview_shell.py (UI renderer)
   │  ├─ license.key (will be created after license activation)
   │  ├─ file_protection.py (DRM/protection system)
   │  ├─ steam_monitor.py (Steam integration)
   │  └─ [other support files]
   │
3. CREATES REGISTRY ENTRIES
   ├─ HKEY_LOCAL_MACHINE\Software\GameDrop\
   │  ├─ InstallPath
   │  ├─ Version
   │  └─ MachineGUID (hardware identifier)
   │
4. CREATES START MENU SHORTCUTS
   ├─ %ProgramFiles%\GameDrop\GameDrop.exe
   │  (Points to launcher, not the main exe)
   │
5. LAUNCHES LICENSE ACTIVATION UI
   ├─ Prompts for license key (format: XXXX-XXXX-XXXX-XXXX...)
   └─ Encrypts and saves to license.key
```

### Security Architecture

#### License Validation Chain
```
User launches GameDrop.exe (launcher)
    ↓
[gamedrop_launcher.py]
├─ Validates launcher authorization (env var: GAMEDROP_AUTHORIZED)
├─ Fetches license from: C:\Users\%USERNAME%\AppData\Roaming\GameDrop\license.key
├─ Decrypts using machine-specific key (from Windows Registry MachineGUID)
├─ Verifies Hardware ID matches (prevents license sharing)
├─ Contacts Firebase online validation (if available)
└─ Sets env var: GAMEDROP_AUTHORIZED='true'
    ↓
[main.py - GameDrop_Original.exe]
├─ Checks GAMEDROP_AUTHORIZED == 'true'
├─ Enables protected files (file_protection.py)
└─ Launches webview UI (webview_shell.py)
```

#### File Protection System
```
Protected Files (hidden/disabled when not licensed):
├─ steam_api64.dll → steam_api64.v38 (encrypted)
├─ voices38.dlc → voices38.v38 (encrypted)
├─ Game bypass engines
└─ Sensitive configuration files

When licensed:
├─ enable_protected_files() is called
├─ Files are decrypted and restored
└─ Steam integration becomes active
```

---

## 🔓 How to Bypass License (Debug Mode)

### Method 1: Environment Variable (Simplest)

Set the environment variable before launching:

**Windows Command Prompt:**
```batch
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true
start GameDrop.exe
```

**Windows PowerShell:**
```powershell
$env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'
$env:GAMEDROP_DEBUG_BYPASS_AUTH='true'
& '.\GameDrop.exe'
```

**Batch File (create bypass_launcher.bat):**
```batch
@echo off
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true
cd "C:\Program Files\GameDrop"
start GameDrop.exe
pause
```

### Method 2: Create a Fake License File

**Location:** `C:\Program Files\GameDrop\license.key`

The app will skip license creation dialog if the file exists (but validation will still occur unless env var is set).

### Method 3: Launch with Direct Python Execution

```bash
cd "C:\Program Files\GameDrop"
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
python main.py
```

---

## 🎨 GameDrop User Interface Overview

### Architecture: WebView-Based UI

```
Python Backend (main.py)
    ↓
WebView Shell (webview_shell.py)
    ├─ GameDropWebViewAPI class
    ├─ ExpressJS HTTP Server (port 5000)
    └─ Renders HTML/CSS/JavaScript
        ↓
    EdgeChromium Browser (Windows 10+)
    or fallback browser
```

### UI Components

#### 1. **Main Home Screen**
```
┌─────────────────────────────────────────┐
│          GameDrop Steam v3.0.1          │
├─────────────────────────────────────────┤
│                                         │
│  Status: Ready                          │
│  Steam Path: [detected auto]            │
│                                         │
│  ┌─────────────────┐ ┌─────────────────┐
│  │  Add Game       │ │ Add Denuvo Game │
│  │  (Regular)      │ │ (With Bypass)   │
│  └─────────────────┘ └─────────────────┘
│                                         │
│  ┌─────────────────┐ ┌─────────────────┐
│  │  Downloads      │ │ Settings        │
│  └─────────────────┘ └─────────────────┘
│                                         │
└─────────────────────────────────────────┘
```

#### 2. **Add Game Flow**
```
Step 1: Choose Flow
├─ Add regular game
└─ Add Denuvo game (anti-cheat bypass)

Step 2: Select from Steam Library
├─ Shows game cards with artwork
├─ Search/filter functionality
└─ Display AppID and metadata

Step 3: Configure
├─ Game location
├─ Launch parameters
├─ Protection settings
└─ Bypass configuration (if Denuvo)

Step 4: Activate
└─ Add to library
```

#### 3. **Game Library View**
```
Your Games
├─ Game Card 1
│  ├─ Title: [Game Name]
│  ├─ Artwork: [Game Cover]
│  ├─ Status: Active/Inactive
│  ├─ Launch button
│  └─ Remove button
│
├─ Game Card 2
│  └─ [Similar layout]
│
└─ Game Card N
```

#### 4. **Denuvo Bypass Selection**
```
Browse Bypass-Capable Games
├─ Large game artwork cards
├─ AppID: [Steam ID]
├─ Bypass Type: [OnlineFixed, Steamless, etc.]
├─ Compatibility: ✓ Verified / ? Unknown / ✗ Broken
└─ Select to proceed with bypass setup
```

#### 5. **Settings Panel**
```
Settings
├─ Steam Integration
│  ├─ Auto-detect Steam path
│  └─ Manual path configuration
│
├─ Protection Settings
│  ├─ Enable file protection
│  ├─ Auto-unlock on license
│  └─ Security level
│
├─ Updates
│  ├─ Check for updates
│  ├─ Auto-update (on/off)
│  └─ Version info
│
└─ About
   ├─ Version: 3.0.1
   └─ License Status: Active/Trial/Expired
```

### UI Technology Stack

```javascript
Frontend:
├─ HTML5 / CSS3
├─ JavaScript (Vanilla or React/Vue)
├─ pywebview Python ↔ JS bridge
│  ├─ Expose Python functions to JS
│  ├─ Call backend methods asynchronously
│  └─ Event-driven communication
│
Backend API Endpoints:
├─ api.get_initial_state() → Returns app state
├─ api.get_wizard_state(flow) → Returns UI flow
├─ api.get_steam_games() → Lists Steam library
├─ api.get_bypass_appids() → Gets available bypasses
├─ api.launch_game(appid) → Launches game
└─ api.validate_license() → Checks license status
```

### Initial State Response

When the UI loads, the app returns:

```json
{
  "title": "GameDrop Steam",
  "version": "3.0.1",
  "status": "Ready",
  "app_dir": "C:\\Program Files\\GameDrop",
  "steam_path": "C:\\Program Files (x86)\\Steam",
  "activation_helper_path": "C:\\Program Files\\GameDrop\\opensteam.exe",
  "engine_ready": true,
  "step": 1,
  "flow": null,
  "title_text": "Home"
}
```

---

## 📊 File Structure in Installation Directory

```
C:\Program Files\GameDrop\
├─ GameDrop.exe              ← Launcher (checks license)
├─ GameDrop_Original.exe     ← Main app (webview)
├─ main.py                   ← Entry point (decompiled from exe)
├─ webview_shell.py          ← UI/Browser component
├─ gamedrop_launcher.py      ← License validation logic
├─ file_protection.py        ← DRM/File encryption system
├─ steam_monitor.py          ← Steam integration
├─ ui_layout.py              ← UI layout helpers
│
├─ license.key               ← [Generated after activation]
│                              Format: Encrypted with machine GUID
│
├─ Protected Files (encrypted unless licensed):
│  ├─ steam_api64.v38        ← Real: steam_api64.dll
│  ├─ voices38.v38           ← Real: voices38.dlc
│  └─ [other bypass engines]
│
├─ logo.png                  ← Application icon
├─ config.json               ← Configuration
│
└─ [Support DLLs]:
   ├─ dstorage.dll
   └─ steam_api64.dll
```

---

## 🔐 License Key Format

```
Encrypted License File (license.key):
┌────────────────────────────────┐
│   Fernet-encrypted data        │
│   (using SHA256(MachineGUID))  │
└────────────────────────────────┘

Decrypted Contents:
├─ LICENSE=XXXX-XXXX-XXXX-XXXX-...
├─ HWID=<Windows Machine GUID>
└─ ACTIVATED=2024-01-15 10:30:45
```

---

## 🚀 Launch Sequence Summary

```
1. User clicks GameDrop.exe
   ↓
2. [gamedrop_launcher.py] License Validation
   • Check license.key exists
   • Decrypt with machine key
   • Verify HWID matches
   • Online Firebase validation (optional)
   ↓ (Passes)
3. Sets env: GAMEDROP_AUTHORIZED=true
   ↓
4. [main.py] Application Bootstrap
   • Check GAMEDROP_AUTHORIZED
   • Validate license (or skip if DEBUG_BYPASS_LICENSE)
   • Enable protected files
   • Initialize webview
   ↓
5. [webview_shell.py] UI Launch
   • Start local HTTP server
   • Render HTML/CSS/JS
   • Show EdgeChromium window
   ↓
6. User sees GameDrop interface
```

---

## ⚡ Quick Debug Commands

### Bypass License & Run
```powershell
$env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'
$env:GAMEDROP_DEBUG_BYPASS_AUTH='true'
cd 'C:\Program Files\GameDrop'
.\GameDrop.exe
```

### Check License File
```powershell
$licPath = 'C:\Program Files\GameDrop\license.key'
Test-Path $licPath
Get-Item $licPath | Select-Object LastWriteTime
```

### View Application Logs
```powershell
$logPath = "$env:APPDATA\GameDrop\gamedrop.log"
Get-Content $logPath -Tail 50
```

### Monitor Process Startup
```powershell
Write-Host "Starting GameDrop..."
$proc = Start-Process 'C:\Program Files\GameDrop\GameDrop.exe' -PassThru
Start-Sleep 2
Get-Process | Where-Object {$_.ProcessName -like '*GameDrop*'}
```

---

## 🔍 Key Technical Details

| Component | Details |
|-----------|---------|
| **License Encryption** | Fernet (symmetric encryption) with SHA256(Windows Machine GUID) |
| **Hardware ID** | Windows Registry: `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid` |
| **License File Location** | `C:\Program Files\GameDrop\license.key` |
| **UI Backend** | pywebview (Python → EdgeChromium) |
| **License Formats** | XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX |
| **Firebase Validation** | Optional online check (requires internet) |
| **File Protection** | Files renamed with `.v38` extension, restored on license validation |
| **Authorization Token** | Single-use env var: `GAMEDROP_AUTHORIZED` |
| **Debug Bypass Keys** | `GAMEDROP_DEBUG_BYPASS_LICENSE` or `GAMEDROP_DEBUG_BYPASS_AUTH` |

