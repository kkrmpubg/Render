import os
import re
import requests
from flask import Flask, jsonify, make_response, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

LUA_REPOS = [
    ("kkrmpubg", "ManifestHub"),
    ("dvahana2424-web", "sojogamesdatabase1"),
    ("hammerwebsite12", "sojogames2"),
]


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


def resolve_bypass_from_manifesthub(appid):
    repo_owner = os.environ.get("DEFAULT_REPO_OWNER", "kkrmpubg")
    repo_name = os.environ.get("DEFAULT_REPO_NAME", "ManifestHub")
    return find_github_release_asset_url(repo_owner, repo_name, appid)


def find_github_branch_tree(owner, repo_name, branch):
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
        response = requests.get(api_url, headers=get_github_headers("application/vnd.github.v3+json"), timeout=12)
        if response.status_code != 200:
            return None
        data = response.json()
        tree = data.get("tree", [])
        if not isinstance(tree, list):
            return None
        return [entry.get("path") for entry in tree if entry.get("type") == "blob" and isinstance(entry.get("path"), str)]
    except Exception:
        return None


def get_github_raw_file(owner, repo_name, branch, path):
    try:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{path}"
        response = requests.get(raw_url, headers=get_github_headers(), timeout=20)
        if response.status_code != 200:
            return None
        return response.content
    except Exception:
        return None


def find_github_release_asset_url(repo_owner, repo_name, appid):
    try:
        appid_str = str(appid)
        archive_exts = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz")
        api_urls = [
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{appid}",
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/re",
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
                assets = release.get("assets", []) or []
                for asset in assets:
                    name = str(asset.get("name", "")).lower()
                    url = asset.get("browser_download_url")
                    if not url:
                        continue
                    if not any(name.endswith(ext) for ext in archive_exts):
                        continue
                    if appid_str in name:
                        return url

        for ext in archive_exts:
            direct_url = f"https://github.com/{repo_owner}/{repo_name}/releases/download/re/{appid_str}{ext}"
            try:
                head_response = requests.head(direct_url, headers=get_github_headers(), timeout=10, allow_redirects=True)
                if head_response.status_code < 400:
                    return direct_url
            except Exception:
                continue

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

    remote_appids = set(get_remote_bypass_appids())
    if appid not in remote_appids:
        fallback_appids = {"1245620", "292030", "1091500", "1151640", "990080", "1174180", "1196590", "1850570"}
        if appid not in fallback_appids:
            return jsonify({"bypass_available": False, "download_url": None, "status": "not_found"})

    download_url = resolve_bypass_from_manifesthub(appid)
    if download_url:
        return jsonify({"bypass_available": True, "download_url": download_url, "status": "ok"})

    return jsonify({"bypass_available": True, "download_url": None, "status": "known_candidate"})


@app.get("/lua-info")
def lua_info():
    appid = (request.args.get("appid") or "").strip()
    if not appid:
        return jsonify({"lua_available": False, "repos": [], "status": "missing_appid"})

    repos = []
    for owner, repo_name in LUA_REPOS:
        branch_paths = find_github_branch_tree(owner, repo_name, appid)
        if not branch_paths:
            continue

        lua_files = [path for path in branch_paths if path.lower().endswith(".lua")]
        if not lua_files:
            continue

        repos.append({
            "owner": owner,
            "repo": repo_name,
            "branch": appid,
            "lua_files": lua_files,
        })

    if repos:
        return jsonify({"lua_available": True, "repos": repos, "status": "ok"})
    return jsonify({"lua_available": False, "repos": [], "status": "not_found"})


@app.get("/lua-file")
def lua_file():
    owner = (request.args.get("owner") or "").strip()
    repo_name = (request.args.get("repo_name") or "").strip()
    branch = (request.args.get("branch") or "").strip()
    path = (request.args.get("path") or "").strip()

    if not owner or not repo_name or not branch or not path:
        return jsonify({"ok": False, "error": "Missing required query parameters."}), 400

    content = get_github_raw_file(owner, repo_name, branch, path)
    if content is None:
        return jsonify({"ok": False, "error": "Unable to fetch Lua file."}), 404

    response = make_response(content)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = f"attachment; filename={os.path.basename(path)}"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
