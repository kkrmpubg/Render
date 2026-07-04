import os
import re
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def get_github_headers(accept=None):
    headers = dict(HEADERS)
    if accept:
        headers["Accept"] = accept
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers


def parse_appids_from_text(text):
    appids = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        cleaned = cleaned.split("#", 1)[0].strip()
        cleaned = re.split(r"[\s,;]+", cleaned)[0].strip()
        cleaned = re.sub(r"[^0-9]", "", cleaned)
        if cleaned.isdigit():
            appids.append(cleaned)
    return appids


def get_remote_bypass_appids():
    url = os.environ.get(
        "REMOTE_BYPASS_URL",
        "https://raw.githubusercontent.com/kkrmpubg/gamedrop-updates/main/bypass_appids.txt",
    )
    try:
        response = requests.get(url, headers=get_github_headers(), timeout=10)
        if response.status_code == 200:
            return parse_appids_from_text(response.text)
    except Exception:
        pass
    return []


def find_github_release_asset_url(repo_owner, repo_name, appid):
    try:
        appid_str = str(appid)
        archive_exts = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz")
        api_urls = [
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{appid}",
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases",
        ]
        for api_url in api_urls:
            response = requests.get(api_url, headers=get_github_headers("application/vnd.github.v3+json"), timeout=12)
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                continue
            releases = response.json()
            if isinstance(releases, dict):
                releases = [releases]
            for release in releases:
                tag_name = str(release.get("tag_name", "")).lower()
                release_name = str(release.get("name", "")).lower()
                release_body = str(release.get("body", "")).lower()
                release_match = appid_str in tag_name or appid_str in release_name or appid_str in release_body
                assets = release.get("assets", []) or []
                for asset in assets:
                    name = str(asset.get("name", "")).lower()
                    url = asset.get("browser_download_url")
                    if not url:
                        continue
                    if release_match and any(name.endswith(ext) for ext in archive_exts):
                        return url
                    if appid_str in name or name.startswith(appid_str):
                        return url
                if release_match and assets:
                    for fallback_asset in assets:
                        fallback_name = str(fallback_asset.get("name", "")).lower()
                        fallback_url = fallback_asset.get("browser_download_url")
                        if fallback_url and any(fallback_name.endswith(ext) for ext in archive_exts):
                            return fallback_url
        return None
    except Exception:
        return None


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "bypass-backend"})


@app.get("/remote-bypass-appids")
def remote_bypass_appids():
    return jsonify({"appids": get_remote_bypass_appids()})


@app.get("/bypass-info")
def bypass_info():
    appid = (request.args.get("appid") or "").strip()
    repo_owner = (request.args.get("repo_owner") or os.environ.get("DEFAULT_REPO_OWNER", "kkrmpubg")).strip()
    repo_name = (request.args.get("repo_name") or os.environ.get("DEFAULT_REPO_NAME", "ManifestHub")).strip()
    if not appid:
        return jsonify({"bypass_available": False, "download_url": None, "status": "missing_appid"})

    download_url = find_github_release_asset_url(repo_owner, repo_name, appid)
    if download_url:
        return jsonify({"bypass_available": True, "download_url": download_url, "status": "ok"})
    return jsonify({"bypass_available": False, "download_url": None, "status": "not_found"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
