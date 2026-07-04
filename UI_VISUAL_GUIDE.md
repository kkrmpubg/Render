# GameDrop UI - Visual Guide & Mockup

## 📱 Application Window Layout

### Main Home Screen (Step 1)

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              🎮 GameDrop Steam v3.0.1                           ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  Status: Ready ✓                                                ║
║                                                                  ║
║  Steam Path: C:\Program Files (x86)\Steam                      ║
║  Engine Ready: Yes ✓                                            ║
║  License: Active ✓                                              ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║                   ┌─────────────┐  ┌─────────────┐             ║
║                   │  Add Game   │  │   Add Game  │             ║
║                   │ (Regular)   │  │  (Denuvo)   │             ║
║                   │   📁        │  │    🛡️      │             ║
║                   └─────────────┘  └─────────────┘             ║
║                                                                  ║
║                   ┌─────────────┐  ┌─────────────┐             ║
║                   │ Downloads   │  │ Settings    │             ║
║                   │   📥        │  │    ⚙️      │             ║
║                   └─────────────┘  └─────────────┘             ║
║                                                                  ║
║                   ┌─────────────┐  ┌─────────────┐             ║
║                   │ My Library  │  │   About     │             ║
║                   │   📚        │  │    ℹ️      │             ║
║                   └─────────────┘  └─────────────┘             ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🎮 Add Game Flow - Step 2: Choose Game Type

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║            Step 2: What type of game do you want to add?        ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  Select your game type:                                         ║
║                                                                  ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  Regular Game                                              │ ║
║  │  ───────────────────────────────────────────────────      │ ║
║  │  • Non-DRM Steam game                                      │ ║
║  │  • No anti-cheat protection                               │ ║
║  │  • Standard library integration                           │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  Denuvo Game (with Bypass)                                 │ ║
║  │  ───────────────────────────────────────────────────────  │ ║
║  │  • Game with Denuvo/DRM protection                         │ ║
║  │  • Requires bypass engine (OpenSteam/OnlineFix)           │ ║
║  │  • Advanced configuration available                       │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║         [ Back ]                               [ Continue ] ► │ ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🎯 Add Game Flow - Step 3: Select from Steam Library

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              Step 3: Choose a game from your library             ║
║                                                                  ║
║  Search: [_______________________] 🔍                           ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          ║
║  │              │  │              │  │              │          ║
║  │   Elden      │  │   Baldur's   │  │   Starfield  │          ║
║  │   Ring       │  │   Gate 3     │  │              │          ║
║  │              │  │              │  │              │          ║
║  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │          ║
║  │ │ [Image]  │ │  │ │ [Image]  │ │  │ │ [Image]  │ │          ║
║  │ │ 760x320  │ │  │ │ 760x320  │ │  │ │ 760x320  │ │          ║
║  │ │          │ │  │ │          │ │  │ │          │ │          ║
║  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │          ║
║  │              │  │              │  │              │          ║
║  │ AppID: 570   │  │ AppID: 1238  │  │ AppID: 1161  │          ║
║  │ Status: ✓    │  │ Status: ✓    │  │ Status: ✓    │          ║
║  │ [SELECT]     │  │ [SELECT]     │  │ [SELECT]     │          ║
║  │              │  │              │  │              │          ║
║  └──────────────┘  └──────────────┘  └──────────────┘          ║
║                                                                  ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          ║
║  │    Cyberpunk │  │   Hogwarts   │  │   Palworld   │          ║
║  │    2077      │  │   Legacy     │  │              │          ║
║  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │          ║
║  │ │ [Image]  │ │  │ │ [Image]  │ │  │ │ [Image]  │ │          ║
║  │ │ 760x320  │ │  │ │ 760x320  │ │  │ │ 760x320  │ │          ║
║  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │          ║
║  │ AppID: 1091  │  │ AppID: 9940  │  │ AppID: 2394  │          ║
║  │ [SELECT]     │  │ [SELECT]     │  │ [SELECT]     │          ║
║  └──────────────┘  └──────────────┘  └──────────────┘          ║
║                                                                  ║
║  [◄ Back]                        [More Games ►] [Next ►]       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## ⚙️ Add Game Flow - Step 4: Configuration

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║           Step 4: Configure Game Settings                       ║
║           Game: Elden Ring (AppID: 570)                         ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  Game Information:                                              ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │ Game Title:    Elden Ring                                  │ ║
║  │ Developer:     FromSoftware                                │ ║
║  │ Steam AppID:   570                                         │ ║
║  │ Size:          60.5 GB                                     │ ║
║  │ Release Date:  February 25, 2022                           │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  Installation & Launch:                                         ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │ Installation Path:                                         │ ║
║  │ [C:\Program Files (x86)\Steam\steamapps\common\ELDEN...] │ ║
║  │                               [ Browse... ]                │ ║
║  │                                                            │ ║
║  │ Launch Options:                                            │ ║
║  │ [-high -nointro -nod3d11] (Advanced)                       │ ║
║  │                                                            │ ║
║  │ Working Directory: [Auto-detect] ✓                        │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  Protection & Bypass Settings:                                 ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │ ☑ Enable file protection                                  │ ║
║  │ ☑ Protect against DRM enforcement                         │ ║
║  │ ☑ Auto-unlock on license validation                       │ ║
║  │ ☑ Monitor for online updates                              │ ║
║  │                                                            │ ║
║  │ Bypass Type: OnlineFix [Verified ✓]                       │ ║
║  │                                                            │ ║
║  │ Engine: OpenSteam v2.5 [Ready]                            │ ║
║  │ Status: Compatible ✓                                      │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  [ ◄ Back ]                          [ Add to Library ] [✓ Done] ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 📚 Game Library View

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║                     🎮 My Game Library                          ║
║                                                                  ║
║  Sort by: [Title ▼] | Filter: [All Games ▼] | Search: [__] 🔍 ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          ║
║  │  Elden Ring  │  │  Baldur's    │  │  Cyberpunk   │          ║
║  │              │  │  Gate 3      │  │  2077        │          ║
║  │┌──────────┐  │  │┌──────────┐  │  │┌──────────┐  │          ║
║  ││ [Game]   │  │  ││ [Game]   │  │  ││ [Game]   │  │          ║
║  ││ Artwork  │  │  ││ Artwork  │  │  ││ Artwork  │  │          ║
║  ││ (760x320)│  │  ││ (760x320)│  │  ││ (760x320)│  │          ║
║  │└──────────┘  │  │└──────────┘  │  │└──────────┘  │          ║
║  │              │  │              │  │              │          ║
║  │Status: Active│  │Status: Trial │  │Status: Active│          ║
║  │Hours: 120.5  │  │Hours: 8.2    │  │Hours: 45.7   │          ║
║  │              │  │              │  │              │          ║
║  │[▶ Launch]    │  │[▶ Launch]    │  │[▶ Launch]    │          ║
║  │[⚙ Config]    │  │[⚙ Config]    │  │[⚙ Config]    │          ║
║  │[✕ Remove]    │  │[✕ Remove]    │  │[✕ Remove]    │          ║
║  │              │  │              │  │              │          ║
║  └──────────────┘  └──────────────┘  └──────────────┘          ║
║                                                                  ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          ║
║  │  Starfield   │  │  Palworld    │  │  Hogwarts    │          ║
║  │              │  │              │  │  Legacy      │          ║
║  │┌──────────┐  │  │┌──────────┐  │  │┌──────────┐  │          ║
║  ││ [Game]   │  │  ││ [Game]   │  │  ││ [Game]   │  │          ║
║  ││ Artwork  │  │  ││ Artwork  │  │  ││ Artwork  │  │          ║
║  ││ (760x320)│  │  ││ (760x320)│  │  ││ (760x320)│  │          ║
║  │└──────────┘  │  │└──────────┘  │  │└──────────┘  │          ║
║  │              │  │              │  │              │          ║
║  │Status: New   │  │Status: Active│  │Status: Trial │          ║
║  │Hours: 0.0    │  │Hours: 123.4  │  │Hours: 2.1    │          ║
║  │              │  │              │  │              │          ║
║  │[▶ Launch]    │  │[▶ Launch]    │  │[▶ Launch]    │          ║
║  │[⚙ Config]    │  │[⚙ Config]    │  │[⚙ Config]    │          ║
║  │[✕ Remove]    │  │[✕ Remove]    │  │[✕ Remove]    │          ║
║  │              │  │              │  │              │          ║
║  └──────────────┘  └──────────────┘  └──────────────┘          ║
║                                                                  ║
║  [+ Add Game ►]                            [Settings] [About] ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🛡️ Denuvo Bypass Games Browser

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     Available Games with Denuvo Bypass Support                 ║
║                                                                  ║
║  Search: [____________________________] 🔍                      ║
║  Filter: [All Bypasses ▼] [All Status ▼]                      ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │        [Large Game Cover Art - 760x320]                   │ ║
║  │                  Elden Ring                                │ ║
║  │                                                            │ ║
║  │  AppID: 570                                                │ ║
║  │  Bypass: OnlineFix v8.3                                   │ ║
║  │  Status: ✓ Verified Working                               │ ║
║  │  Compatibility: ★★★★★ (5/5)                              │ ║
║  │                                                            │ ║
║  │  [Select] [More Info] [Download Bypass]                  │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │        [Large Game Cover Art - 760x320]                   │ ║
║  │                Baldur's Gate 3                             │ ║
║  │                                                            │ ║
║  │  AppID: 1238                                               │ ║
║  │  Bypass: Steamless v11.2 / OnlineFix                      │ ║
║  │  Status: ✓ Verified Working                               │ ║
║  │  Compatibility: ★★★★★ (5/5)                              │ ║
║  │                                                            │ ║
║  │  [Select] [More Info] [Download Bypass]                  │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌────────────────────────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │        [Large Game Cover Art - 760x320]                   │ ║
║  │              Cyberpunk 2077                                │ ║
║  │                                                            │ ║
║  │  AppID: 1091                                               │ ║
║  │  Bypass: OnlineFix v8.1                                   │ ║
║  │  Status: ? Partially Compatible                           │ ║
║  │  Compatibility: ★★★☆☆ (3/5)                              │ ║
║  │                                                            │ ║
║  │  [Select] [More Info] [Download Bypass]                  │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  [◄ More Games ►]                                  [Prev] [Next] ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## ⚙️ Settings Panel

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║                    ⚙️  Settings & Configuration                 ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  ┌─ STEAM INTEGRATION ─────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  Steam Installation Path:                                  │ ║
║  │  [C:\Program Files (x86)\Steam]  [ Browse ]               │ ║
║  │  Status: ✓ Found and accessible                           │ ║
║  │                                                            │ ║
║  │  Auto-Detect Steam Path:  [ ON / OFF Toggle ]             │ ║
║  │  Steam API Integration:   [ ON / OFF Toggle ]             │ ║
║  │  Monitor Steam Updates:   [ ON / OFF Toggle ]             │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌─ FILE PROTECTION ──────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  ☑ Enable File Protection                                 │ ║
║  │    ├─ Protects game files from unauthorized access        │ ║
║  │    └─ Requires valid license                              │ ║
║  │                                                            │ ║
║  │  ☑ Auto-Unlock Protected Files                            │ ║
║  │    └─ Automatically enables protected files on launch     │ ║
║  │                                                            │ ║
║  │  Protection Level: [Standard ▼]                           │ ║
║  │  ├─ Low: Basic obfuscation                                │ ║
║  │  ├─ Standard: Encryption (default)                        │ ║
║  │  └─ High: Full encryption + monitoring                    │ ║
║  │                                                            │ ║
║  │  Protected Files Count: 47                                │ ║
║  │  Last Protected: 2024-01-15 14:23:05                      │ ║
║  │                                                            │ ║
║  │  [ Refresh Protected Files ] [ Clear Protection ]         │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌─ UPDATES & LICENSING ──────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  Application Version: 3.0.1                                │ ║
║  │  Latest Version: 3.0.2                                     │ ║
║  │  Status: Update Available ⚠️                               │ ║
║  │  [ Check for Updates ] [ Update Now ]                     │ ║
║  │                                                            │ ║
║  │  Auto-Update on Launch: [ ON / OFF ]                      │ ║
║  │  Notify for Major Updates: [ ON / OFF ]                   │ ║
║  │                                                            │ ║
║  │  Current License: ACTIVE ✓                                │ ║
║  │  License Activated: 2024-01-10                            │ ║
║  │  Hardware ID: [XXXX-XXXX-XXXX-XXXX-XXXX]                 │ ║
║  │                                                            │ ║
║  │  [ View License Details ] [ Reactivate License ]          │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  ┌─ ABOUT GAMEDROP ──────────────────────────────────────────┐ ║
║  │                                                            │ ║
║  │  GameDrop Steam v3.0.1                                     │ ║
║  │  Advanced Game Management & Library Integration            │ ║
║  │                                                            │ ║
║  │  © 2024 GameDrop. All rights reserved.                    │ ║
║  │                                                            │ ║
║  │  [ Support ] [ Documentation ] [ Report Bug ]             │ ║
║  │                                                            │ ║
║  └────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║                              [ Save ] [ Close ]                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🎯 Launch & Monitoring Screen

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              Launching: Elden Ring                              ║
║              Status: Initializing bypass engine...              ║
║                                                                  ║
╟──────────────────────────────────────────────────────────────────╢
║                                                                  ║
║  Process Status:                                                ║
║  ✓ License Validated                                           ║
║  ✓ Protected Files Enabled                                     ║
║  ✓ Steam API Initialized                                       ║
║  ✓ Bypass Engine Ready (OnlineFix v8.3)                        ║
║  ⟳ Launching Game...                                           ║
║                                                                  ║
║  Progress:                                                      ║
║  ┌────────────────────────────────────────┐                    ║
║  │████████████░░░░░░░░░░░░░░░░░░░░░░░░│ 65%                   ║
║  └────────────────────────────────────────┘                    ║
║                                                                  ║
║  Event Log:                                                     ║
║  [14:23:15] Initializing DirectX...                            ║
║  [14:23:16] Loading Steam overlay...                           ║
║  [14:23:17] Setting up bypass hooks...                         ║
║  [14:23:18] Launching game executable...                       ║
║  [14:23:19] Game loaded successfully ✓                         ║
║                                                                  ║
║  [ Keep Running ] [ Minimize ] [ Exit ]                        ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 🔌 Backend API Calls (Internal)

```javascript
// Frontend communicates with Python backend via pywebview bridge:

// Initialize app state
api.get_initial_state()
→ { title, version, status, app_dir, steam_path, engine_ready }

// Get wizard flow state
api.get_wizard_state("add_game")
→ { step, flow, title, message }

// Get Steam library
api.get_steam_games()
→ [{ appid, title, path, hours, artwork_url, ... }]

// Get available bypasses
api.get_bypass_appids()
→ [{ appid, title, bypass_type, compatibility, ... }]

// Launch a game
api.launch_game(570, { bypass: "onlinefix", options: "-high" })
→ { success, pid, message }

// Validate license
api.validate_license()
→ { valid, hardware_id, expires, message }

// Save settings
api.save_settings({ steam_path, protection_level, auto_update })
→ { success, message }
```

---

## 📊 Color Scheme & Design

```
Primary Colors:
├─ Primary Action: #4CAF50 (Green)
├─ Success: #00BCD4 (Cyan)
├─ Warning: #FF9800 (Orange)
├─ Error: #F44336 (Red)
├─ Info: #2196F3 (Blue)
│
Text Colors:
├─ Primary Text: #212121 (Almost Black)
├─ Secondary Text: #757575 (Gray)
├─ Disabled Text: #BDBDBD (Light Gray)
│
Background:
├─ Main Background: #FAFAFA (Off-White)
├─ Card Background: #FFFFFF (White)
├─ Dark Mode: #212121
│
Fonts:
└─ UI Font: Segoe UI, 10-14pt
   └─ Monospace: Courier New, 11pt (for codes)
```

---

## 🎨 Component Hierarchy

```
Root Window (pywebview)
│
├─ Header
│  ├─ Logo/Title
│  ├─ Version Badge
│  └─ Status Indicator
│
├─ Main Content Area
│  ├─ Home Screen (Step 1)
│  ├─ Wizard Flows (Step 2-4)
│  ├─ Game Library (Browse)
│  ├─ Settings Panel
│  └─ Download Manager
│
├─ Navigation
│  ├─ Primary Menu
│  ├─ Breadcrumb Trail
│  └─ Action Buttons
│
└─ Footer
   ├─ Status Bar
   ├─ Quick Links
   └─ Version/Support
```

