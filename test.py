import os
import json
import requests
import shutil
import zipfile
import tarfile
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import subprocess
import sys
import ctypes
import tkinter.simpledialog
import re
from cryptography.fernet import Fernet
import PIL.Image
import PIL.ImageTk
from io import BytesIO
from security_core import verify_password
from denuvo_activation import (
    find_activation_executable,
    launch_activation_executable,
    load_denuvo_activation_code,
    normalize_denuvo_activation_code,
    redeem_denuvo_activation_code,
)
import threading
import time
import queue
import platform
import psutil
import win32com.client
import winreg
import hashlib
import uuid
from ctypes import windll, c_uint, Structure, c_void_p, POINTER, cast, byref, sizeof, c_bool, WinDLL, c_ulong, c_byte
import logging
from datetime import datetime
import base64
import tempfile

# Set up logging to AppData (user-writable location)
log_dir = os.path.join(os.environ.get('APPDATA', tempfile.gettempdir()), 'GameDrop')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'gamedrop.log')

try:
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,  # Show INFO and above for debugging
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',  # Custom date format
        filemode='a'
    )
except:
    # If logging fails, just disable it
    logging.basicConfig(level=logging.CRITICAL)

# Load required DLLs
kernel32 = WinDLL('kernel32', use_last_error=True)
ntdll = WinDLL('ntdll', use_last_error=True)

# Define Windows constants
PAGE_EXECUTE_READ = 0x20
MEM_COMMIT = 0x1000
HIGH_PRIORITY_CLASS = 0x80
DACL_SECURITY_INFORMATION = 0x4
WM_CLOSE = 0x0010

user32 = ctypes.windll.user32


def enum_windows():
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    windows = []

    def _proc(hwnd, lParam):
        windows.append(hwnd)
        return True

    EnumWindows(EnumWindowsProc(_proc), 0)
    return windows


def get_pid_for_window(hwnd):
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def send_wm_close(hwnd):
    return user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def close_steam_windows():
    steam_pids = {p.pid for p in psutil.process_iter(['name']) if p.info.get('name', '').lower() == 'steam.exe'}
    if not steam_pids:
        return False

    closed = False
    for hwnd in enum_windows():
        try:
            pid = get_pid_for_window(hwnd)
            if pid in steam_pids:
                send_wm_close(hwnd)
                closed = True
        except Exception:
            continue

    return closed

# Standalone function to restart Steam
def find_steam_batch(batch_name):
    """Find the Steam open/close batch file in common locations."""
    candidates = [
        BASE_DIR,
        os.path.join(BASE_DIR, 'dist'),
        os.getcwd(),
        os.path.join(os.getcwd(), 'dist'),
    ]
    for directory in candidates:
        batch_path = os.path.join(directory, batch_name)
        if os.path.exists(batch_path):
            return batch_path
    return None


def find_local_dist_file(filename):
    """Find a local dist file in common source or app locations."""
    candidates = [
        os.path.join(BASE_DIR, 'dist', filename),
        os.path.join(os.getcwd(), 'dist', filename),
        os.path.join(BASE_DIR, filename),
        os.path.join(os.getcwd(), filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def run_steam_batch(batch_name):
    """Run a Steam control batch file using cmd.exe when present."""
    batch_path = find_steam_batch(batch_name)
    if not batch_path:
        logging.error(f"Steam batch file not found: {batch_name}")
        return False
    try:
        subprocess.check_call(
            ["cmd.exe", "/c", "call", batch_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info(f"Ran Steam batch: {batch_name}")
        return True
    except Exception as e:
        logging.error(f"Steam batch {batch_name} execution failed: {e}")
        return False


def is_game_process_running():
    """Return True only when a process clearly appears to be a Steam game executable."""
    try:
        ignored_names = {
            'steam.exe', 'steamwebhelper.exe', 'steamservice.exe', 'gameoverlayui.exe',
            'steamerrorreporter.exe', 'steamclientbootstrapper.exe', 'explorer.exe',
            'conhost.exe', 'cmd.exe', 'python.exe', 'pythonw.exe', 'svchost.exe',
            'gamedrop.exe', 'gamedrop_original.exe', 'steam_monitor.exe', 'cleanup_gamedrop.exe'
        }
        ignored_keywords = (
            'gamedrop', 'steamtools', 'opensteamtool', 'steam_monitor', 'cleanup_gamedrop',
            'python', 'pycharm', 'code', 'vscode', 'notepad', 'winword', 'excel', 'powerpnt',
            'msedge', 'chrome', 'firefox', 'opera', 'brave', 'discord', 'teams', 'slack', 'spotify'
        )

        for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
            try:
                proc_name = (proc.info.get('name') or '').lower()
                if not proc_name or proc_name in ignored_names:
                    continue

                exe_path = (proc.info.get('exe') or '').lower()
                cmdline = ' '.join(proc.info.get('cmdline') or []).lower()
                combined = f"{proc_name} {exe_path} {cmdline}"

                if any(keyword in combined for keyword in ignored_keywords):
                    continue

                if 'steamapps\\common' in exe_path or 'steamapps/common' in exe_path:
                    return True
                if 'steamapps\\common' in cmdline or 'steamapps/common' in cmdline:
                    return True

                if proc_name.endswith('.exe'):
                    if '\\steamapps\\common\\' in exe_path or '/steamapps/common/' in exe_path:
                        return True
                    if proc_name.startswith('steam'):
                        continue
                    if 'steam' in combined:
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logging.debug(f"Could not inspect running processes: {e}")

    return False


def stop_steam_processes():
    """Stop Steam quickly, using a short grace period before force-killing any leftovers."""
    try:
        target_processes = ["steam.exe", "steamwebhelper.exe", "SteamService.exe"]
        for process_name in target_processes:
            subprocess.call(
                ["taskkill", "/IM", process_name],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        deadline = time.time() + 6
        while time.time() < deadline:
            remaining = [
                p for p in psutil.process_iter(['name'])
                if any((p.info.get('name') or '').lower() == name.lower() for name in target_processes)
            ]
            if not remaining:
                return True
            time.sleep(0.5)

        for process_name in target_processes:
            subprocess.call(
                ["taskkill", "/F", "/IM", process_name],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        time.sleep(1)
        return True
    except Exception as e:
        logging.error(f"Failed to stop Steam processes: {e}")
        return False


def wait_for_steam_exit(timeout=8, interval=0.5):
    """Wait briefly for Steam to close without blocking unnecessarily."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        steam_running = any(p.name().lower() == 'steam.exe' for p in psutil.process_iter())
        steam_helper_running = any(p.name().lower() == 'steamwebhelper.exe' for p in psutil.process_iter())
        if not steam_running and not steam_helper_running:
            return True
        time.sleep(interval)
    return False


def find_steam_executable():
    """Resolve the Steam executable path from PATH, the registry, or common install locations."""
    path_from_env = shutil.which('steam.exe')
    if path_from_env:
        return path_from_env

    candidates = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        if steam_path:
            cleaned_path = str(steam_path).strip().strip('"').rstrip('\\')
            cleaned_path = cleaned_path.replace('/', '\\')
            if cleaned_path:
                candidates.append(cleaned_path)
    except Exception:
        pass

    candidates.extend([
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"E:\Steam",
        r"F:\Steam",
    ])

    for path in candidates:
        steam_exe = os.path.join(path, 'steam.exe')
        if os.path.exists(steam_exe):
            return steam_exe
    return None


def find_steam_shortcut(steam_exe=None):
    """Locate a Steam shortcut that can be opened through the shell."""
    candidates = []
    if steam_exe:
        steam_dir = os.path.dirname(steam_exe)
        candidates.append(os.path.join(steam_dir, 'steam.lnk'))

    home = os.path.expanduser('~')
    candidates.extend([
        os.path.join(home, 'Desktop', 'Steam.lnk'),
        os.path.join(home, 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Steam.lnk'),
        os.path.join('C:', 'ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Steam.lnk'),
    ])

    for shortcut in candidates:
        if os.path.exists(shortcut):
            return shortcut
    return None


def shell_launch(target):
    """Launch a file or shortcut through the Windows shell, which is more reliable for Steam."""
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, 'open', target, None, None, 1)
        if int(result) > 32:
            return True
    except Exception as e:
        logging.warning(f'ShellExecuteW launch failed for {target}: {e}')

    try:
        os.startfile(target)
        return True
    except Exception as e:
        logging.warning(f'os.startfile launch failed for {target}: {e}')
    return False


def wait_for_steam_process(timeout=15, interval=1):
    """Wait until Steam is fully started and has a visible window before treating launch as successful."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            steam_running = any(p.name().lower() == 'steam.exe' for p in psutil.process_iter())
            steam_helper_running = any(p.name().lower() == 'steamwebhelper.exe' for p in psutil.process_iter())
            if not (steam_running or steam_helper_running):
                time.sleep(interval)
                continue

            visible_window = False
            for hwnd in enum_windows():
                try:
                    pid = get_pid_for_window(hwnd)
                    if pid and any(
                        p.pid == pid and (p.name().lower() == 'steam.exe' or p.name().lower() == 'steamwebhelper.exe')
                        for p in psutil.process_iter(['name', 'pid'])
                    ):
                        if ctypes.windll.user32.IsWindowVisible(hwnd):
                            visible_window = True
                            break
                except Exception:
                    continue

            if visible_window:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _steam_process_is_running():
    """Return True when Steam or Steam helper processes are currently running."""
    try:
        return any(
            (p.name().lower() == 'steam.exe' or p.name().lower() == 'steamwebhelper.exe')
            for p in psutil.process_iter(['name'])
        )
    except Exception:
        return False


def launch_steam_process():
    """Launch Steam using the direct executable or shortcut path only."""
    if wait_for_steam_process(timeout=2, interval=0.5):
        logging.info('Steam was already running before launch attempt')
        return True

    steam_exe = find_steam_executable()
    wallpaper_shortcut = find_steam_shortcut(steam_exe) if steam_exe else None

    if wallpaper_shortcut and shell_launch(wallpaper_shortcut):
        logging.info('Attempted Steam launch via shortcut')
        time.sleep(2)
        if wait_for_steam_process(timeout=15, interval=1) or _steam_process_is_running():
            logging.info('Steam process launched successfully via shortcut')
            return True

    if steam_exe and shell_launch(steam_exe):
        logging.info('Attempted Steam launch via executable path')
        time.sleep(2)
        if wait_for_steam_process(timeout=15, interval=1) or _steam_process_is_running():
            logging.info('Steam process launched successfully via executable path')
            return True

    logging.error('Failed to launch Steam executable or shortcut')
    return False


def restart_steam_process():
    """Close Steam and prompt the user to reopen it manually."""
    try:
        logging.info("Closing Steam; manual reopen required")

        stop_steam_processes()

        wait_seconds = 25
        interval = 2
        elapsed = 0
        while elapsed < wait_seconds:
            steam_running = any(p.name().lower() == 'steam.exe' for p in psutil.process_iter())
            steam_helper_running = any(p.name().lower() == 'steamwebhelper.exe' for p in psutil.process_iter())
            if not steam_running and not steam_helper_running:
                break
            time.sleep(interval)
            elapsed += interval

        if any(p.name().lower() == 'steam.exe' for p in psutil.process_iter()):
            logging.warning('Steam still running after shutdown attempt; closing was requested anyway')

        messagebox.showinfo(
            'Steam closed',
            'Steam has been closed.\n\nPlease open Steam manually when you are ready.'
        )
        return True

    except Exception as e:
        logging.error(f"Error closing Steam: {e}")
        return False

# Anti-Debug and Protection Measures
class MemoryProtection:
    def __init__(self):
        self._original_checksums = {}
        self._regions = []
        self._initialize_protection()
        
    def _initialize_protection(self):
        try:
            # Get current process handle
            process = kernel32.GetCurrentProcess()
            
            # Initialize memory regions to monitor
            self._regions = self._get_memory_regions()
            
            # Calculate initial checksums
            for region in self._regions:
                self._original_checksums[region] = self._calculate_region_checksum(region)
                
            # Set memory protection
            for region in self._regions:
                kernel32.VirtualProtectEx(
                    process,
                    region,
                    0x1000,  # Standard page size
                    PAGE_EXECUTE_READ,
                    ctypes.byref(c_ulong(0))
                )
        except Exception:
            pass

    def _get_memory_regions(self):
        regions = []
        try:
            process = kernel32.GetCurrentProcess()
            address = 0
            
            class MEMORY_BASIC_INFORMATION(Structure):
                _fields_ = [
                    ("BaseAddress", c_void_p),
                    ("AllocationBase", c_void_p),
                    ("AllocationProtect", c_ulong),
                    ("RegionSize", c_void_p),
                    ("State", c_ulong),
                    ("Protect", c_ulong),
                    ("Type", c_ulong)
                ]
            
            mbi = MEMORY_BASIC_INFORMATION()
            while kernel32.VirtualQueryEx(
                process,
                address,
                byref(mbi),
                sizeof(mbi)
            ):
                if mbi.State == MEM_COMMIT:
                    regions.append(address)
                address = mbi.BaseAddress + mbi.RegionSize
        except Exception:
            pass
        return regions

    def _calculate_region_checksum(self, address):
        try:
            process = kernel32.GetCurrentProcess()
            buffer = (c_byte * 0x1000)()
            bytes_read = c_ulong(0)
            if kernel32.ReadProcessMemory(
                process, 
                address,
                buffer,
                0x1000,
                byref(bytes_read)
            ):
                return hashlib.sha256(bytes(buffer[0:bytes_read.value])).hexdigest()
            return None
        except Exception:
            return None

    def verify_integrity(self):
        try:
            for region in self._regions:
                current = self._calculate_region_checksum(region)
                if current != self._original_checksums.get(region):
                    return False
            return True
        except Exception:
            return False

# Update string handling to work in compiled mode
_STRINGS = {
    'save_dir': 'downloads',
    'config_file': 'config.json',
}


def _get_github_token():
    token = (os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or '').strip()
    return token or None


try:
    SAVE_DIR = _STRINGS['save_dir']
    CONFIG_FILE = _STRINGS['config_file']
    GITHUB_TOKEN = _get_github_token()
except Exception as e:
    logging.error(f"String initialization error: {str(e)}")
    SAVE_DIR = 'downloads'
    CONFIG_FILE = 'config.json'
    GITHUB_TOKEN = _get_github_token()

# Get absolute path for downloads folder relative to executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Make SAVE_DIR absolute
SAVE_DIR = os.path.join(BASE_DIR, SAVE_DIR)

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "GameDrop-Steam/1.0"
} if GITHUB_TOKEN else {}

# Modify security checks for compiled mode
def verify_environment():
    """Verify the runtime environment."""
    try:
        # Basic environment checks that work in compiled mode
        if os.environ.get('COMPUTERNAME', '').lower().startswith(('ec2', 'azure', 'aws')):
            return False
            
        # Check for common VM indicators
        vm_services = ['vmtoolsd', 'vboxservice', 'parallels']
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'].lower() in vm_services:
                    return False
            except:
                continue
                
        # Check for debugger
        if ctypes.windll.kernel32.IsDebuggerPresent():
            return False
            
        return True
    except Exception as e:
        logging.error(f"Environment verification error: {str(e)}")
        return True  # Allow running if checks fail

# Initialize security
try:
    if not verify_environment():
        logging.warning("Security check failed - running in limited mode")
except Exception as e:
    logging.error(f"Security check error: {str(e)}")

if os.name == "nt":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(u"GameDropSteam.AppID")

# String encryption
def _decrypt_string(s):
    try:
        key = bytes([
            ((i * 7 + 13) ^ 0xAA) & 0xFF for i in range(32)
        ])
        f = Fernet(key)
        return f.decrypt(s.encode()).decode()
    except:
        # Silently use fallback values without logging
        if 'save_dir' in s:
            return 'downloads'
        elif 'config_file' in s:
            return 'config.json'
        elif 'github_token' in s:
            return ''
        return s

# Encrypted strings
_STRINGS = {
    'save_dir': 'gAAAAABk7X9zJ2Q3v4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3',
    'config_file': 'gAAAAABk7X9zK2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2',
}

try:
    SAVE_DIR = _decrypt_string(_STRINGS['save_dir'])
    CONFIG_FILE = _decrypt_string(_STRINGS['config_file'])
    GITHUB_TOKEN = _get_github_token()
except Exception:
    # Silently use fallback values without logging
    SAVE_DIR = 'downloads'
    CONFIG_FILE = 'config.json'
    GITHUB_TOKEN = _get_github_token()

# Update token format
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",  # Changed back to "token" format
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "GameDrop-Steam/1.0"
} if GITHUB_TOKEN else {}

FERNET_KEY = b'3xR6WqcVeow4HVXBnK9-Jy9DboH-vqk8DX5w_tAV6Rk='
fernet = Fernet(FERNET_KEY)

class GameSuggestionDropdown(ttk.Frame):
    def __init__(self, parent, entry_widget, **kwargs):
        super().__init__(parent, **kwargs)
        self.entry_widget = entry_widget
        self.popup = None
        self.listbox = None
        self.game_data = {}
        self.image_cache = {}
        self.search_after_id = None
        self.current_search = None
        self.selected_game_frame = None
        self.search_queue = queue.Queue()
        self.image_queue = queue.Queue()
        self.last_search_time = 0
        self.search_results_cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Create image loading threads pool
        self.image_threads = []
        for _ in range(3):  # Create 3 image loading threads
            thread = threading.Thread(target=self.image_worker, daemon=True)
            thread.start()
            self.image_threads.append(thread)
        
        # Create style for hover effect
        style = ttk.Style()
        style.configure('GameItem.TFrame', background='#1E1E1E')
        style.configure('GameItemHover.TFrame', background='#2D5F9A')
        style.configure('SelectedGame.TLabel',
                      background='#1E1E1E',
                      foreground='#4A90E2',
                      font=('Segoe UI', 10))
        style.configure('SelectedGame.TFrame',
                      background='#1E1E1E')
        
        # Create frame for selected game
        self.selected_game_frame = ttk.Frame(parent, style='SelectedGame.TFrame')
        self.selected_game_frame.pack(fill=tk.X, pady=(5, 0))
        self.selected_game_frame.pack_forget()  # Initially hidden
        
        # Bind events
        self.entry_widget.bind('<KeyRelease>', self.on_key_release)
        self.entry_widget.bind('<FocusOut>', lambda e: self.schedule_hide_popup())
        self.entry_widget.bind('<MouseWheel>', self.on_mousewheel)
        self.entry_widget.bind('<Button-1>', self.on_entry_click)
        
        # Start background workers
        self.start_search_worker()

    def start_search_worker(self):
        def worker():
            while True:
                try:
                    query = self.search_queue.get(timeout=0.1)
                    current_time = time.time()
                    
                    # Check cache first
                    cache_key = query.lower()
                    if cache_key in self.search_results_cache:
                        cache_entry = self.search_results_cache[cache_key]
                        if current_time - cache_entry['time'] < 300:  # Cache valid for 5 minutes
                            if query == self.current_search:
                                self.after(0, lambda: self.show_popup(cache_entry['results']))
                            continue
                    
                    # Rate limiting - don't search too frequently
                    time_since_last = current_time - self.last_search_time
                    if time_since_last < 0.1:  # Reduced delay to 100ms
                        time.sleep(0.1 - time_since_last)
                    
                    # Perform search
                    results = self.search_games(query)
                    self.last_search_time = time.time()
                    
                    # Update cache
                    self.search_results_cache[cache_key] = {
                        'time': current_time,
                        'results': results
                    }
                    
                    # Maintain cache size
                    if len(self.search_results_cache) > 200:  # Increased cache size
                        oldest = min(self.search_results_cache.items(), 
                                   key=lambda x: x[1]['time'])
                        del self.search_results_cache[oldest[0]]
                    
                    # Show results if this is still the current search
                    if query == self.current_search:
                        self.after(0, lambda: self.show_popup(results))
                except queue.Empty:
                    time.sleep(0.05)  # Reduced sleep time
                except Exception as e:
                    print(f"Search worker error: {e}")
                    time.sleep(0.05)
                    
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def image_worker(self):
        def load_image(url, max_retries=2):
            for attempt in range(max_retries):
                try:
                    # Try different image URLs if the main one fails
                    urls = [
                        url,
                        url.replace('/header.jpg', '/capsule_sm_120.jpg'),
                        url.replace('/header.jpg', '/capsule_231x87.jpg'),
                        url.replace('/header.jpg', '/capsule_184x69.jpg')
                    ]
                    
                    for img_url in urls:
                        try:
                            response = self.session.get(img_url, timeout=0.5)
                            if response.status_code == 200:
                                img_data = PIL.Image.open(BytesIO(response.content))
                                img_data = img_data.resize((120, 45), PIL.Image.Resampling.LANCZOS)
                                return PIL.ImageTk.PhotoImage(img_data)
                        except:
                            continue
                            
                    # If all URLs fail, try one more time after a short delay
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                    else:
                        print(f"Failed to load image after {max_retries} attempts: {e}")
            return None
            
        while True:
            try:
                url, callback = self.image_queue.get(timeout=0.1)
                if url not in self.image_cache:
                    img = load_image(url)
                    if img:
                        self.image_cache[url] = img
                        # Schedule callback in main thread and force update
                        self.after(0, lambda c=callback, i=img: (c(i), self.update_idletasks()))
                else:
                    # If image is already cached, use it immediately and force update
                    img = self.image_cache[url]
                    self.after(0, lambda c=callback, i=img: (c(i), self.update_idletasks()))
            except queue.Empty:
                time.sleep(0.05)
            except Exception as e:
                print(f"Image worker error: {e}")
                time.sleep(0.05)

    def configure_cursor(self, widget, cursor_type="hand2"):
        try:
            widget.configure(cursor=cursor_type)
        except:
            # For widgets that don't support direct cursor configuration
            widget.bind('<Enter>', lambda e: self.master.configure(cursor=cursor_type))
            widget.bind('<Leave>', lambda e: self.master.configure(cursor=""))
        
    def on_mousewheel(self, event):
        if self.popup and self.popup.winfo_viewable():
            canvas = self.popup.canvas if hasattr(self.popup, 'canvas') else None
            if canvas:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def on_entry_click(self, event):
        """Handle click on search entry to show hot games"""
        # Small delay to ensure the entry gets focus first
        self.after(50, self.show_hot_games_on_click)
    
    def show_hot_games_on_click(self):
        """Show hot games when search bar is clicked"""
        query = self.entry_widget.get().strip()
        if not query:
            # Show a loading indicator
            self.entry_widget.insert(0, "Loading hot games...")
            self.after(100, lambda: self.entry_widget.delete(0, tk.END))
            # Show hot games immediately when clicked
            self.perform_search("")
        
    def schedule_hide_popup(self):
        # Delay hiding to allow for clicks to register
        self.after(200, self.hide_popup)
            
    def show_selected_game(self, game_id, game_name, image_url):
        # Clear previous content
        for widget in self.selected_game_frame.winfo_children():
            widget.destroy()
            
        # Create and pack the image if available
        if image_url in self.image_cache:
            img = self.image_cache[image_url]
        else:
            try:
                response = requests.get(image_url, timeout=2)
                img_data = PIL.Image.open(BytesIO(response.content))
                img_data = img_data.resize((160, 60), PIL.Image.Resampling.LANCZOS)
                img = PIL.ImageTk.PhotoImage(img_data)
                self.image_cache[image_url] = img
            except:
                img = None
                
        if img:
            img_label = ttk.Label(self.selected_game_frame, image=img, background='#1E1E1E')
            img_label.image = img
            img_label.pack(side=tk.LEFT, padx=5, pady=5)
            
        # Create info frame
        info_frame = ttk.Frame(self.selected_game_frame, style='SelectedGame.TFrame')
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Game name and ID
        ttk.Label(info_frame, text=game_name,
                 style='SelectedGame.TLabel',
                 font=('Segoe UI', 11, 'bold')).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"AppID: {game_id}",
                 style='SelectedGame.TLabel',
                 font=('Segoe UI', 9)).pack(anchor=tk.W)
                 
        self.selected_game_frame.pack(fill=tk.X, pady=(5, 0))

    def on_select(self, game_id, game_name, image_url):
        # Check for Denuvo DRM on Steam store page before selecting
        denuvo_cancelled = self.check_denuvo_drm(game_id, game_name)
        if denuvo_cancelled:
            # If user cancelled due to Denuvo warning, don't proceed with selection
            return
        
        # Proceed with normal selection
        self.entry_widget.delete(0, tk.END)
        self.entry_widget.insert(0, f"{game_id} - {game_name}")  # Show both ID and name
        self.selected_game_id = game_id
        self.selected_game_name = game_name
        self.show_selected_game(game_id, game_name, image_url)
        root = self.winfo_toplevel()
        if hasattr(root, 'update_add_buttons_state'):
            root.update_add_buttons_state()
        self.hide_popup()

    def resolve_game_name(self, appid):
        """Resolve a Steam game name from the AppID using Steam Store API."""
        if not appid or not appid.isdigit():
            return None
        try:
            details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=US&l=english"
            response = self.session.get(details_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                app_data = data.get(str(appid), {})
                if app_data.get('success') and isinstance(app_data.get('data'), dict):
                    return app_data['data'].get('name')
        except Exception as e:
            logging.debug(f"Failed to resolve game name for {appid}: {e}")
        return None

    def get_hot_games(self):
        """Fetch hot/popular AAA games from Steam - optimized for speed"""
        try:
            # Use featured categories first (faster than individual searches)
            results = self.get_featured_aaa_games()
            
            # If we need more games, add some specific popular AAA titles (excluding competitive multiplayer)
            if len(results) < 20:
                # Add some well-known AAA single-player/story games directly with correct SteamDB App IDs
                popular_aaa_games = {
                    '1174180': {'name': 'Red Dead Redemption 2', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1174180/header.jpg'},
                    '1091500': {'name': 'Cyberpunk 2077', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/header.jpg'},
                    '292030': {'name': 'The Witcher 3: Wild Hunt', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/292030/header.jpg'},
                    '271590': {'name': 'Grand Theft Auto V', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/271590/header.jpg'},
                    '990080': {'name': 'Hogwarts Legacy', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/990080/header.jpg'},
                    '1888930': {'name': 'The Last of Us Part I', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1888930/header.jpg'},
                    '2531310': {'name': 'The Last of Us Part II Remastered', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/2531310/header.jpg'},
                    '1593500': {'name': 'God of War', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1593500/header.jpg'},
                    '1817070': {'name': 'Marvel\'s Spider-Man Remastered', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1817070/header.jpg'},
                    '1151640': {'name': 'Horizon Zero Dawn Complete Edition', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1151640/header.jpg'},
                    '1659420': {'name': 'Uncharted: Legacy of Thieves Collection', 'image': 'https://cdn.cloudflare.steamstatic.com/steam/apps/1659420/header.jpg'}
                }
                
                for app_id, game_info in popular_aaa_games.items():
                    if app_id not in results:
                        results[app_id] = game_info
            
            return dict(list(results.items())[:25])  # Return up to 25 AAA games
                
        except Exception as e:
            print(f"Error fetching AAA hot games: {e}")
            return self.get_featured_aaa_games()
    
    def is_aaa_game(self, app_id, game_name):
        """Check if a game is likely a AAA title based on publisher and other factors"""
        try:
            # Get detailed game information
            details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
            response = self.session.get(details_url, timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                if data.get(app_id, {}).get('success', False):
                    app_data = data[app_id]['data']
                    
                    # Check publishers and developers
                    publishers = app_data.get('publishers', [])
                    developers = app_data.get('developers', [])
                    
                    # Major AAA publishers
                    aaa_publishers = [
                        'Electronic Arts', 'EA Games', 'Ubisoft', 'Activision', 'Blizzard Entertainment',
                        'Bethesda Softworks', 'Rockstar Games', 'Take-Two Interactive', '2K Games',
                        'Square Enix', 'Capcom', 'Bandai Namco Entertainment', 'Warner Bros. Interactive',
                        'Sony Interactive Entertainment', 'Microsoft Studios', 'Nintendo', 'Valve',
                        'CD Projekt', 'Epic Games', 'Riot Games', 'Bungie', 'Respawn Entertainment',
                        'Infinity Ward', 'Treyarch', 'Sledgehammer Games', 'DICE', 'BioWare',
                        'Crystal Dynamics', 'Eidos Interactive', 'Monolith Productions', 'NetherRealm Studios',
                        'Rocksteady Studios', 'WB Games', 'Gearbox Software', '2K', 'Firaxis Games',
                        'Hangar 13', 'Visual Concepts', 'Cloud Chamber', 'Hangar 13', 'Firaxis Games'
                    ]
                    
                    # Check if any publisher is a major AAA publisher
                    for publisher in publishers:
                        if any(aaa_pub in str(publisher) for aaa_pub in aaa_publishers):
                            return True
                    
                    # Check if any developer is a major AAA developer
                    for developer in developers:
                        if any(aaa_pub in str(developer) for aaa_pub in aaa_publishers):
                            return True
                    
                    # Check price - AAA games are usually $30+ (though some may be free)
                    price_info = app_data.get('price_overview', {})
                    if price_info and 'final' in price_info:
                        price = price_info['final'] / 100  # Convert from cents
                        if price >= 30:  # $30+ is typically AAA pricing
                            return True
                    
                    # Check if it's a well-known franchise (by name patterns)
                    franchise_keywords = [
                        'call of duty', 'battlefield', 'fifa', 'madden', 'nba 2k', 'assassin\'s creed',
                        'grand theft auto', 'red dead redemption', 'cyberpunk', 'witcher', 'elder scrolls',
                        'fallout', 'doom', 'resident evil', 'street fighter', 'tekken', 'final fantasy',
                        'dragon quest', 'monster hunter', 'dark souls', 'elden ring', 'sekiro',
                        'god of war', 'spider-man', 'horizon', 'uncharted', 'the last of us',
                        'halo', 'gears of war', 'forza', 'minecraft', 'counter-strike', 'dota 2',
                        'half-life', 'portal', 'left 4 dead', 'team fortress', 'apex legends',
                        'overwatch', 'world of warcraft', 'diablo', 'starcraft', 'destiny',
                        'borderlands', 'bioshock', 'mass effect', 'dragon age', 'tomb raider',
                        'hitman', 'just cause', 'far cry', 'watch dogs', 'the division',
                        'ghost recon', 'rainbow six', 'for honor', 'star wars', 'battlefront',
                        'marvel', 'batman', 'suicide squad', 'gotham knights', 'wonder woman'
                    ]
                    
                    game_name_lower = game_name.lower()
                    for keyword in franchise_keywords:
                        if keyword in game_name_lower:
                            return True
                            
        except Exception as e:
            print(f"Error checking if game is AAA: {e}")
            
        return False
    
    def get_featured_aaa_games(self):
        """Get featured AAA games from Steam's featured categories - optimized"""
        try:
            url = "https://store.steampowered.com/api/featuredcategories"
            response = self.session.get(url, timeout=2)  # Reduced timeout
            
            if response.status_code == 200:
                data = response.json()
                results = {}
                
                # Get featured games from different categories
                categories = ['featured_win', 'top_sellers', 'new_releases']
                
                for category in categories:
                    if category in data and 'items' in data[category]:
                        for item in data[category]['items'][:10]:  # Get top 10 per category
                            app_id = str(item.get('id', ''))
                            if app_id and app_id not in results:
                                # Quick AAA check based on name patterns (faster than API call)
                                game_name = item.get('name', '').lower()
                                if self.is_likely_aaa_quick(game_name) and not self.is_competitive_multiplayer(game_name):
                                    results[app_id] = {
                                        'name': item.get('name', 'Unknown Game'),
                                        'image': item.get('header_image') or 
                                                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                                    }
                
                return results
                
        except Exception as e:
            print(f"Error fetching featured AAA games: {e}")
            return {}
    
    def is_likely_aaa_quick(self, game_name):
        """Quick AAA game detection based on name patterns (no API calls) - excludes competitive multiplayer"""
        # Keywords for competitive multiplayer games to exclude
        competitive_keywords = [
            'counter-strike', 'cs:', 'cs2', 'cs go', 'dota 2', 'league of legends', 'lol',
            'apex legends', 'overwatch', 'valorant', 'rainbow six siege', 'for honor',
            'world of warcraft', 'wow', 'destiny 2', 'warframe', 'path of exile', 'poe',
            'team fortress', 'left 4 dead', 'pubg', 'fortnite', 'rocket league',
            'fifa', 'madden', 'nba 2k', 'nhl', 'mlb the show', 'nascar', 'f1',
            'call of duty multiplayer', 'battlefield multiplayer', 'halo multiplayer'
        ]
        
        # Check if it's a competitive multiplayer game first
        for keyword in competitive_keywords:
            if keyword in game_name:
                return False
        
        # AAA single-player/story game keywords
        aaa_keywords = [
            'call of duty campaign', 'battlefield campaign', 'assassin', 'grand theft auto',
            'red dead redemption', 'cyberpunk', 'witcher', 'elder scrolls', 'fallout',
            'doom', 'resident evil', 'street fighter', 'tekken', 'final fantasy',
            'dragon quest', 'monster hunter', 'dark souls', 'elden ring', 'sekiro',
            'god of war', 'spider-man', 'horizon', 'uncharted', 'last of us',
            'halo campaign', 'gears of war', 'forza horizon', 'minecraft',
            'half-life', 'portal', 'bioshock', 'mass effect', 'dragon age',
            'tomb raider', 'hitman', 'just cause', 'far cry', 'watch dogs',
            'the division', 'ghost recon', 'star wars', 'battlefront',
            'marvel', 'batman', 'suicide squad', 'gotham knights', 'wonder woman',
            'hogwarts', 'harry potter', 'wolverine', 'avengers', 'guardians',
            'justice league', 'aquaman', 'flash', 'green lantern', 'superman'
        ]
        
        for keyword in aaa_keywords:
            if keyword in game_name:
                return True
        return False
    
    def is_competitive_multiplayer(self, game_name):
        """Check if a game is competitive multiplayer to exclude from suggestions"""
        competitive_keywords = [
            'counter-strike', 'cs:', 'cs2', 'cs go', 'dota 2', 'league of legends', 'lol',
            'apex legends', 'overwatch', 'valorant', 'rainbow six siege', 'for honor',
            'world of warcraft', 'wow', 'destiny 2', 'warframe', 'path of exile', 'poe',
            'team fortress', 'left 4 dead', 'pubg', 'fortnite', 'rocket league',
            'fifa', 'madden', 'nba 2k', 'nhl', 'mlb the show', 'nascar', 'f1',
            'call of duty multiplayer', 'battlefield multiplayer', 'halo multiplayer'
        ]
        
        for keyword in competitive_keywords:
            if keyword in game_name:
                return True
        return False
    
    def get_trending_games(self):
        """Fallback method to get trending games"""
        try:
            # Use Steam's search API with popular terms
            url = "https://store.steampowered.com/api/storesearch"
            params = {
                'term': 'popular',
                'l': 'english',
                'cc': 'US',
                'category1': 998,  # Games only
                'infinite': 1
            }
            
            response = self.session.get(url, params=params, timeout=3)
            if response.status_code == 200:
                data = response.json()
                results = {}
                
                if 'items' in data:
                    for item in data['items'][:15]:  # Increased to 15 results
                        app_id = str(item['id'])
                        results[app_id] = {
                            'name': item['name'],
                            'image': item.get('tiny_image') or 
                                    f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                        }
                
                return results
                
        except Exception as e:
            print(f"Error fetching trending games: {e}")
            
        return {}
    
    def get_additional_trending_games(self):
        """Get additional trending games using different search terms"""
        try:
            # Search for different popular game terms
            search_terms = ['new', 'trending', 'bestseller', 'indie', 'action', 'rpg', 'strategy']
            results = {}
            
            for term in search_terms:
                try:
                    url = "https://store.steampowered.com/api/storesearch"
                    params = {
                        'term': term,
                        'l': 'english',
                        'cc': 'US',
                        'category1': 998,  # Games only
                        'infinite': 1
                    }
                    
                    response = self.session.get(url, params=params, timeout=2)
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'items' in data:
                            for item in data['items'][:5]:  # 5 per term
                                app_id = str(item['id'])
                                if app_id not in results:
                                    results[app_id] = {
                                        'name': item['name'],
                                        'image': item.get('tiny_image') or 
                                                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                                    }
                except Exception as e:
                    print(f"Error fetching games for term '{term}': {e}")
                    continue
                    
            return results
            
        except Exception as e:
            print(f"Error fetching additional trending games: {e}")
            return {}




    def show_denuvo_warning_dialog(self, game_name, game_id):
        """Show simple Denuvo warning dialog. Returns True if user cancelled, False if user proceeded."""
        # Create custom warning dialog
        dialog = tk.Toplevel(self.master)
        dialog.title("Denuvo Warning")
        dialog.geometry("420x320")
        dialog.resizable(False, False)
        
        # Make dialog modal
        dialog.transient(self.master)
        dialog.grab_set()
        
        # Center the dialog on the main app window
        dialog.update_idletasks()
        
        # Get main window position and size
        main_x = self.master.winfo_rootx()
        main_y = self.master.winfo_rooty()
        main_width = self.master.winfo_width()
        main_height = self.master.winfo_height()
        
        # Calculate center position relative to main window
        dialog_width = 450
        dialog_height = 400
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        
        # Ensure dialog stays on screen
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = max(0, min(x, screen_width - dialog_width))
        y = max(0, min(y, screen_height - dialog_height))
        
        # Set the geometry with position
        dialog.geometry(f'{dialog_width}x{dialog_height}+{x}+{y}')
        
        # Force the dialog to appear in the correct position
        dialog.lift()
        dialog.focus_force()
        dialog.update()
        
        # Add icon
        icon_path = os.path.join(os.path.dirname(__file__), "logo.ico")
        if os.path.exists(icon_path):
            dialog.iconbitmap(icon_path)
        
        # Configure dialog style
        dialog.configure(bg='#1E1E1E')
        
        # Create main frame
        frame = ttk.Frame(dialog, padding="25")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning icon and title
        title_frame = ttk.Frame(frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        warning_icon = ttk.Label(title_frame, text="⚠️", font=('Segoe UI', 24))
        warning_icon.pack(side=tk.LEFT, padx=(0, 15))
        
        title_label = ttk.Label(title_frame, text="Denuvo Game Detected", 
                               font=('Segoe UI', 14, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # Game info
        game_label = ttk.Label(frame, text=f"Game: {game_name}",
                             font=('Segoe UI', 11, 'bold'))
        game_label.pack(anchor=tk.W, pady=(0, 15))
        
        # Simple warning message
        warning_text = (
            "This game uses Denuvo protection which may cause:\n"
            "• Performance issues\n"
            "• Compatibility problems\n\n"
            "Contact GameDrop support for Denuvo token authorization\n\n"
            "Do you want to continue?"
        )
        
        msg_label = ttk.Label(frame, text=warning_text, 
                             font=('Segoe UI', 10),
                             wraplength=380,
                             justify=tk.LEFT)
        msg_label.pack(fill=tk.X, pady=(0, 25))
        
        # Buttons frame with better spacing
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Variables to track user choice
        user_choice = {'proceed': False}
        
        def cancel_selection():
            user_choice['proceed'] = False
            dialog.destroy()
            
        def proceed_selection():
            user_choice['proceed'] = True
            dialog.destroy()
        
        # Buttons using regular tk.Button for better visibility
        cancel_btn = tk.Button(btn_frame, text="Cancel", 
                              command=cancel_selection, 
                              width=12,
                              height=2,
                              bg='#E74C3C',
                              fg='white',
                              font=('Segoe UI', 10, 'bold'),
                              relief='raised',
                              bd=2)
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0), pady=15)
        
        continue_btn = tk.Button(btn_frame, text="Continue", 
                                command=proceed_selection, 
                                width=12,
                                height=2,
                                bg='#4A90E2',
                                fg='white',
                                font=('Segoe UI', 10, 'bold'),
                                relief='raised',
                                bd=2)
        continue_btn.pack(side=tk.RIGHT, padx=(0, 10), pady=15)
        
        # Focus on continue button
        continue_btn.focus()
        
        # Bind Enter key to proceed, Escape to cancel
        dialog.bind('<Return>', lambda e: proceed_selection())
        dialog.bind('<Escape>', lambda e: cancel_selection())
        
        # Wait for dialog to close
        dialog.wait_window()
        
        # Return True if user cancelled (didn't proceed), False if user proceeded
        return not user_choice['proceed']

    def show_denuvo_warning(self, game_name, game_id):
        """Show Denuvo warning dialog (legacy method)"""
        return self.show_denuvo_warning_dialog(game_name, game_id)

    def check_denuvo_drm(self, game_id, game_name):
        """Check Steam store page for Denuvo DRM information. Returns True if user cancelled, False otherwise."""
        root = self.winfo_toplevel()
        if hasattr(root, 'selected_game_denuvo'):
            root.selected_game_denuvo = False
        self._reset_progressbar()
        if hasattr(self, 'progress_card'):
            self.progress_card.grid_remove()
            self.progress_hidden_for_add = True
        self.progress["maximum"] = 100
        self.progress["value"] = 15
        self.progress_percent.set("15%")
        self.progress_text.set("Checking Denuvo DRM...")
        self.update_idletasks()
        try:
            print(f"🔍 Checking DRM for {game_name} (ID: {game_id})...")
            
            # Get the Steam store page
            store_url = f"https://store.steampowered.com/app/{game_id}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
                'Cookie': 'birthtime=315532801; mature_content=1; lastagecheckage=1-January-1980'  # Age verification cookie
            }
            
            response = self.session.get(store_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                html_content = response.text
                self.progress["value"] = 50
                self.progress_percent.set("50%")
                self.update_idletasks()
                print(f"  HTML snippet (first 500 chars): {html_content[:500]}...")
                
                # Check if we got the age verification page instead of the game page
                if 'birth date' in html_content.lower() or 'age verification' in html_content.lower() or 'not appropriate for all ages' in html_content.lower():
                    print(f"  ⚠️ Got age verification page, trying alternative approach...")
                    # Try with different URL format
                    alt_url = f"https://store.steampowered.com/app/{game_id}/?snr=1_7_7_151_150_1"
                    alt_response = self.session.get(alt_url, headers=headers, timeout=10)
                    if alt_response.status_code == 200:
                        html_content = alt_response.text
                        print(f"  Alternative URL worked, checking content...")
                    else:
                        print(f"  Alternative URL also failed: HTTP {alt_response.status_code}")
                        return False
                
                # Debug: Look for DRM-related text specifically
                if 'DRM' in html_content:
                    print(f"  Found 'DRM' in HTML")
                    # Find all occurrences of DRM
                    drm_indices = []
                    start = 0
                    while True:
                        index = html_content.find('DRM', start)
                        if index == -1:
                            break
                        drm_indices.append(index)
                        start = index + 1
                    
                    for i, index in enumerate(drm_indices[:3]):  # Show first 3 occurrences
                        context_start = max(0, index - 100)
                        context_end = min(len(html_content), index + 100)
                        context = html_content[context_start:context_end]
                        print(f"  DRM context {i+1}: ...{context}...")
                
                if 'denuvo' in html_content.lower():
                    print(f"  Found 'denuvo' in HTML")
                    # Find all occurrences of denuvo
                    denuvo_indices = []
                    start = 0
                    html_lower = html_content.lower()
                    while True:
                        index = html_lower.find('denuvo', start)
                        if index == -1:
                            break
                        denuvo_indices.append(index)
                        start = index + 1
                    
                    for i, index in enumerate(denuvo_indices[:3]):  # Show first 3 occurrences
                        context_start = max(0, index - 100)
                        context_end = min(len(html_content), index + 100)
                        context = html_content[context_start:context_end]
                        print(f"  Denuvo context {i+1}: ...{context}...")
                
                # Look for DRM information in various formats
                # Steam shows DRM info in different ways on different games
                denuvo_patterns = [
                    # Standard Steam DRM box formats
                    'Incorporates 3rd-party DRM: Denuvo',
                    'incorporates 3rd-party drm: denuvo',
                    'Incorporates third-party DRM: Denuvo',
                    'incorporates third-party drm: denuvo',
                    '3rd-party DRM: Denuvo',
                    'third-party DRM: Denuvo',
                    '3rd-party drm: denuvo',
                    'third-party drm: denuvo',
                    
                    # Shorter formats
                    'DRM: Denuvo',
                    'drm: denuvo',
                    'DRM Denuvo',
                    'drm denuvo',
                    
                    # Denuvo-specific terms
                    'Denuvo Anti-Tamper',
                    'denuvo anti-tamper',
                    'Denuvo Anti Tamper',
                    'denuvo anti tamper',
                    'Denuvo Anti-Tampering',
                    'denuvo anti-tampering',
                    'Denuvo Anti Tampering',
                    'denuvo anti tampering',
                    
                    # Alternative formats
                    'Denuvo DRM',
                    'denuvo drm',
                    'Denuvo Protection',
                    'denuvo protection',
                    'Denuvo Anti-Cheat',
                    'denuvo anti-cheat',
                    'Denuvo Anti Cheat',
                    'denuvo anti cheat',
                    
                    # HTML/JSON data patterns
                    '"drm":"denuvo"',
                    '"DRM":"Denuvo"',
                    '"drm":"Denuvo"',
                    '"DRM":"denuvo"',
                    'drm":"denuvo',
                    'DRM":"Denuvo',
                    
                    # System requirements mentions
                    'Requires Denuvo',
                    'requires denuvo',
                    'Denuvo required',
                    'denuvo required'
                ]
                
                # Check if any Denuvo pattern is found
                found_patterns = []
                for pattern in denuvo_patterns:
                    if pattern in html_content:
                        found_patterns.append(pattern)
                
                # Debug: Test the exact text we expect to find
                expected_text = "Incorporates 3rd-party DRM: Denuvo"
                if expected_text in html_content:
                    print(f"✅ Found exact expected text: '{expected_text}'")
                    proceeded = not self.show_denuvo_warning_dialog(game_name, game_id)
                    if hasattr(root, 'selected_game_denuvo'):
                        root.selected_game_denuvo = proceeded
                    return not proceeded
                else:
                    print(f"❌ Expected text '{expected_text}' NOT found in HTML")

                if found_patterns:
                    print(f"✅ Denuvo DRM detected for {game_name} (ID: {game_id})")
                    print(f"  Found patterns: {found_patterns}")
                    proceeded = not self.show_denuvo_warning_dialog(game_name, game_id)
                    if hasattr(root, 'selected_game_denuvo'):
                        root.selected_game_denuvo = proceeded
                    return not proceeded
                
                # Also check for any mention of "denuvo" in the HTML (case insensitive)
                html_lower = html_content.lower()
                if 'denuvo' in html_lower:
                    print(f"✅ Denuvo mentioned in HTML for {game_name} (ID: {game_id})")
                    # Find the context around "denuvo"
                    denuvo_index = html_lower.find('denuvo')
                    context_start = max(0, denuvo_index - 50)
                    context_end = min(len(html_content), denuvo_index + 50)
                    context = html_content[context_start:context_end]
                    print(f"  Context: ...{context}...")
                    proceeded = not self.show_denuvo_warning_dialog(game_name, game_id)
                    if hasattr(root, 'selected_game_denuvo'):
                        root.selected_game_denuvo = proceeded
                    return not proceeded
                
                # Fallback: Check Steam Store API for DRM info
                print(f"  Checking Steam Store API as fallback...")
                self.progress["value"] = 80
                self.progress_percent.set("80%")
                self.update_idletasks()
                api_found = self._check_steam_api_drm(game_id, game_name)
                if api_found:
                    proceeded = not self.show_denuvo_warning_dialog(game_name, game_id)
                    if hasattr(root, 'selected_game_denuvo'):
                        root.selected_game_denuvo = proceeded
                    return not proceeded
                
                print(f"❌ No Denuvo DRM detected for {game_name} (ID: {game_id})")
                if hasattr(root, 'selected_game_denuvo'):
                    root.selected_game_denuvo = False
                return False
            else:
                print(f"❌ Steam store page error: HTTP {response.status_code}")
                if hasattr(root, 'selected_game_denuvo'):
                    root.selected_game_denuvo = False
                return False
                
        except Exception as e:
            print(f"❌ Error checking DRM: {e}")
            if hasattr(root, 'selected_game_denuvo'):
                root.selected_game_denuvo = False
            return False
        finally:
            self._stop_progress_animation()

    def _check_steam_api_drm(self, game_id, game_name):
        """Check Steam Store API for DRM information as fallback."""
        try:
            api_url = f"https://store.steampowered.com/api/appdetails"
            params = {
                'appids': game_id,
                'cc': 'US',
                'l': 'english'
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://store.steampowered.com/'
            }
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get(game_id, {}).get('success', False):
                    app_data = data[game_id]['data']
                    
                    # Check all text fields for Denuvo
                    text_fields = [
                        str(app_data.get('description', '')),
                        str(app_data.get('short_description', '')),
                        str(app_data.get('detailed_description', '')),
                        str(app_data.get('about_the_game', '')),
                        str(app_data.get('pc_requirements', {})),
                        str(app_data.get('mac_requirements', {})),
                        str(app_data.get('linux_requirements', {}))
                    ]
                    
                    # Check categories and genres
                    for category in app_data.get('categories', []):
                        if isinstance(category, dict):
                            text_fields.append(str(category.get('description', '')))
                    
                    for genre in app_data.get('genres', []):
                        if isinstance(genre, dict):
                            text_fields.append(str(genre.get('description', '')))
                    
                    # Combine all text and check for Denuvo
                    all_text = ' '.join(text_fields).lower()
                    
                    if 'denuvo' in all_text:
                        print(f"✅ Denuvo found in Steam API data for {game_name} (ID: {game_id})")
                        return True
                    else:
                        print(f"  No Denuvo found in Steam API data")
                        return False
                else:
                    print(f"  Steam API returned unsuccessful response")
                    return False
            else:
                print(f"  Steam API error: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"  Error checking Steam API: {e}")
            return False

    def search_games(self, query):
        if not query:
            # Return hot games when no query is provided
            return self.get_hot_games()
            
        try:
            # First, check if the query starts with a number (potential AppID)
            app_id = query.split(' - ')[0] if ' - ' in query else query
            if app_id.isdigit():
                try:
                    details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                    details_response = self.session.get(details_url, timeout=0.5)
                    if details_response.status_code == 200:
                        details_data = details_response.json()
                        if details_data.get(app_id, {}).get('success', False):
                            app_data = details_data[app_id]['data']
                            # Check for DLC indicators in the full app data
                            if (('type' not in app_data or app_data['type'].lower() == 'game') and
                                not app_data.get('dlc', False) and
                                not app_data.get('is_dlc', False) and
                                'dlc' not in str(app_data.get('categories', [])).lower() and
                                'downloadable content' not in str(app_data.get('categories', [])).lower()):
                                return {
                                    app_id: {
                                        'name': app_data['name'],
                                        'image': app_data.get('header_image') or 
                                                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                                    }
                                }
                except Exception as e:
                    print(f"AppID lookup error: {e}")

            # Extract search term (remove AppID if present)
            search_term = query.split(' - ', 1)[1] if ' - ' in query else query

            # Skip empty terms
            if not search_term.strip():
                return {}

            # For short search terms (3 characters or less), add a wildcard
            if len(search_term.strip()) <= 3:
                search_term = search_term.strip() + "*"

            # Then do a general search
            url = "https://store.steampowered.com/api/storesearch"
            params = {
                'term': search_term,
                'l': 'english',
                'cc': 'US',
                'category1': 998,  # Games only
                'infinite': 1      # Get more results
            }
            
            try:
                response = self.session.get(url, params=params, timeout=0.5)
                if response.status_code != 200:
                    print(f"Search API error: Status {response.status_code}")
                    return {}
                    
                data = response.json()
                if not data or 'items' not in data:
                    print(f"No results in response: {data}")
                    # Try with more flexible search for short terms
                    if len(search_term.strip()) <= 3:
                        params['term'] = search_term.strip().replace('*', '')
                        try:
                            response = self.session.get(url, params=params, timeout=0.5)
                            if response.status_code == 200:
                                data = response.json()
                            else:
                                return {}
                        except:
                            return {}
                    if not data or 'items' not in data:
                        return {}
                    
            except Exception as e:
                print(f"Search API error: {e}")
                return {}
            
            results = {}
            if data['items']:
                processed = 0
                for item in data['items']:
                    if processed >= 12:  # Limit to 12 results
                        break
                        
                    app_id = str(item['id'])
                    name = item['name'].lower()
                    
                    # For short search terms, be more lenient with filtering
                    if len(search_term.strip()) <= 3:
                        # Skip only obvious DLC
                        if item.get('type', '').lower() == 'dlc':
                            continue
                    else:
                        # Apply stricter filtering for longer search terms
                        # Skip obvious DLC names
                        if any(x in name for x in [' dlc', 'dlc ', ' pack', ' addon', ' - expansion']):
                            continue
                            
                        # Skip if it's marked as DLC
                        if item.get('type', '').lower() == 'dlc':
                            continue
                            
                        # Skip if it has DLC-related tags
                        tags = str(item.get('tags', [])).lower()
                        if ('dlc' in tags or 'downloadable content' in tags or
                            'add-on' in tags or 'addon' in tags):
                            continue
                            
                        # Skip if name contains DLC patterns
                        if ' - ' in name:
                            base, extra = name.split(' - ', 1)
                            dlc_suffixes = ['edition', 'version', 'pack', 'dlc', 'expansion', 'bundle']
                            if any(suffix in extra.lower() for suffix in dlc_suffixes):
                                continue
                    
                    results[app_id] = {
                        'name': item['name'],
                        'image': item.get('tiny_image') or 
                                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                    }
                    processed += 1
                    
            if not results:
                # If no results, try with more flexible search
                params['term'] = search_term.replace(' ', ' & ').replace('*', '')  # Add OR operator and remove wildcard
                try:
                    response = self.session.get(url, params=params, timeout=0.5)
                    if response.status_code == 200:
                        data = response.json()
                        if 'items' in data and data['items']:
                            processed = 0
                            for item in data['items']:
                                if processed >= 12:
                                    break
                                    
                                app_id = str(item['id'])
                                name = item['name'].lower()
                                
                                # Apply same filtering as above based on search term length
                                if len(search_term.strip()) <= 3:
                                    if item.get('type', '').lower() == 'dlc':
                                        continue
                                else:
                                    if (item.get('type', '').lower() == 'dlc' or
                                        any(x in name for x in [' dlc', 'dlc ', ' pack', ' addon', ' - expansion'])):
                                        continue
                                    
                                results[app_id] = {
                                    'name': item['name'],
                                    'image': item.get('tiny_image') or 
                                            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                                }
                                processed += 1
                except Exception as e:
                    print(f"Flexible search error: {e}")
                    
            return results
            
        except Exception as e:
            print(f"Search error: {e}")
            return {}

    def show_popup(self, suggestions):
        if not suggestions:
            self.hide_popup()
            return
            
        if not self.popup:
            self.popup = tk.Toplevel()
            self.popup.overrideredirect(True)
            self.popup.withdraw()
            self.popup.configure(bg='#1E1E1E')
            
        # Clear previous widgets
        for widget in self.popup.winfo_children():
            widget.destroy()
            
        # Calculate position
        x = self.entry_widget.winfo_rootx()
        y = self.entry_widget.winfo_rooty() + self.entry_widget.winfo_height()
        
        # Create frame for suggestions
        frame = ttk.Frame(self.popup, style='Custom.TFrame')
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Add title if showing hot games (empty query)
        if not self.current_search:
            title_frame = ttk.Frame(frame, style='Custom.TFrame')
            title_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
            title_label = ttk.Label(title_frame, text="🔥 Hot AAA Games on Steam", 
                                   font=('Segoe UI', 10, 'bold'),
                                   background='#1E1E1E',
                                   foreground='#4A90E2')
            title_label.pack(anchor=tk.W)
        
        # Create canvas with scrollbar - adjust height for more games
        max_height = min(len(suggestions) * 80 + 50, 500)  # Increased max height and added padding
        canvas = tk.Canvas(frame, height=max_height, width=400,
                         bg='#1E1E1E', highlightthickness=1, highlightbackground='#4A90E2')
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Store canvas reference for mousewheel scrolling
        self.popup.canvas = canvas
        
        # Inner frame for suggestions
        inner_frame = ttk.Frame(canvas, style='Custom.TFrame')
        canvas.create_window((0, 0), window=inner_frame, anchor='nw', width=380)
        
        # Add suggestions
        for game_id, game_info in suggestions.items():
            suggestion_frame = ttk.Frame(inner_frame, style='GameItem.TFrame')
            suggestion_frame.pack(fill=tk.X, padx=5, pady=5)
            self.configure_cursor(suggestion_frame)
            
            # Image placeholder with loading indicator
            img_frame = ttk.Frame(suggestion_frame, style='GameItem.TFrame', width=120, height=45)
            img_frame.pack_propagate(False)  # Prevent frame from shrinking
            img_frame.pack(side=tk.LEFT, padx=5)
            
            # Create a fixed reference to the game info for this iteration
            current_game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
            
            # Store game info in frame for event handlers
            img_frame.game_info = current_game_info
            
            # Create click handler specifically for this game
            def make_click_handler(game_info):
                def handler(event):
                    self.on_select(game_info['id'], game_info['name'], game_info['image'])
                return handler
                
            click_handler = make_click_handler(current_game_info)
            
            # Bind events to image frame
            img_frame.bind('<Button-1>', click_handler)
            img_frame.bind('<Enter>', lambda e, f=suggestion_frame: self.on_enter(e, f))
            img_frame.bind('<Leave>', lambda e, f=suggestion_frame: self.on_leave(e, f))
            
            loading_label = ttk.Label(img_frame, text="Loading...",
                                    background='#1E1E1E', foreground='#666666')
            loading_label.place(relx=0.5, rely=0.5, anchor='center')
            
            # Store game info in loading label
            loading_label.game_info = current_game_info
            
            # Bind events to loading label
            loading_label.bind('<Button-1>', click_handler)
            loading_label.bind('<Enter>', lambda e, f=suggestion_frame: self.on_enter(e, f))
            loading_label.bind('<Leave>', lambda e, f=suggestion_frame: self.on_leave(e, f))
            
            # Load image in background
            if game_info['image'] in self.image_cache:
                img = self.image_cache[game_info['image']]
                loading_label.destroy()
                img_label = ttk.Label(img_frame, image=img, background='#1E1E1E')
                img_label.image = img
                img_label.place(relx=0.5, rely=0.5, anchor='center')
                
                # Store game info in image label
                img_label.game_info = current_game_info
                
                # Bind events to image label
                img_label.bind('<Button-1>', click_handler)
                img_label.bind('<Enter>', lambda e, f=suggestion_frame: self.on_enter(e, f))
                img_label.bind('<Leave>', lambda e, f=suggestion_frame: self.on_leave(e, f))
            else:
                def update_image(img, frame=img_frame, loading=loading_label, game_info=current_game_info):
                    if img and frame.winfo_exists():  # Check if frame still exists
                        if loading.winfo_exists():  # Check if loading label still exists
                            loading.destroy()
                        img_label = ttk.Label(frame, image=img, background='#1E1E1E')
                        img_label.image = img
                        img_label.place(relx=0.5, rely=0.5, anchor='center')
                        
                        # Store game info in dynamically created image label
                        img_label.game_info = game_info
                        
                        # Create click handler for this specific game
                        click_handler = make_click_handler(game_info)
                        
                        # Bind events to dynamically created image label
                        img_label.bind('<Button-1>', click_handler)
                        # Store game info in label for event handlers
                        img_label.game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
                        
                        # Bind events to dynamically created image label using bound method
                        img_label.bind('<Button-1>', lambda e, f=img_label: self.on_select(f.game_info['id'], 
                                                                                         f.game_info['name'], 
                                                                                         f.game_info['image']))
                        img_label.bind('<Enter>', lambda e, f=suggestion_frame: self.on_enter(e, f))
                        img_label.bind('<Leave>', lambda e, f=suggestion_frame: self.on_leave(e, f))
                        
                        frame.update_idletasks()  # Force frame update
                self.image_queue.put((game_info['image'], update_image))
            
            # Game info
            info_frame = ttk.Frame(suggestion_frame, style='GameItem.TFrame')
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Store game info in info_frame for event handlers
            info_frame.game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
            
            name_label = ttk.Label(info_frame, text=game_info['name'],
                                 font=('Segoe UI', 10, 'bold'),
                                 wraplength=250,
                                 background='#1E1E1E',
                                 foreground='#FFFFFF')
            name_label.pack(anchor=tk.W)
            
            # Store game info in name_label for event handlers
            name_label.game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
            
            id_label = ttk.Label(info_frame, text=f"AppID: {game_id}",
                               font=('Segoe UI', 8),
                               background='#1E1E1E',
                               foreground='#FFFFFF')
            id_label.pack(anchor=tk.W)
            
            # Store game info in id_label for event handlers
            id_label.game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
            
            # Store game info in suggestion_frame for event handlers
            suggestion_frame.game_info = {'id': game_id, 'name': game_info['name'], 'image': game_info['image']}
            
            # Bind events using a function that gets game info from the widget that triggered the event
            def create_click_handler(widget):
                return lambda e: self.on_select(widget.game_info['id'], 
                                              widget.game_info['name'], 
                                              widget.game_info['image'])
            
            def create_enter_handler(frame):
                return lambda e: self.on_enter(e, frame)
                
            def create_leave_handler(frame):
                return lambda e: self.on_leave(e, frame)
            
            # Bind events to all widgets
            for widget in (suggestion_frame, info_frame, name_label, id_label):
                widget.bind('<Button-1>', create_click_handler(widget))
                widget.bind('<Enter>', create_enter_handler(suggestion_frame))
                widget.bind('<Leave>', create_leave_handler(suggestion_frame))
        
        # Pack scrollbar and show popup
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Update canvas scroll region
        inner_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # Bind mouse wheel events to canvas for scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        # Also bind to the popup window to ensure it works when hovering over the popup
        self.popup.bind("<MouseWheel>", on_mousewheel)
        
        # Position and show popup
        popup_width = 400
        popup_height = max_height
        
        # Ensure popup doesn't go off screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        if x + popup_width > screen_width:
            x = screen_width - popup_width
        if y + popup_height > screen_height:
            y = y - popup_height - self.entry_widget.winfo_height()
            
        self.popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
        self.popup.deiconify()
        self.popup.lift()

    def on_enter(self, event, frame):
        frame.configure(style='GameItemHover.TFrame')
        for child in frame.winfo_children():
            if isinstance(child, ttk.Frame):
                child.configure(style='GameItemHover.TFrame')
            elif isinstance(child, ttk.Label):
                child.configure(background='#2D5F9A', foreground='#FFFFFF')
            
    def on_leave(self, event, frame):
        frame.configure(style='GameItem.TFrame')
        for child in frame.winfo_children():
            if isinstance(child, ttk.Frame):
                child.configure(style='GameItem.TFrame')
            elif isinstance(child, ttk.Label):
                child.configure(background='#1E1E1E', foreground='#FFFFFF')

    def hide_popup(self):
        if self.popup:
            self.popup.withdraw()
            if hasattr(self.popup, 'canvas'):
                self.popup.canvas.unbind_all("<MouseWheel>")
    
    def update_popup_position(self):
        """Update popup position when main window moves"""
        if self.popup and self.popup.winfo_viewable():
            # Calculate new position relative to entry widget
            x = self.entry_widget.winfo_rootx()
            y = self.entry_widget.winfo_rooty() + self.entry_widget.winfo_height()
            
            # Get current popup size
            popup_width = self.popup.winfo_width()
            popup_height = self.popup.winfo_height()
            
            # Ensure popup doesn't go off screen
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            if x + popup_width > screen_width:
                x = screen_width - popup_width
            if y + popup_height > screen_height:
                y = y - popup_height - self.entry_widget.winfo_height()
            
            # Update popup position
            self.popup.geometry(f"+{x}+{y}")
            
    def schedule_hide_popup(self):
        # Delay hiding to allow for clicks to register
        self.after(200, self.hide_popup)
            
    def perform_search(self, query):
        self.current_search = query
        self.search_queue.put(query)
            
    def delayed_search(self):
        query = self.entry_widget.get().strip()
        if query:
            self.perform_search(query)
        else:
            # Show hot games when search bar is empty but focused
            if self.entry_widget == self.master.focus_get():
                self.perform_search("")  # Empty query will trigger hot games
            else:
                self.hide_popup()
                self.selected_game_frame.pack_forget()
            
    def on_key_release(self, event):
        if event.keysym in ('Down', 'Up', 'Return', 'Escape'):
            return
            
        # Cancel previous delayed search if any
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
            
        # Schedule new search with shorter delay
        self.search_after_id = self.after(200, self.delayed_search)  # Reduced delay

class DownloadManager:
    def __init__(self, parent):
        self.parent = parent
        self.download_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.current_files = []
        self.total_files = 0
        self.download_thread = None
        self.is_downloading = False
        
    def start_download(self, appid):
        """Start download process in background thread"""
        if self.is_downloading:
            return
            
        self.is_downloading = True
        self.current_files = []
        self.download_thread = threading.Thread(target=self._download_worker, args=(appid,))
        self.download_thread.daemon = True
        self.download_thread.start()
        
        # Start UI update loop
        self.parent.after(100, self._check_progress)
        
    def _download_worker(self, appid):
        """Background thread for downloading files"""
        try:
            repo_order = [
                ("kkrmpubg", "ManifestHub"),
                ("dvahana2424-web", "sojogamesdatabase1"),
                ("hammerwebsite12", "sojogames2"),
                ("SteamAutoCracks", "ManifestHub")
            ]
            
            errors = []
            for owner, name in repo_order:
                try:
                    logging.info(f"Checking repository {owner}/{name}")
                    self.result_queue.put(("status", "Adding game to Steam library..."))
                    
                    files = self.parent.list_files_in_branch(owner, name, appid)
                    if files:
                        logging.info(f"Found {len(files)} files in {owner}/{name}")
                        self.total_files = len(files)
                        downloaded = []
                        
                        for i, f in enumerate(files, start=1):
                            try:
                                logging.info(f"Downloading file {i}/{len(files)}: {f}")
                                self.result_queue.put(("status", "Adding game to Steam library..."))
                                self.result_queue.put(("progress", (i, len(files))))
                                
                                path = self.parent.download_file_from_branch(owner, name, f, appid)
                                if path:
                                    logging.info(f"Successfully downloaded {f}")
                                    downloaded.append(path)
                                else:
                                    logging.warning(f"Failed to download {f}")
                                    
                            except Exception as e:
                                error = f"Error downloading {f}: {str(e)}"
                                errors.append(error)
                                logging.error(error)
                                continue
                                
                        if downloaded:
                            msg = f"Successfully downloaded {len(downloaded)} files"
                            logging.info(msg)
                            self.result_queue.put(("status", msg))
                            if errors:
                                logging.warning("Some files failed: " + "; ".join(errors))
                            self.result_queue.put(("complete", downloaded))
                            return
                    else:
                        msg = f"No files found in {owner}/{name}"
                        logging.info(msg)
                        self.result_queue.put(("status", msg))
                            
                except Exception as e:
                    error = f"Error accessing {owner}/{name}: {str(e)}"
                    errors.append(error)
                    logging.error(error)
                    continue
                    
            if errors:
                error_summary = "\n".join(errors)
                msg = "Failed to find or download game files"
                logging.error(f"{msg}: {error_summary}")
                self.result_queue.put(("status", msg))
                self.result_queue.put(("error", f"{msg}. Please try again later."))
            else:
                msg = "Game could not be found in any repository"
                logging.warning(msg)
                self.result_queue.put(("status", msg))
                self.result_queue.put(("complete", []))
                
        except Exception as e:
            self.result_queue.put(("error", str(e)))
        finally:
            self.is_downloading = False
            
    def _check_progress(self):
        """Check for updates from the download thread and update UI"""
        try:
            while True:  # Process all queued updates
                msg_type, data = self.result_queue.get_nowait()
                try:
                    if msg_type == "status":
                        self.parent.progress_text.set(data)
                    elif msg_type == "progress":
                        current, total = data
                        percent = int((current / total) * 100) if total else 0
                        self.parent.progress_percent.set(f"{percent}%")
                        if hasattr(self.parent.progress, "configure"):
                            self.parent.progress.configure(value=current, maximum=total or 1)
                        else:
                            self.parent.progress["value"] = current
                            self.parent.progress["maximum"] = total or 1
                        try:
                            self.parent.update_idletasks()
                        except Exception:
                            pass
                    elif msg_type == "complete":
                        if data:  # If we have downloaded files
                            self.parent.progress_text.set("Adding Denuvo game to Steam library..." if getattr(self.parent, 'download_denuvo_mode', False) else "Adding game to Steam library...")
                            self.parent.update_idletasks()
                            self.parent.copy_files_to_directories(data, denuvo=getattr(self.parent, 'download_denuvo_mode', False))
                            self.parent.progress_text.set("Game successfully added to Steam library!")
                            self.parent.progress_percent.set("100%")
                            if hasattr(self.parent.progress, "configure"):
                                self.parent.progress.configure(value=self.parent.progress["maximum"])
                            else:
                                self.parent.progress["value"] = self.parent.progress["maximum"]
                            if getattr(self.parent, 'progress_hidden_for_add', False):
                                self.parent.progress_card.grid()
                                self.parent.progress_hidden_for_add = False
                            messagebox.showinfo("Success", 
                                                "Game has been successfully added to Steam library.")
                        else:
                            self.parent.progress_text.set("Game not found")
                            self.parent.progress_percent.set("0%")
                            if hasattr(self.parent.progress, "configure"):
                                self.parent.progress.configure(value=0)
                            else:
                                self.parent.progress["value"] = 0
                            if getattr(self.parent, 'progress_hidden_for_add', False):
                                self.parent.progress_card.grid()
                                self.parent.progress_hidden_for_add = False
                            messagebox.showwarning("Not Found", 
                                                   "Game could not be found.\n"
                                                   "Please verify the Game ID and try again.")
                        self.parent.update_add_buttons_state()
                        return  # Stop checking for updates
                    elif msg_type == "error":
                        self.parent.progress_text.set(f"Error: {data}")
                        logging.error(f"Error during installation: {data}")
                        if getattr(self.parent, 'progress_hidden_for_add', False):
                            self.parent.progress_card.grid()
                            self.parent.progress_hidden_for_add = False
                        messagebox.showerror("Download Error", 
                                             f"An error occurred while downloading:\n{data}")
                        self.parent.update_add_buttons_state()
                        return  # Stop checking for updates
                except Exception:
                    logging.exception("DownloadManager._check_progress failed while processing a message")
                    continue
        except queue.Empty:
            pass

        if self.is_downloading or not self.result_queue.empty():
            self.parent.after(100, self._check_progress)
        else:
            self.parent.update_add_buttons_state()

class ManifestDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Set window title with version
        self.title("GameDrop Steam v3.0.1")
        
        # Initialize Firebase
        self.firebase_db = None
        try:
            self.firebase_db = self.init_firebase()
        except Exception as e:
            print(f"Firebase init failed: {e}")
        
        # Check license BEFORE showing UI
        if not self.verify_license():
            self.destroy()
            sys.exit(1)
        
        self.configure(bg='#1E1E1E')  # Dark background

        # Set icon for both window and taskbar
        icon_path = os.path.join(os.path.dirname(__file__), "logo.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            if os.name == "nt":  # Windows specific
                self.wm_iconbitmap(icon_path)  # Set taskbar icon

        self.steam_path = None
        self.selected_game_denuvo = False
        self.download_denuvo_mode = False
        self.load_config()

        # Legacy Lua migration has been removed; keep startup simple and compatible.

        # Create main frame with padding
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Style configuration
        style = ttk.Style()
        style.theme_use('clam')  # Use clam theme as base
        
        # Configure colors
        PRIMARY_COLOR = '#4A90E2'  # Blue
        SECONDARY_COLOR = '#2D5F9A'  # Darker blue
        BG_COLOR = '#1E1E1E'  # Dark background
        ACCENT_COLOR = '#6AB04C'  # Green
        DANGER_COLOR = '#E74C3C'  # Red
        TEXT_COLOR = '#FFFFFF'  # White
        SECONDARY_TEXT = '#B3B3B3'  # Light gray
        LINK_COLOR = '#4A90E2'  # Blue for links
        
        # Configure base styles
        style.configure('.', 
                      background=BG_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10))
        
        style.configure('TFrame', background=BG_COLOR)
        style.configure('TLabelframe', background=BG_COLOR)
        style.configure('TLabelframe.Label', 
                      background=BG_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10, 'bold'))
        
        # Configure label styles
        style.configure('TLabel', 
                      background=BG_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10))
        
        style.configure('Header.TLabel',
                      background=BG_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 12, 'bold'))
        
        style.configure('Status.TLabel',
                      background=BG_COLOR,
                      foreground=SECONDARY_TEXT,
                      font=('Segoe UI', 9))
        
        # Configure button styles
        style.configure('TButton',
                      background=PRIMARY_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10),
                      padding=5)
        
        style.map('TButton',
                 background=[('active', SECONDARY_COLOR),
                           ('disabled', '#404040')],
                 foreground=[('disabled', SECONDARY_TEXT)])
        
        # Configure accent button style
        style.configure('Accent.TButton',
                      background=ACCENT_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10, 'bold'),
                      padding=10)
        
        style.map('Accent.TButton',
                 background=[('active', '#5C9A43'),  # Darker green
                           ('disabled', '#404040')],
                 foreground=[('disabled', SECONDARY_TEXT)])
        
        # Configure danger button style
        style.configure('Danger.TButton',
                      background=DANGER_COLOR,
                      foreground=TEXT_COLOR,
                      font=('Segoe UI', 10, 'bold'),
                      padding=10)
        
        style.map('Danger.TButton',
                 background=[('active', '#C0392B')],  # Darker red
                 foreground=[('active', TEXT_COLOR)])
        
        # Configure entry style
        style.configure('TEntry',
                      fieldbackground='#2D2D2D',
                      foreground=TEXT_COLOR,
                      insertcolor=TEXT_COLOR)
        
        style.map('TEntry',
                 fieldbackground=[('disabled', '#404040')],
                 foreground=[('disabled', SECONDARY_TEXT)])
        
        # Configure progress bar style
        style.configure('Horizontal.TProgressbar',
                      troughcolor='#2D2D2D',
                      background=ACCENT_COLOR,
                      bordercolor=BG_COLOR,
                      lightcolor=BG_COLOR,
                      darkcolor=BG_COLOR)

        style.configure('Link.TLabel',
                      background=BG_COLOR,
                      foreground=LINK_COLOR,
                      font=('Segoe UI', 9, 'underline'),
                      cursor='hand2')

        # Configure contact and promo styles
        style.configure('Link.TLabel',
                      background=BG_COLOR,
                      foreground=LINK_COLOR,
                      font=('Segoe UI', 10, 'underline'),
                      cursor='hand2')
                      
        style.configure('Contact.TFrame',
                      background=BG_COLOR,
                      relief='solid',
                      borderwidth=1)
                      
        style.configure('Contact.TLabel',
                      background=BG_COLOR,
                      foreground=LINK_COLOR,
                      font=('Segoe UI', 11, 'bold'),
                      cursor='hand2')
                      
        style.configure('Promo.TLabel',
                      background=BG_COLOR,
                      foreground='#FFFFFF',
                      font=('Segoe UI', 9))
                      
        style.map('Contact.TLabel',
                 foreground=[('active', '#5CA8FF')],
                 font=[('active', ('Segoe UI', 11, 'bold', 'underline'))])

        # Modern app shell with card-based layout
        self.geometry("980x760")
        self.minsize(900, 720)

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Style configuration
        style = ttk.Style()
        style.theme_use('clam')

        PRIMARY_COLOR = '#2F73C9'
        SECONDARY_COLOR = '#153A5F'
        ACCENT_COLOR = '#4CC76A'
        DANGER_COLOR = '#E74C3C'
        BG_COLOR = '#0F1727'
        PANEL_COLOR = '#161D2F'
        BORDER_COLOR = '#22324E'
        TEXT_COLOR = '#F5F7FB'
        MUTED_COLOR = '#9DB0C8'
        LINK_COLOR = '#5CA8FF'

        style.configure('.', background=BG_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10))
        style.configure('TFrame', background=BG_COLOR)
        style.configure('TLabelframe', background=BG_COLOR)
        style.configure('TLabelframe.Label', background=BG_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'))
        style.configure('TLabel', background=BG_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10))
        style.configure('Card.TFrame', background=PANEL_COLOR, relief='solid', borderwidth=1)
        style.configure('Card.TLabel', background=PANEL_COLOR, foreground=TEXT_COLOR)
        style.configure('Shadow.TFrame', background=PANEL_COLOR, relief='flat', borderwidth=0)
        style.configure('Muted.TLabel', background=PANEL_COLOR, foreground=MUTED_COLOR, font=('Segoe UI', 9))
        style.configure('Header.TLabel', background=PANEL_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 15, 'bold'))
        style.configure('Title.TLabel', background=PANEL_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 22, 'bold'))
        style.configure('Small.TLabel', background=PANEL_COLOR, foreground=MUTED_COLOR, font=('Segoe UI', 9))
        style.configure('Primary.TButton', background=PRIMARY_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'), padding=8)
        style.map('Primary.TButton', background=[('active', SECONDARY_COLOR), ('disabled', '#404040')], foreground=[('disabled', MUTED_COLOR)])
        style.configure('Accent.TButton', background=ACCENT_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'), padding=8)
        style.map('Accent.TButton', background=[('active', '#3FA65A'), ('disabled', '#404040')], foreground=[('disabled', MUTED_COLOR)])
        style.configure('Danger.TButton', background=DANGER_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'), padding=8)
        style.map('Danger.TButton', background=[('active', '#C0392B')], foreground=[('active', TEXT_COLOR)])
        style.configure('Secondary.TButton', background=SECONDARY_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 10, 'bold'), padding=8)
        style.map('Secondary.TButton', background=[('active', PRIMARY_COLOR), ('disabled', '#404040')], foreground=[('disabled', MUTED_COLOR)])
        style.configure('Compact.TButton', background=PRIMARY_COLOR, foreground=TEXT_COLOR, font=('Segoe UI', 9, 'bold'), padding=6)
        style.configure('Tile.TFrame', background='#1B2438', relief='solid', borderwidth=1)
        style.configure('TileActive.TFrame', background='#22324E', relief='solid', borderwidth=1)
        style.configure('TEntry', fieldbackground='#1B2334', foreground=TEXT_COLOR, insertcolor=TEXT_COLOR)
        style.map('TEntry', fieldbackground=[('disabled', '#404040')], foreground=[('disabled', MUTED_COLOR)])
        style.configure('Horizontal.TProgressbar', troughcolor='#1B2334', background=ACCENT_COLOR, bordercolor=PANEL_COLOR, lightcolor=PANEL_COLOR, darkcolor=PANEL_COLOR)
        style.configure('Link.TLabel', background=PANEL_COLOR, foreground=LINK_COLOR, font=('Segoe UI', 9, 'underline'), cursor='hand2')

        # Header
        header_frame = ttk.Frame(main_frame, style='Shadow.TFrame', padding=18)
        header_frame.pack(fill=tk.X, pady=(0, 16))

        header_content = ttk.Frame(header_frame, style='Shadow.TFrame')
        header_content.pack(fill=tk.X)

        brand_panel = tk.Frame(header_content, bg=PRIMARY_COLOR, highlightthickness=0, bd=0)
        brand_panel.pack(fill=tk.X, pady=(0, 12))
        brand_panel.pack_propagate(False)
        brand_panel.configure(height=78)

        logo_frame = tk.Frame(brand_panel, bg=PRIMARY_COLOR)
        logo_frame.pack(side=tk.LEFT, padx=(16, 10), pady=12)
        try:
            if os.path.exists(icon_path):
                ico_image = PIL.Image.open(icon_path)
                if hasattr(ico_image, 'seek'):
                    try:
                        ico_image.seek(0)
                    except EOFError:
                        pass
                height = 34
                ratio = height / ico_image.size[1]
                width = int(ico_image.size[0] * ratio)
                ico_image = ico_image.resize((width, height), PIL.Image.Resampling.LANCZOS)
                logo_image = PIL.ImageTk.PhotoImage(ico_image)
                logo_label = tk.Label(logo_frame, image=logo_image, bg=PRIMARY_COLOR)
                logo_label.image = logo_image
                logo_label.pack()
        except Exception as e:
            print(f"Failed to load logo: {e}")

        title_label = tk.Label(brand_panel, text='GameDrop Steam', bg=PRIMARY_COLOR, fg=TEXT_COLOR, font=('Segoe UI', 18, 'bold'))
        title_label.pack(side=tk.LEFT, pady=12)

        version_badge = tk.Label(brand_panel, text='v3.0.1', bg=SECONDARY_COLOR, fg=TEXT_COLOR, font=('Segoe UI', 9, 'bold'))
        version_badge.pack(side=tk.RIGHT, padx=16, pady=18)

        subtitle = ttk.Label(header_content, text='Modern Steam game setup, activation, and repair tools in one place.', style='Muted.TLabel')
        subtitle.pack(anchor=tk.W)

        # Main content grid
        content_frame = ttk.Frame(main_frame, style='TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)

        sidebar = ttk.Frame(content_frame, style='Card.TFrame', padding=14)
        sidebar.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 10), pady=(0, 12))
        sidebar.columnconfigure(0, weight=1)

        ttk.Label(sidebar, text='Quick Actions', style='Header.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 10))

        def add_tile(parent, row, title, subtitle, command, icon, style_name='Primary.TButton'):
            tile = ttk.Frame(parent, style='Tile.TFrame', padding=10)
            tile.grid(row=row, column=0, sticky='ew', pady=4)
            tile.bind('<Enter>', lambda e, t=tile: t.configure(style='TileActive.TFrame'))
            tile.bind('<Leave>', lambda e, t=tile: t.configure(style='Tile.TFrame'))
            icon_label = ttk.Label(tile, text=icon, font=('Segoe UI', 14), style='Card.TLabel')
            icon_label.pack(anchor='w')
            ttk.Label(tile, text=title, style='Header.TLabel').pack(anchor='w', pady=(2, 0))
            ttk.Label(tile, text=subtitle, style='Muted.TLabel').pack(anchor='w', pady=(2, 6))
            button = ttk.Button(tile, text='Open', command=command, style=style_name)
            button.pack(anchor='w')
            return tile

        add_tile(sidebar, 1, 'Add Game', 'Install a game directly into Steam.', self.start_download, '🎮', 'Accent.TButton')
        add_tile(sidebar, 2, 'Denuvo Add', 'Add a Denuvo-protected game with extra handling.', lambda: self.start_download(denuvo=True), '🛡️', 'Accent.TButton')
        add_tile(sidebar, 3, 'Activation', 'Launch the Denuvo activation helper.', self.launch_tokeerdrm_activation, '⚙️', 'Secondary.TButton')
        add_tile(sidebar, 4, 'OnlineFix', 'Apply OnlineFix or bypass Denuvo.', self.apply_onlinefix, '🔧', 'Primary.TButton')
        add_tile(sidebar, 5, 'Repair', 'Repair GameDrop and Steam integration.', self.repair_gamedrop, '🧰', 'Primary.TButton')

        main_panel = ttk.Frame(content_frame, style='TFrame')
        main_panel.grid(row=0, column=1, sticky='nsew')
        main_panel.columnconfigure(0, weight=1)

        input_card = ttk.Frame(main_panel, style='Card.TFrame', padding=14)
        input_card.grid(row=0, column=0, sticky='nsew', pady=(0, 12))
        input_header = ttk.Label(input_card, text='Game Lookup', style='Header.TLabel')
        input_header.pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(input_card, text='Steam AppID', style='Muted.TLabel').pack(anchor=tk.W)
        self.appid_entry = ttk.Entry(input_card, font=('Segoe UI', 12), width=30)
        self.appid_entry.pack(fill=tk.X, pady=(6, 8))
        self.game_suggestions = GameSuggestionDropdown(input_card, self.appid_entry)
        self.game_suggestions.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(input_card, text='Enter the numeric ID or start typing a game name.', style='Muted.TLabel').pack(anchor=tk.W)

        steam_card = ttk.Frame(main_panel, style='Card.TFrame', padding=14)
        steam_card.grid(row=1, column=0, sticky='nsew', pady=(0, 12))
        steam_header = ttk.Label(steam_card, text='Steam Controls', style='Header.TLabel')
        steam_header.pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(steam_card, text='Keep Steam stable while managing your library.', style='Muted.TLabel').pack(anchor=tk.W, pady=(0, 6))
        self.restart_steam_btn = ttk.Button(steam_card, text='Close Steam', command=self.restart_steam, style='Secondary.TButton')
        self.restart_steam_btn.pack(fill=tk.X, pady=4)
        self.repair_gamedrop_btn = ttk.Button(steam_card, text='Repair GameDrop', command=self.repair_gamedrop, style='Primary.TButton')
        self.repair_gamedrop_btn.pack(fill=tk.X, pady=4)
        self.change_steam_path_btn = ttk.Button(steam_card, text='Change Steam Path', command=self.ask_steam_path, style='Secondary.TButton')
        self.change_steam_path_btn.pack(fill=tk.X, pady=4)

        progress_card = ttk.Frame(main_panel, style='Card.TFrame', padding=14)
        progress_card.grid(row=2, column=0, sticky='nsew')
        progress_header = ttk.Label(progress_card, text='Progress', style='Header.TLabel')
        progress_header.pack(anchor=tk.W, pady=(0, 8))
        progress_info_frame = ttk.Frame(progress_card, style='Card.TFrame', padding=8)
        progress_info_frame.pack(fill=tk.X, pady=(0, 8))
        self.progress_text = tk.StringVar(value='Waiting to add a game...')
        self.progress_label = ttk.Label(progress_info_frame, textvariable=self.progress_text, width=42, anchor=tk.W, font=('Consolas', 10), style='Card.TLabel')
        self.progress_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_percent = tk.StringVar(value='0%')
        self.percent_label = ttk.Label(progress_info_frame, textvariable=self.progress_percent, width=5, anchor=tk.E, style='Card.TLabel')
        self.percent_label.pack(side=tk.RIGHT)
        self.progress_card = progress_card
        self._create_progressbar()

        footer_frame = ttk.Frame(main_frame, style='Card.TFrame', padding=12)
        footer_frame.pack(fill=tk.X, pady=(12, 0))
        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=1)

        def open_facebook(event=None):
            import webbrowser
            webbrowser.open('https://www.facebook.com/GameDropPhl')

        footer_left = ttk.Frame(footer_frame, style='Card.TFrame')
        footer_left.grid(row=0, column=0, sticky='w')
        ttk.Label(footer_left, text='Need help?', style='Muted.TLabel').pack(anchor=tk.W)
        contact_label = ttk.Label(footer_left, text='Contact Support', style='Link.TLabel')
        contact_label.pack(anchor=tk.W)
        fb_label = ttk.Label(footer_left, text='@GameDropPhl', style='Link.TLabel')
        fb_label.pack(anchor=tk.W)

        footer_right = ttk.Frame(footer_frame, style='Card.TFrame')
        footer_right.grid(row=0, column=1, sticky='e')
        ttk.Label(footer_right, text='Follow us on Facebook', style='Muted.TLabel').pack(anchor=tk.E)
        promo_link = ttk.Label(footer_right, text='facebook.com/GameDropPhl', style='Link.TLabel')
        promo_link.pack(anchor=tk.E)

        def on_enter(event):
            widget = event.widget
            widget.configure(foreground='#5CA8FF')

        def on_leave(event):
            widget = event.widget
            widget.configure(foreground=LINK_COLOR)

        for widget in (contact_label, fb_label, promo_link):
            widget.bind('<Button-1>', open_facebook)
            widget.bind('<Enter>', on_enter)
            widget.bind('<Leave>', on_leave)

        # Schedule for updating Apply/Bypass button states based on AppID availability
        self._update_buttons_job = None
        def schedule_update_action_buttons_state(event=None):
            if self._update_buttons_job:
                try:
                    self.after_cancel(self._update_buttons_job)
                except Exception:
                    pass
            self._update_buttons_job = self.after(500, lambda: threading.Thread(target=self._update_action_buttons_state_thread, daemon=True).start())

        self.appid_entry.bind('<KeyRelease>', schedule_update_action_buttons_state, '+')
        self.appid_entry.bind('<FocusOut>', schedule_update_action_buttons_state, '+')
        schedule_update_action_buttons_state()

        self.bind('<Configure>', self.on_window_configure)

        # Center the window after all widgets are created
        self.update_idletasks()  # Update "requested size" from geometry manager

        # Add download manager
        self.download_manager = DownloadManager(self)

        # Add download manager
        self.download_manager = DownloadManager(self)

    def migrate_old_lua_files(self, lua_dir, legacy_dir):
        """Legacy Lua migration is no longer used; keep this as a no-op for compatibility."""
        return False

    def encrypt_value(self, value):
        return fernet.encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted_value):
        return fernet.decrypt(encrypted_value.encode()).decode()

    def ask_password(self):
        # Create a custom dialog with better explanation
        dialog = tk.Toplevel(self)
        dialog.title("Product Activation")
        dialog.geometry("400x250")
        dialog.resizable(False, False)
        
        # Make dialog modal
        dialog.transient(self)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        # Add icon
        icon_path = os.path.join(os.path.dirname(__file__), "logo.ico")
        if os.path.exists(icon_path):
            dialog.iconbitmap(icon_path)
        
        # Create main frame with padding
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Content frame for everything except buttons
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Determine if this is a new device
        is_new_device = not os.path.exists(CONFIG_FILE)
        
        # Header
        header_text = "New Device Detected" if os.path.exists(CONFIG_FILE) else "Product Activation Required"
        ttk.Label(content_frame, text=header_text, 
                 font=('Segoe UI', 14, 'bold')).pack(pady=(0, 10))
        
        # Explanation text
        if os.path.exists(CONFIG_FILE):
            msg = ("This appears to be a different device than previously authorized.\n"
                  "For security reasons, please enter your product key to activate GameDrop on this device.")
        else:
            msg = ("Welcome to GameDrop Steam!\n\n"
                  "To activate the software for first use,\n"
                  "please enter your product key.")
        
        ttk.Label(content_frame, text=msg, wraplength=350).pack(pady=(0, 15))
        
        # Key entry frame
        key_frame = ttk.Frame(content_frame)
        key_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(key_frame, text="Product Key:", 
                 font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=(0, 10))
        
        # Password entry
        pwd_var = tk.StringVar()
        pwd_entry = ttk.Entry(key_frame, show="●", textvariable=pwd_var)
        pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        pwd_entry.focus()
        
        # Result variable
        result = [False]
        
        def validate_password():
            if verify_password(pwd_var.get(), is_new_device=True):
                result[0] = True
                dialog.destroy()
            else:
                pwd_var.set("")
                pwd_entry.focus()
                messagebox.showerror("Invalid Key", 
                                   "The product key you entered is not valid.\n"
                                   "Please check your key and try again.")
        
        # Bind Enter key to validate
        dialog.bind('<Return>', lambda e: validate_password())
        
        # Button frame at the bottom
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Add buttons with proper padding and width
        cancel_btn = ttk.Button(btn_frame, text="Cancel", 
                              command=dialog.destroy, width=12)
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        ok_btn = ttk.Button(btn_frame, text="Activate", 
                           command=validate_password, width=12)
        ok_btn.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Wait for dialog to close
        dialog.wait_window()
        return result[0]

    def get_volume_serial(self):
        try:
            drive = os.environ.get("SystemDrive", "C:")
            if not drive.endswith(":"):
                drive = drive.rstrip("\\/") + ":"
            output = subprocess.check_output(f"vol {drive}", shell=True, text=True, stderr=subprocess.STDOUT)
            match = re.search(r"([0-9A-Fa-f]{4}-[0-9A-Fa-f]{4})", output)
            if match:
                return match.group(1).upper()
        except Exception:
            pass

        try:
            drive = os.environ.get("SystemDrive", "C:")
            if not drive.endswith(":"):
                drive = drive.rstrip("\\/") + ":"
            output = subprocess.check_output(
                f'wmic logicaldisk where "DeviceID=\'{drive}\'" get VolumeSerialNumber /value',
                shell=True,
                text=True,
                stderr=subprocess.STDOUT
            )
            match = re.search(r"VolumeSerialNumber\s*=\s*([0-9A-Fa-f]{8})", output)
            if match:
                serial = match.group(1).upper()
                return f"{serial[:4]}-{serial[4:]}"
        except Exception:
            pass

        return None

    def auto_find_steam_path(self):
        """Automatically find Steam installation path"""
        # Common Steam installation paths
        common_paths = [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
            r"D:\Steam",
            r"E:\Steam",
            r"D:\Program Files (x86)\Steam",
            r"E:\Program Files (x86)\Steam",
        ]
        
        # Try to get Steam path from registry
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            winreg.CloseKey(key)
            if steam_path and os.path.isdir(steam_path):
                return steam_path.replace('/', '\\')  # Normalize path
        except:
            pass
        
        # Check common paths
        for path in common_paths:
            if os.path.isdir(path):
                return path
        
        return None

    def ask_initial_steam_path(self):
        # Try to auto-detect Steam path first
        auto_path = self.auto_find_steam_path()
        
        if auto_path:
            # Found it automatically!
            return auto_path
        
        # Couldn't find it, ask the user
        # Create a custom dialog
        dialog = tk.Toplevel(self)
        dialog.title("Steam Location Setup")
        dialog.geometry("500x280")
        dialog.resizable(False, False)
        
        # Make dialog modal
        dialog.transient(self)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        # Add icon
        icon_path = os.path.join(os.path.dirname(__file__), "logo.ico")
        if os.path.exists(icon_path):
            dialog.iconbitmap(icon_path)
        
        # Create and pack widgets with padding
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        ttk.Label(frame, text="Steam Installation Location", 
                 font=('Segoe UI', 14, 'bold')).pack(pady=(0, 10))
        
        # Explanation text
        msg = ("GameDrop needs to know where Steam is installed on your computer.\n\n"
               "Common locations are:\n"
               "• C:\\Program Files (x86)\\Steam\n"
               "• C:\\Program Files\\Steam\n\n"
               "Please select your Steam installation folder:")
        
        ttk.Label(frame, text=msg, wraplength=450).pack(pady=(0, 15))
        
        # Path entry and browse button
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X, pady=(0, 15))
        
        path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=path_var)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        def browse():
            path = filedialog.askdirectory(title="Select Steam Folder")
            if path:
                path_var.set(path)
        
        ttk.Button(path_frame, text="Browse...", command=browse).pack(side=tk.RIGHT)
        
        # Result variable
        result = [None]
        
        def validate_path():
            path = path_var.get()
            if path and os.path.isdir(path):
                # Check if it's a Steam directory
                steam_exe = os.path.join(path, "steam.exe")
                if os.path.exists(steam_exe):
                    result[0] = path
                    dialog.destroy()
                else:
                    messagebox.showerror("Invalid Directory", 
                                       "The selected folder doesn't appear to be a Steam installation.\n"
                                       "Please make sure you select the correct Steam folder.")
            else:
                messagebox.showerror("Invalid Directory", 
                                   "Please select a valid Steam installation folder.")
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="OK", command=validate_path).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", 
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Try to auto-detect Steam path
        common_paths = [
            "C:\\Program Files (x86)\\Steam",
            "C:\\Program Files\\Steam",
            os.path.expanduser("~\\Steam")
        ]
        
        for path in common_paths:
            if os.path.exists(os.path.join(path, "steam.exe")):
                path_var.set(path)
                break
        
        # Wait for dialog to close
        dialog.wait_window()
        
        if result[0] is None:
            # If user cancelled, show error and exit
            messagebox.showerror("Setup Required", 
                               "GameDrop cannot function without a valid Steam installation path.\n"
                               "The application will now close.")
            self.destroy()
            sys.exit()
            
        return result[0]

    def get_encryption_key(self):
        """Generate encryption key from machine GUID"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SOFTWARE\Microsoft\Cryptography',
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            machine_guid, _ = winreg.QueryValueEx(key, 'MachineGuid')
            winreg.CloseKey(key)
            # Create Fernet key from machine GUID
            import base64
            key_bytes = hashlib.sha256(machine_guid.encode()).digest()
            return base64.urlsafe_b64encode(key_bytes)
        except:
            # Fallback key
            import base64
            return base64.urlsafe_b64encode(hashlib.sha256(b"GameDrop-Fallback-Key").digest())

    def get_license_path(self):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(app_dir, "license.key")

    def write_license_file(self, license_key):
        try:
            license_data = (
                f"LICENSE={license_key}\n"
                f"HWID={self.get_encryption_key() and self.get_encryption_key()}\n"
            )
            # Use actual hardware ID instead of encrypted key string
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'SOFTWARE\Microsoft\Cryptography',
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                )
                machine_guid, _ = winreg.QueryValueEx(key, 'MachineGuid')
                winreg.CloseKey(key)
                hardware_id = machine_guid
            except:
                import getpass
                import socket
                hardware_id = f"{socket.gethostname()}-{getpass.getuser()}"

            license_data = (
                f"LICENSE={license_key}\n"
                f"HWID={hardware_id}\n"
            )
            from cryptography.fernet import Fernet
            fernet = Fernet(self.get_encryption_key())
            encrypted_data = fernet.encrypt(license_data.encode())
            with open(self.get_license_path(), 'wb') as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            messagebox.showerror("License Error", f"Failed to save license file:\n{e}")
            return False

    def prompt_for_license(self):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        result = [False]
        prompt = tk.Tk()
        prompt.title("GameDrop License Activation")
        prompt.resizable(False, False)
        prompt.geometry("520x280")
        prompt.attributes('-topmost', True)

        tk.Label(prompt, text="GameDrop License Activation", font=("Segoe UI", 14, "bold")).pack(pady=(20, 10))
        tk.Label(
            prompt,
            text="Please enter your license key to activate GameDrop.\nEach license is locked to one device only.",
            font=("Segoe UI", 10),
            justify='center'
        ).pack(pady=(0, 10))

        license_var = tk.StringVar()
        entry = tk.Entry(prompt, textvariable=license_var, font=("Courier", 11), width=40, justify='center')
        entry.pack(pady=5)
        entry.focus()

        tk.Label(
            prompt,
            text="Format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",
            font=("Segoe UI", 8),
            fg="#666"
        ).pack()

        def on_activate():
            license_key = license_var.get().strip().upper()
            if not license_key:
                messagebox.showwarning("License Required", "Please enter a license key!")
                return
            if len(license_key) != 39 or license_key.count('-') != 7:
                messagebox.showerror("License Error", "Invalid license key format.\nExpected format:\nXXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
                return
            if self.write_license_file(license_key):
                messagebox.showinfo("License Activated", "✅ License activated successfully. GameDrop will now continue.")
                result[0] = True
                prompt.destroy()

        buttons = tk.Frame(prompt)
        buttons.pack(pady=20)
        tk.Button(buttons, text="Activate License", command=on_activate, width=18, bg="#4CAF50", fg="white", font=("Segoe UI", 10, "bold")).pack(side='left', padx=10)
        tk.Button(buttons, text="Cancel", command=prompt.destroy, width=18, bg="#f44336", fg="white", font=("Segoe UI", 10, "bold")).pack(side='right', padx=10)

        prompt.bind('<Return>', lambda e: on_activate())
        prompt.mainloop()
        return result[0]

    def verify_license(self):
        """Verify license.key exists and matches this device (encrypted)"""
        if os.environ.get('GAMEDROP_DEBUG_BYPASS_LICENSE') == 'true':
            logging.info("Debug license bypass enabled; skipping license validation")
            return True

        license_file = self.get_license_path()
        
        # Check if license file exists
        if not os.path.exists(license_file):
            self.withdraw()  # Hide window
            if self.prompt_for_license():
                self.deiconify()
                return True
            return False
        
        try:
            # Read encrypted license file
            with open(license_file, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt the data
            from cryptography.fernet import Fernet
            fernet = Fernet(self.get_encryption_key())
            decrypted_data = fernet.decrypt(encrypted_data).decode()
            
            # Parse the decrypted data
            license_data = {}
            for line in decrypted_data.split('\n'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    license_data[key] = value
            
            # Get current hardware ID
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'SOFTWARE\Microsoft\Cryptography',
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                )
                current_hwid, _ = winreg.QueryValueEx(key, 'MachineGuid')
                winreg.CloseKey(key)
            except:
                import getpass
                import socket
                current_hwid = f"{socket.gethostname()}-{getpass.getuser()}"
            
            # Compare hardware IDs
            stored_hwid = license_data.get('HWID', '')
            if stored_hwid != current_hwid:
                self.withdraw()  # Hide window
                messagebox.showerror(
                    "License Error",
                    "❌ Invalid License!\n\n"
                    "This license is locked to a different device.\n"
                    "Each license can only be used on one computer.\n\n"
                    "Please contact support if you need a new license."
                )
                return False
            
            # License is valid locally - now check online
            stored_license = license_data.get('LICENSE', '')
            if self.firebase_db and stored_license:
                valid_online, message = self.check_license_status_online(stored_license, current_hwid)
                # Confirm once more before treating as revoked to avoid false negatives from transient reads.
                if not valid_online:
                    time.sleep(2)
                    retry_valid, retry_message = self.check_license_status_online(stored_license, current_hwid)
                    if retry_valid:
                        valid_online = True
                        message = retry_message
                if not valid_online:
                    # License was revoked/deleted - remove local file
                    try:
                        os.remove(self.get_license_path())
                    except:
                        pass

                    self.withdraw()  # Hide window
                    if self.prompt_for_license():
                        self.deiconify()
                        return True

                    messagebox.showerror(
                        "License Revoked",
                        "❌ Your license has been revoked!\n\n"
                        "Please run GameDrop.exe (the launcher) to enter a new license key.\n\n"
                        "Contact support if you need assistance."
                    )

                    # Restart Steam to disable protected files
                    restart_steam_process()

                    return False
            
            # License is valid
            return True
            
        except Exception as e:
            self.withdraw()  # Hide window
            if self.prompt_for_license():
                self.deiconify()
                return True
            messagebox.showerror(
                "License Error",
                f"❌ Failed to verify license:\n{e}\n\n"
                "Please run GameDrop.exe (the launcher) to reactivate."
            )
            return False
    
    def check_license_status_online(self, license_key, hwid):
        """Check if license is still valid in Firebase"""
        if not self.firebase_db:
            return True, "Offline mode"
        
        try:
            license_doc = self.firebase_db.collection('licenses').document(license_key).get()
            
            if not license_doc.exists:
                return False, "License not found in database (may have been deleted)"
            
            license_data = license_doc.to_dict()
            
            # Check if used/activated
            if not license_data.get('used', False):
                return False, "License is no longer activated"
            
            # Check hardware ID
            stored_hwid = license_data.get('hardware_id', '')
            if stored_hwid != hwid:
                return False, "License hardware ID mismatch"
            
            return True, "License is valid"
        
        except Exception as e:
            # If online check fails (no internet), allow offline usage
            print(f"Warning: Online check failed: {e}")
            return True, "Using cached license (offline)"
    
    def init_firebase(self):
        """Initialize Firebase with encrypted credentials"""
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            from firebase_encrypted import get_firebase_creds
            
            # Get encrypted credentials
            encrypted_creds = get_firebase_creds()
            
            # Decrypt the credentials
            from cryptography.fernet import Fernet
            fernet = Fernet(self.get_encryption_key())
            decrypted_creds = fernet.decrypt(encrypted_creds.encode()).decode()
            
            # Create a temporary JSON file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                tmp_file.write(decrypted_creds)
                tmp_path = tmp_file.name
            
            # Initialize Firebase
            cred = credentials.Certificate(tmp_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            
            # Delete the temporary file
            try:
                os.remove(tmp_path)
            except:
                pass
            
            return db
        except Exception as e:
            print(f"Firebase init error: {e}")
            return None

    def load_config(self):
        # License is now handled by the launcher, so we skip the old password check
        current_serial = self.get_volume_serial()
        if not current_serial:
            messagebox.showerror("Error", "Failed to detect machine serial. Cannot continue.")
            self.destroy()
            sys.exit()

        if not os.path.exists(CONFIG_FILE):
            # First time setup - just ask for Steam path (no password needed)
            self.steam_path = self.ask_initial_steam_path()
            config = {
                "machine_serial": self.encrypt_value(current_serial),
                "steam_path": self.encrypt_value(self.steam_path)
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f)
        else:
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                stored_serial_enc = config.get("machine_serial")
                stored_serial = self.decrypt_value(stored_serial_enc) if stored_serial_enc else None

                if stored_serial != current_serial:
                    # Device changed - update machine serial (no password needed)
                    config["machine_serial"] = self.encrypt_value(current_serial)
                    with open(CONFIG_FILE, "w") as f:
                        json.dump(config, f)

                steam_path_enc = config.get("steam_path")
                self.steam_path = self.decrypt_value(steam_path_enc) if steam_path_enc else None

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load or decrypt config: {e}")
                self.destroy()
                sys.exit()

        if not self.steam_path or not os.path.isdir(self.steam_path):
            self.ask_steam_path()

        if self.steam_path and os.path.isdir(self.steam_path):
            try:
                self.cleanup_stplugin_lua_files(self.steam_path)
            except Exception as e:
                logging.warning(f"Initial stplug-in Lua cleanup failed: {e}")

    def save_config(self):
        config = {
            "steam_path": self.encrypt_value(self.steam_path)
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    current_config = json.load(f)
                if "machine_serial" in current_config:
                    config["machine_serial"] = current_config["machine_serial"]
            except Exception:
                pass
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)

    def on_window_configure(self, event):
        """Handle window movement/resize events to update popup position"""
        # Only handle events for the main window (not child widgets)
        if event.widget == self:
            # Update popup position if it's currently visible
            if hasattr(self.game_suggestions, 'popup') and self.game_suggestions.popup:
                if self.game_suggestions.popup.winfo_viewable():
                    self.game_suggestions.update_popup_position()

    def ask_steam_path(self):
        # Try to auto-detect first
        auto_path = self.auto_find_steam_path()
        
        if auto_path:
            # Ask if user wants to use the detected path
            response = messagebox.askyesno(
                "Steam Detected",
                f"Steam installation found at:\n{auto_path}\n\nUse this location?",
                icon='question'
            )
            if response:
                self.steam_path = auto_path
                self.save_config()
                messagebox.showinfo("Success", "Steam path updated successfully!")
                return
        
        # Either not found or user said no, let them browse
        path = filedialog.askdirectory(title="Select Steam Folder")
        if path and os.path.isdir(path):
            self.steam_path = path
            self.save_config()
            messagebox.showinfo("Success", "Steam path updated successfully!")
        else:
            messagebox.showerror("Error", "You must select a valid Steam folder to continue")

    def list_files_in_branch(self, repo_owner, repo_name, branch):
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents?ref={branch}"
        try:
            logging.debug(f"Attempting to list files from {url}")
            logging.debug(f"Using headers: {HEADERS}")
            
            resp = requests.get(url, headers=HEADERS, timeout=10)
            logging.debug(f"GitHub API Response Status: {resp.status_code}")
            logging.debug(f"GitHub API Response Headers: {resp.headers}")
            logging.debug(f"GitHub API Response Body: {resp.text[:500]}")  # Log first 500 chars
            
            if resp.status_code == 404:
                logging.warning(f"Repository or branch not found: {repo_owner}/{repo_name} branch {branch}")
                return []
            elif resp.status_code == 403:
                logging.error(f"GitHub API rate limit exceeded or token invalid. Response: {resp.text}")
                raise Exception("GitHub API access denied. Please try again later.")
            elif resp.status_code != 200:
                logging.error(f"GitHub API error: {resp.status_code} - {resp.text}")
                raise Exception(f"GitHub API error: {resp.status_code}")
                
            items = resp.json()
            if not items:
                logging.warning(f"No files found in {repo_owner}/{repo_name} branch {branch}")
                return []
                
            file_list = [item['name'] for item in items if item['type'] == 'file']
            logging.debug(f"Found files: {file_list}")
            return file_list
            
        except requests.exceptions.Timeout:
            logging.error("GitHub API request timed out")
            raise Exception("Connection to GitHub timed out. Please check your internet connection.")
        except requests.exceptions.RequestException as e:
            logging.error(f"GitHub API request failed: {str(e)}")
            raise Exception("Failed to connect to GitHub. Please check your internet connection.")
        except Exception as e:
            logging.error(f"Unexpected error in list_files_in_branch: {str(e)}")
            raise

    def download_file_from_branch(self, repo_owner, repo_name, filename, branch):
        url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{filename}"
        try:
            logging.debug(f"Attempting to download file from {url}")
            
            resp = requests.get(url, headers=HEADERS, timeout=10)
            logging.debug(f"GitHub Download Response Status: {resp.status_code}")
            
            if resp.status_code == 404:
                logging.warning(f"File not found: {filename} in {repo_owner}/{repo_name} branch {branch}")
                return None
            elif resp.status_code == 403:
                logging.error(f"GitHub API rate limit exceeded or token invalid. Response: {resp.text}")
                raise Exception("GitHub API access denied. Please try again later.")
            elif resp.status_code != 200:
                logging.error(f"GitHub API error: {resp.status_code} - {resp.text}")
                raise Exception(f"GitHub API error: {resp.status_code}")
                
            os.makedirs(SAVE_DIR, exist_ok=True)
            local_path = os.path.join(SAVE_DIR, filename)
            
            try:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                logging.debug(f"Successfully downloaded and saved file to {local_path}")
                return local_path
            except IOError as e:
                logging.error(f"Failed to write file {local_path}: {str(e)}")
                raise Exception(f"Failed to save file {filename}. Please check disk space and permissions.")
                
        except requests.exceptions.Timeout:
            logging.error("GitHub API request timed out")
            raise Exception("Connection to GitHub timed out. Please check your internet connection.")
        except requests.exceptions.RequestException as e:
            logging.error(f"GitHub API request failed: {str(e)}")
            raise Exception("Failed to connect to GitHub. Please check your internet connection.")
        except Exception as e:
            logging.error(f"Unexpected error in download_file_from_branch: {str(e)}")
            raise

    def download_branch_text_file(self, repo_owner, repo_name, filename, branch):
        """Download a text metadata file from a GitHub branch if it exists."""
        url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{filename}"
        try:
            logging.debug(f"Attempting to download branch text file from {url}")
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 404:
                return None
            if resp.status_code == 403:
                logging.error(f"GitHub API rate limit exceeded or token invalid. Response: {resp.text}")
                raise Exception("GitHub API access denied. Please try again later.")
            if resp.status_code != 200:
                logging.error(f"GitHub API error: {resp.status_code} - {resp.text}")
                return None
            return resp.text
        except requests.exceptions.RequestException as e:
            logging.error(f"GitHub API request failed: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in download_branch_text_file: {str(e)}")
            return None

    def download_url_to_temp(self, url, temp_dir, filename_hint=None):
        """Download a URL to a temporary file and return the local path."""
        try:
            os.makedirs(temp_dir, exist_ok=True)
            base_name = os.path.basename(url.split('?')[0]) or filename_hint or 'downloaded_asset'
            local_path = os.path.join(temp_dir, base_name)
            with requests.get(url, headers=HEADERS, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    logging.error(f"Failed to download URL {url}: status {resp.status_code}")
                    return None
                with open(local_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            logging.info(f"Downloaded release asset to {local_path}")
            return local_path
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download URL {url}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error downloading URL {url}: {e}")
            return None

    def get_hidden_subprocess_kwargs(self):
        """Return subprocess kwargs that hide console windows on Windows."""
        kwargs = {}
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return kwargs

    def find_local_archive_extractor(self):
        """Return a locally installed archive extractor path if available."""
        candidates = [shutil.which('7z'), shutil.which('7za'), shutil.which('unrar')]
        for candidate in candidates:
            if candidate:
                return candidate

        common_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            r"C:\Program Files\7-Zip\7za.exe",
            r"C:\Program Files (x86)\7-Zip\7za.exe",
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
            r"C:\Program Files\WinRAR\Rar.exe",
            r"C:\Program Files (x86)\WinRAR\Rar.exe",
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path

        return None

    def get_portable_7za(self, temp_dir):
        """Download and extract portable 7za.exe from the official 7-Zip zip package."""
        archive_name = '7za920.zip'
        download_url = 'https://www.7-zip.org/a/7za920.zip'
        zip_path = os.path.join(temp_dir, archive_name)

        if not os.path.exists(zip_path):
            downloaded = self.download_url_to_temp(download_url, temp_dir, archive_name)
            if not downloaded:
                logging.error('Failed to download portable 7-Zip extractor')
                return None

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.namelist():
                    if member.lower().endswith('7z.exe') or member.lower().endswith('7za.exe'):
                        target = os.path.join(temp_dir, os.path.basename(member))
                        if not os.path.exists(target):
                            zf.extract(member, temp_dir)
                            extracted_path = os.path.join(temp_dir, member)
                            if os.path.exists(extracted_path) and extracted_path != target:
                                os.replace(extracted_path, target)
                        return target
        except Exception as e:
            logging.error(f'Failed to extract portable 7-Zip: {e}')
            return None

        logging.error('Portable 7-Zip extractor not found in downloaded archive')
        return None

    def extract_modern_7z_from_installer(self, temp_dir, helper_extractor):
        """Extract a modern 7z.exe from the latest 7-Zip installer using helper 7za."""
        installer_name = '7z2405-x64.exe'
        installer_url = 'https://twds.dl.sourceforge.net/project/sevenzip/7-Zip/24.05/7z2405-x64.exe'
        installer_path = os.path.join(temp_dir, installer_name)

        if not os.path.exists(installer_path):
            downloaded = self.download_url_to_temp(installer_url, temp_dir, installer_name)
            if not downloaded:
                logging.error('Failed to download modern 7-Zip installer')
                return None

        modern_exe = os.path.join(temp_dir, '7z.exe')
        if os.path.exists(modern_exe):
            return modern_exe

        try:
            result = subprocess.run([helper_extractor, 'x', '-y', installer_path, f'-o{temp_dir}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **self.get_hidden_subprocess_kwargs())
            if result.returncode != 0:
                logging.error(f'Failed to extract modern 7-Zip from installer: {result.stderr}')
                return None

            for root, dirs, files in os.walk(temp_dir):
                if '7z.exe' in files:
                    return os.path.join(root, '7z.exe')
        except Exception as e:
            logging.error(f'Error extracting modern 7-Zip from installer: {e}')
            return None

        logging.error('Modern 7z executable not found after installer extraction')
        return None

    def get_archive_extractor(self, force_modern=False):
        """Return a local extractor path, or download a modern 7-Zip extractor when needed."""
        extractor = self.find_local_archive_extractor()
        if extractor and not force_modern:
            if extractor.lower().endswith(('unrar.exe', 'rar.exe')):
                logging.info('Local UnRAR/RAR found, but preferring modern 7-Zip if available for RAR/7z extraction')
            else:
                return extractor

        logging.info('No suitable local archive extractor found or forced modern extractor requested; attempting to download portable 7-Zip')
        temp_dir = os.path.join(tempfile.gettempdir(), 'gamedrop_extractor')
        os.makedirs(temp_dir, exist_ok=True)

        helper_extractor = self.get_portable_7za(temp_dir)
        if not helper_extractor:
            return extractor

        modern_extractor = self.extract_modern_7z_from_installer(temp_dir, helper_extractor)
        if modern_extractor:
            return modern_extractor

        return helper_extractor if helper_extractor else extractor

    def extract_archive_to_dir(self, archive_path, extract_dir):
        """Extract a supported archive to a directory."""
        try:
            os.makedirs(extract_dir, exist_ok=True)
            lower = archive_path.lower()
            if lower.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_dir)
                return extract_dir
            elif lower.endswith(('.tar.gz', '.tgz', '.tar')):
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(extract_dir)
                return extract_dir
            elif lower.endswith(('.7z', '.rar')):
                extractor = self.get_archive_extractor()
                if not extractor:
                    logging.error('No archive extractor available for 7z/rar files')
                    return None

                def run_extractor(path_to_extractor):
                    if path_to_extractor.lower().endswith('unrar'):
                        temp_extract = os.path.join(os.path.dirname(extract_dir), 'temp_unrar')
                        os.makedirs(temp_extract, exist_ok=True)
                        cmd = [path_to_extractor, 'x', '-y', archive_path, temp_extract]
                    else:
                        temp_extract = None
                        cmd = [path_to_extractor, 'x', '-y', archive_path, f'-o{extract_dir}']
                    logging.info(f"Running extraction command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **self.get_hidden_subprocess_kwargs())
                    logging.info(f"Extraction return code: {result.returncode}")
                    if result.stderr:
                        logging.info(f"Extraction stderr: {result.stderr}")
                    return result, temp_extract

                result, temp_extract = run_extractor(extractor)
                if result.returncode != 0:
                    logging.warning('Initial archive extractor failed; attempting fallback modern extractor')
                    modern_extractor = self.get_archive_extractor(force_modern=True)
                    if modern_extractor and os.path.abspath(modern_extractor) != os.path.abspath(extractor):
                        result, temp_extract = run_extractor(modern_extractor)
                    if result.returncode != 0:
                        logging.error(f"Archive extraction failed: {result.stderr}")
                        return None

                # For UnRAR, move extracted files from temp to target, flattening single subfolder if needed
                if temp_extract:
                    if not os.path.exists(temp_extract) or not os.listdir(temp_extract):
                        logging.warning(f"UnRAR extraction directory empty: {temp_extract}")
                        return None
                    temp_items = os.listdir(temp_extract)
                    # If archive extracted to a single subdirectory (like "3764200"), flatten it
                    if len(temp_items) == 1 and os.path.isdir(os.path.join(temp_extract, temp_items[0])):
                        source_dir = os.path.join(temp_extract, temp_items[0])
                        logging.info(f"Flattening single extracted directory: {temp_items[0]}")
                        for item in os.listdir(source_dir):
                            src = os.path.join(source_dir, item)
                            dst = os.path.join(extract_dir, item)
                            import shutil
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst)
                                shutil.move(src, dst)
                            else:
                                if os.path.exists(dst):
                                    os.remove(dst)
                                shutil.move(src, dst)
                    else:
                        # Multiple items or files at root level, move everything
                        import shutil
                        for item in temp_items:
                            src = os.path.join(temp_extract, item)
                            dst = os.path.join(extract_dir, item)
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst)
                                shutil.move(src, dst)
                            else:
                                if os.path.exists(dst):
                                    os.remove(dst)
                                shutil.move(src, dst)
                    import shutil
                    shutil.rmtree(temp_extract)
                if os.path.exists(extract_dir) and os.listdir(extract_dir):
                    return extract_dir
                else:
                    logging.warning(f"Extraction directory empty or missing: {extract_dir}")
                    return None
                # For UnRAR, move extracted files from temp to target, flattening single subfolder if needed
                if temp_extract:
                    if not os.path.exists(temp_extract) or not os.listdir(temp_extract):
                        logging.warning(f"UnRAR extraction directory empty: {temp_extract}")
                        return None
                    temp_items = os.listdir(temp_extract)
                    # If archive extracted to a single subdirectory (like "3764200"), flatten it
                    if len(temp_items) == 1 and os.path.isdir(os.path.join(temp_extract, temp_items[0])):
                        source_dir = os.path.join(temp_extract, temp_items[0])
                        logging.info(f"Flattening single extracted directory: {temp_items[0]}")
                        for item in os.listdir(source_dir):
                            src = os.path.join(source_dir, item)
                            dst = os.path.join(extract_dir, item)
                            import shutil
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst)
                                shutil.move(src, dst)
                            else:
                                if os.path.exists(dst):
                                    os.remove(dst)
                                shutil.move(src, dst)
                    else:
                        # Multiple items or files at root level, move everything
                        import shutil
                        for item in temp_items:
                            src = os.path.join(temp_extract, item)
                            dst = os.path.join(extract_dir, item)
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst)
                                shutil.move(src, dst)
                            else:
                                if os.path.exists(dst):
                                    os.remove(dst)
                                shutil.move(src, dst)
                    import shutil
                    shutil.rmtree(temp_extract)
                if os.path.exists(extract_dir) and os.listdir(extract_dir):
                    return extract_dir
                else:
                    logging.warning(f"Extraction directory empty or missing: {extract_dir}")
                    return None
            else:
                logging.info(f"Downloaded file is not an archive: {archive_path}")
                return None
        except Exception as e:
            logging.error(f"Error extracting archive {archive_path}: {e}")
            return None

    def get_onlinefix_branch_metadata(self, repo_owner, repo_name, branch):
        """Try to read metadata from a branch to download a release asset instead of raw files."""
        metadata_files = ['onlinefix.json', 'release_url.txt', 'bypass_url.txt', 'manifest_url.txt']
        for filename in metadata_files:
            content = self.download_branch_text_file(repo_owner, repo_name, filename, branch)
            if not content:
                continue
            try:
                if filename.endswith('.json'):
                    return json.loads(content)
                url = content.strip().splitlines()[0].strip()
                if url:
                    return {'type': 'release', 'url': url}
            except Exception as e:
                logging.warning(f"Failed to parse metadata file {filename}: {e}")
                continue
        return None

    def find_github_release_asset_url(self, repo_owner, repo_name, appid):
        """Search GitHub releases for an asset matching the AppID."""
        try:
            api_urls = [
                f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{appid}",
                f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"
            ]
            appid_str = str(appid)
            for api_url in api_urls:
                resp = requests.get(api_url, headers=HEADERS, timeout=10)
                if resp.status_code == 404:
                    continue
                if resp.status_code != 200:
                    logging.warning(f"GitHub release API returned {resp.status_code} for {api_url}")
                    continue
                releases = resp.json() if isinstance(resp.json(), list) else [resp.json()]
                for release in releases:
                    tag_name = str(release.get('tag_name', '')).lower()
                    release_name = str(release.get('name', '')).lower()
                    release_body = str(release.get('body', '')).lower()
                    release_match = (appid_str in tag_name or appid_str in release_name or appid_str in release_body)
                    assets = release.get('assets', [])
                    for asset in assets:
                        name = asset.get('name', '').lower()
                        url = asset.get('browser_download_url')
                        if not url:
                            continue
                        if release_match:
                            if any(name.endswith(ext) for ext in ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz')):
                                logging.info(f"Found GitHub release asset {name} for AppID {appid} via release metadata")
                                return url
                        if appid_str in name or name.startswith(appid_str):
                            logging.info(f"Found GitHub release asset {name} for AppID {appid}")
                            return url
                    if release_match and assets:
                        # As a last resort, return the first archive asset from the matching release.
                        for fallback_asset in assets:
                            fallback_name = fallback_asset.get('name', '').lower()
                            fallback_url = fallback_asset.get('browser_download_url')
                            if fallback_url and any(fallback_name.endswith(ext) for ext in ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz')):
                                logging.info(f"Found GitHub release asset {fallback_asset.get('name')} for AppID {appid} via release metadata fallback")
                                return fallback_url
            return None
        except Exception as e:
            logging.error(f"Error searching GitHub release assets: {e}")
            return None

    def download_release_asset(self, release_info, temp_dir, appid):
        """Download a release asset from a metadata URL and extract it if needed."""
        if not release_info:
            return None
        url = release_info.get('url')
        if not url:
            return None
        archive_path = self.download_url_to_temp(url, temp_dir, f"{appid}_release")
        if not archive_path:
            return None
        extract_dir = os.path.join(temp_dir, 'extracted')
        extracted = self.extract_archive_to_dir(archive_path, extract_dir)
        if extracted:
            return extracted
        return None

    def test_github_connection(self):
        """Test the GitHub connection and token validity."""
        test_url = "https://api.github.com/rate_limit"
        try:
            logging.info("Testing GitHub connection...")
            resp = requests.get(test_url, headers=HEADERS, timeout=10)
            
            if resp.status_code == 200:
                rate_info = resp.json()
                remaining = rate_info.get('rate', {}).get('remaining', 0)
                logging.info(f"GitHub connection successful. Remaining API calls: {remaining}")
                return True
            elif resp.status_code == 403:
                logging.error(f"GitHub token invalid or expired. Response: {resp.text}")
                return False
            else:
                logging.error(f"GitHub API error: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logging.error(f"GitHub connection test failed: {str(e)}")
            return False

    def launch_tokeerdrm_activation(self):
        """Launch the standalone GameDrop activation helper."""
        try:
            exe_path = find_activation_executable()
            if not exe_path:
                messagebox.showerror(
                    "GameDrop Activation Helper Not Found",
                    "Could not find GameDropActivation_Client.exe. Please place it next to the app or in the dist folder.",
                    parent=self
                )
                return

            launch_activation_executable(exe_path)
            messagebox.showinfo(
                "GameDrop Activation Launched",
                "The GameDrop activation helper has been opened. Use the Activate tab to enter your code.",
                parent=self
            )
        except Exception as exc:
            messagebox.showerror("Launch Failed", f"Could not launch the GameDrop activation helper: {exc}", parent=self)

    def start_download(self, denuvo=None):
        # Extract AppID from the entry text (handles both direct ID and "AppID - Name" format)
        entry_text = self.appid_entry.get().strip()
        if ' - ' in entry_text:
            appid = entry_text.split(' - ')[0].strip()
        else:
            appid = entry_text.strip()
            
        if not appid.isdigit():
            messagebox.showerror("Error", "Please enter a valid Steam Game ID")
            return

        self._reset_progressbar()
        self.download_denuvo_mode = bool(denuvo)
        self.download_btn.config(state="disabled")
        self.add_denuvo_btn.config(state="disabled")
        self.progress_hidden_for_add = True
        self.progress_card.grid_remove()
        self.progress["value"] = 0
        self.progress_percent.set("0%")

        self.progress_text.set("Adding Denuvo game to Steam library..." if self.download_denuvo_mode else "Adding game to Steam library...")
        self.update_idletasks()

        # Test GitHub connection first
        if not self.test_github_connection():
            self.progress_text.set("Error: Cannot connect to game servers")
            self.download_btn.config(state="normal")
            if getattr(self, 'progress_hidden_for_add', False):
                self.progress_card.grid()
                self.progress_hidden_for_add = False
            messagebox.showerror("Connection Error", 
                               "Cannot connect to game servers.\n"
                               "Please check your internet connection and try again.")
            return

        # Start download in background
        self.download_manager.start_download(appid)

    def copy_files_to_directories(self, file_paths, denuvo=False):
        # Resolve Steam base path -- prefer selected path, otherwise try auto-find
        steam_base = self.steam_path or self.auto_find_steam_path()
        if not steam_base:
            logging.error("Steam path could not be determined; cannot copy files to Steam.")
            messagebox.showerror("Steam Path Not Found",
                                 "Steam installation path could not be detected. Please configure the correct Steam path and try again.")
            return

        manifest_dir = os.path.join(steam_base, "config", "depotcache")
        lua_dir = os.path.join(steam_base, "config", "lua")

        for path in file_paths:
            ext = os.path.splitext(path)[1].lower()

            if ext == ".manifest":
                if manifest_dir:
                    target_dir = manifest_dir
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.copy2(path, os.path.join(target_dir, os.path.basename(path)))
                    except Exception as e:
                        logging.error(f"Copy failed: {e}")
                continue

            if ext == ".lua":
                try:
                    os.makedirs(lua_dir, exist_ok=True)
                    lua_target = os.path.join(lua_dir, os.path.basename(path))
                    if denuvo:
                        self.modify_lua_file(path, lua_target, comment_out=True)
                    else:
                        self.modify_lua_file(path, lua_target, comment_out=False)
                except Exception as e:
                    logging.error(f"Lua file copy failed: {e}")
                continue

            # Ignore other file types

        # Remove source temp files after copying
        for f in file_paths:
            try:
                os.remove(f)
            except Exception as e:
                logging.error(f"Failed to delete {f}: {e}")

    def cleanup_stplugin_lua_files(self, steam_root):
        """Remove legacy Lua files from Steam's stplug-in directory if present."""
        try:
            stplugin_dir = os.path.join(steam_root, "config", "stplug-in")
            if not os.path.isdir(stplugin_dir):
                return 0

            removed_count = 0
            for filename in os.listdir(stplugin_dir):
                lower_name = filename.lower()
                if lower_name.endswith('.lua') or lower_name.endswith('.lua.disabled'):
                    try:
                        os.remove(os.path.join(stplugin_dir, filename))
                        removed_count += 1
                        logging.info(f"Removed legacy Lua file from stplug-in: {filename}")
                    except Exception as e:
                        logging.warning(f"Failed to remove Lua file from stplug-in: {filename}: {e}")

            if removed_count:
                logging.info(f"Removed {removed_count} Lua files from {stplugin_dir}")
            return removed_count
        except Exception as e:
            logging.warning(f"Failed to cleanup stplug-in Lua files for {steam_root}: {e}")
            return 0

    def modify_lua_file(self, source_path, target_path, comment_out=True):
        """Toggle Denuvo manifest calls in a .lua file.

        comment_out=True disables the manifest lines by adding '--' at the start.
        comment_out=False re-enables them by removing an existing '--'.
        """
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if comment_out:
                modified_content = re.sub(
                    r'(?mi)^(?P<indent>\s*)(?!\s*--)(?P<code>.*\b(setManifestid|setManifest)\b.*)$',
                    r'\1--\2',
                    content
                )
            else:
                modified_content = re.sub(
                    r'(?mi)^(?P<indent>\s*)--\s*(?P<code>.*\b(setManifestid|setManifest)\b.*)$',
                    r'\1\2',
                    content
                )
            
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
                
            print(f"Modified .lua file: {os.path.basename(target_path)}")
            logging.info(f"Modified .lua file: {os.path.basename(target_path)}")
            
        except Exception as e:
            # If modification fails, just copy the original file
            shutil.copy2(source_path, target_path)
            logging.warning(f"Failed to modify .lua file, copied original: {e}")
            print(f"Failed to modify .lua file, copied original: {e}")

    def fix_denuvo_lua_files(self, root_folder):
        """Re-enable Denuvo manifest calls in any Lua files after Denuvo bypass application."""
        try:
            for dirpath, _, filenames in os.walk(root_folder):
                for filename in filenames:
                    if filename.lower().endswith('.lua'):
                        file_path = os.path.join(dirpath, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()

                            modified_content = re.sub(
                                r'(?mi)^(?P<indent>\s*)--\s*(?P<code>.*\b(setManifestid|setManifest)\b.*)$',
                                r'\1\2',
                                content
                            )
                            if modified_content != content:
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(modified_content)
                                logging.info(f"Fixed Denuvo Lua file: {file_path}")
                        except Exception as inner_e:
                            logging.warning(f"Failed to fix Denuvo Lua file {file_path}: {inner_e}")
        except Exception as e:
            logging.error(f"Error fixing Denuvo Lua files: {e}")

    def update_add_buttons_state(self):
        """Enable/disable add buttons according to selected game DRM status."""
        if getattr(self, 'selected_game_denuvo', False):
            self.download_btn.config(state='disabled')
            self.add_denuvo_btn.config(state='normal')
        else:
            self.download_btn.config(state='normal')
            self.add_denuvo_btn.config(state='disabled')

    def repair_gamedrop(self):
        try:
            self.progress_text.set("Repairing GameDrop...")
            self.update_idletasks()

            if is_game_process_running():
                self.progress_text.set("Repair skipped while a game is running")
                messagebox.showwarning("Steam busy", "A game process is still running, so Steam restart was skipped to avoid interrupting gameplay.")
                return

            steam_base = self.steam_path or self.auto_find_steam_path()
            if not steam_base or not os.path.isdir(steam_base):
                messagebox.showerror("Steam Path Not Found",
                                     "Steam installation path could not be detected. Please select or configure the correct Steam path and try again.")
                return

            steam_exe_path = os.path.join(steam_base, "steam.exe")
            if not os.path.exists(steam_exe_path):
                messagebox.showerror("Steam Path Invalid",
                                     "The selected Steam path does not contain steam.exe. Please select a valid Steam installation.")
                return

            self.steam_path = steam_base
            self.progress_text.set("Closing Steam for repair...")
            self.update_idletasks()

            stop_steam_processes()
            if not wait_for_steam_exit(timeout=8, interval=0.5):
                logging.warning('Steam still running after shutdown attempt; continuing with repair')

            dll_files = ["dwmapi.dll", "xinput1_4.dll", "OpenSteamTool.dll"]
            repo_owner = "kkrmpubg"
            repo_name = "gamedrop-updates"
            branch_candidates = ["main", "master"]

            for dll_name in dll_files:
                downloaded_path = None
                for branch in branch_candidates:
                    try:
                        downloaded_path = self.download_file_from_branch(repo_owner, repo_name, dll_name, branch)
                        if downloaded_path:
                            break
                    except Exception as e:
                        logging.warning(f"Download attempt failed for {dll_name} from branch {branch}: {e}")

                if not downloaded_path:
                    raise Exception(f"Could not download {dll_name} from {repo_owner}/{repo_name}")

                target_path = os.path.join(steam_base, dll_name)
                try:
                    shutil.copy2(downloaded_path, target_path)
                    logging.info(f"Repaired {dll_name} at {target_path}")
                except Exception as e:
                    raise Exception(f"Failed to copy {dll_name} to Steam folder: {e}")

            self.progress_text.set("Steam has been closed for repair")
            self.update_idletasks()
            self.progress_text.set("GameDrop repair complete")
            self.update_idletasks()
            messagebox.showinfo(
                "Success",
                "GameDrop has been repaired.\n\nSteam was closed and left for you to reopen manually when you're ready."
            )

        except Exception as e:
            logging.error(f"Repair GameDrop failed: {e}")
            self.progress_text.set("Repair failed")
            messagebox.showerror("Repair Failed", f"Repair failed: {e}")

    def restart_steam(self):
        try:
            self.progress_text.set("Closing Steam...")
            self.update_idletasks()

            if is_game_process_running():
                self.progress_text.set("Close skipped while a game is running")
                messagebox.showwarning("Steam busy", "A game process is still running, so Steam was not closed to avoid interrupting gameplay.")
                return False

            stop_steam_processes()
            if not wait_for_steam_exit(timeout=8, interval=0.5):
                logging.warning('Steam still running after shutdown attempt; closing was requested anyway')

            self.progress_text.set("Steam has been closed")
            self.update_idletasks()
            messagebox.showinfo("Steam closed", "Steam has been closed.\n\nPlease open Steam manually when you are ready.")
            return True

        except Exception as e:
            self.progress_text.set(f"Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to close Steam: {e}")

    def delete_game_files(self):
        # Extract AppID from the entry text (handles both direct ID and "AppID - Name" format)
        entry_text = self.appid_entry.get().strip()
        if ' - ' in entry_text:
            appid = entry_text.split(' - ')[0].strip()
        else:
            appid = entry_text.strip()
            
        if not appid.isdigit():
            messagebox.showerror("Error", "Please enter a valid Steam Game ID")
            return

        self._reset_progressbar()
        confirm = messagebox.askyesno("Confirm Removal", 
                                    f"Are you sure you want to remove this game (ID: {appid}) from Steam?")
        if not confirm:
            return

        self.progress_text.set(f"Removing game {appid} from Steam...")
        self.progress["value"] = 0
        self.progress_percent.set("0%")
        self.update_idletasks()

        deleted_any = False
        steam_base = self.steam_path or self.auto_find_steam_path()
        if not steam_base:
            logging.error("Steam path could not be determined; cannot remove game files.")
            messagebox.showerror("Steam Path Not Found",
                                 "Steam installation path could not be detected. Please configure the correct Steam path and try again.")
            return

        lua_dir = os.path.join(steam_base, "config", "lua")
        legacy_st_plugin_dir = os.path.join(steam_base, "config", "stplug-in")
        target_dirs = []
        if os.path.isdir(lua_dir):
            target_dirs.append(lua_dir)
        if os.path.isdir(legacy_st_plugin_dir):
            target_dirs.append(legacy_st_plugin_dir)
        
        total_files = 0
        files_to_delete = []
        
        # First pass - count Lua files for this AppID in the active lua folder and legacy stplug-in folder
        for target_dir in target_dirs:
            for fname in os.listdir(target_dir):
                if fname.startswith(appid) and (fname.lower().endswith('.lua') or fname.lower().endswith('.lua.disabled')):
                    files_to_delete.append((target_dir, fname))
                    total_files += 1

        if total_files > 0:
            self.progress["maximum"] = total_files
            self.update_idletasks()
            processed = 0
            
            # Second pass - delete matching Lua files from both locations
            for dir_path, fname in files_to_delete:
                try:
                    full_path = os.path.join(dir_path, fname)
                    if os.path.exists(full_path):
                        os.remove(full_path)
                        deleted_any = True

                    processed += 1
                    percent = int((processed / total_files) * 100)
                    self.progress_percent.set(f"{percent}%")
                    self.progress["value"] = processed
                    self.update_idletasks()
                except Exception as e:
                    logging.error(f"Failed to process {fname}: {e}")
                    print(f"Failed to process {fname}: {e}")

        if deleted_any:
            self.progress_text.set(f"Game {appid} has been removed from Steam")
            self.progress_percent.set("100%")
            self.progress["value"] = self.progress["maximum"]
            messagebox.showinfo("Removed", 
                              f"Game has been removed from Steam.")
        else:
            self.progress_text.set(f"No game files found for ID {appid}")
            self.progress_percent.set("0%")
            self.progress["value"] = 0
            messagebox.showinfo("Not Found", 
                              f"No game files found for ID {appid}.\n"
                              "The game may have already been removed.")

    def apply_onlinefix(self, denuvo=False):
        """Apply OnlineFix or Bypass by downloading from repository and replacing files in Steam game folder"""
        # Extract AppID from the entry text (handles both direct ID and "AppID - Name" format)
        entry_text = self.appid_entry.get().strip()
        if ' - ' in entry_text:
            appid = entry_text.split(' - ')[0].strip()
        else:
            appid = entry_text.strip()
            
        if not appid.isdigit():
            messagebox.showerror("Error", "Please enter a valid Steam Game ID")
            return

        # Get game name for display
        game_name = entry_text.split(' - ')[1].strip() if ' - ' in entry_text else f"Game {appid}"
        
        title = "Confirm Bypass" if denuvo else "Confirm Apply OnlineFix"
        action = "apply Bypass" if denuvo else "apply OnlineFix"
        confirm = messagebox.askyesno(title, 
                                    f"Are you sure you want to {action} to {game_name} (ID: {appid})?\n\n"
                                    "This will download and replace files in your Steam game folder.")
        if not confirm:
            return

        self._reset_progressbar()
        if denuvo:
            self.progress_text.set(f"Applying Bypass to {game_name}... please wait")
        else:
            self.progress_text.set(f"Applying OnlineFix to {game_name}... please wait")
        self.progress["value"] = 0
        self.progress_percent.set("0%")
        self.update_idletasks()

        # Disable action buttons while the apply operation runs in the background.
        self.apply_onlinefix_btn.config(state='disabled')
        self.bypass_btn.config(state='disabled')
        self._stop_progress_animation()
        self._set_busy_cursor(True)

        apply_thread = threading.Thread(
            target=self._apply_onlinefix_worker,
            args=(appid, game_name, denuvo),
            daemon=True
        )
        apply_thread.start()

    def _set_busy_cursor(self, busy=True):
        def callback():
            try:
                self.config(cursor='watch' if busy else '')
                self.update_idletasks()
            except Exception:
                pass
        self.after(0, callback)

    def _create_progressbar(self):
        if hasattr(self, 'progress') and self.progress is not None:
            try:
                self.progress.destroy()
            except Exception:
                pass
        self.progress = ttk.Progressbar(self.progress_card, orient='horizontal', mode='determinate')
        self.progress.pack(fill=tk.X, pady=(6, 0))
        self.progress["maximum"] = 100
        self.progress["value"] = 0

    def _reset_progressbar(self):
        def callback():
            try:
                self._create_progressbar()
                self.progress_percent.set("0%")
                self.progress_text.set('Waiting to add a game...')
                self.update_idletasks()
            except Exception:
                pass
        self.after(0, callback)

    def _start_progress_animation(self, text=None):
        def callback():
            try:
                if text is not None:
                    self.progress_text.set(text)
                self.progress["mode"] = "indeterminate"
                self.progress["value"] = 0
                self.progress_percent.set("...")
                self.progress.start(10)
                self.update_idletasks()
            except Exception:
                pass
        self.after(0, callback)

    def _stop_progress_animation(self):
        def callback():
            try:
                self.progress.stop()
                self.progress["mode"] = "determinate"
                if not self.progress_percent.get():
                    self.progress_percent.set("0%")
                self.update_idletasks()
            except Exception:
                pass
        self.after(0, callback)

    def _update_progress(self, text=None, current=None, maximum=None, percent=None):
        def callback():
            try:
                if text is not None:
                    self.progress_text.set(text)
                if maximum is not None:
                    self.progress["maximum"] = maximum
                if current is not None:
                    self.progress["value"] = current
                if percent is not None:
                    self.progress_percent.set(f"{percent}%")
                elif current is not None and maximum:
                    self.progress_percent.set(f"{int((current / maximum) * 100)}%")
                self.update_idletasks()
            except Exception:
                pass
        self.after(0, callback)

    def _show_messagebox(self, kind, title, message):
        def callback():
            try:
                getattr(messagebox, kind)(title, message)
            except Exception:
                pass
        self.after(0, callback)

    def _finish_apply_onlinefix(self):
        def callback():
            try:
                self._set_busy_cursor(False)
                self.apply_onlinefix_btn.config(state='normal')
                self.bypass_btn.config(state='normal')
            except Exception:
                pass
        self.after(0, callback)

    def _apply_onlinefix_worker(self, appid, game_name, denuvo):
        try:
            self._update_progress("Finding Steam library folders...", current=0, maximum=0)
            steam_libraries = self.find_steam_libraries()
            if not steam_libraries:
                self._show_messagebox("showerror", "Error", "Could not find Steam library folders.\n\nPlease make sure Steam is installed and the path is correct.")
                self._finish_apply_onlinefix()
                return

            self._update_progress("Locating Steam game folder...", current=0, maximum=0)
            steam_game_folder = self.find_steam_game_folder(steam_libraries, appid)
            downloaded_files = None
            if not steam_game_folder:
                self._update_progress("Downloading OnlineFix package for folder detection...", current=0, maximum=0)
                downloaded_files = self.download_onlinefix_files(appid)
                if downloaded_files:
                    steam_game_folder = self.find_steam_game_folder_from_package(
                        steam_libraries, downloaded_files, appid, game_name=game_name
                    )

            if not steam_game_folder:
                self._show_messagebox("showwarning", "Game Not Installed", 
                                     f"Could not find the game automatically in your Steam libraries.\n\n"
                                     f"Please install the game first before applying OnlineFix. (ID: {appid})")
                self._update_progress("Game not installed", current=0, maximum=0)
                self._finish_apply_onlinefix()
                return

            if downloaded_files is None:
                self._update_progress("Downloading...", current=0, maximum=0)
                downloaded_files = self.download_onlinefix_files(appid)
            if not downloaded_files:
                message = "Denuvo bypass file is not available for this game" if denuvo else "OnlineFix file is not available for this game"
                self._show_messagebox("showwarning", "Not Available", f"{message} (ID: {appid}).")
                self._update_progress("Not available for this game", current=0, maximum=0)
                self._finish_apply_onlinefix()
                return

            self._update_progress("Applying Bypass... please wait" if denuvo else "Applying OnlineFix... please wait", current=0, maximum=0)
            self.copy_onlinefix_to_steam(
                downloaded_files,
                steam_game_folder,
                appid,
                denuvo=denuvo,
                steam_libraries=steam_libraries,
                game_name=game_name
            )

            self.cleanup_onlinefix_temp_files(downloaded_files)
        except Exception as e:
            logging.error(f"Error applying OnlineFix: {e}")
            self._show_messagebox("showerror", "Error", f"Failed to apply OnlineFix: {str(e)}")
            self._update_progress("Apply OnlineFix failed", current=0, maximum=0)
        finally:
            self._finish_apply_onlinefix()

    def find_steam_libraries(self):
        """Find all Steam library folders"""
        libraries = []

        steam_path = self.steam_path
        if not steam_path or not os.path.isdir(steam_path):
            steam_path = self.auto_find_steam_path()
        if not steam_path:
            return libraries

        steam_path = os.path.normpath(steam_path)
        steam_parts = [part.lower() for part in steam_path.split(os.sep) if part]

        if 'steamapps' in steam_parts:
            steamapps_index = steam_parts.index('steamapps')
            # Support steam path selected at root, steamapps, steamapps/common, or a game folder inside common
            steam_root = os.sep.join(steam_path.split(os.sep)[:steamapps_index])
            if not steam_root:
                steam_root = os.path.splitdrive(steam_path)[0] + os.sep
            steam_path = steam_root
            logging.info(f"Normalized Steam path to root: {steam_path}")
        else:
            normalized_common = os.path.normpath(os.path.join('steamapps', 'common'))
            normalized_steamapps = os.path.normpath('steamapps')
            if steam_path.lower().endswith(normalized_common.lower()):
                steam_path = os.path.dirname(os.path.dirname(steam_path))
                logging.info(f"Normalized Steam path from common folder to: {steam_path}")
            elif steam_path.lower().endswith(normalized_steamapps.lower()):
                steam_path = os.path.dirname(steam_path)
                logging.info(f"Normalized Steam path from steamapps folder to: {steam_path}")

        # Add main Steam library
        main_library = os.path.join(steam_path, "steamapps", "common")
        if os.path.exists(main_library):
            libraries.append(main_library)

        # Check libraryfolders.vdf for additional libraries
        libraryfolders_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(libraryfolders_path):
            try:
                with open(libraryfolders_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    import re
                    path_pattern = r'"path"\s+"([^"]+)"'
                    paths = re.findall(path_pattern, content)
                    for path in paths:
                        path = path.replace('\\\\', '\\')
                        common_path = os.path.join(path, "steamapps", "common")
                        if os.path.exists(common_path):
                            libraries.append(common_path)
            except Exception as e:
                logging.error(f"Error reading libraryfolders.vdf: {e}")

        # Ensure no duplicates and preserve order
        normalized = []
        for lib in libraries:
            lib_path = os.path.normpath(lib)
            if lib_path not in normalized:
                normalized.append(lib_path)

        return normalized

    def find_repo_game_folder(self, appid):
        """Find game folder in repository downloads"""
        downloads_path = os.path.join(os.getcwd(), SAVE_DIR)
        if not os.path.exists(downloads_path):
            return None
        
        # First, look for folders that contain the appid in their name
        for item in os.listdir(downloads_path):
            item_path = os.path.join(downloads_path, item)
            if os.path.isdir(item_path) and appid in item:
                return item_path
        
        # Look for folders that contain manifest files with the appid
        for item in os.listdir(downloads_path):
            item_path = os.path.join(downloads_path, item)
            if os.path.isdir(item_path):
                # Check if this folder contains manifest files for the appid
                if self.contains_appid_manifest(item_path, appid):
                    return item_path
        
        # If not found by manifest, look for folders that contain game files
        for item in os.listdir(downloads_path):
            item_path = os.path.join(downloads_path, item)
            if os.path.isdir(item_path):
                # Check if this folder contains files for the appid
                if self.contains_game_files(item_path, appid):
                    return item_path
        
        return None

    def contains_appid_manifest(self, folder_path, appid):
        """Check if folder contains manifest files with the given appid"""
        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    # Look for manifest files that contain the appid
                    if file.lower().endswith('.manifest') and appid in file:
                        return True
                    # Also check for .lua files with appid
                    if file.lower().endswith('.lua') and appid in file:
                        return True
        except Exception as e:
            logging.error(f"Error checking manifest in {folder_path}: {e}")
        return False

    def contains_game_files(self, folder_path, appid):
        """Check if folder contains game files for the given appid"""
        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    # Look for common game file patterns
                    if any(file.lower().endswith(ext) for ext in ['.exe', '.dll', '.so', '.dylib']):
                        return True
                    # Also check if any file contains the appid in its name
                    if appid in file:
                        return True
        except Exception as e:
            logging.error(f"Error checking folder {folder_path}: {e}")
        
        return False

    def find_steam_game_folder(self, steam_libraries, appid):
        """Find the Steam game folder for the given appid by checking appmanifest files"""
        # Get game name from entry if available
        entry_text = self.appid_entry.get().strip()
        game_name = None
        if ' - ' in entry_text:
            game_name = entry_text.split(' - ')[1].strip()

        normalized_game_name = self._normalize_game_name(game_name) if game_name else None
        
        # Check each Steam library for the appmanifest file
        for library_path in steam_libraries:
            try:
                # library_path is steamapps/common, we need to go up to steamapps
                steamapps_path = os.path.dirname(library_path)
                appmanifest_file = os.path.join(steamapps_path, f"appmanifest_{appid}.acf")
                
                if os.path.exists(appmanifest_file):
                    # Read the manifest to get the install directory
                    try:
                        with open(appmanifest_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Look for "installdir" field
                            import re
                            match = re.search(r'"installdir"\s+"([^"]+)"', content)
                            if match:
                                install_dir = match.group(1)
                                game_folder = os.path.join(library_path, install_dir)
                                if os.path.exists(game_folder):
                                    logging.info(f"Found game folder via appmanifest: {game_folder}")
                                    return game_folder
                    except Exception as e:
                        logging.error(f"Error reading appmanifest {appmanifest_file}: {e}")
                        
            except Exception as e:
                logging.error(f"Error checking library {library_path}: {e}")
                continue
        
        # Fallback: try to find by folder name containing appid or matching game name
        for library_path in steam_libraries:
            try:
                for item in os.listdir(library_path):
                    item_path = os.path.join(library_path, item)
                    if not os.path.isdir(item_path):
                        continue

                    if appid in item:
                        logging.info(f"Found game folder by appid in name: {item_path}")
                        return item_path

                    if normalized_game_name and self._folder_name_matches_game_name(item, normalized_game_name):
                        logging.info(f"Found game folder by name similarity: {item_path}")
                        return item_path
            except Exception as e:
                logging.error(f"Error scanning library {library_path}: {e}")
                continue

        # Fallback: search by likely game folder when no direct name/appid match exists
        for library_path in steam_libraries:
            try:
                for item in os.listdir(library_path):
                    item_path = os.path.join(library_path, item)
                    if not os.path.isdir(item_path):
                        continue
                    if self.is_game_folder(item_path, appid) and normalized_game_name and self._folder_name_matches_game_name(item, normalized_game_name):
                        logging.info(f"Found game folder by deep heuristic: {item_path}")
                        return item_path
            except Exception as e:
                logging.error(f"Error scanning library {library_path}: {e}")
                continue

        logging.warning(f"Could not find game folder for appid {appid}")
        return None

    def find_steam_game_folder_from_package(self, steam_libraries, package_folder, appid, game_name=None):
        """Use the extracted OnlineFix package to help locate the Steam game folder."""
        normalized_game_name = self._normalize_game_name(game_name) if game_name else None
        package_file_names = set()
        package_rel_paths = set()

        for root, _, files in os.walk(package_folder):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), package_folder)
                path_parts = rel_path.split(os.sep)
                if len(path_parts) > 1:
                    rel_file_path = os.path.join(*path_parts[1:]).replace('\\', '/').lower()
                else:
                    rel_file_path = rel_path.replace('\\', '/').lower()
                package_rel_paths.add(rel_file_path)
                package_file_names.add(os.path.basename(file).lower())

        for library_path in steam_libraries:
            try:
                steamapps_path = os.path.dirname(library_path)
                appmanifest_file = os.path.join(steamapps_path, f"appmanifest_{appid}.acf")
                if os.path.exists(appmanifest_file):
                    try:
                        with open(appmanifest_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            import re
                            match = re.search(r'"installdir"\s+"([^\"]+)"', content)
                            if match:
                                install_dir = match.group(1)
                                candidate = os.path.join(library_path, install_dir)
                                if os.path.exists(candidate):
                                    logging.info(f"Found game folder via manifest while using package: {candidate}")
                                    return candidate
                    except Exception as e:
                        logging.error(f"Error reading appmanifest {appmanifest_file}: {e}")
            except Exception as e:
                logging.error(f"Error checking library {library_path}: {e}")
                continue

        for library_path in steam_libraries:
            try:
                for item in os.listdir(library_path):
                    item_path = os.path.join(library_path, item)
                    if not os.path.isdir(item_path):
                        continue
                    if appid in item:
                        logging.info(f"Found game folder by appid in name from package search: {item_path}")
                        return item_path
                    if normalized_game_name and self._folder_name_matches_game_name(item, normalized_game_name):
                        logging.info(f"Found game folder by name similarity from package search: {item_path}")
                        return item_path
            except Exception as e:
                logging.error(f"Error scanning library {library_path}: {e}")
                continue

        for library_path in steam_libraries:
            try:
                for root, _, files in os.walk(library_path):
                    for file in files:
                        if file.lower() in package_file_names:
                            candidate = root
                            if normalized_game_name and self._folder_name_matches_game_name(os.path.basename(candidate), normalized_game_name):
                                logging.info(f"Found game folder by package file name and folder similarity: {candidate}")
                                return candidate
                            if os.path.basename(candidate).lower() not in ('common', 'steamapps'):
                                logging.info(f"Found game folder by package file name match: {candidate}")
                                return candidate
            except Exception as e:
                logging.error(f"Error scanning library for package files {library_path}: {e}")
                continue

        logging.warning(f"Could not find Steam game folder from package for appid {appid}")
        return None

    def _normalize_game_name(self, game_name):
        if not game_name:
            return None
        import re
        normalized = re.sub(r'[^a-z0-9]+', ' ', game_name.lower()).strip()
        return normalized

    def _folder_name_matches_game_name(self, folder_name, normalized_game_name):
        import re
        folder_normalized = re.sub(r'[^a-z0-9]+', ' ', folder_name.lower()).strip()
        if folder_normalized == normalized_game_name:
            return True
        if normalized_game_name in folder_normalized:
            return True
        folder_tokens = set(folder_normalized.split())
        name_tokens = set(normalized_game_name.split())
        return name_tokens and name_tokens.issubset(folder_tokens)

    def has_appid_manifest(self, folder_path, appid):
        """Check if folder contains manifest files with the appid"""
        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.manifest') and appid in file:
                        return True
        except Exception as e:
            logging.error(f"Error checking manifest in {folder_path}: {e}")
        return False

    def is_game_folder(self, folder_path, appid):
        """Check if folder is likely a game folder"""
        try:
            # Check for common game files
            game_files = []
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith(('.exe', '.dll', '.so', '.dylib')):
                        game_files.append(file)
                        if len(game_files) >= 3:  # If we find several game files, it's likely a game folder
                            return True
        except Exception as e:
            logging.error(f"Error checking game folder {folder_path}: {e}")
        
        return False

    def download_onlinefix_files(self, appid):
        """Download OnlineFix files from GitHub repository for the given appid"""
        try:
            # Repository order to try
            repo_order = [
                ("kkrmpubg", "ManifestHub"),
                ("dvahana2424-web", "sojogamesdatabase1"),
                ("hammerwebsite12", "sojogames2"),
                ("SteamAutoCracks", "ManifestHub")
            ]
            
            # Ensure the app-specific temporary folder is clean before downloading
            downloads_temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
            if os.path.exists(downloads_temp_dir):
                try:
                    shutil.rmtree(downloads_temp_dir)
                except Exception as cleanup_error:
                    logging.warning(f"Could not remove stale temp folder {downloads_temp_dir}: {cleanup_error}")
            
            for owner, repo_name in repo_order:
                try:
                    logging.info(f"Checking repository {owner}/{repo_name} for OnlineFix files")
                    
                    # Check if branch exists
                    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/branches/{appid}"
                    response = requests.get(api_url, headers=HEADERS, timeout=10)
                    
                    if response.status_code == 200:
                        logging.info(f"Found OnlineFix branch {appid} in {owner}/{repo_name}")
                        
                        # Get tree of files in the branch
                        tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{appid}?recursive=1"
                        tree_response = requests.get(tree_url, headers=HEADERS, timeout=10)
                        
                        if tree_response.status_code == 200:
                            tree_data = tree_response.json()

                            # If the branch contains metadata pointing to a release asset, use that first.
                            metadata = self.get_onlinefix_branch_metadata(owner, repo_name, appid)
                            if metadata and metadata.get('type') == 'release':
                                temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                                release_dir = self.download_release_asset(metadata, temp_dir, appid)
                                if release_dir:
                                    return release_dir

                            files_to_download = []
                            root_files = []
                            folder_files = []

                            # Find the main game folder; include root-level AppID-specific files as fallback.
                            for item in tree_data.get('tree', []):
                                if item['type'] == 'blob':  # blob = file
                                    file_path = item['path']
                                    if '/' in file_path:
                                        # This file is inside a folder, include it
                                        folder_files.append(file_path)
                                        files_to_download.append(file_path)
                                    else:
                                        # Include root-level AppID-specific files like 3764200.lua
                                        if file_path.lower().startswith(str(appid).lower()):
                                            root_files.append(file_path)
                                            files_to_download.append(file_path)

                            # If branch only contains root-level metadata files like appid.lua or manifest files,
                            # do not treat that as a valid OnlineFix package by itself.
                            if not folder_files and root_files:
                                valid_root_files = []
                                for root_file in root_files:
                                    ext = os.path.splitext(root_file)[1].lower()
                                    if ext in ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.exe', '.dll', '.bin', '.dat'):
                                        valid_root_files.append(root_file)
                                if not valid_root_files:
                                    logging.info(f"Branch {appid} in {owner}/{repo_name} contains only metadata/root manifest files; skipping as no fix package available")
                                    release_url = self.find_github_release_asset_url(owner, repo_name, appid)
                                    if release_url:
                                        temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                                        release_dir = self.download_url_to_temp(release_url, temp_dir, f"{appid}_release")
                                        if release_dir:
                                            extracted = self.extract_archive_to_dir(release_dir, os.path.join(temp_dir, 'extracted'))
                                            if extracted:
                                                return extracted
                                            logging.info(f"Found release asset URL for {appid} but could not extract it")
                                        else:
                                            logging.info(f"Release asset download failed for {appid}")
                                    continue
                                root_files = valid_root_files
                                files_to_download = valid_root_files

                            # Prefer release assets when the branch only exposes root-level AppID-specific files.
                            if not folder_files and root_files:
                                release_url = self.find_github_release_asset_url(owner, repo_name, appid)
                                if release_url:
                                    temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                                    release_dir = self.download_url_to_temp(release_url, temp_dir, f"{appid}_release")
                                    if release_dir:
                                        extracted = self.extract_archive_to_dir(release_dir, os.path.join(temp_dir, 'extracted'))
                                        if extracted:
                                            return extracted
                                        logging.info(f"Found release asset URL for {appid} but could not extract it")
                                    else:
                                        logging.info(f"Release asset download failed for {appid}")
                                else:
                                    logging.info(f"No release asset found for {appid}; falling back to branch files")

                            # If no matching branch files found, try release assets instead of raw branch files
                            if not files_to_download:
                                release_url = self.find_github_release_asset_url(owner, repo_name, appid)
                                if release_url:
                                    temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                                    release_dir = self.download_url_to_temp(release_url, temp_dir, f"{appid}_release")
                                    if release_dir:
                                        extracted = self.extract_archive_to_dir(release_dir, os.path.join(temp_dir, 'extracted'))
                                        if extracted:
                                            return extracted
                                        # If direct asset download is not an archive, nothing to extract
                                    logging.info(f"Found release asset URL for {appid} but could not extract it")
                                logging.info(f"No game folder found in branch {appid} for {owner}/{repo_name}")
                                continue

                            if files_to_download:
                                # Create temporary directory for OnlineFix files
                                temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                                os.makedirs(temp_dir, exist_ok=True)
                                
                                downloaded_paths = []
                                total_files = len(files_to_download)
                                
                                self.progress["maximum"] = total_files
                                
                                for i, file_path in enumerate(files_to_download, 1):
                                    try:
                                        # Download file
                                        file_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{appid}/{file_path}"
                                        file_response = requests.get(file_url, headers=HEADERS, timeout=30)
                                        
                                        if file_response.status_code == 200:
                                            # Save file to temp directory
                                            local_path = os.path.join(temp_dir, file_path)
                                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                            
                                            with open(local_path, 'wb') as f:
                                                f.write(file_response.content)
                                            
                                            downloaded_paths.append(local_path)
                                            
                                            # Update progress
                                            percent = int((i / total_files) * 100)
                                            self.progress_percent.set(f"{percent}%")
                                            self.progress["value"] = i
                                            self.progress_text.set(f"Downloading... {i}/{total_files}")
                                            self.update_idletasks()
                                            
                                            logging.info(f"Downloaded {file_path}")
                                        else:
                                            logging.warning(f"Failed to download {file_path}")
                                            
                                    except Exception as e:
                                        logging.error(f"Error downloading {file_path}: {e}")
                                        continue
                                
                                if downloaded_paths:
                                    archive_extensions = ('.zip', '.tar.gz', '.tgz', '.tar', '.7z', '.rar')
                                    archive_paths = [p for p in downloaded_paths if p.lower().endswith(archive_extensions)]
                                    extraction_failed = False
                                    for archive_path in archive_paths:
                                        extracted = self.extract_archive_to_dir(archive_path, temp_dir)
                                        if extracted:
                                            logging.info(f"Extracted archive {archive_path} into {temp_dir}")
                                            try:
                                                os.remove(archive_path)
                                                logging.info(f"Removed archive {archive_path} after extraction")
                                            except Exception as e:
                                                logging.warning(f"Could not remove archive {archive_path} after extraction: {e}")
                                        else:
                                            logging.error(f"Failed to extract archive {archive_path}")
                                            extraction_failed = True
                                    if extraction_failed:
                                        logging.error(f"One or more archives failed to extract for AppID {appid}")
                                        return None
                                    return temp_dir
                    elif response.status_code == 404:
                        release_url = self.find_github_release_asset_url(owner, repo_name, appid)
                        if release_url:
                            temp_dir = os.path.join(os.getcwd(), SAVE_DIR, f"onlinefix_{appid}")
                            release_path = self.download_url_to_temp(release_url, temp_dir, f"{appid}_release")
                            if release_path:
                                extracted = self.extract_archive_to_dir(release_path, os.path.join(temp_dir, 'extracted'))
                                if extracted:
                                    return extracted
                                logging.info(f"Found release asset URL for {appid} but could not extract it")
                        continue
                    else:
                        logging.warning(f"GitHub branch check returned {response.status_code} for {owner}/{repo_name} branch {appid}")
                        continue
                except Exception as e:
                    logging.error(f"Error checking repository {owner}/{repo_name}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logging.error(f"Error downloading OnlineFix files: {e}")
            return None

    def check_fix_availability(self, appid):
        """Quick check whether an OnlineFix or Bypass is available for the given AppID.
        Returns (onlinefix_available: bool, bypass_available: bool)
        This performs lightweight GitHub API checks only (no downloads).
        """
        try:
            if not appid or not str(appid).isdigit():
                return (False, False)

            repo_order = [
                ("kkrmpubg", "ManifestHub"),
                ("dvahana2424-web", "sojogamesdatabase1"),
                ("hammerwebsite12", "sojogames2"),
                ("SteamAutoCracks", "ManifestHub")
            ]

            appid_str = str(appid)
            onlinefix_found = False
            bypass_found = False

            for owner, repo_name in repo_order:
                try:
                    # Check branch/tree
                    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/branches/{appid_str}"
                    resp = requests.get(api_url, headers=HEADERS, timeout=10)
                    if resp.status_code == 200:
                        tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{appid_str}?recursive=1"
                        tree_resp = requests.get(tree_url, headers=HEADERS, timeout=10)
                        if tree_resp.status_code == 200:
                            tree = tree_resp.json().get('tree', [])
                            folder_files = [t for t in tree if t.get('type') == 'blob' and '/' in t.get('path','')]
                            root_files = [t for t in tree if t.get('type') == 'blob' and '/' not in t.get('path','')]

                            # If branch contains files in folders, treat as OnlineFix available
                            if folder_files:
                                onlinefix_found = True

                            # If there are root files, ensure they are real packages (archives/binaries)
                            if root_files and not onlinefix_found:
                                valid_root = False
                                for rf in root_files:
                                    ext = os.path.splitext(rf.get('path',''))[1].lower()
                                    if ext in ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.exe', '.dll', '.bin', '.dat'):
                                        valid_root = True
                                        break
                                if valid_root:
                                    onlinefix_found = True

                            # Check branch metadata for bypass pointers
                            meta = self.get_onlinefix_branch_metadata(owner, repo_name, appid_str)
                            if meta and meta.get('type') == 'release':
                                # metadata points to a release URL; treat as available
                                onlinefix_found = True
                                # if the release url contains the AppID, mark bypass as available too
                                url = meta.get('url','')
                                if appid_str in url:
                                    bypass_found = True
                            else:
                                # also check for explicit bypass_url.txt
                                bypass_txt = self.download_branch_text_file(owner, repo_name, 'bypass_url.txt', appid_str)
                                if bypass_txt:
                                    bypass_found = True

                    # If branch lookup failed, check releases for assets mentioning the AppID
                    release_url = self.find_github_release_asset_url(owner, repo_name, appid_str)
                    if release_url:
                        onlinefix_found = True
                        # If the asset name contains the AppID, consider bypass available
                        if appid_str in os.path.basename(release_url):
                            bypass_found = True

                    if onlinefix_found and bypass_found:
                        break

                except Exception:
                    continue

            return (onlinefix_found, bypass_found)
        except Exception as e:
            logging.error(f"Error checking fix availability for {appid}: {e}")
            return (False, False)

    def _update_action_buttons_state_thread(self):
        """Background thread target that checks availability and updates the UI buttons."""
        try:
            entry_text = self.appid_entry.get().strip()
            if ' - ' in entry_text:
                appid = entry_text.split(' - ')[0].strip()
            else:
                appid = entry_text.strip()
            # Dynamic graying out disabled: keep both action buttons enabled for responsiveness.
            try:
                self.after(0, lambda: (self.apply_onlinefix_btn.config(state='normal'), self.bypass_btn.config(state='normal')))
            except Exception:
                pass
        except Exception as e:
            logging.error(f"_update_action_buttons_state_thread error: {e}")

    def copy_onlinefix_to_steam(self, onlinefix_folder, steam_folder, appid, denuvo=False, steam_libraries=None, game_name=None):
        """Copy OnlineFix files to Steam game folder, intelligently matching file paths"""
        try:
            copied_files = 0
            total_files = 0
            files_to_copy = []
            archive_extensions = ('.zip', '.tar.gz', '.tgz', '.tar', '.7z', '.rar')
            
            # Count total files and prepare copy list
            archive_files_to_remove = []
            for root, dirs, files in os.walk(onlinefix_folder):
                for file in files:
                    src_path = os.path.join(root, file)
                    if src_path.lower().endswith(archive_extensions):
                        archive_files_to_remove.append(file)
                        continue
                    files_to_copy.append(src_path)
                    total_files += 1
            
            if total_files == 0:
                messagebox.showwarning("Game Not Installed", 
                                     "Please install the game first before applying OnlineFix.")
                self.progress_text.set("No files to apply")
                self.progress_percent.set("0%")
                self.progress["value"] = 0
                return
            
            # Validate that the Steam folder matches by checking for matching executables
            if not self.validate_steam_game_folder(onlinefix_folder, steam_folder, game_name=game_name):
                if steam_libraries:
                    alt_folder = self.find_steam_game_folder_from_package(
                        steam_libraries, onlinefix_folder, appid, game_name=game_name
                    )
                    if alt_folder and alt_folder != steam_folder:
                        logging.info(f"Switching to alternate Steam folder found from package: {alt_folder}")
                        steam_folder = alt_folder
                if not self.validate_steam_game_folder(onlinefix_folder, steam_folder, game_name=game_name):
                    messagebox.showwarning("Game Not Installed", 
                                         "Please install the game first before applying OnlineFix.\n\n"
                                         "The selected folder does not match the game executables.")
                    self.progress_text.set("Wrong game folder")
                    self.progress_percent.set("0%")
                    self.progress["value"] = 0
                    return
            
            self.progress["maximum"] = total_files
            
            # Determine whether the OnlineFix folder has a single wrapper directory for nested files
            rel_paths = [os.path.relpath(src_path, onlinefix_folder) for src_path in files_to_copy]
            strip_wrapper = False
            wrapper = None
            if rel_paths:
                nested_paths = [rel_path for rel_path in rel_paths if os.sep in rel_path]
                if nested_paths:
                    first_parts = [rel_path.split(os.sep) for rel_path in nested_paths]
                    wrapper_names = {parts[0] for parts in first_parts}
                    if len(wrapper_names) == 1:
                        wrapper_candidate = next(iter(wrapper_names))
                        wrapper_dir = os.path.join(onlinefix_folder, wrapper_candidate)
                        if os.path.isdir(wrapper_dir):
                            strip_wrapper = True
                            wrapper = wrapper_candidate
                            logging.info(f"Detected wrapper folder '{wrapper}' for nested OnlineFix files; stripping it during copy")

            # Copy files with intelligent path matching
            for src_path in files_to_copy:
                try:
                    # Calculate relative path from onlinefix folder
                    rel_path = os.path.relpath(src_path, onlinefix_folder)
                    path_parts = rel_path.split(os.sep)
                    if strip_wrapper and len(path_parts) > 1 and path_parts[0] == wrapper:
                        rel_path_stripped = os.path.join(*path_parts[1:])
                    else:
                        rel_path_stripped = rel_path
                    
                    # Build destination path directly in Steam game folder
                    dst_path = os.path.join(steam_folder, rel_path_stripped)
                    
                    # Create destination directory if it doesn't exist
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    # Copy file (overwrite if exists)
                    shutil.copy2(src_path, dst_path)
                    copied_files += 1
                    
                    logging.info(f"Copied: {rel_path_stripped} -> {dst_path}")
                    
                    # Update progress
                    percent = int((copied_files / total_files) * 100)
                    self.progress_percent.set(f"{percent}%")
                    self.progress["value"] = copied_files
                    self.progress_text.set(f"Applying Bypass... {copied_files}/{total_files}" if denuvo else f"Applying OnlineFix... {copied_files}/{total_files}")
                    self.update_idletasks()
                    
                except Exception as e:
                    logging.error(f"Error copying file {os.path.basename(src_path)}: {e}")
                    continue
            
            # Check if any files were actually copied
            if copied_files == 0:
                messagebox.showwarning("Game Not Installed", 
                                     "Please install the game first before applying OnlineFix.")
                self.progress_text.set("No files applied")
                self.progress_percent.set("0%")
                self.progress["value"] = 0
                return
            
            # Remove stale archive files matching the AppID from the Steam folder
            for root, _, files in os.walk(steam_folder):
                for file in files:
                    if file.lower().endswith(archive_extensions) and file.lower().startswith(str(appid).lower()):
                        try:
                            os.remove(os.path.join(root, file))
                            logging.info(f"Removed stale archive from Steam folder: {file}")
                        except Exception as e:
                            logging.warning(f"Could not remove stale archive {file}: {e}")

            # Success message
            self.progress_text.set(f"Bypass applied successfully!" if denuvo else f"OnlineFix applied successfully!")
            self.progress_percent.set("100%")
            self.progress["value"] = self.progress["maximum"]
            success_title = "Success"
            success_msg = "Denuvo bypass has been successfully applied!" if denuvo else "OnlineFix has been successfully applied!"
            messagebox.showinfo(success_title, success_msg)
            
        except Exception as e:
            logging.error(f"Error copying OnlineFix files: {e}")
            messagebox.showerror("Error", f"Failed to copy files: {str(e)}")

    def validate_steam_game_folder(self, onlinefix_folder, steam_folder, game_name=None):
        """Validate that the Steam folder matches by checking for matching executables or DLL files"""
        try:
            normalized_game_name = self._normalize_game_name(game_name) if game_name else None
            # Get all .exe and .dll files from OnlineFix folder (strip first folder level)
            onlinefix_files = set()
            has_exe = False
            
            for root, dirs, files in os.walk(onlinefix_folder):
                for file in files:
                    if file.lower().endswith(('.exe', '.dll')):
                        # Get relative path and strip first folder level
                        src_path = os.path.join(root, file)
                        rel_path = os.path.relpath(src_path, onlinefix_folder)
                        path_parts = rel_path.split(os.sep)
                        
                        if len(path_parts) > 1:
                            # Remove the first folder level
                            rel_file_path = os.path.join(*path_parts[1:])
                        else:
                            rel_file_path = path_parts[0]
                        
                        onlinefix_files.add(rel_file_path.lower())
                        if file.lower().endswith('.exe'):
                            has_exe = True
            
            # If no exe or dll files in OnlineFix, skip validation (generic fix)
            if not onlinefix_files:
                logging.info("No exe/dll files in OnlineFix - assuming generic fix, skipping validation")
                return True
            
            # If OnlineFix has files, check if Steam game folder has any exe files (to verify it's installed)
            steam_has_exe = False
            for root, dirs, files in os.walk(steam_folder):
                for file in files:
                    if file.lower().endswith('.exe'):
                        steam_has_exe = True
                        break
                if steam_has_exe:
                    break
            
            # If Steam folder has no exe files, game is not installed
            if not steam_has_exe:
                logging.warning(f"Steam folder has no exe files - game may not be installed: {steam_folder}")
                return False
            
            # If OnlineFix has exe files, validate by matching
            if has_exe:
                # Check if any of the OnlineFix exe/dll files exist in Steam folder by exact relative path
                for file_rel_path in onlinefix_files:
                    steam_file_path = os.path.join(steam_folder, file_rel_path)
                    if os.path.exists(steam_file_path):
                        logging.info(f"Validated: Found matching file {file_rel_path}")
                        return True

                # If exact matches fail, allow validation by matching executable or DLL names anywhere inside the Steam folder
                package_names = {os.path.basename(p) for p in onlinefix_files}
                for root, _, files in os.walk(steam_folder):
                    for file in files:
                        if file.lower() in package_names:
                            logging.info(f"Validated by file name match: {file} in {root}")
                            return True

                # Allow name similarity to the game folder when package content includes expected files
                if normalized_game_name and self._folder_name_matches_game_name(os.path.basename(steam_folder), normalized_game_name):
                    logging.info(f"Validated by game name similarity: {steam_folder}")
                    return True

                logging.warning(f"Validation failed: No matching executables found in {steam_folder}")
                logging.warning(f"OnlineFix files: {onlinefix_files}")
                return False
            else:
                # OnlineFix only has DLL files (generic fix), check if Steam folder is valid (has exe)
                logging.info("OnlineFix contains only DLL files - assuming generic fix")
                return steam_has_exe
            
        except Exception as e:
            logging.error(f"Error validating Steam game folder: {e}")
            # If validation fails due to error, allow the copy to proceed
            return True
    
    def cleanup_onlinefix_temp_files(self, temp_folder):
        """Clean up temporary OnlineFix files, including any archive sibling left behind after extraction."""
        try:
            if not temp_folder:
                return

            candidate_paths = []
            normalized_path = os.path.abspath(str(temp_folder))
            if os.path.exists(normalized_path):
                candidate_paths.append(normalized_path)
                if os.path.isdir(normalized_path) and os.path.basename(normalized_path).lower() == 'extracted':
                    parent_dir = os.path.dirname(normalized_path)
                    if parent_dir and os.path.exists(parent_dir):
                        candidate_paths.append(parent_dir)

            for candidate_path in candidate_paths:
                if not os.path.exists(candidate_path):
                    continue
                if os.path.isdir(candidate_path):
                    shutil.rmtree(candidate_path)
                else:
                    os.remove(candidate_path)

            if candidate_paths:
                logging.info(f"Cleaned up temporary OnlineFix files under: {temp_folder}")
        except FileNotFoundError:
            logging.info(f"Temporary OnlineFix path already removed: {temp_folder}")
        except Exception as e:
            logging.error(f"Error cleaning up temp files: {e}")

    def copy_files_to_steam_folder(self, repo_folder, steam_folder, appid):
        """Copy files from repository folder to Steam game folder"""
        try:
            copied_files = 0
            total_files = 0
            
            # Count total files first
            for root, dirs, files in os.walk(repo_folder):
                total_files += len(files)
            
            if total_files == 0:
                messagebox.showwarning("Warning", "No files found in repository folder")
                return
            
            self.progress["maximum"] = total_files
            
            # Copy files
            for root, dirs, files in os.walk(repo_folder):
                for file in files:
                    try:
                        src_path = os.path.join(root, file)
                        # Calculate relative path
                        rel_path = os.path.relpath(src_path, repo_folder)
                        dst_path = os.path.join(steam_folder, rel_path)
                        
                        # Create destination directory if it doesn't exist
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        
                        # Copy file
                        shutil.copy2(src_path, dst_path)
                        copied_files += 1
                        
                        # Update progress
                        percent = int((copied_files / total_files) * 100)
                        self.progress_percent.set(f"{percent}%")
                        self.progress["value"] = copied_files
                        self.progress_text.set(f"Copying files... {copied_files}/{total_files}")
                        self.update_idletasks()
                        
                    except Exception as e:
                        logging.error(f"Error copying file {file}: {e}")
                        continue
            
            # Success message
            self.progress_text.set(f"Bypass applied successfully!" if denuvo else f"OnlineFix applied successfully!")
            self.progress_percent.set("100%")
            self.progress["value"] = self.progress["maximum"]
            success_title = "Success"
            success_msg = (f"Denuvo bypass has been successfully applied to the game!\n\n"
                          f"Copied {copied_files} files to Steam game folder.") if denuvo else (
                          f"OnlineFix has been successfully applied to the game!\n\n"
                          f"Copied {copied_files} files to Steam game folder.")
            messagebox.showinfo(success_title, success_msg)
            
        except Exception as e:
            logging.error(f"Error copying files: {e}")
            messagebox.showerror("Error", f"Failed to copy files: {str(e)}")

if __name__ == "__main__":
    try:
        logging.info("Creating main application window...")
        app = ManifestDownloader()
        
        logging.info("Configuring window properties...")
        # Center the window after all widgets are created
        app.update_idletasks()  # Update "requested size" from geometry manager
        
        # Get window size and set minimum size
        window_width = app.winfo_reqwidth()
        window_height = app.winfo_reqheight()
        
        # Set minimum size to prevent window from getting smaller
        app.minsize(window_width, window_height)
        
        # Get screen size
        screen_width = app.winfo_screenwidth()
        screen_height = app.winfo_screenheight()
        
        # Calculate position coordinates
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # Set the position of the window to the center of the screen
        app.geometry(f"+{x}+{y}")
        
        # Prevent window resizing
        app.resizable(False, False)
        
        logging.info("Starting main event loop...")
        app.mainloop()
        
    except Exception as e:
        logging.error(f"Critical error: {str(e)}", exc_info=True)
        try:
            messagebox.showerror("Error", f"An error occurred: {str(e)}\nCheck gamedrop.log for details.")
        except:
            pass
        sys.exit(1)
