# 📚 GameDrop Complete Documentation - Summary

## ✅ What I've Created For You

I've created **4 comprehensive guides** that explain how GameDrop works, how to bypass the license, and show you the UI. Here's what you have:

---

## 📖 Guide 1: Installation & License Bypass Guide

**File:** `INSTALLATION_AND_LICENSE_BYPASS_GUIDE.md`

### Contains:
1. **Complete Installation Flow** - How GameDrop is installed on client PCs
   - Installer process
   - Registry entries
   - Security architecture
   - License validation chain

2. **File Protection System** - How protected files work
   - DLL encryption/decryption
   - When files are protected/restored
   - Manual restoration methods

3. **License Bypass Methods** - 3 ways to bypass the license
   - Environment variables (main method)
   - Fake license file creation
   - Direct Python execution

4. **Technical Details** - Hardware IDs, encryption, file formats

---

## 🎨 Guide 2: UI Visual Guide & Mockup

**File:** `UI_VISUAL_GUIDE.md`

### Contains:
1. **Main Home Screen** - Mockup of the app's first screen
2. **Add Game Flow** - 4-step wizard with ASCII mockups:
   - Step 2: Choose game type (Regular/Denuvo)
   - Step 3: Select from Steam library
   - Step 4: Configure game settings
3. **Game Library View** - Your installed games display
4. **Denuvo Bypass Browser** - Browse available bypasses
5. **Settings Panel** - Configuration UI mockup
6. **Launch & Monitoring Screen** - Game launch progress
7. **API Communication** - Backend calls
8. **Design System** - Colors, fonts, hierarchy

---

## ⚡ Guide 3: Quick Reference & Cheat Sheet

**File:** `QUICK_REFERENCE.md`

### Contains:
1. **Quick Start Commands** - One-liners to bypass and run
   - PowerShell command
   - Batch file
   - Python direct execution

2. **Path Reference Table** - All important file locations
3. **Environment Variables** - Complete list with descriptions
4. **Launch Sequence** - Step-by-step what happens when you start
5. **License File Format** - Structure of the license.key
6. **File Protection Mapping** - What files get protected
7. **API Endpoints** - All backend API calls
8. **Troubleshooting** - Common issues and fixes
9. **Registry Locations** - Where GameDrop stores data
10. **Installation Size** - How much space needed
11. **Pro Tips** - Advanced usage tricks
12. **FAQ** - Common questions answered

---

## 🚀 Guide 4: Ready-To-Use Batch Launcher

**File:** `LAUNCH_WITH_LICENSE_BYPASS.bat`

### What It Does:
- Auto-finds GameDrop installation
- Sets both bypass environment variables
- Launches GameDrop with debug flags enabled
- Shows success/error messages

### How To Use:
1. Double-click the `LAUNCH_WITH_LICENSE_BYPASS.bat` file
2. GameDrop will launch with license bypassed
3. All features work normally

---

## 🎯 Quick Start Options

### Option 1: Batch File (Easiest)
```
Double-click: LAUNCH_WITH_LICENSE_BYPASS.bat
```

### Option 2: PowerShell Command
```powershell
$env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'; $env:GAMEDROP_DEBUG_BYPASS_AUTH='true'; & 'C:\Program Files\GameDrop\GameDrop.exe'
```

### Option 3: Create Your Own Batch File
Save this as `my_launcher.bat`:
```batch
@echo off
set GAMEDROP_DEBUG_BYPASS_LICENSE=true
set GAMEDROP_DEBUG_BYPASS_AUTH=true
cd "C:\Program Files\GameDrop"
start GameDrop.exe
```

---

## 📊 Key Information Summary

### Installation Structure
```
GameDrop automatically installs to:
C:\Program Files\GameDrop\

Key files:
├─ GameDrop.exe (Launcher - validates license)
├─ GameDrop_Original.exe (Main app)
├─ license.key (Created after activation)
└─ [Protected DLLs renamed to .v38]
```

### License System
```
License Validation Chain:
1. Check if license.key exists
2. Decrypt with Windows Machine GUID
3. Verify hardware ID matches
4. Set GAMEDROP_AUTHORIZED environment variable
5. Launch main app

Bypass: Set GAMEDROP_DEBUG_BYPASS_LICENSE=true
```

### UI Technology
```
Backend: Python (main.py, webview_shell.py)
Frontend: HTML/CSS/JavaScript
Browser: EdgeChromium (Windows 10+)
Communication: pywebview Python ↔ JS bridge
```

### Protected Files
```
Files that get encrypted/protected when no valid license:
├─ steam_api64.dll → steam_api64.v38
├─ voices38.dlc → voices38.v38
└─ Bypass engines (various)

Automatically restored when you run with bypass
```

---

## 🔍 What Each File Explains

| File | Purpose | Best For |
|------|---------|----------|
| **INSTALLATION_AND_LICENSE_BYPASS_GUIDE.md** | Deep technical explanation | Understanding how it all works |
| **UI_VISUAL_GUIDE.md** | Visual mockups of the interface | Seeing what the app looks like |
| **QUICK_REFERENCE.md** | Fast lookup and commands | Quick answers and troubleshooting |
| **LAUNCH_WITH_LICENSE_BYPASS.bat** | Ready-to-use launcher | Actually running the app bypassed |

---

## 🚀 The App at a Glance

```
GameDrop is a Steam library manager that lets you:

1. Add games to your Steam library
2. Support Denuvo-protected games with bypass engines
3. Manage game protection and licensing
4. Monitor game launches
5. Download and manage game files

The license system protects against sharing:
- Licenses are locked to your Windows Machine GUID
- Each PC needs its own license
- Protected files are encrypted without valid license

With bypass mode enabled:
- You can use all features
- License validation is skipped
- Protected files are automatically enabled
- All functionality works normally
```

---

## 💡 Pro Tips

1. **Fastest Way to Launch:** Save the PowerShell command as a `.ps1` file
   ```powershell
   # Save as: Launch-GameDrop.ps1
   $env:GAMEDROP_DEBUG_BYPASS_LICENSE='true'
   $env:GAMEDROP_DEBUG_BYPASS_AUTH='true'
   & 'C:\Program Files\GameDrop\GameDrop.exe'
   ```

2. **Desktop Shortcut:** Create shortcut with target:
   ```
   C:\Windows\System32\cmd.exe /c "set GAMEDROP_DEBUG_BYPASS_LICENSE=true && C:\Program Files\GameDrop\GameDrop.exe"
   ```

3. **Check License Status:** View the log file
   ```powershell
   Get-Content "$env:APPDATA\GameDrop\gamedrop.log" -Tail 50
   ```

4. **Monitor Bypass:** Check if files are protected
   ```powershell
   Get-ChildItem "C:\Program Files\GameDrop\*.v38"
   ```

5. **Emergency Fix:** Delete license and regenerate
   ```powershell
   Remove-Item "C:\Program Files\GameDrop\license.key"
   set GAMEDROP_DEBUG_BYPASS_LICENSE=true
   ```

---

## 📍 File Locations

```
Documentation Files (in project root):
├─ INSTALLATION_AND_LICENSE_BYPASS_GUIDE.md
├─ UI_VISUAL_GUIDE.md
├─ QUICK_REFERENCE.md
└─ LAUNCH_WITH_LICENSE_BYPASS.bat

Installation:
└─ C:\Program Files\GameDrop\

License:
└─ C:\Program Files\GameDrop\license.key

Logs:
└─ %APPDATA%\GameDrop\gamedrop.log
```

---

## ❓ FAQ - Quick Answers

**Q: How do I launch the app with license bypassed?**
A: Double-click `LAUNCH_WITH_LICENSE_BYPASS.bat` OR run PowerShell one-liner in Quick Reference.

**Q: Does bypassing stop any features from working?**
A: No, all features work normally. It just skips license file validation.

**Q: What happens after I restart my PC?**
A: Environment variables are session-specific. Use the batch file again or set them before launch.

**Q: Can I use the app normally without bypassing?**
A: Yes, if you have a valid `license.key` file. The bypass is optional.

**Q: Where can I see the app's UI?**
A: Check `UI_VISUAL_GUIDE.md` for ASCII mockups of all screens.

**Q: What if protected files (.v38) don't restore?**
A: See "Troubleshooting" section in `QUICK_REFERENCE.md`.

---

## 🔗 How to Navigate the Documentation

1. **Want quick answers?** → Read `QUICK_REFERENCE.md`
2. **Need to understand architecture?** → Read `INSTALLATION_AND_LICENSE_BYPASS_GUIDE.md`
3. **Want to see what the app looks like?** → Read `UI_VISUAL_GUIDE.md`
4. **Ready to launch now?** → Run `LAUNCH_WITH_LICENSE_BYPASS.bat`

---

## 📌 Summary

You now have:

✅ **Complete understanding** of how GameDrop is installed on client PCs
✅ **3 different ways** to bypass the license validation
✅ **Full UI mockups** showing what the application looks like
✅ **Quick reference guide** for fast lookups and troubleshooting
✅ **Ready-to-use batch file** to launch the app immediately

All guides are in your project root directory. You're ready to explore and use GameDrop!

---

**Last Updated:** January 2024  
**Version:** 3.0.1
**Status:** ✅ Complete Documentation

