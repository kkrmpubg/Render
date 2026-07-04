# GameDrop Professional Installer Guide

## 📦 Overview

The GameDrop installer is a professional-grade application installation system that includes:

✅ **Firebase License Validation** - Online license checking against Firebase Firestore  
✅ **Anti-Tamper Protection** - File integrity verification with SHA256 checksums  
✅ **Encrypted Credentials** - Firebase credentials encrypted at rest  
✅ **Registry Protection** - Secure registry entries for license tracking  
✅ **System Verification** - Validates Windows version, disk space, admin rights  
✅ **Automatic Updates** - Steam monitor for continuous license validation  

---

## 🏗️ Installer Components

### 1. **Enhanced Inno Setup Script** (`installer_enhanced.iss`)

Professional Inno Setup configuration with:

```ini
Features:
├─ LZMA2 compression (smallest file size)
├─ Modern UI with custom branding
├─ Admin privileges requirement
├─ Automatic application closure
├─ Anti-tamper file verification
├─ Custom registry entries
└─ Pre/post-installation checks
```

**Registry Entries Created:**
```
HKEY_LOCAL_MACHINE
├─ Software\GameDrop\
│  ├─ InstallPath: [Installation directory]
│  ├─ Version: 3.0.1
│  ├─ Publisher: GameDrop
│  └─ LastInstalled: [Timestamp]
│
└─ Software\GameDrop\Security\
   ├─ AntiTamperEnabled: 1
   ├─ InstallerVersion: 3.0.1
   └─ InstallHash: [SHA256 hash]
```

### 2. **Build System** (`build_installer.py`)

Python script that:

```python
1. Verifies all required files exist
   ├─ GameDrop.exe (Launcher)
   ├─ GameDrop_Original.exe (Main app)
   ├─ steam_api64.dll (API wrapper)
   └─ [Other critical files]

2. Generates checksums for all files
   ├─ SHA256 hashes calculated
   ├─ Build manifest created
   └─ Security config generated

3. Verifies Firebase setup
   ├─ Credentials file present
   ├─ Encrypted module available
   └─ Configuration validated

4. Creates security artifacts
   ├─ build_manifest.json (file verification)
   ├─ security_config.json (security settings)
   ├─ verify_installation.py (runtime verification)
   └─ README_INSTALLATION.txt (user guide)

5. Compiles Inno Setup installer
   ├─ Invokes ISCC.exe (Inno Setup compiler)
   ├─ Creates final .exe file
   └─ Outputs to /output directory
```

---

## 🔒 Security Features

### Anti-Tamper Protection

**File Integrity Verification:**
```
Each file gets a SHA256 checksum:
├─ Stored in: build_manifest.json
├─ Verified during: Installation & Runtime
└─ Action on tampering: Blocks execution + alert

Example manifest entry:
{
  "GameDrop.exe": {
    "size": 45892000,
    "modified": "2024-06-28T14:23:15",
    "checksum_sha256": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6..."
  }
}
```

### Firebase License Validation

**During Installation:**
```
Launcher (gamedrop_launcher.py)
    ↓
1. Initialize Firebase connection
   └─ Load encrypted credentials
       └─ Decrypt with app key
2. Check license in Firestore database
   └─ Validate license format
   └─ Verify hardware ID matches
   └─ Check expiration date (Philippines Time)
3. Result: ✓ Valid / ✗ Invalid
   └─ Grant/Deny access
```

**Stored License File:**
```
Location: C:\Program Files\GameDrop\license.key
Format: Fernet-encrypted (symmetric encryption)
Key: SHA256(Windows Machine GUID)

Decrypted contents:
├─ LICENSE=XXXX-XXXX-XXXX-XXXX-...
├─ HWID=<Windows Machine GUID>
└─ ACTIVATED=<Timestamp>
```

### Encrypted Credentials

**Firebase Credentials Protection:**
```
Raw credentials:
  firebase-credentials.json (human-readable JSON)
        ↓ [Encryption]
  firebase_encrypted.py (encrypted Python module)
        ↓ [Installation]
  Embedded in .exe files during build
        ↓ [Runtime]
  Decrypted in memory only when needed
```

### System Integrity Checks

**Pre-Installation Validation:**
```
✓ Admin rights verification
✓ Windows 7 SP1 or later
✓ 1 GB minimum free disk space
✓ Valid installation directory
✓ Safe directory path (not system folders)
✓ No conflicting installations
```

**Post-Installation Verification:**
```
✓ All files present
✓ File checksums match manifest
✓ Registry entries created
✓ License validation passed
✓ File protection enabled
```

---

## 🚀 Building the Installer

### Prerequisites

1. **Inno Setup 6** (or later)
   - Download: https://jrsoftware.org/isdl.php
   - Install to default location

2. **Python 3.8+** (for build script)
   ```bash
   python --version
   ```

3. **Build files in `/dist` directory:**
   ```
   dist/
   ├─ GameDrop.exe
   ├─ GameDrop_Original.exe
   ├─ steam_api64.dll
   ├─ voices38.dlc
   ├─ firebase_encrypted.py
   ├─ firebase-credentials.json
   ├─ steam_monitor.exe
   ├─ logo.png
   ├─ logo.ico
   ├─ cleanup_gamedrop.exe
   ├─ close.bat
   └─ open.bat
   ```

### Build Steps

**Step 1: Prepare build files**
```batch
:: Copy all built executables and resources to /dist
cd "project_root"
mkdir dist
copy "build\GameDrop.exe" dist\
copy "build\GameDrop_Original.exe" dist\
:: ... copy other files
```

**Step 2: Run build script**
```batch
python build_installer.py
```

**Output:**
```
[14:23:15] [SUCCESS] Build completed successfully!
[14:23:15] [INFO] Output directory: output/
[14:23:15] [INFO] Files ready for distribution:
  - GameDrop_Setup_v3.0.1.exe (45 MB)
  - build_manifest.json
  - security_config.json
  - verify_installation.py
  - README_INSTALLATION.txt
```

**Step 3: Sign installer (optional)**
```batch
:: For code signing (requires certificate)
signtool.exe sign /f certificate.pfx /p password /t http://timestamp.server.com "output\GameDrop_Setup_v3.0.1.exe"
```

---

## 📋 Installer Installation Flow

```
User downloads: GameDrop_Setup_v3.0.1.exe
        ↓
User runs installer (as Admin)
        ↓
[Installer Wizard Page 1: Welcome]
├─ Display app name, version, description
├─ Mention security features
└─ System requirement check
        ↓
[Installer Wizard Page 2: Select Installation Directory]
├─ Default: C:\Program Files\GameDrop
├─ Verify disk space available
└─ Warn if unsafe directory
        ↓
[Installer Wizard Page 3: Select Tasks]
├─ Create desktop shortcut
└─ Create Start Menu shortcut
        ↓
[Installer Wizard Page 4: Ready]
├─ Show installation summary
├─ Display security features
└─ Confirm anti-tamper protection
        ↓
[Installation Process]
├─ Extract files
├─ Verify checksums
├─ Set registry entries
├─ Create shortcuts
└─ Run post-installation
        ↓
[Post-Installation]
├─ Create registry entries for license tracking
├─ Install Steam monitor task
├─ Enable file protection
└─ Launch application
        ↓
[Application Launch]
├─ Check launcher authorization
├─ Validate Firebase license
├─ Verify file integrity
└─ Show GameDrop UI
```

---

## 🔍 File Verification

### Automatic Verification

During installation, the installer:
1. Checks each file before extraction
2. Verifies checksums after extraction
3. Blocks installation if tampering detected

### Manual Verification

Users can verify installation integrity:

**Windows Command:**
```batch
cd "C:\Program Files\GameDrop"
python ..\verify_installation.py
```

**Output:**
```
[*] Verifying GameDrop v3.0.1 Installation Integrity
============================================================
✓ OK: GameDrop.exe
✓ OK: GameDrop_Original.exe
✓ OK: steam_api64.dll
✓ OK: firebase_encrypted.py
✗ MODIFIED: some_file.dll
  Expected: a1b2c3d4e5f6...
  Got:      f6e5d4c3b2a1...
============================================================

⚠ WARNING: Tampering detected! Files may have been modified.
Reinstall GameDrop from official sources.
```

---

## 📊 Build Manifest Structure

**File:** `build_manifest.json`

```json
{
  "app_name": "GameDrop",
  "version": "3.0.0",
  "build_date": "2024-06-28T14:23:15.123456",
  "files": {
    "GameDrop.exe": {
      "size": 45892000,
      "modified": "2024-06-28T14:20:00",
      "checksum_sha256": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6..."
    },
    "GameDrop_Original.exe": {
      "size": 52341000,
      "modified": "2024-06-28T14:20:00",
      "checksum_sha256": "b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7..."
    }
  },
  "checksums": {
    "GameDrop.exe": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6...",
    "GameDrop_Original.exe": "b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7..."
  },
  "security": {
    "firebase_enabled": true,
    "anti_tamper_enabled": true,
    "code_signed": false
  }
}
```

---

## ⚙️ Security Configuration

**File:** `security_config.json`

```json
{
  "version": "3.0.0",
  "timestamp": "2024-06-28T14:23:15.123456",
  "security_features": {
    "firebase_license_check": true,
    "file_integrity_verification": true,
    "anti_tamper_protection": true,
    "encrypted_credentials": true,
    "registry_protection": true
  },
  "minimum_requirements": {
    "os": "Windows 7 SP1",
    "disk_space_mb": 1024,
    "admin_rights": true
  }
}
```

---

## 🛠️ Troubleshooting

### Installation Fails: "Required file missing"
```
Solution:
1. Ensure all files are in /dist directory
2. Run: build_installer.py verify
3. Check file permissions
```

### Installation Fails: "Inno Setup not found"
```
Solution:
1. Install Inno Setup 6: https://jrsoftware.org/isdl.php
2. Install to default location: C:\Program Files (x86)\Inno Setup 6\
3. Restart build script
```

### Firebase License Check Fails
```
Solution:
1. Check internet connection
2. Verify firebase-credentials.json is valid
3. Ensure Firebase Firestore database is accessible
4. Check license expiration date (Philippines Time)
```

### File Tampering Detected
```
Solution:
1. Run verify_installation.py to identify changed files
2. Uninstall GameDrop
3. Reinstall from official source
4. Do NOT modify files in installation directory
```

---

## 📝 Distribution Checklist

Before distributing the installer:

- [ ] All required files present in `/dist`
- [ ] Build script runs successfully
- [ ] Installer file created: `GameDrop_Setup_v3.0.1.exe`
- [ ] Checksum verification script works
- [ ] Firebase credentials properly encrypted
- [ ] Registry entries correctly configured
- [ ] Anti-tamper protection enabled
- [ ] File integrity checksums validated
- [ ] Installer signed (if required)
- [ ] README_INSTALLATION.txt included
- [ ] Test installation on clean system
- [ ] Test license validation works
- [ ] Test uninstallation completes cleanly

---

## 🔐 Security Checklist for Users

**After Installation, Users Should:**

- [ ] Verify no unauthorized modifications: `verify_installation.py`
- [ ] Check license status in GameDrop settings
- [ ] Ensure Steam is working correctly
- [ ] Keep Windows updated
- [ ] Scan system with antivirus
- [ ] Don't modify files in installation directory
- [ ] Keep license credentials private
- [ ] Report any suspicious behavior to support

---

## 📊 Performance & File Sizes

**Typical Sizes:**
```
GameDrop_Setup_v3.0.1.exe:    ~45-50 MB (compressed)
build_manifest.json:           ~5-10 KB
security_config.json:          ~2-5 KB
verify_installation.py:        ~8-12 KB

After Installation:
C:\Program Files\GameDrop\:    ~200-300 MB
C:\ProgramData\GameDrop\:      ~50-100 MB
```

**Installation Time:**
```
System Check:         5 seconds
File Extraction:      15-30 seconds
Firebase Validation:  10-20 seconds
Total:               30-60 seconds
```

---

## 🎯 Next Steps

1. **Prepare Build Files**
   ```bash
   mkdir dist
   # Copy all compiled executables to dist/
   ```

2. **Run Build Script**
   ```bash
   python build_installer.py
   ```

3. **Test Installation**
   - Run installer on clean Windows system
   - Verify all features work
   - Check file integrity
   - Test license validation

4. **Sign & Distribute**
   - Sign installer with code certificate (optional)
   - Upload to distribution server
   - Create download page
   - Publish release notes

5. **Monitor & Support**
   - Track installation success metrics
   - Monitor Firebase license validation
   - Support user issues
   - Plan updates

---

## 📞 Support & References

- **Inno Setup Documentation:** https://jrsoftware.org/isinfo.php
- **Firebase Documentation:** https://firebase.google.com/docs
- **Windows Registry Reference:** https://docs.microsoft.com/en-us/windows/win32/sysinfo/registry

