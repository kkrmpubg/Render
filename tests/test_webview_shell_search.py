import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from check_onlinefix_bypass import check_appid
from webview_shell import GameDropWebViewAPI, build_html


class FakeResponse:
    def __init__(self, text="", content=b"", status_code=200):
        self.text = text
        self.content = content
        self.status_code = status_code

    def json(self):
        return {}


def test_normalize_search_results_filters_dlc_and_preserves_game_data():
    api = GameDropWebViewAPI()
    payload = {
        "items": [
            {"id": 570, "name": "Dota 2", "tiny_image": "img-570"},
            {"id": 440, "name": "Team Fortress 2", "type": "game"},
            {"id": 123, "name": "Example DLC", "type": "dlc"},
        ]
    }

    results = api.normalize_search_results(payload)

    assert len(results) == 2
    assert results[0]["id"] == "570"
    assert results[0]["name"] == "Dota 2"
    assert results[1]["id"] == "440"


def test_extract_appid_handles_id_name_input():
    api = GameDropWebViewAPI()

    assert api.extract_appid("570 - Dota 2") == "570"
    assert api.extract_appid("Counter-Strike 2") is None
    assert api.extract_appid("440") == "440"


def test_format_search_value_returns_id_name_label():
    api = GameDropWebViewAPI()

    assert api.format_search_value({"id": "570", "name": "Dota 2"}) == "570 - Dota 2"


def test_build_search_option_adds_display_metadata():
    api = GameDropWebViewAPI()
    option = api.build_search_option({"id": "570", "name": "Dota 2", "image": "img"})

    assert option["id"] == "570"
    assert option["name"] == "Dota 2"
    assert option["image"] == "img"
    assert option["search_value"] == "570 - Dota 2"


def test_get_wizard_state_moves_add_game_to_search_step():
    api = GameDropWebViewAPI()

    state = api.get_wizard_state("add_game")

    assert state["step"] == 2
    assert state["flow"] == "add_game"
    assert state["title"] == "Step 2: Add to Library"


def test_check_appid_uses_remote_bypass_list_fast_path(monkeypatch):
    check_appid.cache_clear()
    monkeypatch.setattr("check_onlinefix_bypass.get_remote_bypass_appids", lambda: ("2358720",))
    monkeypatch.setattr("check_onlinefix_bypass.get_release_assets_for_tag", lambda *args, **kwargs: tuple())
    monkeypatch.setattr("check_onlinefix_bypass.get_release_page_text", lambda *args, **kwargs: "")

    assert check_appid("2358720") == (False, True)


def test_check_appid_reports_remote_bypass_when_listed(monkeypatch):
    check_appid.cache_clear()
    monkeypatch.setattr("check_onlinefix_bypass.get_remote_bypass_appids", lambda: ("2358720",))

    assert check_appid("2358720") == (False, True)


def test_check_appid_reports_non_remote_bypass_when_not_listed(monkeypatch):
    check_appid.cache_clear()
    monkeypatch.setattr("check_onlinefix_bypass.get_remote_bypass_appids", lambda: ())

    assert check_appid("570") == (False, False)


def test_check_denuvo_drm_detects_store_page_markers():
    api = GameDropWebViewAPI()

    with patch.object(
        api.session,
        "get",
        return_value=FakeResponse(text="<html>Incorporates 3rd-party DRM: Denuvo</html>"),
    ):
        result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is True
    assert "Denuvo" in result["message"]


def test_check_denuvo_drm_uses_alternative_store_url_when_needed():
    api = GameDropWebViewAPI()
    responses = [
        FakeResponse(text="<html>no drm markers here</html>"),
        FakeResponse(text="<html>Incorporates 3rd-party DRM: Denuvo</html>"),
    ]

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": False, "bypass_available": False}):
        with patch.object(api.session, "get", side_effect=responses):
            result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is True


def test_check_onlinefix_availability_returns_false_for_invalid_appid():
    api = GameDropWebViewAPI()

    assert api._check_onlinefix_availability("abc") == {
        "onlinefix_available": False,
        "bypass_available": False,
    }


def test_close_steam_uses_exit_uri_and_force_kills_remaining_processes(monkeypatch):
    api = GameDropWebViewAPI()
    seen = []

    monkeypatch.setattr("webview_shell.os.startfile", lambda target: seen.append(("startfile", target)))
    monkeypatch.setattr("webview_shell.subprocess.Popen", lambda *args, **kwargs: seen.append(("popen", args)))
    monkeypatch.setattr("webview_shell.subprocess.call", lambda *args, **kwargs: seen.append(("taskkill", args)))
    monkeypatch.setattr("webview_shell.time.sleep", lambda *args, **kwargs: None)

    api._close_steam()

    assert any(item[0] == "startfile" for item in seen)
    assert any(item[0] == "taskkill" for item in seen)


def test_remove_steam_lua_files_deletes_only_selected_appid_files(tmp_path, monkeypatch):
    import file_protection

    api = GameDropWebViewAPI()
    steam_dir = tmp_path / "Steam"
    lua_dir = steam_dir / "config" / "lua"
    lua_dir.mkdir(parents=True)

    (lua_dir / "570_fix.lua").write_text("setmanifest 570\n", encoding="utf-8")
    (lua_dir / "790_fix.lua").write_text("setmanifest 790\n", encoding="utf-8")
    (lua_dir / "shared.lua").write_text("setmanifest\n", encoding="utf-8")

    monkeypatch.setattr(file_protection, "get_steam_path", lambda: str(steam_dir))

    removed = api._remove_steam_lua_files("570")

    assert removed == 1
    remaining_files = sorted(os.listdir(lua_dir))
    assert "790_fix.lua" in remaining_files
    assert "shared.lua" in remaining_files


def test_build_html_does_not_contain_remove_denuvo_game_label():
    html = build_html()

    assert "Remove Denuvo game" not in html
    assert "Remove game from library" in html


def test_run_action_repair_closes_steam_and_overwrites_required_dlls(tmp_path, monkeypatch):
    api = GameDropWebViewAPI()
    steam_dir = tmp_path / "Steam"
    steam_dir.mkdir()

    for dll_name in ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]:
        (steam_dir / dll_name).write_bytes(b"old")

    monkeypatch.setattr(api, "_get_steam_install_dir", lambda: str(steam_dir))
    monkeypatch.setattr(api, "_close_steam", lambda: None)

    downloaded_files = []

    def fake_download(url, destination):
        Path(destination).write_bytes(b"new")
        downloaded_files.append((url, destination))

    monkeypatch.setattr(api, "_download_file_to_path", fake_download)

    result = api.run_action("repair", {})
    print(result)

    assert result["ok"] is True
    assert (steam_dir / "OpenSteamTool.dll").read_bytes() == b"new"
    assert (steam_dir / "dwmapi.dll").read_bytes() == b"new"
    assert (steam_dir / "xinput1_4.dll").read_bytes() == b"new"
    assert len(downloaded_files) == 3


def test_check_bypass_uses_remote_bypass_list(monkeypatch):
    api = GameDropWebViewAPI()
    monkeypatch.setattr("webview_shell.get_remote_bypass_appids", lambda: ("2358720",))

    assert api._check_bypass_availability("2358720") == {
        "onlinefix_available": False,
        "bypass_available": True,
    }


def test_get_bypass_games_returns_empty_when_remote_list_is_empty(tmp_path, monkeypatch):
    api = GameDropWebViewAPI(app_dir=str(tmp_path))
    bypass_file = tmp_path / "bypass_appids.txt"
    bypass_file.write_text("\n".join([f"{i} - Game {i}" for i in range(1, 8)]), encoding="utf-8")
    monkeypatch.setattr("webview_shell.get_remote_bypass_appids", lambda: ())

    results = api.get_bypass_games()

    assert results == []


def test_get_bypass_games_prefers_remote_bypass_source_when_available(tmp_path, monkeypatch):
    api = GameDropWebViewAPI(app_dir=str(tmp_path))
    bypass_file = tmp_path / "bypass_appids.txt"
    bypass_file.write_text("570 - Dota 2\n", encoding="utf-8")
    monkeypatch.setattr("webview_shell.get_remote_bypass_appids", lambda: ("2358720",))

    results = api.get_bypass_games()

    assert results[0]["id"] == "2358720"


def test_find_manifesthub_release_asset_url_prefers_rar_asset(monkeypatch):
    api = GameDropWebViewAPI()
    release_payload = {
        "assets": [
            {"name": "570-bypass.zip", "browser_download_url": "https://example.com/570-bypass.zip"},
            {"name": "570-bypass.rar", "browser_download_url": "https://example.com/570-bypass.rar"},
        ]
    }
    monkeypatch.setattr(api.session, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: release_payload))

    url = api._find_manifesthub_release_asset_url("570")

    assert url == "https://example.com/570-bypass.rar"


def test_download_manifesthub_release_asset_extracts_archive(monkeypatch, tmp_path):
    api = GameDropWebViewAPI()
    manifest_payload = {
        "assets": [{"name": "570-bypass.rar", "browser_download_url": "https://example.com/570-bypass.rar"}]
    }
    def fake_get(url, stream=False, timeout=None, **kwargs):
        if url.endswith('/re'):
            return SimpleNamespace(status_code=200, json=lambda: manifest_payload)
        return SimpleNamespace(status_code=200, headers={}, iter_content=lambda chunk_size: [b'data'], content=b'data')

    monkeypatch.setattr(api.session, "get", fake_get)
    monkeypatch.setattr(api, "_extract_downloaded_archive", lambda path, dest: True)

    extracted = api._download_manifesthub_release_asset("570", str(tmp_path / 'download'))

    assert extracted == str(tmp_path / 'download')


def test_build_html_clears_bypass_gallery_after_selection():
    html = build_html()

    assert "gallery.innerHTML = ''" in html
    assert "selectedGame = await loadSelectedGameDetails(game);" in html


def test_build_html_keeps_thumbnail_preview_visible_after_selection():
    html = build_html()

    assert "panel.classList.remove('hidden');" in html
    assert "panel.style.display = 'grid';" in html
    assert "selectedGame = await loadSelectedGameDetails(game);" in html


def test_build_html_keeps_add_and_bypass_pages_in_two_column_layout():
    html = build_html()

    assert "contentGrid.classList.toggle('single-column', shouldShowHome);" in html
    assert "style.display = shouldShowHome ? 'grid' : 'block';" not in html


def test_build_html_keeps_thumbnail_preview_hidden_on_first_load():
    html = build_html()

    assert "thumbnailPanel.classList.add('hidden');" in html
    assert "thumbnailPanel.style.display = 'none';" in html


def test_build_html_starts_home_page_in_single_column_layout():
    html = build_html()

    assert '<div class="content-grid single-column">' in html


def test_wrapper_package_files_are_validated_and_copied_with_stripped_paths(tmp_path):
    api = GameDropWebViewAPI()
    package_dir = tmp_path / "package"
    steam_dir = tmp_path / "steam"
    wrapper_dir = package_dir / "wrapper"
    wrapper_dir.mkdir(parents=True)
    steam_dir.mkdir()

    (wrapper_dir / "game.exe").write_bytes(b"exe")
    (wrapper_dir / "sub").mkdir()
    (wrapper_dir / "sub" / "patch.dll").write_bytes(b"dll")

    assert api._validate_steam_game_folder(str(package_dir), str(steam_dir), game_name="Example Game") is False

    copied = api._copy_files_to_steam_folder(str(package_dir), str(steam_dir))

    assert len(copied) == 2
    assert (steam_dir / "game.exe").exists()
    assert (steam_dir / "sub" / "patch.dll").exists()


def test_find_package_in_repos_prefers_branch_files_before_release(tmp_path):
    api = GameDropWebViewAPI()

    class BranchResponse(FakeResponse):
        pass

    with patch.object(api, "_download_github_branch_tree", return_value=["3764200.lua"]), patch.object(api.session, "get", return_value=BranchResponse(content=b"print('hello')", status_code=200)):
        result = api._find_package_in_repos("3764200")

    assert result["path"].endswith("branch")
    assert result["owner"] == "kkrmpubg"
    assert result["repo"] == "ManifestHub"
    assert result["source"] == "branch"
    assert "temp_root" in result


def test_apply_onlinefix_package_cleans_temp_package_after_success(tmp_path):
    api = GameDropWebViewAPI()
    temp_root = tmp_path / "gamedrop_3764200_temp"
    package_dir = temp_root / "package"
    package_dir.mkdir(parents=True)
    (package_dir / "file.txt").write_text("payload", encoding="utf-8")

    with patch.object(
        api,
        "_download_onlinefix_package",
        return_value=str(package_dir),
    ), patch.object(api, "_get_steam_library_roots", return_value=[str(tmp_path / "steamapps" / "common")]), patch.object(api, "_find_steam_game_folder", return_value=str(tmp_path / "game")), patch.object(api, "_find_steam_game_folder_from_package", return_value=str(tmp_path / "game")), patch.object(api, "_validate_steam_game_folder", return_value=True), patch.object(api, "_copy_onlinefix_to_steam", return_value=[str(tmp_path / "game" / "file.txt")]):
        result = api._apply_onlinefix_package("3764200", game_name="Example Game", denuvo=True)

    assert result["ok"] is True
    assert not package_dir.exists()


def test_validate_steam_game_folder_requires_matching_files(tmp_path):
    api = GameDropWebViewAPI()
    package_dir = tmp_path / "package"
    steam_dir = tmp_path / "steam"
    package_dir.mkdir(parents=True)
    steam_dir.mkdir(parents=True)

    (package_dir / "wrapper" / "game.exe").parent.mkdir(parents=True, exist_ok=True)
    (package_dir / "wrapper" / "game.exe").write_bytes(b"exe")
    (package_dir / "wrapper" / "sub" / "patch.dll").parent.mkdir(parents=True, exist_ok=True)
    (package_dir / "wrapper" / "sub" / "patch.dll").write_bytes(b"dll")
    (steam_dir / "othergame.exe").write_bytes(b"exe")

    assert api._validate_steam_game_folder(str(package_dir), str(steam_dir), game_name="Example Game") is False


def test_validate_steam_game_folder_accepts_matching_game_file(tmp_path):
    api = GameDropWebViewAPI()
    package_dir = tmp_path / "package"
    steam_dir = tmp_path / "steam"
    package_dir.mkdir(parents=True)
    steam_dir.mkdir(parents=True)

    (package_dir / "wrapper" / "game.exe").parent.mkdir(parents=True, exist_ok=True)
    (package_dir / "wrapper" / "game.exe").write_bytes(b"exe")
    (steam_dir / "game.exe").write_bytes(b"exe")

    assert api._validate_steam_game_folder(str(package_dir), str(steam_dir), game_name="Example Game") is True


def test_download_github_release_asset_extracts_rar_archives(tmp_path):
    api = GameDropWebViewAPI()
    destination = tmp_path / "download"
    destination.mkdir()
    archive_path = destination / "3764200.rar"
    archive_path.write_bytes(b"fake-rar")

    class FakeResponse:
        status_code = 200

        def __init__(self, payload=None, content=b""):
            self._payload = payload or {}
            self.content = content

        def json(self):
            return self._payload

        def __iter__(self):
            return iter(())

        def iter_content(self, chunk_size=8192):
            if self.content:
                yield self.content
            else:
                yield b""

    fake_release = {"tag_name": "re", "assets": [{"name": "3764200.rar", "browser_download_url": "https://example.test/3764200.rar"}]}

    with patch.object(api, "_find_github_release_asset_url", return_value=("https://example.test/3764200.rar", False)), patch.object(api.session, "get", return_value=FakeResponse(content=b"fake-rar")) as mock_get, patch("webview_shell.shutil.which", return_value="C:/Program Files/WinRAR/UnRAR.exe"), patch("webview_shell.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0)
        result = api._download_github_release_asset("kkrmpubg", "ManifestHub", "3764200", str(destination))

    assert result == str(destination)
    mock_get.assert_called_once()
    mock_run.assert_called_once()


def test_download_manifesthub_release_asset_uses_backend_download_url(tmp_path):
    api = GameDropWebViewAPI()
    destination = tmp_path / "download"
    destination.mkdir()

    class BackendResponse:
        status_code = 200

        def json(self):
            return {"bypass_available": True, "download_url": "https://example.test/backend/1001270.rar", "status": "ok"}

    with patch.object(api.session, "get", return_value=BackendResponse()) as mock_get, patch.object(api, "_download_url_to_temp", return_value=str(destination / "asset.rar")) as mock_download, patch.object(api, "_extract_downloaded_archive", return_value=True):
        result = api._download_manifesthub_release_asset("1001270", str(destination))

    assert result == str(destination)
    mock_download.assert_called_once_with("https://example.test/backend/1001270.rar", str(destination), "1001270_asset")
    assert mock_get.call_count >= 1


def test_build_html_places_add_and_remove_actions_in_separate_groups():
    html = build_html()

    assert 'class="action-buttons-main"' in html
    assert 'class="action-buttons-left"' in html
    assert 'class="action-buttons-right"' in html


def test_build_html_uses_distinct_step_two_action_card():
    html = build_html()

    assert 'action-step-card' in html
    assert 'action-step-kicker' in html
    assert 'action-cta primary' in html


def test_build_html_fades_step_one_card_when_selection_exists():
    html = build_html()

    assert 'id="step1-card"' in html
    assert "updateSelectedGameSummary(selectedGame);" in html


def test_build_html_keeps_bypass_nav_item_highlightable():
    html = build_html()

    assert "itemFlow !== 'add_denuvo_game'" not in html
    assert "const isActive = itemFlow === normalizedFlow" in html


def test_build_html_uses_text_labels_instead_of_emoji_icons():
    html = build_html()

    assert "🏠" not in html
    assert "⚡" not in html
    assert "🔍" not in html
    assert "✅" not in html
    assert "⛨" not in html


def test_remote_bypass_appids_refresh_on_every_call(monkeypatch):
    import check_onlinefix_bypass

    calls = []

    class FakeResponse:
        status_code = 200
        text = "570\n"

        def json(self):
            return {}

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(check_onlinefix_bypass.requests, "get", fake_get)
    check_onlinefix_bypass.get_remote_bypass_appids.cache_clear() if hasattr(check_onlinefix_bypass.get_remote_bypass_appids, "cache_clear") else None

    assert check_onlinefix_bypass.get_remote_bypass_appids() == ("570",)
    assert check_onlinefix_bypass.get_remote_bypass_appids() == ("570",)
    assert len(calls) == 2


def test_initial_state_refreshes_remote_bypass_list(monkeypatch):
    api = GameDropWebViewAPI()
    calls = []
    monkeypatch.setattr("webview_shell.get_remote_bypass_appids", lambda: calls.append("called") or ())

    api.get_initial_state()

    assert calls == ["called"]


def test_wizard_state_does_not_refresh_remote_bypass_appids(monkeypatch):
    calls = []
    monkeypatch.setattr("webview_shell.get_remote_bypass_appids", lambda: calls.append("called") or ())

    api = GameDropWebViewAPI()
    calls.clear()

    api.get_wizard_state("add_denuvo_game")
    api.get_wizard_state("add_denuvo_game")

    assert calls == []


def test_check_onlinefix_availability_reports_remote_bypass_for_known_appid():
    api = GameDropWebViewAPI()

    result = api._check_onlinefix_availability("2358720")

    assert result["onlinefix_available"] is False
    assert result["bypass_available"] is True


def test_check_onlinefix_availability_falls_back_to_html_for_tag_branch():
    api = GameDropWebViewAPI()

    result = api._check_onlinefix_availability("3527290")

    assert result["onlinefix_available"] is False
    assert result["bypass_available"] is False


def test_check_onlinefix_availability_html_login_page_does_not_count():
    api = GameDropWebViewAPI()

    result = api._check_onlinefix_availability("440")

    assert result["onlinefix_available"] is False
    assert result["bypass_available"] is False


def test_check_denuvo_drm_includes_fix_status():
    api = GameDropWebViewAPI()

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": True, "bypass_available": True}):
        with patch.object(api.session, "get", return_value=FakeResponse(text="<html>no drm markers here</html>")):
            result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is False
    assert result["onlinefix_available"] is True
    assert result["bypass_available"] is True
    assert result["activation_available"] is False


def test_check_denuvo_drm_activation_available_when_no_bypass():
    api = GameDropWebViewAPI()

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": False, "bypass_available": False}):
        with patch.object(api, "_check_bypass_availability", return_value={"onlinefix_available": False, "bypass_available": False}):
            with patch.object(api.session, "get", return_value=FakeResponse(text="<html>Incorporates 3rd-party DRM: Denuvo</html>")):
                result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is True
    assert result["activation_available"] is True
    assert result["bypass_available"] is False


def test_check_denuvo_drm_uses_bypass_status_when_denuvo_detected():
    api = GameDropWebViewAPI()

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": False, "bypass_available": False}):
        with patch.object(api, "_check_bypass_availability", return_value={"onlinefix_available": False, "bypass_available": True}):
            with patch.object(api.session, "get", return_value=FakeResponse(text="<html>Incorporates 3rd-party DRM: Denuvo</html>")):
                result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is True
    assert result["bypass_available"] is True
    assert result["onlinefix_available"] is False
    assert result["activation_available"] is False


def test_check_denuvo_drm_preserves_onlinefix_when_denuvo_detected():
    api = GameDropWebViewAPI()

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": True, "bypass_available": False}):
        with patch.object(api.session, "get", return_value=FakeResponse(text="<html>Incorporates 3rd-party DRM: Denuvo</html>")):
            result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is True
    assert result["bypass_available"] is False
    assert result["onlinefix_available"] is True
    assert result["activation_available"] is False


def test_check_denuvo_drm_preserves_bypass_when_not_denuvo():
    api = GameDropWebViewAPI()

    with patch.object(api, "_check_onlinefix_availability", return_value={"onlinefix_available": False, "bypass_available": True}):
        with patch.object(api.session, "get", return_value=FakeResponse(text="<html>No DRM markers here</html>")):
            with patch.object(api, "_check_steam_api_drm", return_value=False):
                result = api.check_denuvo_drm("570", "Dota 2")

    assert result["denuvo_detected"] is False
    assert result["onlinefix_available"] is False
    assert result["bypass_available"] is True
    assert result["activation_available"] is False


def test_build_html_keeps_onlinefix_badge_priority():
    html = build_html()

    assert "const onlinefix = normalizeFlag(result.onlinefix_available);" in html
    assert "const activation = !bypass && !onlinefix && normalizeFlag(result.activation_available);" in html


def test_build_html_skips_initial_content_animation_on_first_load():
    html = build_html()

    assert "let initialLoad = true;" in html
    assert "const shouldAnimate = !(initialLoad && currentFlow === '');" in html


def test_build_html_scales_sidebar_for_smaller_windows():
    html = build_html()

    assert ".shell {" in html
    assert "min-height: 100vh;" in html
    assert "height: 100vh;" in html
    assert "overflow: hidden;" in html
    assert ".app-shell {" in html
    assert ".sidebar {" in html
    assert "overflow-y: auto;" in html


def test_build_html_prevents_repeated_nav_flow_switches():
    html = build_html()

    assert "let flowSwitchInProgress = false;" in html
    assert "flowSwitchInProgress = true;" in html
    assert "flowSwitchInProgress = false;" in html


def test_build_html_clears_bypass_wizard_message_while_loading():
    html = build_html()

    assert "wizardMessage.textContent = '';" in html
    assert "showProgress('Loading bypass suggestions…');" in html


def test_build_html_hides_shell_until_initialization_finishes():
    html = build_html()

    assert ".shell.ready" in html
    assert "visibility: visible;" in html
    assert "shell.classList.add('ready');" in html


def test_build_html_stabilizes_bypass_scroll_container():
    html = build_html()

    assert "overflow-anchor: none;" in html
    assert "bypassPanel.scrollTop =" in html


def test_build_html_keeps_bypass_thumbnails_visible_for_single_results():
    html = build_html()

    assert ".bypass-gallery.single-result .bypass-item-image" not in html


def test_build_html_lowers_selected_game_action_buttons():
    html = build_html()

    assert "#action-panel {" in html
    assert "margin-top: 18px;" in html


def test_build_html_keeps_bypass_specific_buttons_for_selected_game():
    html = build_html()

    assert 'id="bypass-button"' in html
    assert "bypass-actions-group" in html


def test_build_html_wires_bypass_button_click_handlers():
    html = build_html()

    assert "addEventListener('click', handleBypassAction)" in html


def test_build_html_includes_bypass_result_panel_with_back_button():
    html = build_html()

    assert 'id="bypass-result-panel"' in html
    assert 'id="bypass-result-back-button"' in html


def test_build_html_uses_step_style_result_panels():
    html = build_html()

    assert 'class="action-step-card result-step-card"' in html
    assert 'id="bypass-result-title"' in html


def test_build_html_autofocuses_search_on_each_sidebar_flow_selection():
    html = build_html()

    assert "if (normalizedFlow === 'add_game' || normalizedFlow === 'add_denuvo_game')" in html


def test_build_html_restores_home_panel_on_home_flow():
    html = build_html()

    assert "homePanel.style.display = shouldShowHome ? 'block' : 'none';" in html


def test_build_html_bootstraps_shell_without_pywebview_api():
    html = build_html()

    assert "const fallbackState =" in html
    assert "homePanel.style.display = 'block';" in html


def test_build_html_keeps_shell_visible_until_js_ready():
    html = build_html()

    assert "visibility: visible;" in html
    assert "shell.classList.add('ready');" in html


def test_build_html_restores_add_game_action_buttons():
    html = build_html()

    assert 'id="next-button"' in html
    assert 'id="remove-button"' in html


def test_build_html_keeps_thumbnail_preview_visible_for_add_flows():
    html = build_html()

    assert "const shouldShowPreview = normalizedFlow === 'add_game' || normalizedFlow === 'add_denuvo_game';" in html


def test_build_html_declares_bypass_button_for_flow_updates():
    html = build_html()

    assert "const bypassButton = document.getElementById('bypass-button');" in html


def test_onlinefix_action_uses_bypass_application_handler(monkeypatch):
    api = GameDropWebViewAPI()
    calls = {}

    def fake_apply(appid, game_name=None, denuvo=True):
        calls["appid"] = appid
        calls["game_name"] = game_name
        calls["denuvo"] = denuvo
        return {"ok": True, "message": "Applied"}

    monkeypatch.setattr(api, "_apply_onlinefix_package", fake_apply)
    with patch.object(api, "_get_steam_app_details", return_value={"id": "570", "name": "Dota 2"}):
        result = api.run_action("onlinefix", {"appid": "570"})

    assert result["ok"] is True
    assert calls == {"appid": "570", "game_name": "Dota 2", "denuvo": True}


def test_build_html_centers_home_flow_vertically():
    html = build_html()

    assert ".workspace {" in html
    assert "grid-template-rows: auto minmax(0, 1fr);" in html
    assert ".content-grid.single-column {" in html
    assert "display: flex;" in html
    assert "justify-content: center;" in html
    assert "align-items: center;" in html


def test_build_html_preserves_completion_panel_until_reset():
    html = build_html()

    assert "function clearCompletionPanel(force = false) {" in html
    assert "if (!force && completionPanelVisible) {" in html
    assert "completionPanelVisible = true;" in html


def test_build_html_uses_bypass_or_activation_note_for_denuvo_success():
    html = build_html()

    assert "const note = denuvo" in html
    assert "go to bypass page for denuvo bypass" in html
    assert "Denuvo activation available" in html


def test_remove_game_action_deletes_lua_files_for_valid_appid(tmp_path):
    api = GameDropWebViewAPI()
    steam_dir = tmp_path / "steam"
    lua_dir = steam_dir / "config" / "lua"
    lua_dir.mkdir(parents=True)
    lua_file = lua_dir / "570.lua"
    lua_file.write_text("print('hello')\n", encoding="utf-8")

    with patch("file_protection.get_steam_path", return_value=str(steam_dir)):
        result = api.run_action("remove_game", {"appid": "570"})

    assert result["ok"] is True
    assert result["removed"] is True
    assert "game removed from steam" in result["message"].lower()
    assert not lua_file.exists()


def test_remove_game_action_reports_missing_game_when_no_lua_files(tmp_path):
    api = GameDropWebViewAPI()
    steam_dir = tmp_path / "steam"
    steam_dir.mkdir(parents=True)

    with patch("file_protection.get_steam_path", return_value=str(steam_dir)):
        result = api.run_action("remove_game", {"appid": "570"})

    assert result["ok"] is True
    assert result["removed"] is False
    assert result["message"] == "Game is not on your library."


def test_remove_game_action_deletes_lua_files_from_stplugin_and_content_match(tmp_path):
    api = GameDropWebViewAPI()
    steam_dir = tmp_path / "steam"
    lua_dir = steam_dir / "config" / "lua"
    stplugin_dir = steam_dir / "config" / "stplug-in"
    lua_dir.mkdir(parents=True)
    stplugin_dir.mkdir(parents=True)

    lua_file = lua_dir / "random.lua"
    lua_file.write_text("setManifest(570)\n", encoding="utf-8")
    disabled_file = stplugin_dir / "other.lua.disabled"
    disabled_file.write_text("setManifestid(570)\n", encoding="utf-8")

    with patch("file_protection.get_steam_path", return_value=str(steam_dir)):
        result = api.run_action("remove_game", {"appid": "570"})

    assert result["ok"] is True
    assert not lua_file.exists()
    assert not disabled_file.exists()


def test_build_html_contains_remove_game_completion_copy():
    html = build_html()

    assert "Game removed from your Steam library" in html
    assert "The Lua file was removed." in html


def test_add_game_action_downloads_package_and_patches_lua(tmp_path):
    api = GameDropWebViewAPI()
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    lua_file = package_dir / "example.lua"
    lua_file.write_text("-- setManifest(12345)\nprint('hello')\n", encoding="utf-8")

    def fake_find_package_in_repos(appid):
        return {"path": str(package_dir), "owner": "kkrmpubg", "repo": "ManifestHub", "source": "branch"}

    api._find_package_in_repos = fake_find_package_in_repos
    with patch.object(api, "_get_steam_app_details", return_value={"id": "570", "name": "Dota 2"}):
        result = api.run_action("add_game", {"appid": "570"})

    assert result["ok"] is True
    assert "Dota 2 is added to the Steam library" in result["message"]
    assert "Lua file(s) installed to Steam" in result["message"]
    assert lua_file.read_text(encoding="utf-8") == "-- setManifest(12345)\nprint('hello')\n"


def test_add_denuvo_game_action_uncomments_manifest_calls(tmp_path):
    api = GameDropWebViewAPI()
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    lua_file = package_dir / "denuvo.lua"
    lua_file.write_text("-- setManifestid(54321)\nreturn true\n", encoding="utf-8")

    api._find_package_in_repos = lambda appid: {"path": str(package_dir), "owner": "SteamAutoCracks", "repo": "ManifestHub", "source": "release"}
    with patch.object(api, "_get_steam_app_details", return_value={"id": "570", "name": "Denuvo Game"}):
        result = api.run_action("add_denuvo_game", {"appid": "570"})

    assert result["ok"] is True
    assert "Denuvo Game is added to the Steam library" in result["message"]
    assert "Lua file(s) installed to Steam" in result["message"]
    assert lua_file.read_text(encoding="utf-8") == "setManifestid(54321)\nreturn true\n"


def test_build_html_embeds_logo_when_uri_is_available(tmp_path):
    image_path = tmp_path / "logo.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png")

    html = build_html(logo_uri=image_path.resolve().as_uri())

    assert 'class="sidebar-logo"' in html
    assert 'src="data:image/png;base64,' in html
