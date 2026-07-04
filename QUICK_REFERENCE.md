# GameDrop - Quick Reference & Cheat Sheet

## 🚀 Quick Start - License Bypass

### One-Liner (PowerShell)
```powershell
$env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'; $env:GAMEDROP_DEBUG_BYPASS_AUTH='true'; & 'C:\Program Files\GameDrop\GameDrop.exe'
```

### Batch File (Save as `bypass.bat`)
```batch
@echo off
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true
cd C:\Program Files\GameDrop
start GameDrop.exe
```

### Python Direct Execution
```bash
cd C:\Program Files\GameDrop
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
python main.py
```

---

## 📊 Installation Path Reference

| Component | Path |
|-----------|------|
| **Installation** | `C:\Program Files\GameDrop\` |
| **Launcher** | `C:\Program Files\GameDrop\GameDrop.exe` |
| **Main App** | `C:\Program Files\GameDrop\GameDrop_Original.exe` |
| **License File** | `C:\Program Files\GameDrop\license.key` |
| **App Logs** | `%APPDATA%\GameDrop\gamedrop.log` |
| **Protected Files** | `*.v38` extension (renamed) |
| **Steam Default** | `C:\Program Files (x86)\Steam\` |

---

## 🔓 License Bypass Environment Variables

### Primary Variables (Use One)

```
GAMEDROP_DEBUG_BYPASS_LICENSE=true
   ├─ Skips local license file validation
   └─ Allows app to launch without license.key

GAMEDROP_DEBUG_BYPASS_AUTH=true
   ├─ Bypasses launcher authorization check
   └─ Allows direct execution of GameDrop_Original.exe
```

### Combined Usage (Recommended)
```batch
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true
```

### Authorization Variables (Runtime)
```
GAMEDROP_AUTHORIZED=true
   └─ Set by launcher; required by main app

GAMEDROP_LAUNCHER_TOKEN
   └─ Single-use token; cleared after verification
```

---

## 🎮 App Launch Sequence

```
1. User runs: GameDrop.exe (launcher)
                    ↓
2. Launcher validates license.key
   ├─ Decrypts with machine GUID
   ├─ Verifies hardware ID
   └─ Optional: Firebase online check
                    ↓ (Success)
3. Sets: GAMEDROP_AUTHORIZED=true
                    ↓
4. Launches: GameDrop_Original.exe (main app)
                    ↓
5. main.py checks GAMEDROP_AUTHORIZED
                    ↓
6. Loads webview_shell.py (UI)
                    ↓
7. Shows UI in EdgeChromium browser
```

---

## 🔒 License File Format

### Location
```
C:\Program Files\GameDrop\license.key
```

### Storage Format
```
[Fernet-Encrypted Data]
↓ (Decrypted with SHA256(Windows Machine GUID))
├─ LICENSE=XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
├─ HWID=<Windows Machine GUID>
└─ ACTIVATED=2024-01-15 10:30:45
```

### Create Fake License (Manual)
```python
import base64
from cryptography.fernet import Fernet
import hashlib
import winreg

# Get machine GUID
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
    r'SOFTWARE\Microsoft\Cryptography', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
machine_guid, _ = winreg.QueryValueEx(key, 'MachineGuid')

# Create encryption key
key_bytes = hashlib.sha256(machine_guid.encode()).digest()
encryption_key = base64.urlsafe_b64encode(key_bytes)

# Create license data
license_data = f"""LICENSE=DEMO-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
HWID={machine_guid}
ACTIVATED=2024-01-01 00:00:00"""

# Encrypt and save
fernet = Fernet(encryption_key)
encrypted = fernet.encrypt(license_data.encode())

with open('license.key', 'wb') as f:
    f.write(encrypted)
```

---

## 📁 File Protection System

### Protected File Mapping

| Original File | Protected Name | Restored When |
|---------------|----------------|----------------|
| `steam_api64.dll` | `steam_api64.v38` | License valid |
| `voices38.dlc` | `voices38.v38` | License valid |
| Game bypass engines | `*.v38` | License valid |
| Config files | `*.v38` | License valid |

### Restore Protected Files (Manual)

```python
from file_protection import enable_protected_files
enable_protected_files()  # Restores all .v38 files
```

### Disable Protected Files (License Loss)
```python
from file_protection import disable_protected_files
disable_protected_files()  # Encrypts files → .v38
```

---

## 🌐 API Endpoints (Internal HTTP Server)

The webview launches a local HTTP server at `http://localhost:5000/`

```
Python Backend (pywebview API)
│
├─ api.get_initial_state()
│  └─ Returns: { title, version, status, steam_path, engine_ready, ... }
│
├─ api.get_wizard_state(flow)
│  └─ Returns: { step, flow, title, message }
│  └─ Flows: "add_game", "add_denuvo_game"
│
├─ api.get_steam_games(filter=None)
│  └─ Returns: [{ appid, title, path, hours, artwork, ... }]
│
├─ api.get_bypass_appids()
│  └─ Returns: [{ appid, title, bypass_type, compatibility, ... }]
│
├─ api.launch_game(appid, config)
│  └─ Returns: { success, pid, message }
│
├─ api.validate_license()
│  └─ Returns: { valid, hwid, expires, message }
│
└─ api.save_settings(settings_dict)
   └─ Returns: { success, message }
```

---

## 🛠️ Troubleshooting

### License Bypass Not Working

**Issue:** "GameDrop - Unauthorized Launch" error
```
Solution 1: Set both environment variables:
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true

Solution 2: Launch from correct directory:
cd C:\Program Files\GameDrop
start GameDrop.exe

Solution 3: Run with elevated privileges:
Right-click → Run as Administrator
```

### Protected Files Not Restoring

**Issue:** Game shows `*.v38` files instead of DLLs
```
Solution:
python -c "from file_protection import enable_protected_files; enable_protected_files()"
```

### License File Corrupted

**Issue:** "Failed to decrypt license file"
```
Solution 1: Delete and regenerate:
del "C:\Program Files\GameDrop\license.key"

Solution 2: Set bypass:
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
python main.py
```

### Steam Not Found

**Issue:** "Steam path not detected"
```
Solution 1: Install Steam to default location
C:\Program Files (x86)\Steam\

Solution 2: Manual path in Settings:
Settings → Steam Integration → Browse
```

---

## 📝 Registry Locations

### GameDrop Installation Registry

```
Location: HKEY_LOCAL_MACHINE\SOFTWARE\GameDrop
Values:
├─ InstallPath: C:\Program Files\GameDrop
├─ Version: 3.0.1
└─ LastRun: 2024-01-15 14:23:05
```

### Machine Identifier

```
Location: HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography
Values:
├─ MachineGuid: [Unique Windows ID]
└─ (Used for license encryption)
```

### Steam Registry

```
Location: HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Valve\Steam
Values:
├─ InstallPath: C:\Program Files (x86)\Steam
└─ (Auto-detected by GameDrop)
```

---

## 🔍 Checking License Status

### View License File (Encrypted)
```powershell
$path = 'C:\Program Files\GameDrop\license.key'
Get-Item $path | Select-Object LastWriteTime, Length
```

### View Application Logs
```powershell
$log = "$env:APPDATA\GameDrop\gamedrop.log"
Get-Content $log -Tail 30 -Wait
```

### Check Process Status
```powershell
Get-Process | Where-Object {$_.ProcessName -like '*GameDrop*'}
```

### Monitor File Protection
```powershell
Get-ChildItem "C:\Program Files\GameDrop\*.v38" | Measure-Object
```

---

## 📦 Installation Size Reference

```
GameDrop Installation:
├─ Application files: ~50 MB
├─ Bypass engines: ~100-200 MB
├─ Protected file archives: ~300-500 MB
├─ Steam integration: ~30 MB
└─ Total: ~500 MB - 1 GB

Game Library:
└─ Varies by number and size of games installed
```

---

## 🔄 Update & Maintenance

### Check for Updates
```powershell
cd 'C:\Program Files\GameDrop'
python check_github_release.py
```

### Manual Update
```powershell
# Download latest GameDrop_Original.exe from GitHub
# Place in C:\Program Files\GameDrop\
# Restart application
```

### Clean Installation
```powershell
# Remove all protected file markers
python -c "from file_protection import clear_protected_files_tracking; clear_protected_files_tracking()"

# Regenerate license
del 'C:\Program Files\GameDrop\license.key'
```

---

## 💡 Pro Tips

1. **Fastest Bypass:** Use PowerShell one-liner
   ```powershell
   $env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'; & 'C:\Program Files\GameDrop\GameDrop.exe'
   ```

2. **Batch Automation:** Create `.bat` file in Start Menu
   ```
   C:\Users\[User]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\
   ```

3. **Command-Line Launch:** Create shortcut with arguments
   ```
   Target: cmd.exe /c "set GAMEDROP_DEBUG_BYPASS_LICENSE=true && GameDrop.exe"
   ```

4. **Monitor Bypass Status:** Check environment variables
   ```powershell
   [System.Environment]::GetEnvironmentVariable('GAMEDROP_DEBUG_BYPASS_LICENSE')
   ```

5. **Performance:** License bypass has no performance impact
   ```
   Bypass just skips: License file I/O, decryption, HWID verification, Firebase check
   ```

---

## ❓ FAQ

**Q: Does bypassing license prevent the app from working?**
A: No, the bypass just skips license validation. All features work normally.

**Q: Can I run without the environment variables set?**
A: Only if a valid `license.key` file exists and hardware ID matches.

**Q: What if I restart the PC?**
A: Environment variables are session-specific. You need to set them again or use a batch file.

**Q: Can multiple users use the same license?**
A: No, licenses are locked to machine GUID. Each PC needs its own license.

**Q: Does the bypass work with Steam auto-launch?**
A: No, environment variables must be set before launch. Use the batch file instead.

**Q: What happens to protected files if license expires?**
A: Files are automatically encrypted (renamed to `.v38`) on next startup.

**Q: Can I share my license.key file?**
A: No, it's encrypted with your machine's hardware ID. Other PCs can't decrypt it.

---

## 📞 Support Resources

```
Documentation: [Workspace root]/INSTALLATION_AND_LICENSE_BYPASS_GUIDE.md
UI Reference:  [Workspace root]/UI_VISUAL_GUIDE.md
Batch Launcher: [Workspace root]/LAUNCH_WITH_LICENSE_BYPASS.bat

Debug Logs:    %APPDATA%\GameDrop\gamedrop.log
Installation:  C:\Program Files\GameDrop\
License File:  C:\Program Files\GameDrop\license.key
```

