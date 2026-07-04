import base64
import ctypes
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

BACKEND_BASE_URL = os.environ.get("GAME_DROP_BACKEND_URL", "https://simple-drm-backend.onrender.com")

import requests
import webview

from check_onlinefix_bypass import get_remote_bypass_appids


def get_webview_start_kwargs():
    """Return the most stable startup options for the available platform."""
    if sys.platform == "win32":
        return {"gui": "edgechromium", "debug": False}
    return {"debug": False}


def start_webview_runtime():
    """Start pywebview with a Windows-friendly backend preference."""
    kwargs = get_webview_start_kwargs()
    try:
        webview.start(**kwargs)
    except Exception:
        webview.start(debug=False)


class GameDropWebViewAPI:
    def __init__(self, app_dir=None):
        self.app_dir = app_dir or os.path.dirname(os.path.abspath(__file__))
        self.status = "Ready"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        self.remote_bypass_appids = tuple()
        self._remote_bypass_appids_last_refresh = 0.0

    def _get_github_headers(self, accept=None):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": accept or "application/json, text/plain, */*",
        }
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        return headers

    def _refresh_remote_bypass_appids(self, force=False, max_age_seconds=300):
        now = time.time()
        if not force and self.remote_bypass_appids and (now - self._remote_bypass_appids_last_refresh) < max_age_seconds:
            return self.remote_bypass_appids
        try:
            self.remote_bypass_appids = tuple(get_remote_bypass_appids() or ())
        except Exception:
            if not self.remote_bypass_appids:
                self.remote_bypass_appids = tuple()
        self._remote_bypass_appids_last_refresh = now
        return self.remote_bypass_appids

    def get_initial_state(self):
        self._refresh_remote_bypass_appids(force=True)
        steam_path = None
        try:
            from file_protection import get_steam_path
            steam_path = get_steam_path()
        except Exception:
            steam_path = None

        activation_helper_path = None
        engine_ready = False
        try:
            from denuvo_activation import find_activation_executable, get_opensteam_engine_status
            activation_helper_path = find_activation_executable()
            engine_ready = get_opensteam_engine_status().get("ready", False)
        except Exception:
            activation_helper_path = None
            engine_ready = False

        return {
            "title": "GameDrop Steam",
            "version": "3.0.0",
            "status": self.status,
            "app_dir": self.app_dir,
            "steam_path": steam_path,
            "activation_helper_path": activation_helper_path,
            "engine_ready": engine_ready,
            "step": 1,
            "flow": None,
            "title_text": "Home",
        }

    def get_wizard_state(self, flow=None):
        flow = (flow or "").strip()
        if flow == "add_denuvo_game":
            return {
                "step": 3,
                "flow": flow,
                "title": "Bypasses",
                "message": "Loading games with available bypass",
            }
        if flow == "add_game":
            return {
                "step": 2,
                "flow": flow,
                "title": "Step 2: Add to Library",
                "message": "Pick the game you want to add to your Steam library.",
            }

        if flow in {"onlinefix", "launch_activation", "repair", "restart_steam"}:
            # Provide clearer titles for action flows
            title_map = {
                "onlinefix": "OnlineFix",
                "launch_activation": "Denuvo activator",
                "repair": "Repair",
                "restart_steam": "Restart Steam",
            }
            msg_map = {
                "onlinefix": "The OnlineFix flow is ready for the selected title.",
                "launch_activation": "Denuvo activator can be launched.",
                "repair": "The repair routine is ready to run.",
                "restart_steam": "Restart Steam to apply changes.",
            }
            return {
                "step": 3,
                "flow": flow,
                "title": title_map.get(flow, "Step 3: Action"),
                "message": msg_map.get(flow, "The selected action is ready to run."),
            }
        return {
            "step": 1,
            "flow": None,
            "title": "Home",
            "message": "This is the friendly overview for new users. It explains how GameDrop helps them add Steam games and finish installation safely.",
        }

    def set_status(self, message):
        self.status = message
        return {"ok": True, "message": message}

    def _get_steam_app_details(self, appid):
        try:
            response = self.session.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": appid, "cc": "US", "l": "english"},
                timeout=4,
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            app_data = payload.get(str(appid), {})
            if not app_data.get("success"):
                return None
            data = app_data.get("data", {})
            if not isinstance(data, dict):
                return None
            if data.get("type", "").lower() != "game" and not data.get("is_game"):
                return None
            if data.get("is_dlc") or data.get("type", "").lower() == "dlc":
                return None
            return {
                "id": str(appid),
                "name": data.get("name") or f"Steam App {appid}",
                "image": data.get("header_image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                "description": str(data.get("short_description") or data.get("about_the_game") or data.get("detailed_description") or data.get("description") or "").strip(),
            }
        except Exception:
            return None

    def _check_steam_api_drm(self, game_id, game_name):
        try:
            response = self.session.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": game_id, "cc": "US", "l": "english"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://store.steampowered.com/",
                },
                timeout=6,
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            app_data = payload.get(str(game_id), {}).get("data", {}) or {}
            if not isinstance(app_data, dict):
                return False
            text_fields = [
                str(app_data.get("description") or ""),
                str(app_data.get("short_description") or ""),
                str(app_data.get("detailed_description") or ""),
                str(app_data.get("about_the_game") or ""),
                str(app_data.get("pc_requirements") or ""),
                str(app_data.get("mac_requirements") or ""),
                str(app_data.get("linux_requirements") or ""),
            ]
            for category in app_data.get("categories", []) or []:
                if isinstance(category, dict):
                    text_fields.append(str(category.get("description") or ""))
            for genre in app_data.get("genres", []) or []:
                if isinstance(genre, dict):
                    text_fields.append(str(genre.get("description") or ""))
            combined = " ".join(text_fields).lower()
            return "denuvo" in combined
        except Exception:
            return False

    def _download_branch_text_file(self, owner, repo_name, filename, branch):
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{filename}"
            response = self.session.get(raw_url, timeout=10)
            if response.status_code == 200:
                return response.text or None
        except Exception:
            pass
        return None

    def _get_onlinefix_branch_metadata(self, repo_owner, repo_name, branch):
        metadata_files = ['onlinefix.json', 'release_url.txt', 'bypass_url.txt', 'manifest_url.txt']
        for filename in metadata_files:
            content = self._download_branch_text_file(repo_owner, repo_name, filename, branch)
            if not content:
                continue
            try:
                if filename.endswith('.json'):
                    return json.loads(content)
                url = content.strip().splitlines()[0].strip()
                if url:
                    return {'type': 'release', 'url': url}
            except Exception:
                continue
        return None

    def _find_manifesthub_release_asset_url(self, appid):
        try:
            appid_str = str(appid)
            archive_exts = ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz')
            api_url = "https://api.github.com/repos/kkrmpubg/ManifestHub/releases/tags/re"
            response = self.session.get(
                api_url,
                headers=self._get_github_headers("application/vnd.github.v3+json"),
                timeout=10,
            )
            if response.status_code != 200:
                return None
            release = response.json() or {}
            assets = release.get("assets", []) or []
            exact_matches = []
            starts_with_matches = []
            contains_matches = []

            for asset in assets:
                asset_name = str(asset.get("name") or "").lower()
                asset_url = asset.get("browser_download_url")
                if not asset_url or not any(asset_name.endswith(ext) for ext in archive_exts):
                    continue

                if re.search(rf'(^|[^0-9]){re.escape(appid_str)}([^0-9]|$)', asset_name):
                    exact_matches.append(asset_url)
                elif asset_name.startswith(appid_str):
                    starts_with_matches.append(asset_url)
                elif appid_str in asset_name:
                    contains_matches.append(asset_url)

            def pick_preferred(urls):
                if not urls:
                    return None
                for url in urls:
                    if url.lower().endswith('.rar'):
                        return url
                return urls[0]

            return pick_preferred(exact_matches) or pick_preferred(starts_with_matches) or pick_preferred(contains_matches)
        except Exception:
            return None

    def _find_github_release_asset_url(self, owner, repo_name, appid):
        try:
            api_urls = [
                f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{appid}",
                f"https://api.github.com/repos/{owner}/{repo_name}/releases",
            ]
            appid_str = str(appid)
            archive_exts = ('.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz')
            for api_url in api_urls:
                response = self.session.get(
                    api_url,
                    headers=self._get_github_headers("application/vnd.github.v3+json"),
                    timeout=10,
                )
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    continue
                releases = response.json()
                if isinstance(releases, dict):
                    releases = [releases]
                for release in releases:
                    tag_name = str(release.get('tag_name', '')).lower()
                    release_name = str(release.get('name', '')).lower()
                    release_body = str(release.get('body', '')).lower()
                    release_match = appid_str in tag_name or appid_str in release_name or appid_str in release_body
                    assets = release.get('assets', []) or []
                    for asset in assets:
                        name = str(asset.get('name', '')).lower()
                        url = asset.get('browser_download_url')
                        if not url:
                            continue
                        if release_match and any(name.endswith(ext) for ext in archive_exts):
                            return url, False
                        if appid_str in name or name.startswith(appid_str):
                            return url, False
                    if release_match and assets:
                        for fallback_asset in assets:
                            fallback_name = str(fallback_asset.get('name', '')).lower()
                            fallback_url = fallback_asset.get('browser_download_url')
                            if fallback_url and any(fallback_name.endswith(ext) for ext in archive_exts):
                                return fallback_url, False
            return None, False
        except Exception:
            return None, False

    def _download_github_release_asset(self, owner, repo_name, appid, dest_dir):
        url, _ = self._find_github_release_asset_url(owner, repo_name, appid)
        if not url:
            return None
        archive_path = self._download_url_to_temp(url, dest_dir, f"{appid}_release")
        if not archive_path:
            return None
        if self._extract_downloaded_archive(archive_path, dest_dir):
            return dest_dir
        return None

    def _check_onlinefix_availability(self, appid):
        try:
            appid_str = str(appid or "").strip()
            if not appid_str.isdigit():
                return {"onlinefix_available": False, "bypass_available": False}

            if self._is_bypass_appid(appid_str):
                return {"onlinefix_available": False, "bypass_available": True}

            return {"onlinefix_available": False, "bypass_available": False}
        except Exception:
            return {"onlinefix_available": False, "bypass_available": False}

    def _check_bypass_availability(self, appid):
        try:
            appid_str = str(appid or "").strip()
            if not appid_str.isdigit():
                return {"onlinefix_available": False, "bypass_available": False}

            if self._is_bypass_appid(appid_str):
                return {"onlinefix_available": False, "bypass_available": True}

            try:
                response = self.session.get(
                    f"{BACKEND_BASE_URL}/bypass-info",
                    params={"appid": appid_str},
                    timeout=12,
                )
                if response.status_code == 200:
                    payload = response.json() or {}
                    if payload.get("bypass_available"):
                        return {"onlinefix_available": False, "bypass_available": True, "backend_status": payload.get("status")}
            except Exception:
                pass

            return {"onlinefix_available": False, "bypass_available": False}
        except Exception:
            return {"onlinefix_available": False, "bypass_available": False}

    def _normalize_fix_status_for_denuvo(self, denuvo_detected, fix_status):
        onlinefix = bool(fix_status.get("onlinefix_available"))
        bypass = bool(fix_status.get("bypass_available"))
        if denuvo_detected:
            if bypass:
                return {
                    "onlinefix_available": False,
                    "bypass_available": True,
                }
            if onlinefix:
                return {
                    "onlinefix_available": True,
                    "bypass_available": False,
                }
            return {
                "onlinefix_available": False,
                "bypass_available": False,
            }
        return {
            "onlinefix_available": onlinefix,
            "bypass_available": bypass,
        }

    def check_denuvo_drm(self, game_id, game_name, marker_only=False):
        fix_status = {"onlinefix_available": False, "bypass_available": False}
        bypass_status = {"onlinefix_available": False, "bypass_available": False}
        if not marker_only:
            fix_status = self._check_onlinefix_availability(game_id)
            bypass_status = self._check_bypass_availability(game_id)
        combined_status = {
            "onlinefix_available": bool(fix_status.get("onlinefix_available", False)),
            "bypass_available": bool(bypass_status.get("bypass_available", False)),
        }
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cookie": "birthtime=315532801; mature_content=1; lastagecheckage=1-January-1980",
            }

            for store_url in [
                f"https://store.steampowered.com/app/{game_id}/",
                f"https://store.steampowered.com/app/{game_id}/?snr=1_7_7_151_150_1",
            ]:
                response = self.session.get(store_url, headers=headers, timeout=8)
                if response.status_code != 200:
                    continue

                html_content = response.text or ""
                html_lower = html_content.lower()
                if "denuvo" in html_lower:
                    if marker_only:
                        return {
                            "denuvo_detected": True,
                            "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                            "onlinefix_available": False,
                            "bypass_available": False,
                            "activation_available": True,
                        }
                    normalized_fix = self._normalize_fix_status_for_denuvo(True, combined_status)
                    bypass_available = bool(normalized_fix.get("bypass_available", False))
                    onlinefix_available = bool(normalized_fix.get("onlinefix_available", False))
                    return {
                        "denuvo_detected": True,
                        "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                        **normalized_fix,
                        "activation_available": not bypass_available and not onlinefix_available,
                    }

                denuvo_patterns = [
                    "incorporates 3rd-party drm: denuvo",
                    "incorporates third-party drm: denuvo",
                    "3rd-party drm: denuvo",
                    "third-party drm: denuvo",
                    "drm: denuvo",
                    "drm denuvo",
                    "denuvo anti-tamper",
                    "denuvo anti tamper",
                    "denuvo protection",
                    "denuvo drm",
                    "requires denuvo",
                    "denuvo required",
                    '"drm":"denuvo"',
                ]
                if any(pattern in html_lower for pattern in denuvo_patterns):
                    if marker_only:
                        return {
                            "denuvo_detected": True,
                            "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                            "onlinefix_available": False,
                            "bypass_available": False,
                            "activation_available": True,
                        }
                    normalized_fix = self._normalize_fix_status_for_denuvo(True, combined_status)
                    bypass_available = bool(normalized_fix.get("bypass_available", False))
                    onlinefix_available = bool(normalized_fix.get("onlinefix_available", False))
                    return {
                        "denuvo_detected": True,
                        "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                        **normalized_fix,
                        "activation_available": not bypass_available and not onlinefix_available,
                    }

            if self._check_steam_api_drm(game_id, game_name):
                if marker_only:
                    return {
                        "denuvo_detected": True,
                        "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                        "onlinefix_available": False,
                        "bypass_available": False,
                        "activation_available": True,
                    }
                normalized_fix = self._normalize_fix_status_for_denuvo(True, combined_status)
                bypass_available = bool(normalized_fix.get("bypass_available", False))
                onlinefix_available = bool(normalized_fix.get("onlinefix_available", False))
                return {
                    "denuvo_detected": True,
                    "message": f"Denuvo protection was detected for {game_name} ({game_id}).",
                    **normalized_fix,
                    "activation_available": not bypass_available and not onlinefix_available,
                }

            normalized_fix = self._normalize_fix_status_for_denuvo(False, fix_status)
            return {
                "denuvo_detected": False,
                "message": f"No Denuvo markers were found for {game_name} ({game_id}).",
                **normalized_fix,
                "activation_available": False,
            }
        except Exception as exc:
            return {
                "denuvo_detected": False,
                "message": f"Denuvo check failed: {exc}",
                **fix_status,
                "activation_available": False,
            }

    def normalize_search_results(self, payload):
        results = []
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("id") or "")
            if not app_id.isdigit():
                continue
            name = item.get("name") or f"Steam App {app_id}"
            name_lower = name.lower()
            item_type = str(item.get("type", "") or "").lower()
            if item_type == "dlc":
                continue
            if any(marker in name_lower for marker in [" dlc", "dlc ", " pack", " addon", " - expansion"]):
                continue
            tags = str(item.get("tags", [])).lower()
            if "dlc" in tags or "downloadable content" in tags or "add-on" in tags or "addon" in tags:
                continue
            if " - " in name_lower:
                base, extra = name_lower.split(" - ", 1)
                dlc_suffixes = ["edition", "version", "pack", "dlc", "expansion", "bundle"]
                if any(suffix in extra for suffix in dlc_suffixes):
                    continue
            results.append({
                "id": app_id,
                "name": name,
                "image": item.get("tiny_image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
                "description": str(item.get("short_description") or item.get("description") or item.get("headline") or "") .strip(),
            })
        return results[:10]

    def get_hot_games(self):
        return [
            {"id": "1245620", "name": "ELDEN RING", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_184x69.jpg"},
            {"id": "1174180", "name": "Red Dead Redemption 2", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1174180/capsule_184x69.jpg"},
            {"id": "292030", "name": "The Witcher 3: Wild Hunt", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/292030/capsule_184x69.jpg"},
            {"id": "1091500", "name": "Cyberpunk 2077", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/capsule_184x69.jpg"},
            {"id": "1151640", "name": "Horizon Zero Dawn Complete Edition", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1151640/capsule_184x69.jpg"},
            {"id": "1196590", "name": "Resident Evil Village", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1196590/capsule_184x69.jpg"},
            {"id": "1850570", "name": "DEATH STRANDING DIRECTOR'S CUT", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1850570/capsule_184x69.jpg"},
            {"id": "990080", "name": "Hogwarts Legacy", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/990080/capsule_184x69.jpg"},
        ]

    def _get_bypass_game_candidates(self):
        # Create a simple bypass candidate list based on hot games and manually curated popular titles.
        return [
            {"id": "1245620", "name": "ELDEN RING", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_184x69.jpg"},
            {"id": "292030", "name": "The Witcher 3: Wild Hunt", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/292030/capsule_184x69.jpg"},
            {"id": "1091500", "name": "Cyberpunk 2077", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/capsule_184x69.jpg"},
            {"id": "1151640", "name": "Horizon Zero Dawn Complete Edition", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1151640/capsule_184x69.jpg"},
            {"id": "990080", "name": "Hogwarts Legacy", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/990080/capsule_184x69.jpg"},
        ]

    def _load_bypass_entries_from_remote(self):
        self._refresh_remote_bypass_appids(force=True)
        appids = self.remote_bypass_appids
        results = []
        for appid in appids:
            details = self._get_steam_app_details(appid)
            if details:
                results.append({
                    "id": str(appid),
                    "name": details.get("name") or f"AppID {appid}",
                    "image": details.get("image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                    "description": details.get("description") or "",
                })
            else:
                results.append({
                    "id": str(appid),
                    "name": f"AppID {appid}",
                    "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                    "description": "",
                })
        return results

    def _is_bypass_appid(self, appid):
        appid_str = str(appid or "").strip()
        if not appid_str.isdigit():
            return False
        self._refresh_remote_bypass_appids(force=True)
        return appid_str in self.remote_bypass_appids

    def get_bypass_games(self, query=None):
        results = self._load_bypass_entries_from_remote()
        if query:
            query = str(query or "").strip().lower()
            results = [
                game for game in results
                if query in str(game.get('id', '')).lower() or query in str(game.get('name', '')).lower()
            ]
        return results

    def _download_text(self, url, timeout=12):
        try:
            response = self.session.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.text
        except Exception:
            pass
        return None

    def _parse_github_release_page_asset_names(self, html, owner, repo_name, tag):
        pattern = rf'/{re.escape(owner)}/{re.escape(repo_name)}/releases/download/{re.escape(tag)}/([^"\']+)'
        return set(re.findall(pattern, html))

    def _get_bypass_game_candidates(self):
        self._refresh_remote_bypass_appids(force=True)
        results = []
        for appid in self.remote_bypass_appids:
            details = self._get_steam_app_details(appid)
            if details:
                results.append({
                    "id": str(appid),
                    "name": details.get("name") or f"AppID {appid}",
                    "image": details.get("image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                    "description": details.get("description") or "",
                })
            else:
                results.append({
                    "id": str(appid),
                    "name": f"AppID {appid}",
                    "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                    "description": "",
                })
        return results

    def extract_appid(self, value):
        text = (value or "").strip()
        if not text:
            return None
        if text.isdigit():
            return text
        if " - " in text:
            prefix = text.split(" - ", 1)[0].strip()
            if prefix.isdigit():
                return prefix
        return None

    def format_search_value(self, game):
        game_id = str(game.get("id") or "").strip()
        name = str(game.get("name") or "").strip()
        if game_id and name:
            return f"{game_id} - {name}"
        if game_id:
            return game_id
        return name

    def build_search_option(self, game):
        return {
            "id": str(game.get("id") or "").strip(),
            "name": str(game.get("name") or "").strip(),
            "image": str(game.get("image") or "").strip(),
            "search_value": self.format_search_value(game),
        }

    def search_games(self, query):
        query = (query or "").strip()
        if not query:
            return self.get_hot_games()

        app_id = query.split(" - ", 1)[0] if " - " in query else query
        if app_id.isdigit():
            details = self._get_steam_app_details(app_id)
            if details:
                return [details]

        search_term = query.split(" - ", 1)[1] if " - " in query else query
        if not search_term.strip():
            return []

        if len(search_term.strip()) <= 3:
            search_term = search_term.strip() + "*"

        try:
            response = self.session.get(
                "https://store.steampowered.com/api/storesearch",
                params={
                    "term": search_term,
                    "l": "english",
                    "cc": "US",
                    "category1": 998,
                    "infinite": 1,
                },
                timeout=4,
            )
            if response.status_code != 200:
                return []
            data = response.json()
            items = data.get("items", []) or []
            results = self.normalize_search_results({"items": items})
            if not results and len(search_term.strip()) <= 3:
                response = self.session.get(
                    "https://store.steampowered.com/api/storesearch",
                    params={
                        "term": search_term.strip().replace("*", ""),
                        "l": "english",
                        "cc": "US",
                        "category1": 998,
                        "infinite": 1,
                    },
                    timeout=4,
                )
                if response.status_code == 200:
                    data = response.json()
                    results = self.normalize_search_results({"items": data.get("items", []) or []})
            return results
        except Exception:
            return []

    def search_bypass_games(self, query):
        return self.get_bypass_games(query=query)

    def _download_github_branch_tree(self, owner, repo_name, branch):
        tree_paths = self._download_github_branch_tree_from_api(owner, repo_name, branch)
        if tree_paths:
            return tree_paths
        return self._download_github_branch_tree_from_html(owner, repo_name, branch)

    def _download_github_branch_tree_from_api(self, owner, repo_name, branch):
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
            response = self.session.get(api_url, timeout=10)
            if response.status_code != 200:
                return None
            data = response.json()
            tree = data.get("tree", [])
            if not isinstance(tree, list):
                return None
            return [entry.get("path") for entry in tree if entry.get("type") == "blob" and isinstance(entry.get("path"), str)]
        except Exception:
            return None

    def _download_github_branch_tree_from_html(self, owner, repo_name, branch):
        try:
            page_url = f"https://github.com/{owner}/{repo_name}/tree/{branch}"
            response = self.session.get(
                page_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                timeout=15,
            )
            if response.status_code != 200:
                return None
            html = response.text or ""
            pattern = rf'href=["\']/{re.escape(owner)}/{re.escape(repo_name)}/blob/{re.escape(branch)}/([^"\'#]+)["\']'
            paths = []
            for match in re.finditer(pattern, html, flags=re.IGNORECASE):
                file_path = match.group(1)
                if file_path and file_path not in paths:
                    paths.append(file_path)
            return paths if paths else None
        except Exception:
            return None

    def _download_github_branch_files(self, owner, repo_name, branch, dest_dir):
        tree_paths = self._download_github_branch_tree(owner, repo_name, branch)
        if not tree_paths:
            return None
        downloaded_paths = []
        for path in tree_paths:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{path}"
            try:
                response = self.session.get(raw_url, timeout=20)
                if response.status_code != 200:
                    continue
                target_path = os.path.join(dest_dir, path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(response.content)
                downloaded_paths.append(target_path)
            except Exception:
                continue
        return dest_dir if downloaded_paths else None

    def _extract_downloaded_archive(self, asset_path, dest_dir):
        if not asset_path or not os.path.exists(asset_path):
            return False
        lower_path = asset_path.lower()
        if lower_path.endswith(".zip"):
            try:
                import zipfile
                with zipfile.ZipFile(asset_path, "r") as archive:
                    archive.extractall(dest_dir)
                os.remove(asset_path)
                return True
            except Exception:
                return False

        if lower_path.endswith(".rar"):
            try:
                extractor = None
                candidate_paths = []
                if shutil.which("unrar"):
                    candidate_paths.append(shutil.which("unrar"))
                if shutil.which("7z"):
                    candidate_paths.append(shutil.which("7z"))

                for candidate in [
                    r"C:\Program Files\WinRAR\UnRAR.exe",
                    r"C:\Program Files\7-Zip\7z.exe",
                    r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
                    r"C:\Program Files (x86)\7-Zip\7z.exe",
                ]:
                    if os.path.exists(candidate):
                        candidate_paths.append(candidate)

                for candidate in candidate_paths:
                    if not candidate:
                        continue
                    if os.path.basename(candidate).lower().startswith("unrar"):
                        extractor = candidate
                        break
                    if os.path.basename(candidate).lower().startswith("7z"):
                        extractor = candidate
                        break

                if not extractor:
                    return False

                startupinfo = None
                creationflags = 0
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

                if os.path.basename(extractor).lower().startswith("unrar"):
                    subprocess.run(
                        [extractor, "x", "-y", asset_path, dest_dir],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                    )
                else:
                    subprocess.run(
                        [extractor, "x", asset_path, f"-o{dest_dir}"],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                    )

                try:
                    os.remove(asset_path)
                except Exception:
                    pass
                return True
            except Exception:
                return False

        return False

    def _download_manifesthub_release_asset(self, appid, dest_dir):
        backend_url = None
        try:
            response = self.session.get(
                f"{BACKEND_BASE_URL}/bypass-info",
                params={"appid": str(appid)},
                timeout=12,
            )
            if response.status_code == 200:
                payload = response.json() or {}
                backend_url = payload.get("download_url") or None
        except Exception:
            backend_url = None

        if backend_url:
            try:
                os.makedirs(dest_dir, exist_ok=True)
                asset_path = self._download_url_to_temp(backend_url, dest_dir, f"{appid}_asset")
                if asset_path and self._extract_downloaded_archive(asset_path, dest_dir):
                    return dest_dir
                return None
            except Exception:
                return None

        url = self._find_manifesthub_release_asset_url(appid)
        if not url:
            return None
        try:
            response = self.session.get(url, stream=True, timeout=60)
            if response.status_code != 200:
                return None
            os.makedirs(dest_dir, exist_ok=True)
            asset_name = os.path.basename(urlparse(url).path) or f"{appid}_asset"
            asset_path = os.path.join(dest_dir, asset_name)
            with open(asset_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            if self._extract_downloaded_archive(asset_path, dest_dir):
                return dest_dir
            return None
        except Exception:
            return None

    def _create_package_temp_dir(self, appid):
        try:
            return tempfile.mkdtemp(prefix=f"gamedrop_{appid}_")
        except Exception:
            fallback = os.path.join(tempfile.gettempdir(), f"gamedrop_{appid}")
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def _patch_lua_setmanifest_files(self, root_dir, uncomment=True):
        if not root_dir or not os.path.isdir(root_dir):
            return []
        patched_files = []
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if not filename.lower().endswith(".lua"):
                    continue
                full_path = os.path.join(dirpath, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if uncomment:
                        modified = re.sub(
                            r'(?mi)^(?P<indent>\s*)--\s*(?P<code>.*\b(setManifestid|setManifest)\b.*)$',
                            r"\1\2",
                            content,
                        )
                    else:
                        modified = re.sub(
                            r'(?mi)^(?P<indent>\s*)(?!--\s*)(?P<code>.*\b(setManifestid|setManifest)\b.*)$',
                            r"\1-- \2",
                            content,
                        )
                    if modified != content:
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(modified)
                        patched_files.append(full_path)
                except Exception:
                    continue
        return patched_files

    def _get_steam_lua_dir(self):
        try:
            from file_protection import get_steam_path
        except Exception:
            return None

        steam_path = get_steam_path()
        if not steam_path:
            return None

        lua_dir = os.path.join(steam_path, "config", "lua")
        try:
            os.makedirs(lua_dir, exist_ok=True)
            return lua_dir
        except Exception:
            return None

    def _install_lua_files_to_steam(self, root_dir):
        if not root_dir or not os.path.isdir(root_dir):
            return []

        lua_dir = self._get_steam_lua_dir()
        if not lua_dir:
            return []

        installed_files = []
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if not filename.lower().endswith(".lua"):
                    continue
                source_path = os.path.join(dirpath, filename)
                dest_path = os.path.join(lua_dir, filename)
                try:
                    shutil.copy2(source_path, dest_path)
                    installed_files.append(dest_path)
                except Exception:
                    continue
        return installed_files

    def _remove_steam_lua_files(self, appid):
        try:
            from file_protection import get_steam_path
        except Exception:
            return 0

        steam_path = get_steam_path()
        if not steam_path:
            return 0

        removed_count = 0
        appid_str = str(appid).lower()
        candidate_dirs = [
            os.path.join(steam_path, "config", "lua"),
            os.path.join(steam_path, "config", "stplug-in"),
        ]

        for lua_dir in candidate_dirs:
            if not os.path.isdir(lua_dir):
                continue

            for filename in os.listdir(lua_dir):
                lower_name = filename.lower()
                if not (lower_name.endswith(".lua") or lower_name.endswith(".lua.disabled")):
                    continue

                full_path = os.path.join(lua_dir, filename)
                remove_file = False

                if appid_str in lower_name:
                    remove_file = True
                else:
                    try:
                        if lower_name.endswith(".lua") or lower_name.endswith(".lua.disabled"):
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read().lower()
                            if appid_str in content and ("setmanifest" in content or "setmanifestid" in content):
                                remove_file = True
                    except Exception:
                        pass

                if not remove_file:
                    continue

                try:
                    os.remove(full_path)
                    removed_count += 1
                except Exception:
                    continue

        return removed_count

    def _find_lua_files_in_repos(self, appid, temp_root=None):
        """Find Lua files specifically from repos using the branch-tree download path."""
        lua_repos = [
            ("kkrmpubg", "ManifestHub"),
            ("dvahana2424-web", "sojogamesdatabase1"),
            ("hammerwebsite12", "sojogames2"),
        ]
        if not temp_root:
            temp_root = self._create_package_temp_dir(appid)

        for owner, repo_name in lua_repos:
            branch_dir = os.path.join(temp_root, owner, repo_name, str(appid), "lua")
            branch_path = self._download_github_branch_files(owner, repo_name, str(appid), branch_dir)
            if branch_path and self._has_lua_files(branch_path):
                return branch_path
        return None

    def _has_lua_files(self, directory):
        """Check if directory contains any .lua files."""
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                if filename.lower().endswith(".lua"):
                    return True
        return False

    def _has_any_downloaded_files(self, directory):
        """Check if directory contains any downloaded files."""
        if not directory or not os.path.isdir(directory):
            return False
        for _, _, filenames in os.walk(directory):
            if filenames:
                return True
        return False

    def _find_package_in_repos(self, appid):
        repo_order = [
            ("kkrmpubg", "ManifestHub"),
            ("dvahana2424-web", "sojogamesdatabase1"),
            ("hammerwebsite12", "sojogames2"),
            ("SteamAutoCracks", "ManifestHub"),
        ]
        temp_root = self._create_package_temp_dir(appid)
        appid_str = str(appid).lower()

        for owner, repo_name in repo_order:
            try:
                branch_dir = os.path.join(temp_root, owner, repo_name, str(appid), "branch")
                tree_paths = self._download_github_branch_tree(owner, repo_name, str(appid))
                if not tree_paths:
                    continue

                files_to_download = []
                root_files = []
                folder_files = []

                for file_path in tree_paths:
                    if '/' in file_path:
                        folder_files.append(file_path)
                        files_to_download.append(file_path)
                    else:
                        if file_path.lower().startswith(appid_str):
                            root_files.append(file_path)
                            files_to_download.append(file_path)

                if not folder_files and root_files:
                    valid_root_files = []
                    for root_file in root_files:
                        ext = os.path.splitext(root_file)[1].lower()
                        if ext in ('.lua', '.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz', '.exe', '.dll', '.bin', '.dat'):
                            valid_root_files.append(root_file)
                    if not valid_root_files:
                        continue
                    root_files = valid_root_files
                    files_to_download = valid_root_files

                if not files_to_download:
                    continue

                os.makedirs(branch_dir, exist_ok=True)
                downloaded_paths = []
                for file_path in files_to_download:
                    try:
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{appid}/{file_path}"
                        response = self.session.get(raw_url, timeout=20)
                        if response.status_code != 200:
                            continue
                        target_path = os.path.join(branch_dir, file_path)
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, 'wb') as f:
                            f.write(response.content)
                        downloaded_paths.append(target_path)
                    except Exception:
                        continue

                if downloaded_paths:
                    archive_extensions = ('.zip', '.tar.gz', '.tgz', '.tar', '.7z', '.rar')
                    extraction_failed = False
                    for archive_path in [p for p in downloaded_paths if p.lower().endswith(archive_extensions)]:
                        extracted = self._extract_downloaded_archive(archive_path, branch_dir)
                        if extracted:
                            try:
                                os.remove(archive_path)
                            except Exception:
                                pass
                        else:
                            extraction_failed = True
                    if extraction_failed:
                        continue
                    return {"path": branch_dir, "owner": owner, "repo": repo_name, "source": "branch", "temp_root": temp_root}
            except Exception:
                continue

        return None


    def _download_url_to_temp(self, url, temp_dir, filename_hint=None):
        try:
            os.makedirs(temp_dir, exist_ok=True)
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or (filename_hint or str(int(time.time())))
            destination = os.path.join(temp_dir, filename)
            response = self.session.get(url, stream=True, timeout=60)
            if response.status_code != 200:
                return None
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
            return destination
        except Exception:
            return None

    def _download_release_asset(self, release_info, temp_dir, appid):
        if not release_info or not isinstance(release_info, dict) or not release_info.get("url"):
            return None
        archive_path = self._download_url_to_temp(release_info["url"], temp_dir, f"{appid}_release")
        if not archive_path:
            return None
        extracted_dir = os.path.join(temp_dir, "extracted")
        if self._extract_downloaded_archive(archive_path, extracted_dir):
            return extracted_dir
        return None

    def _download_onlinefix_package(self, appid):
        downloads_temp_dir = self._create_package_temp_dir(appid)
        if os.path.exists(downloads_temp_dir):
            try:
                shutil.rmtree(downloads_temp_dir)
            except Exception:
                pass

        temp_dir = os.path.join(downloads_temp_dir, "release")
        release_path = self._download_manifesthub_release_asset(appid, temp_dir)
        return release_path

    def _cleanup_onlinefix_temp_files(self, temp_folder):
        try:
            if not temp_folder:
                return
            normalized_path = os.path.abspath(str(temp_folder))
            if os.path.exists(normalized_path):
                if os.path.isdir(normalized_path):
                    shutil.rmtree(normalized_path, ignore_errors=True)
                else:
                    os.remove(normalized_path)
            if os.path.basename(normalized_path).lower() == "extracted":
                parent_dir = os.path.dirname(normalized_path)
                if parent_dir and os.path.exists(parent_dir):
                    shutil.rmtree(parent_dir, ignore_errors=True)
        except Exception:
            pass

    def _get_steam_library_roots(self):
        candidate_roots = []
        try:
            from file_protection import get_steam_path
            steam_path = get_steam_path()
            if steam_path:
                candidate_roots.append(steam_path)
        except Exception:
            pass

        for path in [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
            r"D:\Steam",
            r"E:\Steam",
            r"D:\SteamLibrary",
            r"E:\SteamLibrary",
        ]:
            if os.path.isdir(path) and path not in candidate_roots:
                candidate_roots.append(path)

        if shutil.which("steam.exe"):
            steam_exe = os.path.realpath(shutil.which("steam.exe"))
            steam_dir = os.path.dirname(steam_exe)
            if steam_dir and steam_dir not in candidate_roots:
                candidate_roots.append(steam_dir)

        libraries = []
        seen = set()
        for root in candidate_roots:
            if not root or not os.path.isdir(root):
                continue
            normalized = os.path.normpath(root)
            if normalized in seen:
                continue
            seen.add(normalized)

            steam_parts = [part.lower() for part in normalized.split(os.sep) if part]
            if "steamapps" in steam_parts:
                steamapps_index = steam_parts.index("steamapps")
                steam_root = os.sep.join(normalized.split(os.sep)[:steamapps_index])
                if not steam_root:
                    steam_root = os.path.splitdrive(normalized)[0] + os.sep
            elif normalized.lower().endswith(os.path.join("steamapps", "common")):
                steam_root = os.path.dirname(os.path.dirname(normalized))
            elif normalized.lower().endswith("steamapps"):
                steam_root = os.path.dirname(normalized)
            elif normalized.lower().endswith("common"):
                steam_root = os.path.dirname(normalized)
            else:
                steam_root = normalized

            common_library = os.path.join(steam_root, "steamapps", "common")
            if os.path.isdir(common_library) and common_library not in libraries:
                libraries.append(common_library)

            libraryfolders_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
            if os.path.exists(libraryfolders_path):
                try:
                    with open(libraryfolders_path, "r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read()
                    for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                        lib_path = match.group(1).replace('\\\\', '\\')
                        common_path = os.path.join(lib_path, "steamapps", "common")
                        if os.path.isdir(common_path) and common_path not in libraries:
                            libraries.append(common_path)
                except Exception:
                    pass

        return libraries

    def _normalize_game_name(self, game_name):
        if not game_name:
            return None
        normalized = re.sub(r"[^a-z0-9]+", " ", str(game_name).lower()).strip()
        return normalized

    def _folder_name_matches_game_name(self, folder_name, normalized_game_name):
        if not folder_name or not normalized_game_name:
            return False
        folder_normalized = re.sub(r"[^a-z0-9]+", " ", str(folder_name).lower()).strip()
        if folder_normalized == normalized_game_name:
            return True
        if normalized_game_name in folder_normalized:
            return True
        folder_tokens = set(folder_normalized.split())
        name_tokens = set(normalized_game_name.split())
        return bool(name_tokens and name_tokens.issubset(folder_tokens))

    def _find_steam_game_folder(self, steam_libraries, appid, game_name=None):
        for library_path in steam_libraries:
            try:
                steamapps_path = os.path.dirname(library_path)
                appmanifest_file = os.path.join(steamapps_path, f"appmanifest_{appid}.acf")
                if os.path.exists(appmanifest_file):
                    with open(appmanifest_file, "r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read()
                    match = re.search(r'"installdir"\s+"([^"]+)"', content)
                    if match:
                        install_dir = match.group(1)
                        candidate_folder = os.path.join(library_path, install_dir)
                        if os.path.isdir(candidate_folder):
                            return candidate_folder
            except Exception:
                continue
        return None

    def _strip_package_wrapper(self, relative_paths):
        if not relative_paths:
            return []
        wrapper_names = {path.split(os.sep)[0] for path in relative_paths if os.sep in path}
        if len(wrapper_names) != 1:
            return relative_paths

        wrapper = next(iter(wrapper_names))
        stripped = []
        for rel_path in relative_paths:
            parts = rel_path.split(os.sep)
            if len(parts) > 1 and parts[0] == wrapper:
                stripped.append(os.path.join(*parts[1:]))
            else:
                stripped.append(rel_path)
        return stripped

    def _find_steam_game_folder_from_package(self, steam_libraries, package_folder, appid, game_name=None):
        for library_path in steam_libraries:
            try:
                steamapps_path = os.path.dirname(library_path)
                appmanifest_file = os.path.join(steamapps_path, f"appmanifest_{appid}.acf")
                if os.path.exists(appmanifest_file):
                    with open(appmanifest_file, "r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read()
                    match = re.search(r'"installdir"\s+"([^"]+)"', content)
                    if match:
                        install_dir = match.group(1)
                        candidate_folder = os.path.join(library_path, install_dir)
                        if os.path.isdir(candidate_folder):
                            return candidate_folder
            except Exception:
                continue
        return None

    def _validate_steam_game_folder(self, package_folder, steam_folder, game_name=None):
        if not package_folder or not os.path.isdir(package_folder) or not steam_folder or not os.path.isdir(steam_folder):
            return False

        package_paths = []
        onlinefix_files = set()
        archive_extensions = (".zip", ".tar.gz", ".tgz", ".tar", ".7z", ".rar")
        for root, _, files in os.walk(package_folder):
            for filename in files:
                if filename.lower().endswith(archive_extensions):
                    continue
                src_path = os.path.join(root, filename)
                rel_path = os.path.relpath(src_path, package_folder)
                package_paths.append(rel_path)
                if filename.lower().endswith((".exe", ".dll")):
                    onlinefix_files.add(rel_path)

        if not package_paths:
            return False

        stripped_paths = self._strip_package_wrapper(package_paths)
        normalized_package_paths = set(path.replace("\\", "/").lower() for path in package_paths)
        normalized_stripped_paths = set(path.replace("\\", "/").lower() for path in stripped_paths)
        package_names = {os.path.basename(path).lower() for path in package_paths}
        package_names.update(os.path.basename(path).lower() for path in stripped_paths)

        steam_has_exe = False
        for root, _, files in os.walk(steam_folder):
            for filename in files:
                if filename.lower().endswith(".exe"):
                    steam_has_exe = True
                    break
            if steam_has_exe:
                break

        if not steam_has_exe:
            return False

        for rel_path in normalized_package_paths | normalized_stripped_paths:
            steam_file_path = os.path.join(steam_folder, *rel_path.split("/"))
            if os.path.exists(steam_file_path):
                return True

        for root, _, files in os.walk(steam_folder):
            for filename in files:
                if filename.lower() in package_names:
                    return True

        normalized_game_name = self._normalize_game_name(game_name)
        if normalized_game_name and self._folder_name_matches_game_name(os.path.basename(steam_folder), normalized_game_name):
            return True

        return False

    def _copy_files_to_steam_folder(self, source_folder, steam_folder):
        copied_files = []
        archive_extensions = (".zip", ".tar.gz", ".tgz", ".tar", ".7z", ".rar")

        files_to_copy = []
        for root, _, files in os.walk(source_folder):
            for filename in files:
                src_path = os.path.join(root, filename)
                if src_path.lower().endswith(archive_extensions):
                    continue
                files_to_copy.append(src_path)

        if not files_to_copy:
            return copied_files

        rel_paths = [os.path.relpath(src_path, source_folder) for src_path in files_to_copy]
        strip_wrapper = False
        wrapper = None
        nested_paths = [rel_path for rel_path in rel_paths if os.sep in rel_path]
        if nested_paths:
            wrapper_names = {rel_path.split(os.sep)[0] for rel_path in nested_paths}
            if len(wrapper_names) == 1:
                wrapper_candidate = next(iter(wrapper_names))
                wrapper_dir = os.path.join(source_folder, wrapper_candidate)
                if os.path.isdir(wrapper_dir):
                    strip_wrapper = True
                    wrapper = wrapper_candidate

        for src_path in files_to_copy:
            try:
                rel_path = os.path.relpath(src_path, source_folder)
                path_parts = rel_path.split(os.sep)
                if strip_wrapper and len(path_parts) > 1 and path_parts[0] == wrapper:
                    rel_path = os.path.join(*path_parts[1:])
                dst_path = os.path.join(steam_folder, rel_path)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                copied_files.append(dst_path)
            except Exception:
                continue

        for root, _, files in os.walk(steam_folder):
            for filename in files:
                if filename.lower().endswith(archive_extensions) and filename.lower().startswith(str(os.path.basename(steam_folder)).lower()):
                    try:
                        os.remove(os.path.join(root, filename))
                    except Exception:
                        pass

        return copied_files

    def _copy_onlinefix_to_steam(self, onlinefix_folder, steam_folder, appid, denuvo=False, steam_libraries=None, game_name=None):
        copied_files = []
        archive_extensions = (".zip", ".tar.gz", ".tgz", ".tar", ".7z", ".rar")

        files_to_copy = []
        for root, _, files in os.walk(onlinefix_folder):
            for filename in files:
                src_path = os.path.join(root, filename)
                if src_path.lower().endswith(archive_extensions):
                    continue
                files_to_copy.append(src_path)

        if not files_to_copy:
            return copied_files

        rel_paths = [os.path.relpath(src_path, onlinefix_folder) for src_path in files_to_copy]
        strip_wrapper = False
        wrapper = None
        nested_paths = [rel_path for rel_path in rel_paths if os.sep in rel_path]
        if nested_paths:
            wrapper_names = {rel_path.split(os.sep)[0] for rel_path in nested_paths}
            if len(wrapper_names) == 1:
                wrapper_candidate = next(iter(wrapper_names))
                wrapper_dir = os.path.join(onlinefix_folder, wrapper_candidate)
                if os.path.isdir(wrapper_dir):
                    strip_wrapper = True
                    wrapper = wrapper_candidate

        for src_path in files_to_copy:
            try:
                rel_path = os.path.relpath(src_path, onlinefix_folder)
                path_parts = rel_path.split(os.sep)
                if strip_wrapper and len(path_parts) > 1 and path_parts[0] == wrapper:
                    rel_path = os.path.join(*path_parts[1:])

                dst_path = os.path.join(steam_folder, rel_path)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                copied_files.append(dst_path)
            except Exception:
                continue

        for root, _, files in os.walk(steam_folder):
            for filename in files:
                if filename.lower().endswith(archive_extensions) and filename.lower().startswith(str(appid).lower()):
                    try:
                        os.remove(os.path.join(root, filename))
                    except Exception:
                        pass

        return copied_files

    def _apply_onlinefix_package(self, appid, game_name=None, denuvo=True):
        appid = self.extract_appid(str(appid or ""))
        if not appid:
            return {"ok": False, "message": "Please enter a valid Steam AppID."}

        steam_libraries = self._get_steam_library_roots()
        if not steam_libraries:
            return {"ok": False, "message": "Unable to find your Steam libraries."}

        steam_game_folder = self._find_steam_game_folder(steam_libraries, appid, game_name=game_name)
        downloaded_files = None

        if not steam_game_folder:
            downloaded_files = self._download_onlinefix_package(appid)
            if downloaded_files:
                steam_game_folder = self._find_steam_game_folder_from_package(
                    steam_libraries, downloaded_files, appid, game_name=game_name
                )

        if not steam_game_folder:
            return {
                "ok": False,
                "message": f"The game for AppID {appid} is not installed in Steam yet. Install the game first, then try the bypass/OnlineFix button again."
            }

        if downloaded_files is None:
            downloaded_files = self._download_onlinefix_package(appid)

        if not downloaded_files:
            message = "Denuvo bypass file is not available for this game" if denuvo else "OnlineFix file is not available for this game"
            return {"ok": False, "message": f"{message} (ID: {appid})."}

        if not self._validate_steam_game_folder(downloaded_files, steam_game_folder, game_name=game_name):
            alt_folder = self._find_steam_game_folder_from_package(
                steam_libraries, downloaded_files, appid, game_name=game_name
            )
            if alt_folder and alt_folder != steam_game_folder:
                steam_game_folder = alt_folder

        if not steam_game_folder or not os.path.isdir(steam_game_folder):
            return {
                "ok": False,
                "message": f"The game for AppID {appid} is not installed in Steam yet. Install the game first, then try the bypass/OnlineFix button again."
            }

        if not self._validate_steam_game_folder(downloaded_files, steam_game_folder, game_name=game_name):
            return {
                "ok": False,
                "message": f"The game for AppID {appid} is not installed in Steam yet. Install the game first, then try the bypass/OnlineFix button again."
            }

        copied_files = self._copy_onlinefix_to_steam(downloaded_files, steam_game_folder, appid, denuvo=denuvo, steam_libraries=steam_libraries, game_name=game_name)
        if not copied_files:
            return {"ok": False, "message": "No files were copied into the Steam game folder."}

        label = "Bypass" if denuvo else "OnlineFix"
        result = {
            "ok": True,
            "message": f"{label} applied successfully to {game_name or f'AppID {appid}' }.",
            "copied_files": len(copied_files),
        }

        self._cleanup_onlinefix_temp_files(downloaded_files)
        return result

    def _get_steam_install_dir(self):
        try:
            from file_protection import get_steam_path
            steam_path = get_steam_path()
            if steam_path and os.path.isdir(steam_path):
                return steam_path
        except Exception:
            pass

        candidates = []
        program_files_x86 = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
        if program_files_x86:
            candidates.append(os.path.join(program_files_x86, "Steam"))
        candidates.extend([
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
        ])

        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return candidate
        return None

    def _terminate_processes_by_name(self, process_names):
        targets = {name.lower() for name in process_names if name}
        if not targets:
            return []

        terminated = []

        try:
            import psutil
        except Exception:
            psutil = None

        if psutil:
            for proc in psutil.process_iter(["name"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                except Exception:
                    continue
                if name in targets:
                    try:
                        proc.terminate()
                        terminated.append(name)
                    except Exception:
                        pass

        if len(terminated) >= len(targets):
            return terminated

        try:
            kernel32 = ctypes.windll.kernel32
            snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
            if snapshot == -1:
                return terminated

            try:
                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [
                        ("dwSize", ctypes.c_ulong),
                        ("cntUsage", ctypes.c_ulong),
                        ("th32ProcessID", ctypes.c_ulong),
                        ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", ctypes.c_ulong),
                        ("cntThreads", ctypes.c_ulong),
                        ("th32ParentProcessID", ctypes.c_ulong),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", ctypes.c_ulong),
                        ("szExeFile", ctypes.c_wchar * 260),
                    ]

                entry = PROCESSENTRY32()
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
                if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                    while True:
                        name = entry.szExeFile.lower()
                        if name in targets:
                            try:
                                handle = kernel32.OpenProcess(0x0001F0000, False, entry.th32ProcessID)
                                if handle:
                                    try:
                                        kernel32.TerminateProcess(handle, 1)
                                    finally:
                                        kernel32.CloseHandle(handle)
                                terminated.append(name)
                            except Exception:
                                pass
                        if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                            break
            finally:
                kernel32.CloseHandle(snapshot)
        except Exception:
            pass

        return terminated

    def _close_steam(self):
        if sys.platform != "win32":
            return

        try:
            os.startfile("steam://exit")
        except Exception:
            try:
                ctypes.windll.shell32.ShellExecuteW(None, "open", "steam://exit", None, None, 0)
            except Exception:
                pass

        for _ in range(3):
            self._terminate_processes_by_name(["steam.exe", "steamwebhelper.exe", "SteamService.exe"])
            time.sleep(0.5)

        for _ in range(3):
            self._terminate_processes_by_name(["steam.exe", "steamwebhelper.exe", "SteamService.exe"])
            time.sleep(0.5)

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            subprocess.call(
                ["taskkill", "/F", "/IM", "steam.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    def _download_file_to_path(self, url, destination):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "wb") as handle:
                handle.write(data)
            return destination
        except Exception:
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
            return destination

    def run_action(self, action, payload=None):
        payload = payload or {}
        action = (action or "").strip()

        try:
            if action == "ping":
                return {"ok": True, "message": "WebView shell is live."}

            if action == "add_game" or action == "add_denuvo_game":
                appid = self.extract_appid(str(payload.get("appid", "") or ""))
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}

                self.status = f"Downloading game package for AppID {appid}"
                package_info = self._find_package_in_repos(appid)
                if not package_info:
                    self.status = f"No package found for AppID {appid}"
                    return {
                        "ok": False,
                        "message": f"Unable to download package for AppID {appid} from configured repositories.",
                    }

                # For Denuvo games, ensure Lua files are available from reliable sources
                lua_source_path = package_info["path"]
                if action == "add_denuvo_game":
                    # Try to get Lua files from repos known to have them
                    lua_files_path = self._find_lua_files_in_repos(appid, package_info.get("temp_root"))
                    if lua_files_path and self._has_lua_files(lua_files_path):
                        lua_source_path = lua_files_path

                uncomment = action == "add_denuvo_game" or bool(payload.get("denuvo_detected"))
                patched_files = self._patch_lua_setmanifest_files(package_info["path"], uncomment=uncomment)
                
                # Also patch Lua files from the separate source if they're different
                if lua_source_path != package_info["path"]:
                    self._patch_lua_setmanifest_files(lua_source_path, uncomment=uncomment)
                
                patch_message = ""
                if patched_files:
                    if uncomment:
                        patch_message = f" Lua manifest calls were restored in {len(patched_files)} file(s)."
                    else:
                        patch_message = f" Lua manifest calls were commented in {len(patched_files)} file(s)."

                # Install Lua files from the source that has them
                installed_files = self._install_lua_files_to_steam(lua_source_path)
                install_message = ""
                if installed_files:
                    install_message = f" {len(installed_files)} Lua file(s) installed to Steam."
                else:
                    install_message = " No Lua files were installed to Steam."

                details = self._get_steam_app_details(appid)
                game_name = details.get("name") if details else f"AppID {appid}"
                self.status = f"Downloaded package for AppID {appid}"
                return {
                    "ok": True,
                    "message": f"{game_name} is added to the Steam library.{patch_message}{install_message}",
                }

            if action == "remove_game":
                appid = self.extract_appid(str(payload.get("appid", "") or ""))
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}

                removed_count = self._remove_steam_lua_files(appid)
                self.status = f"Removed Lua files for AppID {appid}"

                if removed_count:
                    return {
                        "ok": True,
                        "removed": True,
                        "message": f"Game removed from Steam for AppID {appid}.",
                    }

                return {
                    "ok": True,
                    "removed": False,
                    "message": "Game is not on your library.",
                }

            if action == "search_games":
                query = str(payload.get("query", "") or "").strip()
                results = self.search_games(query)
                self.status = f"Loaded {len(results)} Steam matches"
                return {"ok": True, "results": results, "query": query}

            if action == "get_bypass_games":
                results = self.get_bypass_games()
                self.status = f"Loaded {len(results)} bypass candidates"
                return {"ok": True, "results": results}

            if action == "search_bypass_games":
                query = str(payload.get("query", "") or "").strip()
                results = self.get_bypass_games(query=query)
                self.status = f"Loaded {len(results)} bypass candidates"
                return {"ok": True, "results": results, "query": query}

            if action == "get_game_details":
                appid = self.extract_appid(str(payload.get("appid", "") or ""))
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}
                details = self._get_steam_app_details(appid)
                if not details:
                    return {"ok": False, "message": f"Unable to load details for AppID {appid}."}
                return {"ok": True, **details}

            if action == "check_denuvo":
                appid = str(payload.get("appid", "") or "").strip()
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}
                marker_only = bool(payload.get("marker_only"))
                result = self.check_denuvo_drm(appid, payload.get("name") or f"Steam App {appid}", marker_only=marker_only)
                self.status = result["message"]
                return {"ok": True, **result}

            if action == "check_bypass":
                appid = self.extract_appid(str(payload.get("appid", "") or ""))
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}
                result = self._check_bypass_availability(appid)
                self.status = f"Checked bypass availability for AppID {appid}"
                return {"ok": True, **result}

            if action == "launch_activation":
                from denuvo_activation import find_activation_executable, launch_activation_executable
                exe_path = find_activation_executable()
                if not exe_path:
                    return {"ok": False, "message": "Denuvo activator could not be found."}
                launch_activation_executable(exe_path, parent_to_launcher=False, use_ipc=False, hide_windows=False)
                self.status = "Denuvo activator launched"
                return {"ok": True, "message": "Denuvo activator launched."}

            if action == "close_activation":
                from denuvo_activation import _stop_active_helper
                _stop_active_helper()
                self.status = "Denuvo activator closed"
                return {"ok": True, "message": "Denuvo activator closed."}

            if action == "redeem_activation_code":
                from denuvo_activation import redeem_denuvo_activation_code
                code = str(payload.get("code", "") or "").strip()
                if not code:
                    return {"ok": False, "message": "Please enter an activation code."}
                result = redeem_denuvo_activation_code(code, server_url=payload.get("server_url") or None, target_path=payload.get("target_path") or None)
                self.status = "Activation code processed" if result.get("ok") else "Activation code failed"
                return result

            if action == "install_engine":
                from denuvo_activation import find_activation_executable, launch_activation_command, launch_activation_executable
                exe_path = find_activation_executable()
                if not exe_path:
                    return {"ok": False, "message": "The activation helper could not be found."}
                launch_activation_command(exe_path, ["--install-engine"], wait=False, timeout=900, elevate=True)
                launch_activation_executable(exe_path, parent_to_launcher=False, use_ipc=False, hide_windows=False)
                self.status = "OpenSteamTool install started"
                return {"ok": True, "message": "OpenSteamTool install started. The page will update once the helper finishes."}

            if action == "update_engine":
                from denuvo_activation import find_activation_executable, launch_activation_command
                exe_path = find_activation_executable()
                if not exe_path:
                    return {"ok": False, "message": "The activation helper could not be found."}
                launch_activation_command(exe_path, ["--update-engine"], wait=False, timeout=900, elevate=True)
                self.status = "OpenSteamTool repair/update started"
                return {"ok": True, "message": "Repair / update started."}

            if action == "uninstall_engine":
                from denuvo_activation import find_activation_executable, launch_activation_command
                exe_path = find_activation_executable()
                if not exe_path:
                    return {"ok": False, "message": "The activation helper could not be found."}
                launch_activation_command(exe_path, ["--uninstall-engine"], wait=False, timeout=900, elevate=True)
                self.status = "OpenSteamTool uninstall started"
                return {"ok": True, "message": "Remove OpenSteamTool started."}

            if action == "repair":
                steam_dir = self._get_steam_install_dir()
                if not steam_dir or not os.path.isdir(steam_dir):
                    return {"ok": False, "message": "Steam installation directory could not be found."}

                self._close_steam()
                self.status = "Steam closed for repair"

                dll_names = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
                repo_base = "https://raw.githubusercontent.com/kkrmpubg/gamedrop-updates/main"

                for dll_name in dll_names:
                    target_path = os.path.join(steam_dir, dll_name)
                    download_url = f"{repo_base}/{dll_name}"
                    self._download_file_to_path(download_url, target_path)

                return {
                    "ok": True,
                    "message": "Repair completed. Please reopen Steam manually when you're ready.",
                }

            if action == "restart_steam":
                from test import restart_steam_process
                restart_steam_process()
                self.status = "Steam restart requested"
                return {"ok": True, "message": "Steam restart requested."}

            if action == "onlinefix":
                appid = self.extract_appid(str(payload.get("appid", "") or ""))
                if not appid:
                    return {"ok": False, "message": "Please enter a valid Steam AppID."}

                game_name = (payload.get("name") or payload.get("game_name") or "").strip() or None
                details = self._get_steam_app_details(appid)
                if details and not game_name:
                    game_name = details.get("name")

                result = self._apply_onlinefix_package(appid, game_name=game_name, denuvo=True)
                self.status = result.get("message", "OnlineFix flow ready")
                return result

            return {"ok": False, "message": f"Unknown action: {action}"}
        except Exception as exc:
            return {"ok": False, "message": f"Action failed: {exc}"}


def build_html(logo_uri=None):
    logo_uri = logo_uri or ""
    logo_markup = ""
    if logo_uri:
        try:
            parsed = urlparse(logo_uri)
            candidate_path = None
            if parsed.scheme == "file":
                decoded_path = unquote(parsed.path)
                if sys.platform.startswith("win") and decoded_path.startswith("/"):
                    decoded_path = decoded_path[1:]
                candidate_path = Path(decoded_path)
            else:
                candidate_path = Path(logo_uri)

            if candidate_path.exists():
                extension = candidate_path.suffix.lower().lstrip('.')
                if extension in {"png", "jpg", "jpeg", "gif", "webp", "ico"}:
                    mime = "image/png" if extension == "png" else "image/jpeg" if extension in {"jpg", "jpeg"} else "image/gif" if extension == "gif" else "image/webp" if extension == "webp" else "image/x-icon"
                    logo_data = base64.b64encode(candidate_path.read_bytes()).decode("ascii")
                    logo_markup = f'<img class="sidebar-logo" src="data:{mime};base64,{logo_data}" alt="GameDrop logo" />'
        except Exception:
            logo_markup = ""

    if not logo_markup:
        logo_markup = '<div class="sidebar-brand-mark" style="display: inline-flex; align-items: center; gap: 10px; font-weight: 800; letter-spacing: 0.04em; color: #ffe17a; font-size: 16px;"><span style="display: inline-flex; width: 26px; height: 26px; border-radius: 8px; align-items: center; justify-content: center; background: linear-gradient(135deg, #ff1f1f, #ffd400); color: #111; font-size: 13px;">G</span><span>GameDrop</span></div>'

    html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>GameDrop Steam</title>
      <style>
        :root {
          color-scheme: dark;
          --bg: #080808;
          --card: #151515;
          --card-strong: #1f1f1f;
          --ink: #fdf6e7;
          --muted: #b6b0a6;
          --accent: #ffd400;
          --accent-2: #ff1f1f;
          --accent-soft: rgba(255, 31, 31, 0.16);
          --accent-soft-2: rgba(255, 212, 0, 0.16);
          --danger: #ff6b4a;
          --border: #3f3020;
        }
        * { box-sizing: border-box; }
        body {
          margin: 0;
          font-family: Segoe UI, Arial, sans-serif;
          background: radial-gradient(circle at top left, rgba(255, 31, 31, 0.24) 0%, rgba(255, 212, 0, 0.12) 42%, var(--bg) 100%);
          color: var(--ink);
          min-height: 100vh;
        }
        .shell {
          padding: 24px;
          display: grid;
          gap: 16px;
          min-height: 100vh;
          height: 100vh;
          overflow: hidden;
          visibility: visible;
          opacity: 1;
          transition: opacity 120ms ease;
        }
        .shell.ready { opacity: 1; }
        .shell.is-hidden { visibility: hidden; opacity: 0; }
        .app-shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 16px; min-height: 0; height: 100%; }
        .sidebar, .card { background: linear-gradient(135deg, rgba(15, 23, 40, 0.98), rgba(8, 14, 24, 0.96)); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 18px 58px rgba(0,0,0,0.3); }
        .hero { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); box-shadow: inset 0 1px 0 rgba(255,255,255,0.04); }
        .sidebar { padding: 18px 14px; display: flex; flex-direction: column; gap: 16px; min-height: 0; overflow-y: auto; }
        .sidebar-brand { display: flex; flex-direction: column; gap: 6px; padding: 6px 4px 10px; }
        .sidebar-brand strong { font-size: 15px; }
        .sidebar-brand span { color: rgba(255,255,255,0.62); font-size: 12px; line-height: 1.35; }
        .sidebar-nav { display: grid; gap: 10px; padding-top: 4px; }
        .sidebar-section-title {
          font-size: 11px; text-transform: uppercase; letter-spacing: 0.16em; color: rgba(255,255,255,0.45); font-weight: 700; padding: 4px 6px 2px;
        }
        .nav-item {
          width: 100%; text-align: left; border: 1px solid rgba(255,255,255,0.06); color: rgba(255,255,255,0.8); background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: 14px;
          display: flex; align-items: center; justify-content: flex-start; gap: 10px; font-weight: 600; font-size: 13px; cursor: pointer; letter-spacing: 0.01em;
          transition: transform 160ms ease, border-color 160ms ease, background 160ms ease, color 160ms ease, box-shadow 160ms ease;
        }
        .nav-icon {
          width: 17px; height: 17px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; color: currentColor;
        }
        .nav-icon svg {
          width: 16px; height: 16px; display: block;
        }
        .nav-icon svg path,
        .nav-icon svg circle,
        .nav-icon svg rect,
        .nav-icon svg line {
          stroke: currentColor; stroke-width: 1.7; fill: none; stroke-linecap: round; stroke-linejoin: round;
        }
        .nav-label { display: inline-block; }
        .nav-item.primary { background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.08); color: rgba(255,255,255,0.92); }
        .nav-item.primary:hover { background: rgba(255,255,255,0.07); transform: translateX(1px); }
        .nav-item.active { color: white; background: linear-gradient(135deg, rgba(255, 31, 31, 0.24), rgba(255, 212, 0, 0.15)); border-color: rgba(255, 212, 0, 0.28); box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 10px 22px rgba(255, 31, 31, 0.16); }
        .nav-item:hover, .nav-item:focus {
          color: white;
          background: linear-gradient(135deg, rgba(255, 31, 31, 0.24), rgba(255, 212, 0, 0.15));
          border-color: rgba(255, 212, 0, 0.28);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 10px 22px rgba(255, 31, 31, 0.16);
          outline: none;
        }
        .nav-item.secondary { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.012); border-color: rgba(255,255,255,0.04); font-weight: 600; padding: 10px 12px; opacity: 0.82; font-size: 12px; }
        .nav-item.secondary:hover { color: rgba(255,255,255,0.8); background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.08); transform: translateX(1px); opacity: 1; }
        .nav-item.secondary .nav-hint { color: rgba(255,255,255,0.44); }
        .nav-item:not(.secondary) { box-shadow: inset 0 1px 0 rgba(255,255,255,0.05); }
        .nav-item:not(.secondary):hover { background: rgba(255,255,255,0.08); }
        .sidebar-footer { margin-top: auto; display: grid; gap: 10px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); }
        .workspace {
          display: grid;
          gap: 6px;
          min-width: 0;
          min-height: 0;
          grid-template-rows: auto minmax(0, 1fr);
          overflow: hidden;
        }
        .workspace > section.card:first-of-type { padding-top: 0; }
        .topbar { display: flex; justify-content: space-between; align-items: center; width: 100%; min-height: 80px; height: 80px; padding: 0 20px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; backdrop-filter: blur(10px); }
        .topbar-brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
        .topbar-title-group { display: grid; gap: 4px; min-width: 0; }
        .topbar-title { font-size: 16px; font-weight: 700; color: white; line-height: 1.2; }
        .topbar-subtitle { font-size: 12px; color: rgba(255,255,255,0.72); line-height: 1.4; }
        .topbar-status { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.92); font-size: 12px; font-weight: 700; box-shadow: inset 0 1px 0 rgba(255,255,255,0.03); }
        .topbar-status.ready .status-dot { width: 6px; height: 6px; border-radius: 50%; background: #39d353; box-shadow: 0 0 0 3px rgba(57,211,83,0.12); }
        .hero-copy { display: grid; gap: 10px; min-width: 0; min-height: 48px; height: auto; overflow: hidden; width: 100%; }
        .hero-title-block { display: grid; gap: 6px; }
        .hero-title-block h1 { margin: 0; font-size: 26px; line-height: 1.08; color: white; }
        .hero-title-block p { margin: 0; color: rgba(255,255,255,0.75); font-size: 14px; line-height: 1.6; max-width: 680px; }
        .hero-title-block p:empty { display: none; }
        .hero-copy h1 { margin: 0; font-size: 28px; line-height: 1.15; }
        .hero-copy p { margin: 0; color: rgba(255,255,255,0.75); font-size: 14px; max-width: 560px; }
        .hero-copy.fade-transition { animation: hero-fade 220ms ease; }
        @keyframes hero-fade { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        .hero-badge { display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 999px; background: rgba(255,255,255,0.08); color: #fff; border: 1px solid rgba(255,255,255,0.14); font-size: 12px; font-weight: 700; margin-bottom: 0; letter-spacing: 0.02em; }
        .steps {
          display: flex; gap: 0; margin: 0 0 12px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%;
          padding: 6px; border-radius: 999px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
        }
        .step-pill {
          position: relative; display: inline-flex; align-items: center; justify-content: center;
          padding: 8px 14px; color: var(--muted); font-size: 13px; min-width: 96px; flex: 0 1 auto;
        }
        .step-pill:not(:last-child)::after {
          content: '›'; position: absolute; right: -4px; top: 50%; transform: translateY(-50%); color: rgba(255,255,255,0.25); font-size: 16px;
        }
        .step-pill.active {
          background: linear-gradient(135deg, var(--accent-2), var(--accent) 100%); color: white; border-radius: 999px;
          box-shadow: 0 8px 22px rgba(255, 31, 31, 0.24);
        }
        .hidden { display: none !important; }
        .hero h1 { margin: 0 0 6px; font-size: 26px; }
        .hero p { margin: 0; color: var(--muted); }
        .pill { background: linear-gradient(135deg, var(--accent-2), var(--accent) 100%); color: white; padding: 8px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; box-shadow: 0 10px 24px rgba(255, 31, 31, 0.2); position: relative; overflow: hidden; }
        .pill::after {
          content: '';
          position: absolute;
          top: -40%;
          left: -60%;
          width: 40%;
          height: 200%;
          background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.75) 50%, rgba(255,255,255,0) 100%);
          transform: rotate(25deg) translateX(-200%);
          opacity: 0;
          pointer-events: none;
        }
        .pill:hover::after, .pill.shine-anim::after {
          opacity: 1;
          animation: shine 1s cubic-bezier(.2,.9,.3,1) forwards;
        }
        @keyframes shine {
          from { transform: rotate(25deg) translateX(-200%); opacity: 0; }
          30% { opacity: 0.9; }
          to { transform: rotate(25deg) translateX(220%); opacity: 0; }
        }
        .content-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.9fr); gap: 16px; position: relative; margin-top: 0; }
        .content-grid.single-column {
          display: flex !important;
          flex-direction: column;
          grid-template-columns: none !important;
          justify-items: normal;
          align-items: center;
          justify-content: flex-start;
          align-content: flex-start;
          width: 100%;
          min-height: 100%;
          padding-top: 8px;
        }
        .content-grid.single-column > section.card { width: min(980px, 100%); margin-inline: auto; }
        .content-grid.single-column > #home-panel,
        .content-grid.single-column > .home-panel {
          width: min(980px, 100%);
          margin-inline: auto;
          justify-self: center;
          align-self: center;
        }
        .content-grid.content-transition { animation: content-slide 240ms ease; }
        @keyframes content-slide {
          from { opacity: 0; transform: translateX(14px); }
          to { opacity: 1; transform: translateX(0); }
        }
        .thumbnail-panel {
          display: grid; gap: 16px; align-content: start; min-height: 460px;
          background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .thumbnail-preview {
          position: relative; overflow: hidden; border-radius: 18px; min-height: 320px;
          background: linear-gradient(180deg, rgba(10,19,32,0.96), rgba(13,30,51,0.92));
          border: 1px solid rgba(255,255,255,0.08);
          display: flex; align-items: center; justify-content: center; padding: 14px;
        }
        .thumbnail-preview img {
          max-width: 100%; max-height: 100%; object-fit: contain; display: block;
        }
        .thumbnail-preview span {
          color: rgba(255,255,255,0.68); font-size: 14px; text-align: center; padding: 14px;
        }
        .thumbnail-meta { display: grid; gap: 8px; }
        .thumbnail-meta h3 { margin: 0; font-size: 20px; color: white; }
        .thumbnail-meta p { margin: 0; color: rgba(255,255,255,0.72); line-height: 1.55; font-size: 13px; }
        .thumbnail-meta .meta { display: grid; gap: 6px; color: rgba(255,255,255,0.68); font-size: 13px; }
        .card { padding: 18px; }
        .card h2 { margin: 0 0 8px; font-size: 17px; }
        .card p { color: var(--muted); line-height: 1.45; }
        .actions { display: grid; gap: 10px; }
        .home-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }
        .home-panel {
          background: linear-gradient(135deg, rgba(15, 23, 40, 0.98), rgba(8, 14, 24, 0.96));
          border: 1px solid var(--border);
          box-shadow: 0 18px 58px rgba(0,0,0,0.3);
          border-radius: 18px;
          width: 100%;
          max-width: 980px;
          margin-inline: auto;
          align-self: center;
        }
        .home-panel .card { padding: 18px; }
        .home-panel-intro { display: grid; gap: 10px; margin-bottom: 18px; }
        .home-panel h2 { margin: 0; font-size: 22px; color: white; }
        .home-panel p { margin: 0; color: rgba(255,255,255,0.72); font-size: 14px; line-height: 1.6; }
        .home-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }
        .guide-panel {
          margin-top: 8px; padding: 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.08);
          background: rgba(255,255,255,0.03); box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .guide-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
        .guide-title { font-size: 15px; font-weight: 700; color: white; }
        .guide-subtitle { margin-top: 4px; color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.6; }
        .detail-panel-title {
          margin: 0 0 18px;
          font-size: 17px;
          font-weight: 700;
          color: white;
          background: transparent;
          padding: 0;
          border-radius: 0;
          border: none;
          max-width: fit-content;
          letter-spacing: 0.01em;
          line-height: 1.3;
          box-shadow: none;
          transition: opacity 220ms ease, transform 220ms ease, max-height 220ms ease, margin-bottom 220ms ease, padding 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
          overflow: hidden;
        }
        .fade-hidden {
          opacity: 0;
          transform: translateY(-10px);
          max-height: 0;
          margin-top: 0;
          margin-bottom: 0;
          padding-top: 0;
          padding-bottom: 0;
          border-color: transparent;
          box-shadow: none;
          pointer-events: none;
        }
        .fade-visible {
          opacity: 1;
          transform: translateY(0);
          max-height: 160px;
          margin-bottom: 18px;
          padding-top: 14px;
          padding-bottom: 14px;
          border-color: rgba(255,255,255,0.10);
          box-shadow: 0 2px 16px rgba(0,0,0,0.08);
        }
        .action-flow-title {
          margin-top: 0 !important;
          margin-bottom: 8px !important;
          color: #f7d59c;
          font-size: 18px;
        }
        #action-panel.fade-hidden {
          opacity: 0;
          transform: translateY(-8px);
          max-height: 0;
          margin: 0;
          padding: 0;
          overflow: hidden;
          pointer-events: none;
        }
        #action-panel.fade-visible {
          opacity: 1;
          transform: translateY(0);
          max-height: 260px;
          margin-top: 18px;
          padding-top: 0;
          padding-bottom: 0;
          overflow: visible;
        }
        .hidden { display: none !important; }
        .guide-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-top: 16px; }
        .home-card {
          padding: 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); cursor: pointer;
          transition: transform 160ms ease, border-color 160ms ease, background 160ms ease, box-shadow 160ms ease;
          display: grid; gap: 8px;
        }
        .home-card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.22); background: rgba(255,255,255,0.08); box-shadow: 0 12px 30px rgba(0,0,0,0.18); }
        .home-card.secondary { background: rgba(255,255,255,0.02); border-color: rgba(255,255,255,0.08); }
        .home-card-icon {
          width: 34px; height: 34px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;
          background: linear-gradient(135deg, rgba(255, 212, 0, 0.2), rgba(255, 31, 31, 0.16)); color: #ffe17a; font-size: 16px; font-weight: 800;
        }
        .home-card strong { display: block; font-size: 15px; margin-bottom: 4px; color: white; }
        .home-card span { color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.45; }
        .home-card .card-kicker { font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #ffd44d; font-weight: 700; }
        .guide-step {
          padding: 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04);
          display: flex; flex-direction: column; gap: 10px;
        }
        .guide-step strong { font-size: 14px; color: white; }
        .guide-step span { color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.65; }
        .guide-step .step-badge {
          width: 34px; height: 34px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
          background: linear-gradient(135deg, rgba(255, 212, 0, 0.2), rgba(255, 31, 31, 0.16)); color: white; font-size: 13px; font-weight: 800;
        }
          width: 28px; height: 28px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
          background: linear-gradient(135deg, var(--accent-2), var(--accent)); color: white; font-size: 12px; font-weight: 700;
        }
        .home-card {
          padding: 16px; border-radius: 16px; border: 1px solid var(--border); background: linear-gradient(135deg, rgba(255, 31, 31, 0.16), rgba(255, 212, 0, 0.08));
          cursor: pointer; transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease; min-height: 112px; display: flex; flex-direction: column; justify-content: center;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 26px rgba(0,0,0,0.16);
          gap: 6px;
        }
        .home-card:hover { transform: translateY(-2px); border-color: var(--accent-2); box-shadow: 0 16px 32px rgba(255, 31, 31, 0.16); }
        .home-card-icon {
          width: 34px; height: 34px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center;
          background: rgba(255,255,255,0.08); color: #ffe17a; font-size: 15px; font-weight: 700; margin-bottom: 2px;
        }
        .home-card strong { display: block; font-size: 15px; margin-bottom: 2px; }
        .home-card span { color: var(--muted); font-size: 13px; line-height: 1.45; }
        .home-card .card-kicker { font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #ffe17a; font-weight: 700; }
        .back-button {
          margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,0.06); color: var(--ink);
          border: 1px solid var(--border); cursor: pointer; align-self: flex-start;
        }
        .refresh-suggestions-button {
          margin-top: 12px;
          padding: 10px 14px;
          border-radius: 999px;
          background: linear-gradient(135deg, var(--accent), #ff8c1f);
          color: #190b04;
          border: 1px solid rgba(255, 216, 118, 0.34);
          box-shadow: 0 10px 22px rgba(255, 93, 25, 0.18);
          font-weight: 800;
          align-self: center;
        }
        .refresh-suggestions-button:hover {
          transform: translateY(-1px);
          box-shadow: 0 14px 28px rgba(255, 93, 25, 0.24);
        }
        .action-help {
          margin-top: 12px; padding: 14px 15px; border-radius: 14px;
          background: linear-gradient(135deg, rgba(255, 31, 31, 0.17), rgba(255, 212, 0, 0.12));
          border: 1px solid rgba(143, 211, 255, 0.24);
          color: var(--ink); min-height: 86px;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .action-help strong { display: block; margin-bottom: 6px; color: #ffe17a; font-size: 14px; }
        .action-help span { color: #dce7f7; line-height: 1.5; font-size: 14px; }
        .completion-panel {
          display: grid; gap: 12px; margin-top: 18px; padding: 18px; border-radius: 18px;
          background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
        }
        .completion-panel h3 { margin: 0; font-size: 18px; color: white; }
        .completion-panel p { margin: 0; color: rgba(255,255,255,0.78); line-height: 1.65; }
        .success-panel {
          display: grid; gap: 18px; margin: 0 auto; padding: 28px; border-radius: 24px;
          width: min(100%, 760px);
          grid-column: 1 / -1;
          justify-self: center;
          align-self: center;
          background: linear-gradient(135deg, rgba(255, 142, 33, 0.16), rgba(255, 255, 255, 0.04));
          border: 1px solid rgba(255, 177, 75, 0.24);
          box-shadow: 0 20px 45px rgba(0,0,0,0.16);
          text-align: center;
          align-items: center;
          justify-content: center;
          position: relative;
          overflow: hidden;
        }
        .result-step-card {
          display: grid; gap: 16px; width: 100%; justify-items: center;
        }
        .result-step-copy { display: grid; gap: 8px; justify-items: center; text-align: center; }
        .result-step-title {
          margin: 0;
          font-size: 24px;
          color: #ffd36d;
          letter-spacing: 0.01em;
        }
        .result-step-message {
          margin: 0;
          width: 100%;
          max-width: 560px;
          color: rgba(255,255,255,0.9);
          line-height: 1.65;
          font-size: 15px;
        }
        .success-note { font-size: 14px; color: rgba(255, 218, 148, 0.92); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
        .success-note.hidden { display: none !important; }
        .success-panel .inline-actions {
          display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;
          margin-top: 4px;
        }
        .success-panel button {
          min-width: 220px;
          padding: 12px 18px;
          border-radius: 14px;
          background: linear-gradient(135deg, #ffb43c, #ff3f0f);
          color: #1b0f05;
          box-shadow: 0 12px 24px rgba(255, 93, 25, 0.2);
          border: 1px solid rgba(255, 216, 118, 0.34);
        }
        button {
          border: 0; border-radius: 12px; padding: 11px 14px; font-weight: 700; cursor: pointer; color: white; background: var(--accent-2); transition: transform 160ms ease, opacity 160ms ease;
        }
        button:hover { transform: translateY(-1px); opacity: 0.95; }
        button.secondary { background: #1f3a5a; }
        button.success { background: var(--accent); }
        button.danger { background: var(--danger); }
        /* Add button: prominent primary style */
        .next-button {
          background: linear-gradient(135deg, var(--accent), #ff9f1f);
          border: 1px solid rgba(255, 212, 0, 0.28);
          min-height: 48px;
          padding: 14px 24px;
          position: relative;
          display: inline-flex;
          align-items: center;
          gap: 10px;
          font-weight: 800;
          box-shadow: 0 12px 30px rgba(255, 93, 25, 0.16);
          transition: transform 140ms ease, box-shadow 140ms ease;
        }
        .next-button::before {
          content: '+';
          display: inline-block;
          font-size: 14px;
          margin-right: 4px;
          color: rgba(27,11,3,0.9);
        }
        .next-button:hover { transform: translateY(-1px); }

        /* Remove button: outlined/destructive with hover fill */
        .remove-button {
          background: transparent;
          border: 1px solid rgba(255, 90, 100, 0.28);
          color: rgba(255, 180, 180, 0.95);
          min-height: 48px;
          padding: 14px 20px;
          position: relative;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: background 160ms ease, color 160ms ease, transform 120ms ease;
        }
        .remove-button::before { content: '−'; display: inline-block; font-size: 16px; margin-right: 6px; }
        .remove-button:hover {
          background: linear-gradient(135deg, #ff5467, #c01f3d);
          color: white;
          border-color: rgba(255,112,112,0.6);
          transform: translateY(-1px);
        }
        .next-button:disabled,
        .remove-button:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }
        .field { display: grid; gap: 6px; margin-top: 10px; }
        input { width: 100%; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; background: #0b1421; color: var(--ink); }
        .search-field { position: relative; display: flex; align-items: center; width: 100%; }
        .search-field .search-icon {
          position: absolute; left: 12px; color: rgba(255,255,255,0.6); pointer-events: none;
          display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
        }
        .search-field .search-icon svg {
          width: 16px; height: 16px; display: block;
        }
        .search-field .search-icon svg path,
        .search-field .search-icon svg circle,
        .search-field .search-icon svg line {
          stroke: currentColor; stroke-width: 1.6; fill: none; stroke-linecap: round; stroke-linejoin: round;
        }
        .search-field input { padding-left: 40px; padding-right: 40px; min-height: 46px; font-size: 15px; border-radius: 10px; }
        .search-field input:focus { box-shadow: 0 8px 30px rgba(255,160,40,0.06); border-color: rgba(255,160,40,0.6); outline: none; }
        .search-clear {
          position: absolute; right: 8px; background: transparent; border: none; color: rgba(255,255,255,0.7);
          padding: 6px 8px; border-radius: 8px; cursor: pointer; display: none; font-size: 14px;
          align-items: center; justify-content: center;
        }
        .search-clear svg {
          width: 14px; height: 14px; display: block;
        }
        .search-clear svg line {
          stroke: currentColor; stroke-width: 1.7; stroke-linecap: round;
        }
        .search-clear:hover { background: rgba(255,255,255,0.02); }
        .search-suggestions { display: grid; gap: 8px; margin-top: 6px; max-height: 320px; overflow-y: auto; padding-right: 4px; }
        .search-item {
          display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 12px; border: 1px solid var(--border);
          background: rgba(10, 19, 32, 0.9); cursor: pointer; transition: transform 120ms ease, border-color 120ms ease;
        }
        .search-item:hover { transform: translateY(-1px); border-color: var(--accent-2); }
        .search-thumb { width: 56px; height: 22px; border-radius: 8px; background: linear-gradient(135deg, rgba(255, 212, 0, 0.3), rgba(255, 31, 31, 0.28)); display: flex; align-items: center; justify-content: center; color: #fff4d6; font-size: 11px; overflow: hidden; }
        .search-thumb img { width: 100%; height: 100%; object-fit: cover; }
        .bypass-panel {
          display: grid;
          gap: 16px;
          margin-top: 18px;
          max-height: min(58vh, 520px);
          overflow-y: auto;
          overflow-x: hidden;
          overflow-anchor: none;
          padding-right: 6px;
          overscroll-behavior: contain;
          scrollbar-gutter: stable;
        }
        .bypass-gallery {
          display: grid;
          gap: 8px;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        }
        .bypass-gallery.single-result {
          justify-content: center;
          grid-template-columns: repeat(auto-fit, minmax(180px, 220px));
          margin-inline: auto;
        }
        .bypass-gallery.single-result .bypass-item {
          grid-template-rows: minmax(120px, auto) auto;
        }
        .bypass-item {
          display: grid;
          grid-template-rows: 1fr auto;
          width: 100%;
          border-radius: 16px;
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(9, 15, 28, 0.95);
          padding: 0;
          overflow: hidden;
          cursor: pointer;
          text-align: left;
          transition: transform 180ms ease, box-shadow 180ms ease;
        }
        .bypass-item:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .bypass-item-image { min-height: 84px; background: #0e172b; display: grid; place-items: center; overflow: hidden; }
        .bypass-item-image img { width: 100%; height: 100%; object-fit: cover; }
        .bypass-item-placeholder { color: rgba(255,255,255,0.55); font-size: 13px; padding: 24px; }
        .bypass-item-body { padding: 8px 10px; display: grid; gap: 4px; }
        .bypass-item-body h3 { margin: 0; font-size: 13px; color: #fff; line-height: 1.25; }
        .bypass-item-body p { margin: 0; color: rgba(255,255,255,0.68); font-size: 12px; line-height: 1.35; }
        .bypass-empty { color: rgba(255,255,255,0.72); font-size: 15px; padding: 28px; border: 1px dashed rgba(255,255,255,0.18); border-radius: 18px; text-align: center; }
        .search-item strong { display: block; font-size: 13px; }
        .search-item span { color: var(--muted); font-size: 12px; }
        .status { margin-top: 0; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.03); color: var(--ink); border: 1px solid rgba(255,255,255,0.08); min-height: 44px; line-height: 1.45; box-shadow: inset 0 1px 0 rgba(255,255,255,0.02); }
        .activation-shell { display: grid; gap: 16px; }
        .activation-hero { display: grid; gap: 6px; padding: 16px 18px; border-radius: 18px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.12); }
        .activation-hero h3 { margin: 0; color: #fff; font-size: 18px; font-weight: 600; }
        .activation-hero p { margin: 0; color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.6; max-width: 520px; }
        .activation-grid { display: block; }
        .activation-card {
          max-width: 520px;
          margin: 0 auto;
          padding: 22px;
          border-radius: 20px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          display: grid;
          gap: 14px;
          text-align: left;
        }
        .activation-step-card { margin-top: 4px; }
        .activation-card .action-cta { width: 100%; min-height: 50px; padding: 14px 16px; font-size: 15px; justify-content: center; }
        .activation-card .status { margin: 0; padding: 0; border: none; background: transparent; color: rgba(255,255,255,0.72); min-height: auto; font-size: 13px; line-height: 1.6; }
        .activation-card .status.muted { opacity: 0.82; }
        .activation-pill, .activation-inline-row { display: none; }
        .activation-form { display: grid; gap: 8px; }
        .activation-form input { min-height: 38px; padding: 9px 11px; font-size: 14px; }
        .activation-form .next-button { min-height: 40px; padding: 9px 12px; font-size: 14px; }
        .progress-container { margin-top: 4px; display: grid; gap: 8px; padding: 12px 14px; border: 1px solid rgba(255,206,74,0.35); border-radius: 16px; background: linear-gradient(135deg, rgba(255,206,74,0.16), rgba(255,31,31,0.12)); box-shadow: 0 14px 40px rgba(0,0,0,0.18); }
        .progress-container.hidden { display: none; }
        .progress-track { width: 100%; height: 12px; border-radius: 999px; background: rgba(255,255,255,0.14); overflow: hidden; position: relative; }
        .progress-fill { width: 30%; height: 100%; background: linear-gradient(135deg, rgba(255,212,0,0.95), rgba(255,31,31,0.95)); border-radius: 999px; transform: translateX(-120%); transition: transform 220ms ease; }
        .progress-fill.indeterminate { animation: indeterminate-progress 1.4s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
        @keyframes indeterminate-progress {
          0% { transform: translateX(-120%); }
          50% { transform: translateX(20%); }
          100% { transform: translateX(120%); }
        }
        .progress-label { color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 700; }
        .repair-progress-overlay { position: fixed; inset: 0; background: rgba(4, 8, 14, 0.7); display: grid; place-items: center; z-index: 9999; padding: 24px; }
        .repair-progress-overlay.hidden { display: none; }
        .repair-progress-card { width: min(420px, 100%); padding: 20px; border-radius: 20px; background: rgba(9, 15, 28, 0.97); border: 1px solid rgba(255,206,74,0.35); box-shadow: 0 24px 70px rgba(0,0,0,0.35); display: grid; gap: 12px; }
        .repair-progress-card h3 { margin: 0; color: white; font-size: 18px; }
        .repair-progress-card p { margin: 0; color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.5; }
        .denuvo-badge,
        .fix-badge {
          margin-top: 10px; padding: 10px 14px; border-radius: 999px; display: inline-flex; align-items: center; gap: 8px;
          font-size: 13px; font-weight: 700; letter-spacing: 0.03em; width: fit-content; border: 1px solid transparent;
          box-shadow: 0 12px 25px rgba(0,0,0,0.08);
        }
        .denuvo-badge.safe,
        .fix-badge.safe { background: rgba(21, 141, 82, 0.16); color: #b7f3c7; border-color: rgba(21, 141, 82, 0.28); }
        .fix-badge.info { background: rgba(14, 102, 227, 0.16); color: #b8d8ff; border-color: rgba(14, 102, 227, 0.28); }
        .fix-badge.bypass { background: rgba(255, 180, 56, 0.18); color: #ffe5aa; border-color: rgba(255, 155, 22, 0.28); }
        .denuvo-badge.warning,
        .fix-badge.warning { background: rgba(255, 31, 31, 0.16); color: #ffb4b4; border-color: rgba(255, 31, 31, 0.28); }
        .detail-header { display: grid; gap: 10px; margin-top: 10px; }
        .step-card {
          display: grid;
          gap: 12px;
          padding: 18px;
          border-radius: 20px;
          background: linear-gradient(135deg, rgba(255, 142, 33, 0.12), rgba(255, 255, 255, 0.04));
          border: 1px solid rgba(255, 177, 75, 0.22);
          box-shadow: 0 16px 36px rgba(0,0,0,0.14);
        }
        .step-card-primary { margin-top: 16px; }
        .step-card-copy { display: grid; gap: 6px; }
        #step1-card.fade-hidden {
          opacity: 0;
          transform: translateY(-8px);
          max-height: 0;
          margin-top: 0;
          margin-bottom: 0;
          padding-top: 0;
          padding-bottom: 0;
          overflow: hidden;
          pointer-events: none;
          border-color: transparent;
          box-shadow: none;
        }
        #step1-card.fade-visible {
          opacity: 1;
          transform: translateY(0);
          max-height: 500px;
          margin-top: 16px;
          padding-top: 18px;
          padding-bottom: 18px;
          border-color: rgba(255, 177, 75, 0.22);
          box-shadow: 0 16px 36px rgba(0,0,0,0.14);
        }
        #action-panel { margin-top: 18px; padding-top: 6px; }
        .action-panel { display: block; }
        .action-step-card {
          display: grid;
          gap: 16px;
          padding: 18px;
          border-radius: 20px;
          background: linear-gradient(135deg, rgba(255, 142, 33, 0.16), rgba(255, 255, 255, 0.04));
          border: 1px solid rgba(255, 177, 75, 0.24);
          box-shadow: 0 20px 45px rgba(0,0,0,0.16);
        }
        .action-step-copy { display: grid; gap: 6px; }
        .action-step-kicker {
          width: fit-content;
          padding: 6px 10px;
          border-radius: 999px;
          background: rgba(255, 204, 102, 0.16);
          color: #ffe0a3;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.16em;
          text-transform: uppercase;
        }
        .action-step-subtitle {
          margin: 0;
          color: rgba(255,255,255,0.7);
          font-size: 13px;
          line-height: 1.55;
        }
        .action-buttons-row {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          margin-top: 4px;
        }
        .action-buttons-row.bypass-selected { justify-content: flex-start; }
        .action-buttons-left,
        .action-buttons-right,
        .action-buttons-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .action-buttons-left { justify-content: flex-start; }
        .action-buttons-right { justify-content: flex-end; }
        .action-buttons-main {
          width: 100%;
          justify-content: flex-start;
          margin-top: 6px;
          padding-top: 2px;
          border-top: 1px solid rgba(255,255,255,0.08);
        }
        .bypass-actions-group {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          justify-content: flex-end;
          margin-top: 0;
          margin-left: auto;
          width: auto;
        }
        .action-cta {
          min-height: 48px;
          padding: 12px 16px;
          border-radius: 14px;
          font-weight: 800;
          letter-spacing: 0.01em;
          border: 1px solid transparent;
          box-shadow: 0 12px 24px rgba(0,0,0,0.16);
          transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease;
        }
        .action-cta:hover { transform: translateY(-1px); box-shadow: 0 14px 30px rgba(0,0,0,0.2); }
        .action-cta.primary {
          background: linear-gradient(135deg, #ffb33f, #ff6b1f);
          color: #190b04;
          border-color: rgba(255, 216, 118, 0.34);
        }
        .action-cta.secondary {
          background: linear-gradient(135deg, rgba(255, 88, 88, 0.22), rgba(177, 33, 56, 0.28));
          color: #ffd7db;
          border-color: rgba(255, 126, 142, 0.34);
        }
        .action-cta.danger {
          background: linear-gradient(135deg, rgba(255, 91, 101, 0.24), rgba(186, 38, 64, 0.28));
          color: #ffd7db;
          border-color: rgba(255, 122, 139, 0.3);
        }
        .action-cta.ghost {
          background: rgba(255,255,255,0.04);
          color: rgba(255,255,255,0.82);
          border-color: rgba(255,255,255,0.12);
          box-shadow: none;
        }
        .action-cta:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
          box-shadow: none;
        }
        .selected-game-summary {
          display: block;
          padding: 14px 16px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 16px;
          min-height: 72px;
        }
        .selected-game-summary.empty {
          background: transparent;
          border: none;
          padding: 0;
          box-shadow: none;
          min-height: 72px;
        }
        .selected-game-title { margin: 0; font-size: 16px; color: white; }
        .selected-game-subtitle { margin: 0; color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.5; }
        .fix-legend { margin-top: 12px; color: rgba(255,255,255,0.66); font-size: 12px; line-height: 1.6; }
        .fix-legend strong { color: #fff; }
        .meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 13px; margin-top: 10px; }
        .sidebar-logo { width: 100%; height: auto; max-height: 56px; display: block; object-fit: contain; }
        @media (max-width: 1120px) {
          .app-shell { grid-template-columns: 1fr; }
          .content-grid, .home-grid { grid-template-columns: 1fr; }
          .home-panel, .guide-panel { width: 100%; }
        }
        @media (max-width: 900px) {
          .hero { flex-direction: column; align-items: flex-start; height: auto; min-height: 110px; }
          .hero-copy { width: 100%; height: auto; min-height: 80px; overflow: visible; }
          .content-grid { gap: 12px; }
          .home-grid { gap: 12px; }
          .meta { flex-direction: column; gap: 6px; }
        }
        @media (max-width: 720px) {
          body { min-height: auto; }
          .shell { padding: 14px; }
          .app-shell { gap: 12px; }
          .sidebar { padding: 14px; }
          .workspace { gap: 12px; }
          .card { padding: 14px; }
          .home-panel { padding: 14px; }
          .guide-panel { padding: 14px; }
          .home-panel-intro { gap: 8px; }
          .guide-steps { gap: 12px; }
          .guide-step { padding: 14px; }
          .step-pill { min-width: auto; padding: 8px 10px; }
          .activation-grid { grid-template-columns: 1fr; }
        }
      </style>
    </head>
    <body>
      <div class="shell">
        <div class="app-shell">
          <aside class="sidebar">
            <div class="sidebar-brand">
              <div class="hero-badge">★ GameDrop</div>
            </div>
            <nav class="sidebar-nav">
              <button class="nav-item primary active" data-flow="" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/></svg>
                </span>
                <span class="nav-label">Home</span>
              </button>
              <button class="nav-item primary" data-flow="add_game" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </span>
                <span class="nav-label">Add Game</span>
              </button>
              <button class="nav-item primary" data-flow="add_denuvo_game" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M8 10V7a4 4 0 0 1 8 0v3"/><rect x="5" y="10" width="14" height="9" rx="2"/></svg>
                </span>
                <span class="nav-label">Denuvo bypass/OnlineFix</span>
              </button>
              <button class="nav-item primary" data-flow="launch_activation" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="m13 3-7 9h5l-1 9 7-9h-5z"/></svg>
                </span>
                <span class="nav-label">Denuvo Activation</span>
              </button>
            </nav>
            <div class="sidebar-footer">
              <button class="nav-item secondary" data-flow="repair" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M15 4a2 2 0 0 1 2.8 2.8l-8.2 8.2a4 4 0 1 1-2.8-2.8l8.2-8.2Z"/></svg>
                </span>
                <span class="nav-label">Repair</span>
              </button>
              <button class="nav-item secondary" data-flow="contact_support" type="button">
                <span class="nav-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M6 7h12a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H10l-4 3V9a2 2 0 0 1 2-2Z"/></svg>
                </span>
                <span class="nav-label">Contact Support</span>
              </button>
              <div class="logo-wrap" style="margin-top: 8px; padding: 10px; border-radius: 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center;">
                __LOGO_MARKUP__
              </div>
              <div class="meta" style="display: grid; gap: 4px; margin-top: 0;">
                <span id="meta-path"></span>
                <span id="meta-version"></span>
              </div>
            </div>
          </aside>

          <main class="workspace">
            <div class="topbar">
              <div class="topbar-brand">
                <div class="hero-badge">★ Welcome to GameDrop</div>
                <div class="topbar-title-group">
                  <div class="topbar-subtitle">Drop In. Game On.</div>
                </div>
              </div>
              <div class="topbar-status ready" id="topbar-status"><span class="status-dot"></span> System ready</div>
            </div>
            <div class="content-grid single-column">
                <section class="card home-panel" id="home-panel" style="padding: 16px;">
                  <div id="wizard-panel">
                            <div class="home-panel-intro">
                      <h2 id="wizard-title">Home</h2>
                      <p id="wizard-message">This is the friendly overview for new users. It explains how GameDrop helps them add Steam games and finish installation safely.</p>
                    </div>
                    <div class="home-grid">
                      <div class="guide-panel">
                        <div class="guide-top">
                          <div>
                            <div class="card-kicker">How GameDrop works</div>
                            <div class="guide-title">Just 4 easy steps</div>
                            <div class="guide-subtitle">Follow this guided flow to add a game and install it through Steam.</div>
                          </div>
                          <button class="pill" data-flow="add_game" type="button" id="start-here-button" aria-label="Start add game flow">Start here</button>
                        </div>
                        <div class="guide-steps">
                          <div class="guide-step">
                          <div class="step-badge">1</div>
                          <strong>Start Add Game</strong>
                          <span>Open the add game flow from the sidebar.</span>
                        </div>
                        <div class="guide-step">
                          <div class="step-badge">2</div>
                          <strong>Find your game</strong>
                          <span>Search Steam or paste the AppID directly.</span>
                        </div>
                        <div class="guide-step">
                          <div class="step-badge">3</div>
                          <strong>Add game / Remove game</strong>
                          <span>Add or remove the selected game from your Steam library.</span>
                        </div>
                        <div class="guide-step">
                          <div class="step-badge">4</div>
                          <strong>Install through Steam</strong>
                          <span>Complete the process in Steam as usual.</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <section class="card hidden" id="activation-panel" style="padding: 16px;">
                  <div class="step-card step-card-primary activation-step-card">
                    <div class="step-card-copy">
                      <div class="action-step-kicker">Step 1</div>
                      <h2 class="detail-panel-title action-flow-title" id="activation-flow-title">Step 1: Open Denuvo activator</h2>
                      <p class="action-step-subtitle">Open the activator and finish the activation flow in its own window.</p>
                    </div>
                    <div class="activation-shell">
                      <div class="activation-grid">
                        <div class="activation-card">
                          <button class="action-cta primary" type="button" id="launch-activation-button">Open Denuvo activator</button>
                          <div style="color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.6; text-align: left;">
                            <strong style="display:block; margin-bottom: 8px; color: #fff;">Steps</strong>
                            <ol style="margin: 0; padding-left: 18px;">
                              <li>Paste the code into the Denuvo activator.</li>
                              <li>Press Apply ticket.</li>
                              <li>Run your game through Steam.</li>
                            </ol>
                          </div>
                          <div class="status muted" id="activation-status">Ready</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <div class="repair-progress-overlay hidden" id="repair-progress-overlay" aria-live="polite">
                  <div class="repair-progress-card">
                    <h3 id="repair-progress-title">Repair in progress</h3>
                    <p id="repair-progress-message">Preparing the Steam repair process.</p>
                    <div class="progress-container" id="repair-progress-container">
                      <div class="progress-label" id="repair-progress-label">Starting…</div>
                      <div class="progress-track">
                        <div class="progress-fill" id="repair-progress-fill"></div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- step indicator removed per user request -->
                <section class="card hidden" id="detail-panel" style="padding: 16px; display: none; flex-direction: column; min-height: 100%;">
                  <div class="step-card step-card-primary" id="step1-card">
                    <div class="step-card-copy">
                      <div class="action-step-kicker">Step 1</div>
                      <h2 class="detail-panel-title" id="step2-flow-title">Step 1: Find your game</h2>
                      <p class="action-step-subtitle">Pick a game first, then continue to the next step.</p>
                    </div>
                    <div class="detail-header">
                      <div class="selected-game-summary" id="selected-game-summary">
                        <div class="selected-game-title" id="selected-game-label">No game selected</div>
                        <div class="selected-game-subtitle" id="selected-game-subtitle">Paste an AppID or choose a result to preview the fix.</div>
                      </div>
                    </div>
                  </div>
                  <div class="completion-panel hidden" id="completion-panel">
                    <h3 id="completion-title">Game added to Steam library</h3>
                    <p id="completion-message">Please check your Steam library and install the game through Steam.</p>
                  </div>
                    <div class="field" id="search-panel">
                      <div class="search-field">
                        <span class="search-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="5.5"/><line x1="15" y1="15" x2="19" y2="19"/></svg>
                        </span>
                        <input id="appid" placeholder="Type AppID or game title" autocomplete="off" />
                        <button type="button" class="search-clear" id="search-clear" aria-label="Clear search">
                          <svg viewBox="0 0 24 24"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
                        </button>
                      </div>
                      <div class="search-suggestions" id="search-suggestions"></div>
                    </div>
                  <div class="status" id="status-box">Ready</div>
                  <div class="bypass-panel hidden" id="bypass-panel">
                    <div class="bypass-gallery" id="bypass-gallery"></div>
                  </div>
                  <div class="progress-container hidden" id="check-progress">
                    <div class="progress-track">
                      <div class="progress-fill" id="progress-fill"></div>
                    </div>
                    <div class="progress-label" id="progress-label">Working…</div>
                  </div>
                  <div class="denuvo-badge safe" id="denuvo-badge" style="display: none;">Denuvo protection detected</div>
                  <div class="fix-badge safe" id="fix-badge" style="display: none;"></div>
                  <div id="action-panel" class="action-panel fade-hidden">
                    <div class="action-step-card">
                      <div class="action-step-copy">
                        <div class="action-step-kicker">Step 2</div>
                        <h2 class="detail-panel-title action-flow-title" id="action-flow-title">Step 2: Add game / Remove game</h2>
                        <p class="action-step-subtitle" id="action-step-subtitle">Choose the best action for this selected game.</p>
                      </div>
                      <div class="action-buttons-row" id="action-buttons-row">
                        <div class="action-buttons-left">
                          <button class="action-cta secondary" id="remove-button" type="button" style="display:none;" disabled>Remove game</button>
                        </div>
                        <div class="action-buttons-right">
                          <button class="action-cta primary" id="next-button" type="button" style="display:none;" disabled>Add game to library</button>
                        </div>
                        <div class="bypass-actions-group" id="bypass-actions-group">
                          <button class="action-cta primary bypass-action" id="bypass-button" type="button" style="display:none;" disabled>Bypass / OnlineFix</button>
                        </div>
                        <div class="action-buttons-main">
                          <button class="action-cta ghost" id="back-button" type="button">← Back to Home</button>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>
                <section class="card hidden" id="no-bypass-panel" style="display: grid; gap: 18px; min-height: 360px; padding: 28px;">
                  <h2 id="no-bypass-title">No bypass / OnlineFix available</h2>
                  <p id="no-bypass-message">No bypass/OnlineFix is currently available for this game. Contact support to request it.</p>
                  <div style="display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;">
                    <button class="back-button refresh-suggestions-button" id="no-bypass-refresh-button" type="button">Refresh suggestions</button>
                    <button class="back-button" id="no-bypass-back-button" type="button">Back to game select</button>
                  </div>
                </section>
                <section class="card hidden success-panel" id="success-panel" style="display: grid; gap: 18px; min-height: 360px; padding: 28px;">
                  <div class="action-step-card result-step-card">
                    <div class="result-step-copy">
                      <h2 class="result-step-title" id="success-title">Game added to your Steam library</h2>
                      <p class="result-step-message" id="success-message">A premium fix package has been installed and is ready in Steam.</p>
                      <p id="success-note" class="success-note hidden"></p>
                    </div>
                    <div class="inline-actions">
                      <button class="success" id="success-add-more-button" type="button">Add more game</button>
                      <button class="success" id="success-home-button" type="button">Back to Home</button>
                    </div>
                  </div>
                </section>
                <section class="card hidden success-panel" id="bypass-result-panel" style="display: grid; gap: 18px; min-height: 360px; padding: 28px;">
                  <div class="action-step-card result-step-card">
                    <div class="result-step-copy">
                      <h2 class="result-step-title" id="bypass-result-title">Bypass / OnlineFix result</h2>
                      <p class="result-step-message" id="bypass-result-message">The bypass action has finished.</p>
                    </div>
                    <div class="inline-actions">
                      <button class="success" id="bypass-result-back-button" type="button">Back to game select</button>
                    </div>
                  </div>
                </section>
                <section class="card hidden thumbnail-panel" id="thumbnail-panel" style="padding: 16px;">
                  <div class="thumbnail-preview" id="thumbnail-image">
                    <span>Choose a game from search results to preview its thumbnail here.</span>
                  </div>
                  <div class="thumbnail-meta">
                    <h3 id="thumbnail-title">No game selected</h3>
                    <p id="thumbnail-subtitle">Search for a Steam title or paste an AppID to preview the selected game art.</p>
                    <div class="meta">
                      <span id="thumbnail-appid">AppID: —</span>
                      <span id="thumbnail-platform">Platform: Steam</span>
                    </div>
                  </div>
                </section>
              </div>
            </section>
          </main>
        </div>
      </div>

      <script>
        function setStatus(message) {
          const box = document.getElementById('status-box');
          if (box) box.textContent = message;
        }

        function showProgress(label) {
          const progress = document.getElementById('check-progress');
          const progressLabel = document.getElementById('progress-label');
          const progressFill = document.getElementById('progress-fill');
          if (!progress) return;
          if (progressLabel && label) {
            progressLabel.textContent = label;
          }
          if (progressFill) {
            progressFill.classList.add('indeterminate');
            progressFill.style.transform = 'translateX(-120%)';
          }
          progress.classList.remove('hidden');
        }

        function hideProgress() {
          const progress = document.getElementById('check-progress');
          const progressLabel = document.getElementById('progress-label');
          const progressFill = document.getElementById('progress-fill');
          if (!progress) return;
          progress.classList.add('hidden');
          if (progressLabel) {
            progressLabel.textContent = 'Working…';
          }
          if (progressFill) {
            progressFill.classList.remove('indeterminate');
            progressFill.style.transform = 'translateX(-120%)';
          }
        }

        function updateSystemStatus() {
          const statusBar = document.getElementById('topbar-status');
          if (!statusBar) return;
          statusBar.classList.add('ready');
          statusBar.classList.remove('maintenance');
          statusBar.innerHTML = `<span class="status-dot"></span> System ready`;
        }

        function updateSidebarStatus(state) {
          const metaPath = document.getElementById('meta-path');
          const metaVersion = document.getElementById('meta-version');
          if (metaPath) {
            metaPath.textContent = state && state.steam_path ? `Steam path: ${state.steam_path}` : 'Steam path: loading...';
          }
          if (metaVersion) {
            metaVersion.textContent = state && state.version ? `Version: ${state.version}` : 'Version: loading...';
          }
          updateActivationHelperPath(state);
        }

        function updateActivationHelperPath(state) {
          const helperPath = document.getElementById('activation-helper-path');
          if (!helperPath) return;
          if (state && state.activation_helper_path) {
            helperPath.textContent = `Helper: ${state.activation_helper_path}`;
          } else {
            helperPath.textContent = 'Helper: not found or unavailable';
          }
          updateEngineStatus(state);
        }

        function updateEngineStatus(state) {
          const engineStatus = document.getElementById('engine-status');
          if (!engineStatus) return;
          if (state && state.engine_ready) {
            engineStatus.textContent = 'Engine ready: activation can proceed.';
          } else if (state && state.activation_helper_path) {
            engineStatus.textContent = 'Engine pending: install or repair the helper first.';
          } else {
            engineStatus.textContent = 'Engine unavailable: helper was not detected.';
          }
        }

        updateSidebarStatus({});

        function updateDenuvoBadge(result) {
          const badge = document.getElementById('denuvo-badge');
          if (!badge) return;
          if (currentFlow === 'add_denuvo_game') {
            badge.style.display = 'none';
            return;
          }
          if (!result) {
            badge.style.display = 'none';
            return;
          }
          badge.style.display = 'inline-flex';
          badge.className = 'denuvo-badge ' + (result.denuvo_detected ? 'warning' : 'safe');
          badge.textContent = result.denuvo_detected ? 'Denuvo detected' : 'No Denuvo detected';
        }

        function normalizeFlag(flag) {
          return flag === true || flag === 'true';
        }

        function updateFixBadge(result) {
          const badge = document.getElementById('fix-badge');
          if (!badge) return;
          if (currentFlow === 'add_denuvo_game') {
            badge.style.display = 'none';
            return;
          }
          if (!result) {
            badge.style.display = 'none';
            return;
          }
          const denuvo = normalizeFlag(result.denuvo_detected);
          const bypass = normalizeFlag(result.bypass_available);
          const onlinefix = normalizeFlag(result.onlinefix_available);
          const activation = !bypass && !onlinefix && normalizeFlag(result.activation_available);
          if (!bypass && !onlinefix && !activation) {
            badge.style.display = 'none';
            return;
          }
          badge.style.display = 'inline-flex';
          if (bypass) {
            badge.className = 'fix-badge bypass';
            badge.textContent = 'Bypass available';
          } else if (onlinefix) {
            badge.className = 'fix-badge info';
            badge.textContent = 'OnlineFix available';
          } else if (activation) {
            badge.className = 'fix-badge safe';
            badge.textContent = 'Activation available';
          } else {
            badge.style.display = 'none';
          }
        }

        function updateHelp(button) {
          const help = document.getElementById('action-help');
          if (!help) return;
          const title = button.getAttribute('data-help-title') || 'Action';
          const body = button.getAttribute('data-help-body') || 'This button runs a workflow from the GameDrop dashboard.';
          help.innerHTML = '<strong>' + title + '</strong><span>' + body + '</span>';
        }

        function getPywebviewApi() {
          try {
            return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
          } catch (error) {
            return null;
          }
        }

        async function waitForPywebviewApi(timeoutMs = 10000) {
          const start = Date.now();
          while (Date.now() - start < timeoutMs) {
            const api = getPywebviewApi();
            if (api) {
              return api;
            }
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return null;
        }

        async function callAction(action, payload = {}) {
          const mergedPayload = {
            ...(payload || {}),
            appid: document.getElementById('appid').value || ''
          };
          const api = getPywebviewApi();
          if (!api) {
            const message = 'GameDrop interface is not ready yet.';
            setStatus(message);
            return { ok: false, message };
          }
          try {
            const result = await api.run_action(action, mergedPayload);
            const message = result && (result.message || result.error || 'Done');
            setStatus(message);
            return result;
          } catch (error) {
            const message = 'Action failed: ' + error;
            setStatus(message);
            return { ok: false, message };
          }
        }

        async function closeActivationHelper() {
          if (currentFlow !== 'launch_activation') {
            return { ok: true, message: 'No active Denuvo activator to close.' };
          }
          const result = await callAction('close_activation');
          if (!result.ok) {
            showActivationFeedback(result.message || 'Unable to close Denuvo activator.', true);
          }
          return result;
        }

        function showActivationFeedback(message, isError = false) {
          const statusElement = document.getElementById('activation-status');
          const statusBar = document.getElementById('topbar-status');
          if (statusElement) {
            statusElement.textContent = message;
          }
          setStatus(message);
          if (statusBar) {
            statusBar.classList.remove('maintenance');
            statusBar.classList.add(isError ? 'maintenance' : 'ready');
            statusBar.innerHTML = `<span class="status-dot"></span> ${message}`;
          }
        }

        function setActivationProgress(percent, label) {
          const progress = document.getElementById('activation-progress');
          const fill = document.getElementById('activation-progress-fill');
          const progressLabel = document.getElementById('activation-progress-label');
          if (!progress || !fill) return;
          const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
          fill.style.width = `${safePercent}%`;
          if (progressLabel && label) {
            progressLabel.textContent = label;
          }
          progress.classList.remove('hidden');
        }

        function startActivationProgress(label) {
          setActivationProgress(5, label || 'Preparing…');
        }

        function hideActivationProgress() {
          const progress = document.getElementById('activation-progress');
          if (!progress) return;
          progress.classList.add('hidden');
        }

        function showRepairProgress(label) {
          const overlay = document.getElementById('repair-progress-overlay');
          const title = document.getElementById('repair-progress-title');
          const message = document.getElementById('repair-progress-message');
          const fill = document.getElementById('repair-progress-fill');
          const progressLabel = document.getElementById('repair-progress-label');
          if (!overlay || !fill) return;
          if (title) title.textContent = 'Repair in progress';
          if (message) message.textContent = 'GameDrop is closing Steam and refreshing the required DLL files in your Steam folder.';
          if (progressLabel && label) progressLabel.textContent = label;
          fill.style.width = '8%';
          overlay.classList.remove('hidden');
        }

        function updateRepairProgress(percent, label) {
          const fill = document.getElementById('repair-progress-fill');
          const progressLabel = document.getElementById('repair-progress-label');
          if (!fill) return;
          const safePercent = Math.max(8, Math.min(100, Number(percent) || 8));
          fill.style.width = `${safePercent}%`;
          if (progressLabel && label) progressLabel.textContent = label;
        }

        function hideRepairProgress() {
          const overlay = document.getElementById('repair-progress-overlay');
          if (!overlay) return;
          overlay.classList.add('hidden');
        }

        async function refreshActivationState() {
          const api = getPywebviewApi();
          if (!api) {
            return false;
          }
          try {
            const state = await api.get_initial_state();
            updateSidebarStatus(state);
            return Boolean(state && state.engine_ready);
          } catch (error) {
            return false;
          }
        }

        async function waitForActivationReady(label, timeoutMs = 180000) {
          const startedAt = Date.now();
          while (Date.now() - startedAt < timeoutMs) {
            const ready = await refreshActivationState();
            if (ready) {
              return true;
            }
            await new Promise((resolve) => setTimeout(resolve, 2000));
          }
          return false;
        }

        async function waitForRepairReady(timeoutMs = 240000) {
          const startedAt = Date.now();
          let attempt = 0;
          while (Date.now() - startedAt < timeoutMs) {
            attempt += 1;
            const ready = await refreshActivationState();
            if (ready) {
              return true;
            }
            const percent = Math.min(92, 20 + Math.floor((attempt - 1) * 6));
            updateRepairProgress(percent, attempt % 2 === 0 ? 'Waiting for OpenSteamTool DLLs…' : 'Installing helper files…');
            await new Promise((resolve) => setTimeout(resolve, 2500));
          }
          return false;
        }

        async function runActivationAction(action, label, waitForReady = false) {
          const statusElement = document.getElementById('activation-status');
          startActivationProgress(label);
          if (statusElement) {
            statusElement.textContent = label;
          }
          const result = await callAction(action);
          if (!result.ok) {
            hideActivationProgress();
            if (statusElement) {
              statusElement.textContent = result.message || 'Unable to start the OpenSteamTool action.';
            }
            return result;
          }
          if (waitForReady) {
            const ready = await waitForActivationReady(label);
            hideActivationProgress();
            if (ready) {
              if (statusElement) {
                statusElement.textContent = 'OpenSteamTool is ready.';
              }
            } else if (statusElement) {
              statusElement.textContent = 'OpenSteamTool is still finishing. Please wait a moment and check again.';
            }
          } else {
            setTimeout(() => {
              hideActivationProgress();
              if (statusElement) {
                statusElement.textContent = 'OpenSteamTool action started.';
              }
            }, 1800);
          }
          return result;
        }

        async function launchActivationHelper() {
          const statusElement = document.getElementById('activation-status');
          if (statusElement) {
            statusElement.textContent = 'Starting Denuvo activator…';
          }
          const result = await callAction('launch_activation');
          if (result.ok) {
            if (statusElement) {
              statusElement.textContent = 'Denuvo activator launched.';
            }
          } else {
            if (statusElement) {
              statusElement.textContent = result.message || 'Unable to launch Denuvo activator.';
            }
          }
          return result;
        }

        function clearCompletionPanel(force = false) {
          if (!force && completionPanelVisible) {
            return;
          }
          const panel = document.getElementById('success-panel');
          if (panel) {
            panel.classList.add('hidden');
            panel.style.display = 'grid';
          }
          const bypassResultPanel = document.getElementById('bypass-result-panel');
          if (bypassResultPanel) {
            bypassResultPanel.classList.add('hidden');
            bypassResultPanel.style.display = 'grid';
          }
          completionPanelVisible = false;
        }
        function resetSearchBar() {
          if (searchInput) {
            searchInput.value = '';
          }
          if (suggestionsBox) {
            suggestionsBox.innerHTML = '';
          }
          selectedGame = null;
          lastFixResult = null;
          if (removeButton) removeButton.disabled = true;
          if (nextButton) nextButton.disabled = true;
          updateNextButton();
          updateDenuvoBadge(null);
          updateFixBadge(null);
          updateSelectedGameSummary(null);
          updateThumbnail(null);
          clearCompletionPanel();
        }
        function showCompletionPanel(game, note, options = {}) {
          const panel = document.getElementById('success-panel');
          const title = document.getElementById('success-title');
          const message = document.getElementById('success-message');
          const noteElement = document.getElementById('success-note');
          if (!panel || !title || !message || !noteElement) return;
          const name = (game && (game.name || game.id)) ? (game.name || `AppID ${game.id}`) : 'This game';
          const state = options.state || 'added';
          if (state === 'removed') {
            title.textContent = `Game removed from your Steam library`;
            message.textContent = `The Lua file was removed.`;
          } else {
            title.textContent = `${name} is added to your Steam library`;
            message.textContent = `Please check your library and install.`;
          }
          if (note) {
            noteElement.textContent = note;
            noteElement.classList.remove('hidden');
          } else {
            noteElement.classList.add('hidden');
          }
          panel.classList.remove('hidden');
          panel.style.setProperty('display', 'grid', 'important');
          panel.style.setProperty('visibility', 'visible', 'important');
          panel.style.setProperty('opacity', '1', 'important');
          panel.style.setProperty('z-index', '10', 'important');
          completionPanelVisible = true;
          const cards = document.querySelectorAll('section.card');
          cards.forEach((card) => {
            if (card !== panel) {
              card.classList.add('hidden');
              card.style.setProperty('display', 'none', 'important');
            }
          });
          const contentGrid = document.querySelector('.content-grid');
          if (contentGrid) {
            contentGrid.classList.add('single-column');
          }
          panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function showBypassResultPanel(title, message) {
          const panel = document.getElementById('bypass-result-panel');
          const titleElement = document.getElementById('bypass-result-title');
          const messageElement = document.getElementById('bypass-result-message');
          if (!panel || !titleElement || !messageElement) return;
          titleElement.textContent = title;
          messageElement.textContent = message;
          panel.classList.remove('hidden');
          panel.style.display = 'grid';
          const detailPanel = document.getElementById('detail-panel');
          const thumbnailPanel = document.getElementById('thumbnail-panel');
          const contentGrid = document.querySelector('.content-grid');
          if (detailPanel) detailPanel.classList.add('hidden');
          if (thumbnailPanel) thumbnailPanel.classList.add('hidden');
          if (contentGrid) contentGrid.classList.add('single-column');
        }

        function hideBypassResultPanel() {
          const panel = document.getElementById('bypass-result-panel');
          if (panel) {
            panel.classList.add('hidden');
            panel.style.display = 'grid';
          }
        }

        async function performRepairAction() {
          const statusElement = document.getElementById('activation-status');
          showRepairProgress('Starting Steam repair…');
          updateRepairProgress(12, 'Starting Steam repair…');
          const result = await callAction('repair');
          updateRepairProgress(result.ok ? 100 : 20, result.ok ? 'Steam DLL refresh completed.' : (result.message || 'Unable to start Steam repair.'));
          setTimeout(() => hideRepairProgress(), 1400);
          if (result.ok) {
            hideBypassResultPanel();
            if (statusElement) {
              statusElement.textContent = 'Repair complete. Please reopen Steam manually.';
            }
            setStatus(result.message || 'Repair complete. Please reopen Steam manually.');
          } else {
            if (statusElement) {
              statusElement.textContent = result.message || 'Unable to start Steam repair.';
            }
            setStatus(result.message || 'Unable to start Steam repair.');
          }
          return result;
        }

        async function switchFlow(flow) {
          const normalizedFlow = flow || '';
          if (flowSwitchInProgress) {
            return;
          }
          try {
            flowSwitchInProgress = true;
            if (currentFlow === 'launch_activation' && normalizedFlow !== 'launch_activation') {
              await closeActivationHelper();
            }
            if (normalizedFlow === 'repair') {
              await performRepairAction();
              return;
            }
            const api = getPywebviewApi();
            const state = api ? await api.get_wizard_state(normalizedFlow) : { step: 1, flow: normalizedFlow, title: 'Home', message: 'Choose a task to begin.' };
            // step indicator removed per user request
            const wizardTitle = document.getElementById('wizard-title');
            const wizardMessage = document.getElementById('wizard-message');
            const detailTitle = document.getElementById('detail-title');
            const detailDescription = document.getElementById('detail-description');
            const actionHelp = document.getElementById('action-help');
            const detailPanel = document.getElementById('detail-panel');
            const activationPanel = document.getElementById('activation-panel');
            const homePanel = document.getElementById('home-panel');
            const thumbnailPanel = document.getElementById('thumbnail-panel');
            const shouldShowHome = normalizedFlow === '';
            const shouldShowPreview = normalizedFlow === 'add_game' || normalizedFlow === 'add_denuvo_game';
            document.querySelectorAll('.nav-item').forEach((item) => {
              const itemFlow = (item.getAttribute('data-flow') || '').toString();
              const isActive = itemFlow === normalizedFlow;
              item.classList.toggle('active', isActive);
            });
            // No step indicator to update
            if (detailPanel) {
              const showDetail = normalizedFlow === 'add_game' || normalizedFlow === 'add_denuvo_game';
              detailPanel.classList.toggle('hidden', !showDetail);
              detailPanel.style.display = showDetail ? 'flex' : 'none';
              if (!showDetail) {
                detailPanel.style.opacity = '0';
              } else {
                detailPanel.style.opacity = '';
              }
            }
            const showActivation = normalizedFlow === 'launch_activation';
            if (activationPanel) {
              activationPanel.classList.toggle('hidden', !showActivation);
              activationPanel.style.display = showActivation ? 'block' : 'none';
            }
            const bypassPanel = document.getElementById('bypass-panel');
            if (bypassPanel) {
              bypassPanel.classList.toggle('hidden', normalizedFlow !== 'add_denuvo_game');
            }
            const noBypassPanel = document.getElementById('no-bypass-panel');
            if (noBypassPanel) {
              noBypassPanel.classList.add('hidden');
            }
            const successPanel = document.getElementById('success-panel');
            if (successPanel) {
              successPanel.classList.add('hidden');
              successPanel.style.display = 'grid';
            }
            hideBypassResultPanel();
            completionPanelVisible = false;
            if (homePanel) {
              homePanel.classList.toggle('hidden', !shouldShowHome);
              homePanel.style.display = shouldShowHome ? 'block' : 'none';
            }
            if (thumbnailPanel) {
              const hasSelection = Boolean(selectedGame && selectedGame.id);
              const shouldShowThumbnail = shouldShowPreview && hasSelection;
              thumbnailPanel.classList.toggle('hidden', !shouldShowThumbnail);
              thumbnailPanel.style.display = shouldShowThumbnail ? 'grid' : 'none';
            }
            const contentGrid = document.querySelector('.content-grid');
            if (contentGrid) {
              contentGrid.classList.toggle('single-column', shouldShowHome);
            }
            if (normalizedFlow === 'launch_activation') {
              const statusElement = document.getElementById('activation-status');
              if (statusElement) {
                statusElement.textContent = 'Ready to open Denuvo activator.';
              }
            }
            if (wizardTitle) wizardTitle.textContent = state.title || 'Home';
            if (wizardMessage) wizardMessage.textContent = state.message || 'Choose a task to begin.';
            if (detailTitle) {
              // Keep the main wizard title generic so the Step 2 panel remains the task-specific label.
              if (normalizedFlow === 'add_game') {
                detailTitle.textContent = 'Welcome';
              } else if (normalizedFlow === 'add_denuvo_game') {
                detailTitle.textContent = 'Bypasses';
              } else {
                detailTitle.textContent = state.title || 'Search';
              }
            }
            if (detailDescription) {
              // Use explicit, non-redundant descriptions per flow so the UI doesn't repeat.
              if (normalizedFlow === 'add_game') {
                detailDescription.textContent = 'Use the search box below to find and select a game.';
              } else if (normalizedFlow === 'add_denuvo_game') {
                detailDescription.textContent = 'Browse bypass-capable titles (placeholder).';
              } else {
                detailDescription.textContent = state.message || 'Choose a task to begin.';
              }
            }
            if (actionHelp) {
              const helpText = state.step === 1 ? 'Choose a task from the sidebar to begin.' : 'No additional UI for this selection.';
              // If selecting add_game show the normal help; otherwise show minimal help for inert flows
              const helpTitle = state.step === 1 ? 'Step 1' : (normalizedFlow === 'add_game' ? 'Step ' + state.step : 'Info');
              actionHelp.innerHTML = '<strong>' + helpTitle + '</strong><span>' + helpText + '</span>';
            }
            currentFlow = normalizedFlow;
            setStatus(state.message || 'Ready');
            hideProgress();
            animateContentPanel();
            animateTopbarContent();
            if (initialLoad) {
              initialLoad = false;
            }
            // Keep bypass page empty until the user focuses or types.
            // The add-game flow can still show suggestions on focus immediately.
            //if (normalizedFlow === 'add_denuvo_game' && searchInput && searchInput.value.trim()) {
            //  void searchGames();
            //}
            if (normalizedFlow === 'add_game' || normalizedFlow === 'add_denuvo_game') {
              setTimeout(() => {
                const si = document.getElementById('appid');
                const hasExistingSelection = Boolean(selectedGame && selectedGame.id);
                if (si && !hasExistingSelection) {
                  si.focus();
                }
                const sc = document.getElementById('search-clear');
                if (sc) sc.style.display = (si && si.value) ? 'inline-flex' : 'none';
              }, 120);
            }
          } catch (error) {
            setStatus('Unable to switch flow: ' + error);
          } finally {
            flowSwitchInProgress = false;
          }
        }

        function animateContentPanel() {
          const contentGrid = document.querySelector('.content-grid');
          if (!contentGrid) return;
          const shouldAnimate = !(initialLoad && currentFlow === '');
          if (!shouldAnimate) {
            contentGrid.classList.remove('content-transition');
            return;
          }
          contentGrid.classList.remove('content-transition');
          void contentGrid.offsetWidth;
          contentGrid.classList.add('content-transition');
        }

        function animateTopbarContent() {
          const heroCopy = document.querySelector('.hero-copy');
          if (!heroCopy) return;
          const shouldAnimate = !(initialLoad && currentFlow === '');
          if (!shouldAnimate) {
            heroCopy.classList.remove('fade-transition');
            return;
          }
          heroCopy.classList.remove('fade-transition');
          void heroCopy.offsetWidth;
          heroCopy.classList.add('fade-transition');
        }

        let searchTimer = null;
        let initialLoad = true;
        let currentFlow = '';
        let flowSwitchInProgress = false;
        let selectedGame = null;
        let lastFixResult = null;
        let completionPanelVisible = false;
        let pywebviewInitAttempts = 0;
        const searchInput = document.getElementById('appid');
        const suggestionsBox = document.getElementById('search-suggestions');
        const searchClear = document.getElementById('search-clear');
        if (searchClear && searchInput) {
          // show/hide clear button based on value
          searchClear.style.display = (searchInput.value && searchInput.value.length) ? 'inline-flex' : 'none';
          searchClear.addEventListener('click', () => {
            searchInput.value = '';
            scheduleSearch();
            searchInput.focus();
            searchClear.style.display = 'none';
          });
          searchInput.addEventListener('input', () => {
            searchClear.style.display = (searchInput.value && searchInput.value.length) ? 'inline-flex' : 'none';
          });
        }
        const nextButton = document.getElementById('next-button');
        const removeButton = document.getElementById('remove-button');
        const bypassButton = document.getElementById('bypass-button');
        const actionButtonsRow = document.getElementById('action-buttons-row');
        const bypassActionsGroup = document.getElementById('bypass-actions-group');

        function updateThumbnail(game) {
          const panel = document.getElementById('thumbnail-panel');
          const image = document.getElementById('thumbnail-image');
          const title = document.getElementById('thumbnail-title');
          const subtitle = document.getElementById('thumbnail-subtitle');
          const appid = document.getElementById('thumbnail-appid');
          if (!panel || !image || !title || !subtitle || !appid) return;
          if (!game || !game.id) {
            panel.classList.add('hidden');
            panel.style.display = 'none';
            image.innerHTML = '<span>Pick a game to preview its thumbnail.</span>';
            title.textContent = 'No game selected';
            subtitle.textContent = 'Search Steam or paste an AppID to view the selected game.';
            appid.textContent = 'AppID: —';
            return;
          }
          panel.classList.remove('hidden');
          panel.style.display = 'grid';
          if (game.image) {
            image.innerHTML = `<img src="${game.image}" alt="${(game.name || 'Game art').replace(/"/g, '&quot;')}" />`;
          } else {
            image.innerHTML = '<span>Preview unavailable for this selection.</span>';
          }
          title.textContent = game.name || 'Selected game';
          subtitle.textContent = game.description || 'Select a game from the search results to see artwork and details here.';
          appid.textContent = `AppID: ${game.id || '—'}`;
        }

        function parseAppIdFromInput() {
          const value = (searchInput ? searchInput.value : '').trim();
          if (!value) return '';
          const candidate = value.split(' - ', 1)[0].trim();
          return /^\\d+$/.test(candidate) ? candidate : '';
        }

        function updateNextButton() {
          const actionFlowTitle = document.getElementById('action-flow-title');
          const hasAppId = Boolean(parseAppIdFromInput());
          const isBypassFlow = currentFlow === 'add_denuvo_game';
          const showAddButtons = !isBypassFlow && hasAppId;
          const bypassAvailable = lastFixResult && (normalizeFlag(lastFixResult.bypass_available) || normalizeFlag(lastFixResult.onlinefix_available));
          const showBypassButtons = isBypassFlow && Boolean(selectedGame) && bypassAvailable;
          if (actionButtonsRow) {
            actionButtonsRow.classList.toggle('bypass-selected', isBypassFlow && Boolean(selectedGame));
          }
          if (bypassActionsGroup) {
            bypassActionsGroup.style.display = showBypassButtons ? 'flex' : 'none';
          }
          if (nextButton) {
            if (!showAddButtons) {
              nextButton.style.display = 'none';
            } else {
              nextButton.style.display = '';
              nextButton.disabled = !hasAppId;
              if (currentFlow === 'add_denuvo_game') {
                nextButton.textContent = 'Add Denuvo game';
              } else {
                nextButton.textContent = 'Add game to library';
              }
            }
          }
          if (removeButton) {
            if (!showAddButtons) {
              removeButton.style.display = 'none';
            } else {
              removeButton.style.display = '';
              removeButton.disabled = !hasAppId;
              removeButton.textContent = hasAppId ? 'Remove game from library' : 'Remove game';
            }
          }
          if (bypassButton) {
            if (!showBypassButtons) {
              bypassButton.style.display = 'none';
            } else {
              bypassButton.style.display = '';
              bypassButton.disabled = !lastFixResult;
              bypassButton.textContent = 'Bypass / OnlineFix';
            }
          }
          const actionStepSubtitle = document.getElementById('action-step-subtitle');
          if (actionFlowTitle) {
            actionFlowTitle.textContent = (currentFlow === 'add_denuvo_game')
              ? 'Step 2: Bypass / OnlineFix'
              : 'Step 2: Add game / Remove game';
          }
          if (actionStepSubtitle) {
            actionStepSubtitle.textContent = (currentFlow === 'add_denuvo_game')
              ? 'Choose the bypass or OnlineFix option for this selected game.'
              : 'Choose the best action for this selected game.';
          }
        }

        function updateSelectedGameSummary(game) {
          const summary = document.getElementById('selected-game-summary');
          const title = document.getElementById('selected-game-label');
          const subtitle = document.getElementById('selected-game-subtitle');
          const actionFlowTitle = document.getElementById('action-flow-title');
          const step1Card = document.getElementById('step1-card');
          if (!summary || !title || !subtitle || !actionFlowTitle) return;
          const actionPanel = document.getElementById('action-panel');
          if (!game) {
            summary.classList.add('empty');
            if (actionPanel) {
              actionPanel.classList.add('fade-hidden');
              actionPanel.classList.remove('fade-visible');
            }
            actionFlowTitle.classList.add('fade-hidden');
            actionFlowTitle.classList.remove('fade-visible');
            const step1Title = document.getElementById('step2-flow-title');
            if (step1Card) {
              step1Card.classList.remove('fade-hidden');
              step1Card.classList.add('fade-visible');
            }
            if (step1Title) {
              step1Title.classList.remove('fade-hidden');
              step1Title.classList.add('fade-visible');
            }
            // Always keep the summary visually empty when no game is selected.
            title.textContent = '';
            subtitle.textContent = '';
            return;
          }
          summary.classList.remove('empty');
          const isBypassFlow = currentFlow === 'add_denuvo_game';
          const showActionPanel = isBypassFlow ? Boolean(game) : Boolean(lastFixResult && game);
          const step1Title = document.getElementById('step2-flow-title');
          if (showActionPanel) {
            if (actionPanel) {
              actionPanel.classList.remove('fade-hidden');
              actionPanel.classList.add('fade-visible');
            }
            actionFlowTitle.classList.remove('fade-hidden');
            actionFlowTitle.classList.add('fade-visible');
            if (step1Card) {
              step1Card.classList.add('fade-hidden');
              step1Card.classList.remove('fade-visible');
            }
            if (step1Title) {
              step1Title.classList.add('fade-hidden');
              step1Title.classList.remove('fade-visible');
            }
          } else {
            if (actionPanel) {
              actionPanel.classList.add('fade-hidden');
              actionPanel.classList.remove('fade-visible');
            }
            actionFlowTitle.classList.add('fade-hidden');
            actionFlowTitle.classList.remove('fade-visible');
            if (step1Card) {
              step1Card.classList.remove('fade-hidden');
              step1Card.classList.add('fade-visible');
            }
            if (step1Title) {
              step1Title.classList.remove('fade-hidden');
              step1Title.classList.add('fade-visible');
            }
          }
          title.textContent = `${game.name || 'Selected game'} (${game.id || 'unknown'})`;
          if (currentFlow === 'add_denuvo_game' && lastFixResult) {
            const bypass = normalizeFlag(lastFixResult.bypass_available);
            const onlinefix = normalizeFlag(lastFixResult.onlinefix_available);
            if (!bypass && !onlinefix) {
              subtitle.textContent = 'No bypass/OnlineFix available. Contact support to request.';
            } else {
              subtitle.textContent = '';
            }
          } else {
            subtitle.textContent = '';
          }
        }

        function showNoBypassPanel() {
          const detailPanel = document.getElementById('detail-panel');
          const noBypassPanel = document.getElementById('no-bypass-panel');
          if (detailPanel) {
            detailPanel.classList.add('hidden');
            detailPanel.style.display = 'none';
          }
          if (noBypassPanel) {
            noBypassPanel.classList.remove('hidden');
            noBypassPanel.style.display = 'grid';
          }
        }

        function hideNoBypassPanel() {
          const detailPanel = document.getElementById('detail-panel');
          const noBypassPanel = document.getElementById('no-bypass-panel');
          if (detailPanel) {
            detailPanel.classList.remove('hidden');
            detailPanel.style.display = 'flex';
          }
          if (noBypassPanel) {
            noBypassPanel.classList.add('hidden');
          }
        }

        async function backToBypassSelection() {
          if (currentFlow !== 'add_denuvo_game') return;
          selectedGame = null;
          lastFixResult = null;
          if (searchInput) {
            searchInput.value = '';
          }
          if (suggestionsBox) {
            suggestionsBox.innerHTML = '';
          }
          if (searchClear) {
            searchClear.style.display = 'none';
          }
          updateSelectedGameSummary(null);
          updateDenuvoBadge(null);
          updateFixBadge(null);
          updateNextButton();
          hideNoBypassPanel();
          updateThumbnail(null);
          await searchGames();
        }

        async function checkDenuvoForSelection() {
          const appid = parseAppIdFromInput();
          if (!appid) return;
          const api = getPywebviewApi();
          if (!api) {
            const message = 'GameDrop interface is not ready yet.';
            setStatus(message);
            hideProgress();
            return;
          }
          setStatus('Checking availability...');
          showProgress('Checking availability...');
          try {
            let result;
            if (currentFlow === 'add_denuvo_game') {
              result = await api.run_action('check_bypass', { appid });
            } else {
              result = await api.run_action('check_denuvo', {
                appid,
                name: (searchInput ? searchInput.value : '').trim(),
                marker_only: currentFlow !== 'add_denuvo_game',
              });
            }
            if (result.ok) {
              lastFixResult = result;
              clearCompletionPanel(true);
              setStatus(currentFlow === 'add_denuvo_game' ? 'Bypass availability check complete.' : 'Denuvo check complete.');
              updateDenuvoBadge(result);
              updateFixBadge(result);
              updateSelectedGameSummary(selectedGame);
              updateNextButton();
              const bypass = normalizeFlag(result.bypass_available);
              const onlinefix = normalizeFlag(result.onlinefix_available);
              if (currentFlow === 'add_denuvo_game' && selectedGame && !bypass && !onlinefix) {
                showNoBypassPanel();
              } else {
                hideNoBypassPanel();
              }
            }
          } catch (error) {
            setStatus('Availability check failed: ' + error);
          } finally {
            hideProgress();
          }
        }

        async function loadSelectedGameDetails(game) {
          if (!game || !game.id) {
            return game;
          }
          const api = getPywebviewApi();
          if (!api) {
            console.warn('pywebview API is not ready; skipping game detail load');
            return game;
          }
          try {
            const result = await api.run_action('get_game_details', { appid: game.id });
            if (result.ok) {
              return {
                ...game,
                description: result.description || game.description || '',
                image: result.image || game.image,
                name: result.name || game.name,
              };
            }
          } catch (error) {
            console.warn('Unable to load selected game details', error);
          }
          return game;
        }

        function renderBypassResults(results) {
          const gallery = document.getElementById('bypass-gallery');
          const bypassPanel = document.getElementById('bypass-panel');
          if (!gallery) return;
          const previousScrollTop = bypassPanel ? bypassPanel.scrollTop : 0;
          gallery.innerHTML = '';
          gallery.classList.toggle('single-result', Boolean(results && results.length === 1));
          if (!results || !results.length) {
            gallery.classList.remove('single-result');
            gallery.innerHTML = `
              <div class="bypass-empty">
                <div>No bypass games are available at this time.</div>
                <button class="back-button refresh-suggestions-button" id="bypass-refresh-button" type="button" style="margin-top: 12px;">Refresh suggestions</button>
              </div>`;
            const bypassRefreshButton = document.getElementById('bypass-refresh-button');
            if (bypassRefreshButton) {
              bypassRefreshButton.addEventListener('click', async () => {
                if (currentFlow === 'add_denuvo_game') {
                  await searchGames();
                }
              });
            }
            if (bypassPanel) {
              requestAnimationFrame(() => {
                bypassPanel.scrollTop = Math.min(previousScrollTop, Math.max(0, bypassPanel.scrollHeight - bypassPanel.clientHeight));
              });
            }
            return;
          }
          results.forEach((game) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'bypass-item';
            item.innerHTML = `
              <div class="bypass-item-image">
                ${game.image ? `<img src="${game.image}" alt="${(game.name || 'Game').replace(/"/g, '&quot;')}" />` : '<div class="bypass-item-placeholder">No image</div>'}
              </div>
              <div class="bypass-item-body">
                <h3>${(game.name || 'Untitled').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</h3>
                <p>AppID ${game.id || '—'}</p>
              </div>`;
            const selectGame = async () => {
              if (searchInput) {
                searchInput.value = `${game.id} - ${game.name}`;
                if (document.activeElement === searchInput) {
                  searchInput.blur();
                }
              }
              selectedGame = await loadSelectedGameDetails(game);
              updateSelectedGameSummary(selectedGame);
              updateThumbnail(selectedGame);
              if (gallery) {
                gallery.innerHTML = '';
              }
              setStatus(`Selected ${selectedGame.name} (${selectedGame.id}).`);
              await checkDenuvoForSelection();
              updateNextButton();
            };
            item.addEventListener('pointerdown', (event) => {
              event.preventDefault();
              selectGame();
            });
            item.addEventListener('click', selectGame);
            gallery.appendChild(item);
          });
          if (bypassPanel) {
            requestAnimationFrame(() => {
              bypassPanel.scrollTop = Math.min(previousScrollTop, Math.max(0, bypassPanel.scrollHeight - bypassPanel.clientHeight));
            });
          }
        }

        function renderResults(results) {
          if (!suggestionsBox) return;
          suggestionsBox.innerHTML = '';
          (results || []).forEach((game) => {
            const item = document.createElement('div');
            item.className = 'search-item';
            item.innerHTML = `
              <div class="search-thumb">
                ${game.image ? `<img src="${game.image}" alt="${game.name || ''}" />` : '<span>Game</span>'}
              </div>
              <div>
                <strong>${(game.name || 'Untitled').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</strong>
                <span>${game.id || ''}</span>
              </div>`;
            const selectGame = async () => {
              searchInput.value = `${game.id} - ${game.name}`;
              if (document.activeElement === searchInput) {
                searchInput.blur();
              }
              suggestionsBox.innerHTML = '';
              selectedGame = await loadSelectedGameDetails(game);
              updateSelectedGameSummary(selectedGame);
              updateThumbnail(selectedGame);
              setStatus(`Selected ${selectedGame.name} (${selectedGame.id}).`);
              await checkDenuvoForSelection();
            };
            item.addEventListener('pointerdown', (event) => {
              event.preventDefault();
              selectGame();
            });
            item.addEventListener('click', selectGame);
            suggestionsBox.appendChild(item);
          });
        }

        async function searchGames() {
          const value = (searchInput ? searchInput.value : '').trim();
          const wizardMessage = document.getElementById('wizard-message');
          const api = getPywebviewApi();
          if (!api) {
            const message = 'GameDrop interface is not ready yet.';
            setStatus(message);
            hideProgress();
            return;
          }
          clearCompletionPanel(true);
          if (currentFlow === 'add_denuvo_game') {
            if (wizardMessage) {
              wizardMessage.textContent = '';
            }
            showProgress('Loading bypass suggestions…');
          }
          try {
            let result;
            if (currentFlow === 'add_denuvo_game') {
              if (value) {
                result = await api.run_action('search_bypass_games', { query: value });
              } else {
                result = await api.run_action('get_bypass_games', { strict: true });
              }
            } else {
              result = await api.run_action('search_games', { query: value });
            }
            if (result.ok) {
              if (currentFlow === 'add_denuvo_game') {
                if (suggestionsBox) {
                  suggestionsBox.innerHTML = '';
                }
                renderBypassResults(result.results || []);
              } else {
                renderResults(result.results || []);
              }
              const count = (result.results || []).length;
              if (currentFlow === 'add_denuvo_game' && !value) {
                setStatus(count ? `Showing ${count} bypass-capable games.` : 'No bypass games available.');
              } else if (!value) {
                setStatus(count ? `Showing ${count} suggested games.` : 'No suggestions available.');
              } else {
                setStatus(count ? `Showing ${count} Steam matches for "${value}".` : 'No Steam matches found.');
              }
              if (parseAppIdFromInput() && result.results && result.results.length === 1) {
                selectedGame = await loadSelectedGameDetails(result.results[0]);
                updateSelectedGameSummary(selectedGame);
                updateThumbnail(selectedGame);
                await checkDenuvoForSelection();
              } else if (!parseAppIdFromInput()) {
                selectedGame = null;
                updateSelectedGameSummary(null);
                updateDenuvoBadge(null);
                updateFixBadge(null);
                lastFixResult = null;
                updateThumbnail(null);
                hideNoBypassPanel();
              }
              updateNextButton();
            } else {
              setStatus(result.message || 'Search failed.');
            }
          } catch (error) {
            setStatus('Search failed: ' + error);
          } finally {
            if (currentFlow === 'add_denuvo_game') {
              hideProgress();
            }
          }
        }

        function scheduleSearch() {
          if (searchTimer) clearTimeout(searchTimer);
          searchTimer = setTimeout(searchGames, 220);
        }

        async function handleNextAction() {
          if (!nextButton) return;
          const appid = parseAppIdFromInput();
          if (!appid) {
            setStatus('Enter a valid AppID or choose a game first.');
            return;
          }
          if (!lastFixResult && currentFlow === 'add_denuvo_game') {
            setStatus('Please select a bypass-capable game and check Denuvo before continuing.');
            return;
          }
          const action = currentFlow === 'add_denuvo_game' ? 'add_denuvo_game' : 'add_game';
          const payload = {};
          if (normalizeFlag(lastFixResult && lastFixResult.denuvo_detected)) {
            payload.denuvo_detected = true;
          }
          setStatus('Adding game to library...');
          showProgress('Adding game to Steam...');
          nextButton.disabled = true;
          if (removeButton) removeButton.disabled = true;
          const result = await callAction(action, payload);
          hideProgress();
          if (result.ok) {
            const denuvo = normalizeFlag(lastFixResult && lastFixResult.denuvo_detected);
            const note = denuvo
              ? (normalizeFlag(lastFixResult && lastFixResult.bypass_available)
                  ? 'go to bypass page for denuvo bypass'
                  : (normalizeFlag(lastFixResult && lastFixResult.activation_available) ? 'Denuvo activation available' : ''))
              : (normalizeFlag(lastFixResult && lastFixResult.onlinefix_available) ? 'go to bypass page for onlinefix' : '');
            showCompletionPanel(selectedGame || { id: appid, name: `AppID ${appid}` }, note);
          }
          updateNextButton();
        }

        async function handleRemoveAction() {
          if (!removeButton) return;
          const appid = parseAppIdFromInput();
          if (!appid) {
            setStatus('Enter a valid AppID or choose a game first.');
            return;
          }
          setStatus('Removing game from library...');
          showProgress('Removing game from Steam...');
          removeButton.disabled = true;
          if (nextButton) nextButton.disabled = true;
          const result = await callAction('remove_game');
          hideProgress();
          removeButton.disabled = false;
          if (nextButton) nextButton.disabled = false;
          if (result.ok) {
            setStatus('Game removal completed.');
            if (result.removed) {
              showCompletionPanel(selectedGame || { id: appid, name: `AppID ${appid}` }, '', { state: 'removed' });
            } else {
              setStatus('No Lua entry was found for this game.');
            }
            updateNextButton();
          }
        }

        async function handleBypassAction() {
          if (!bypassButton) return;
          const appid = parseAppIdFromInput();
          if (!appid) {
            setStatus('Enter a valid AppID or choose a game first.');
            return;
          }
          setStatus('Preparing bypass/onlinefix...');
          showProgress('Preparing bypass/onlinefix...');
          bypassButton.disabled = true;
          const result = await callAction('onlinefix');
          hideProgress();
          bypassButton.disabled = false;
          if (result.ok) {
            setStatus(result.message || 'Bypass / OnlineFix flow is ready.');
            showBypassResultPanel('Bypass / OnlineFix completed', result.message || 'The bypass action completed successfully.');
          } else {
            setStatus(result.message || 'Bypass / OnlineFix action failed.');
            showBypassResultPanel('Bypass / OnlineFix failed', result.message || 'The bypass action could not be completed.');
          }
        }

        if (nextButton) {
          nextButton.addEventListener('click', handleNextAction);
        }
        if (removeButton) {
          removeButton.addEventListener('click', handleRemoveAction);
        }
        if (bypassButton) {
          bypassButton.addEventListener('click', handleBypassAction);
        }
        const noBypassBackButton = document.getElementById('no-bypass-back-button');
        if (noBypassBackButton) {
          noBypassBackButton.addEventListener('click', backToBypassSelection);
        }
        const noBypassRefreshButton = document.getElementById('no-bypass-refresh-button');
        if (noBypassRefreshButton) {
          noBypassRefreshButton.addEventListener('click', async () => {
            if (currentFlow === 'add_denuvo_game') {
              await searchGames();
            }
          });
        }
        const bypassResultBackButton = document.getElementById('bypass-result-back-button');
        if (bypassResultBackButton) {
          bypassResultBackButton.addEventListener('click', () => {
            hideBypassResultPanel();
            switchFlow('add_denuvo_game');
          });
        }

        document.querySelectorAll('[data-flow]').forEach((button) => {
          button.addEventListener('click', () => {
            resetSearchBar();
            const flow = button.dataset.flow;
            if (flow === 'contact_support') {
              window.open('https://www.facebook.com/GameDropPhl', '_blank');
              return;
            }
            if (flow === 'repair') {
              void (async () => {
                await performRepairAction();
              })();
              return;
            }
            switchFlow(flow);
          });
        });

        const backButton = document.getElementById('back-button');
        if (backButton) {
          backButton.addEventListener('click', () => switchFlow(''));
        }
        const successHomeButton = document.getElementById('success-home-button');
        if (successHomeButton) {
          successHomeButton.addEventListener('click', () => switchFlow(''));
        }
        const repairSuccessHomeButton = document.getElementById('repair-success-home-button');
        if (repairSuccessHomeButton) {
          repairSuccessHomeButton.addEventListener('click', () => switchFlow(''));
        }
        const successAddMoreButton = document.getElementById('success-add-more-button');
        if (successAddMoreButton) {
          successAddMoreButton.addEventListener('click', () => {
            resetSearchBar();
            switchFlow('add_game');
          });
        }

        const launchActivationButton = document.getElementById('launch-activation-button');
        if (launchActivationButton) {
          launchActivationButton.addEventListener('click', () => {
            void launchActivationHelper();
          });
        }

        document.querySelectorAll('[data-action]').forEach((button) => {
          button.addEventListener('mouseenter', () => updateHelp(button));
          button.addEventListener('focus', () => updateHelp(button));
          button.addEventListener('click', async () => {
            const action = button.dataset.action;
            if (action === 'install_engine') {
              await runActivationAction(action, 'Installing OpenSteamTool…', true);
            } else if (action === 'update_engine') {
              await runActivationAction(action, 'Repairing OpenSteamTool…', true);
            } else if (action === 'uninstall_engine') {
              await runActivationAction(action, 'Removing OpenSteamTool…');
            } else {
              await callAction(action);
            }
          });
        });

        if (searchInput) {
            searchInput.addEventListener('input', () => { scheduleSearch(); updateNextButton(); });
            searchInput.addEventListener('focus', () => {
              if (currentFlow === 'add_game' || currentFlow === 'add_denuvo_game' || searchInput.value.trim()) {
                searchGames();
              }
            });
            searchInput.addEventListener('blur', () => {
              setTimeout(() => {
                if (suggestionsBox) suggestionsBox.innerHTML = '';
              }, 140);
            });
            searchInput.addEventListener('keydown', (event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                searchGames();
              }
            });
            searchInput.addEventListener('change', () => {
              if (currentFlow === 'add_denuvo_game' && parseAppIdFromInput()) {
                checkDenuvoForSelection();
              }
              updateNextButton();
            });
        }

        async function initializeShell() {
          const shell = document.querySelector('.shell');
          const detailPanel = document.getElementById('detail-panel');
          const homePanel = document.getElementById('home-panel');
          const noBypassPanel = document.getElementById('no-bypass-panel');
          const successPanel = document.getElementById('success-panel');
          const thumbnailPanel = document.getElementById('thumbnail-panel');
          const fallbackState = { status: 'Ready', title: 'Home', message: 'Welcome to GameDrop.' };
          try {
            if (shell) {
              shell.classList.remove('is-hidden');
              shell.classList.add('ready');
            }
            if (detailPanel) {
              detailPanel.classList.add('hidden');
              detailPanel.style.display = 'none';
            }
            if (homePanel) {
              homePanel.classList.remove('hidden');
              homePanel.style.display = 'block';
            }
            if (noBypassPanel) {
              noBypassPanel.classList.add('hidden');
              noBypassPanel.style.display = 'none';
            }
            if (successPanel) {
              successPanel.classList.add('hidden');
              successPanel.style.display = 'none';
            }
            if (thumbnailPanel) {
              thumbnailPanel.classList.add('hidden');
              thumbnailPanel.style.display = 'none';
            }
            const api = await waitForPywebviewApi(10000);
            if (!api) {
              updateSidebarStatus(fallbackState);
              setStatus('Waiting for GameDrop backend...');
              updateSystemStatus();
              const activationStatus = document.getElementById('activation-status');
              if (activationStatus) {
                activationStatus.textContent = 'Preparing Denuvo activator...';
              }
              pywebviewInitAttempts += 1;
              if (pywebviewInitAttempts < 6) {
                setTimeout(initializeShell, 1200);
              }
              return;
            }
            pywebviewInitAttempts = 0;
            const state = await api.get_initial_state();
            updateSidebarStatus(state);
            setStatus(state.status || 'Ready');
            updateSystemStatus();
            switchFlow(null);
            requestAnimationFrame(() => {
              const homePanel = document.getElementById('home-panel');
              if (homePanel) {
                homePanel.style.transform = 'translateZ(0)';
                homePanel.style.willChange = 'transform';
              }
            });
            searchGames();
            const activationStatus = document.getElementById('activation-status');
            if (activationStatus) {
              activationStatus.textContent = 'Ready to open Denuvo activator.';
            }
            // Shine animation for the Start here pill: gentle periodic highlight
            try {
              const startPill = document.getElementById('start-here-button');
              if (startPill) {
                const triggerShine = () => {
                  startPill.classList.add('shine-anim');
                  setTimeout(() => startPill.classList.remove('shine-anim'), 1100);
                };
                // initial sparkle shortly after load
                setTimeout(triggerShine, 700);
                // repeat occasionally to draw attention
                setInterval(triggerShine, 8000);
              }
            } catch (e) {
              // ignore in environments without DOM
            }
          } catch (error) {
            if (shell) {
              shell.classList.remove('is-hidden');
              shell.classList.add('ready');
            }
            setStatus('Unable to load shell state.');
          }
        }

        window.addEventListener('DOMContentLoaded', initializeShell);
        window.addEventListener('load', initializeShell);
        window.addEventListener('pywebviewready', initializeShell);
      </script>
    </body>
    </html>
    """
    return html.replace("__LOGO_MARKUP__", logo_markup)


def get_logo_uri(app_dir):
    logo_candidates = [os.path.join(app_dir, "logo.png"), os.path.join(app_dir, "logo.ico")]
    for logo_path in logo_candidates:
        if os.path.exists(logo_path):
            return Path(logo_path).resolve().as_uri()
    return ""


def launch_webview_app():
    api = GameDropWebViewAPI()
    logo_uri = get_logo_uri(api.app_dir)
    html = build_html(logo_uri=logo_uri)

    window = webview.create_window(
        "GameDrop Steam",
        html=html,
        js_api=api,
        width=1380,
        height=940,
        x=0,
        y=0,
        min_size=(1280, 860),
        resizable=True,
        background_color="#07111f",
    )
    try:
        start_webview_runtime()
    finally:
        try:
            from denuvo_activation import _stop_active_helper
            _stop_active_helper()
        except Exception:
            pass


if __name__ == "__main__":
    launch_webview_app()
