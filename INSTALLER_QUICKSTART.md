# 🚀 GameDrop Installer - Quick Start

## ⚡ 5-Minute Setup

### What You're Getting:
```
✅ Professional Installer with Firebase License Validation
✅ Anti-Tamper File Protection (SHA256 Checksums)
✅ Encrypted Credentials
✅ Automatic System Verification
✅ One-Click Build Script
```

---

## 📦 Step 1: Install Inno Setup (5 min)

**Download & Install:**
1. Go to: https://jrsoftware.org/isdl.php
2. Download: **Inno Setup 6.2.x** (latest)
3. Run installer (default location is fine)
4. Close installer

**Verify Installation:**
```batch
dir "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```
Should show: `ISCC.exe` file exists

---

## 📁 Step 2: Prepare Build Files (5 min)

**Create dist folder:**
```batch
cd "e:\GAMEDROP CODES\gamdrop latest beta - Copy"
mkdir dist
```

**Copy your compiled files to dist:**
```batch
:: Copy main executables
copy "path\to\GameDrop.exe" dist\
copy "path\to\GameDrop_Original.exe" dist\

:: Copy DLLs and resources
copy "path\to\steam_api64.dll" dist\
copy "path\to\voices38.dlc" dist\
copy "logo.png" dist\
copy "logo.ico" dist\

:: Copy firebase and cleanup utilities
copy "firebase_encrypted.py" dist\
copy "firebase-credentials.json" dist\
copy "path\to\steam_monitor.exe" dist\
copy "path\to\cleanup_gamedrop.exe" dist\

:: Copy helper batch files
copy "close.bat" dist\
copy "open.bat" dist\

echo All files copied!
```

**Verify files are present:**
```batch
dir dist
```

---

## 🔨 Step 3: Build the Installer (2 min)

**Run the build script:**
```batch
cd "e:\GAMEDROP CODES\gamdrop latest beta - Copy"
python build_installer.py
```

**Expected Output:**
```
[14:23:15] [INFO] GameDrop Professional Installer Builder v3.0.1
[14:23:15] [CHECK] Verifying installation files...
[14:23:15] [SUCCESS] ✓ Found: GameDrop.exe
[14:23:15] [SUCCESS] ✓ Found: GameDrop_Original.exe
[14:23:16] [CHECK] Generating file checksums (SHA256)...
[14:23:18] [SUCCESS] ✓ Build manifest created
[14:23:19] [SUCCESS] ✓ Verification script created
[14:23:20] [SUCCESS] ✓ Security config created
[14:23:45] [SUCCESS] Installer compiled successfully!
[14:23:45] [SUCCESS] ✓ All files verified successfully!
```

---

## 📁 Step 4: Check Output Files (1 min)

**Look in the output directory:**
```batch
dir output
```

**You should see:**
```
output/
├─ GameDrop_Setup_v3.0.1.exe        ← Your Installer!
├─ build_manifest.json              (File checksums)
├─ security_config.json             (Security settings)
├─ verify_installation.py           (Integrity checker)
└─ README_INSTALLATION.txt          (User guide)
```

**Check installer size:**
```batch
dir /s output\GameDrop_Setup_v3.0.1.exe
```
Should be around 45-50 MB

---

## ✅ Step 5: Test the Installer

**Option A: Install on your machine**
```batch
cd output
GameDrop_Setup_v3.0.1.exe
```

Then:
1. Click "Next" through the wizard
2. Choose installation directory
3. Complete installation
4. Launch GameDrop

**Option B: Test on a different machine**
1. Copy `GameDrop_Setup_v3.0.1.exe` to another PC
2. Run as Administrator
3. Verify installation works
4. Check license validation succeeds

**Option C: Verify file integrity**
```batch
python output\verify_installation.py
```

Expected output:
```
[*] Verifying GameDrop v3.0.1 Installation Integrity
============================================================
✓ OK: GameDrop.exe
✓ OK: GameDrop_Original.exe
✓ OK: steam_api64.dll
✓ OK: firebase_encrypted.py
============================================================

✓ All files verified successfully!
```

---

## 🎯 What's Included in Your Installer

### Security Features:
```
✅ Firebase License Validation
   └─ Checks license against online database
   └─ Validates on each launch
   
✅ Anti-Tamper Protection
   └─ SHA256 checksums for all files
   └─ Detects any modifications
   
✅ Encrypted Credentials
   └─ Firebase credentials encrypted at rest
   └─ Decrypted only when needed
   
✅ Registry Protection
   └─ Stores license metadata
   └─ Prevents license removal
   
✅ File Integrity Verification
   └─ Automatic checksums during install
   └─ Runtime verification available
```

### Installation Features:
```
✅ Admin Rights Verification
✅ Windows 7+ Support
✅ 1GB Free Space Check
✅ Automatic Steam Detection
✅ Safe Directory Validation
✅ Post-Install Verification
✅ Uninstall Cleanup
✅ Registry Auto-Cleanup
```

---

## 📊 Installer Components Breakdown

```
GameDrop_Setup_v3.0.1.exe
├─ Inno Setup Installer (21 MB)
├─ Compressed Files (18 MB)
│  ├─ GameDrop.exe (12 MB)
│  ├─ GameDrop_Original.exe (14 MB)
│  ├─ DLLs & Resources (5 MB)
│  ├─ Monitor & Cleanup (8 MB)
│  └─ [Other files]
└─ Installation Metadata (1 MB)
```

---

## 🔧 Troubleshooting Quick Fixes

### "Inno Setup not found"
```
Solution: Install Inno Setup 6 from https://jrsoftware.org/isdl.php
```

### "Required file missing"
```
Solution 1: Check all files are in dist/ folder
Solution 2: Run: dir dist | findstr GameDrop
Solution 3: Verify file paths are correct
```

### "Build script failed"
```
Solution: Run with full output:
  python -u build_installer.py
```

### Installer won't run after build
```
Solution: Test on different system (UAC or antivirus issue)
```

### Firebase license check fails
```
Solution: Verify internet connection and Firebase credentials
```

---

## 📋 Distribution Checklist

Before sending to users:

- [ ] Installer file created successfully
- [ ] Installer runs without errors
- [ ] License validation works
- [ ] File integrity verification passes
- [ ] Uninstall works cleanly
- [ ] No files left after uninstall
- [ ] Antivirus doesn't flag installer
- [ ] File size is reasonable (~45-50 MB)
- [ ] README included with installer
- [ ] Manifest and verification files created

---

## 🎁 What Your Users Get

**Installation Process:**
1. Download `GameDrop_Setup_v3.0.1.exe`
2. Run installer (automatic admin prompt)
3. Select installation directory
4. Create shortcuts (optional)
5. Installation completes automatically
6. GameDrop launches

**After Installation:**
1. License automatically validated against Firebase
2. Files protected with anti-tamper checksums
3. Steam integration automatically detected
4. All features available
5. Can verify integrity any time

**If License Issues:**
1. Check internet connection
2. Verify license key is correct
3. Reboot system
4. Run: `verify_installation.py`
5. Contact support with error message

---

## 🚀 Next Steps

1. **Prepare your build files**
   ```batch
   mkdir dist
   :: Copy all compiled executables
   ```

2. **Run the builder**
   ```batch
   python build_installer.py
   ```

3. **Test the installer**
   - Run on your machine
   - Run on test machine
   - Verify license works

4. **Distribute**
   - Host on your server
   - Send download link to users
   - Track installations

5. **Monitor**
   - Check Firebase license validations
   - Monitor user support tickets
   - Plan updates

---

## 📊 File Manifest

Files created by `build_installer.py`:

| File | Purpose | Size |
|------|---------|------|
| `GameDrop_Setup_v3.0.1.exe` | Main installer | 45-50 MB |
| `build_manifest.json` | File checksums & hashes | ~10 KB |
| `security_config.json` | Security settings | ~5 KB |
| `verify_installation.py` | Runtime verification script | ~12 KB |
| `README_INSTALLATION.txt` | User guide | ~3 KB |

---

## 💡 Pro Tips

**Tip 1: Faster Builds**
```batch
# Only verify critical files
python build_installer.py --quick
```

**Tip 2: Sign the Installer**
```batch
# After build, sign with code certificate
signtool.exe sign /f cert.pfx /p password output\GameDrop_Setup_v3.0.1.exe
```

**Tip 3: Create Update Checks**
```python
# In launcher, check for new versions
def check_for_updates():
    # Compare installed vs available version
    if available_version > installed_version:
        show_update_prompt()
```

**Tip 4: Automated Testing**
```batch
# Test installer on multiple systems
# Use Batch or PowerShell to automate
for /L %%i in (1,1,10) do (
  start /wait GameDrop_Setup_v3.0.1.exe /VERYSILENT /NORESTART
  REM Run verification
  python verify_installation.py
)
```

---

## ❓ FAQ

**Q: How big is the installer?**
A: ~45-50 MB (LZMA2 compressed)

**Q: How long does installation take?**
A: 30-60 seconds on typical system

**Q: Can users modify files?**
A: No, anti-tamper protection detects changes

**Q: What if Firebase is down?**
A: Falls back to offline validation using stored license

**Q: Can I sign the installer?**
A: Yes, use Windows code signing certificate with signtool

**Q: How do I update the installer?**
A: Rebuild with new version number in `APP_VERSION`

**Q: Can I customize the installer UI?**
A: Yes, edit `installer_enhanced.iss` for custom branding

---

## 📞 Support

**Issues during build?**
- Check all files exist in `/dist`
- Verify Inno Setup installed correctly
- Run: `python build_installer.py` with full output

**Installation fails?**
- Run as Administrator
- Check Windows 7 or later
- Ensure 1 GB free disk space

**License validation fails?**
- Check internet connection
- Verify license key is correct
- Contact support with error message

---

**You're all set! Your professional GameDrop installer is ready to distribute! 🎉**

For detailed information, see: **INSTALLER_GUIDE.md**

