from datetime import datetime

import app.main as main_module


def test_filebrowser_default_files_url_prefers_today_upload_excel_folder(monkeypatch, tmp_path):
    (tmp_path / "260604").mkdir()
    monkeypatch.setattr(main_module, "FILE_BROWSER_UPLOAD_EXCEL_ROOT", tmp_path)
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 6, 4, 9, 30))

    assert main_module._filebrowser_default_files_url() == "/files/upload_excel/260604/"


def test_filebrowser_default_files_url_falls_back_to_upload_excel_root(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "FILE_BROWSER_UPLOAD_EXCEL_ROOT", tmp_path)
    monkeypatch.setattr(main_module, "_local_now", lambda: datetime(2026, 6, 4, 9, 30))

    assert main_module._filebrowser_default_files_url() == "/files/upload_excel/"


def test_filebrowser_clean_ui_injects_style_and_behavior_script():
    html = b"<html><head><title>Files</title></head><body><div id='app'></div></body></html>"

    patched = main_module._inject_filebrowser_clean_ui(html, "text/html; charset=utf-8")

    assert b"caifuclaw-filebrowser-clean-ui" in patched
    assert b"caifuclaw-filebrowser-behavior" in patched
    assert b"DOWNLOAD_ONLY_EXTENSIONS" not in patched
    assert b"--background: #f3f6fb" in patched
    assert b"header .breadcrumbs" in patched
    assert b"#multiple-selection" in patched
    assert b".context-menu" in patched
    assert b"#previewer header title" in patched
    assert b"caifuclaw-filebrowser-selected" in patched
    assert b"caifuclaw-filebrowser-select-all" in patched
    assert b"downloadSelectedRows" in patched
    assert b"saveBlobDownload" in patched
    assert b"triggerIframeDownloadFallback" in patched
    assert b"content-disposition" in patched
    assert b"formatExactDateTime" in patched
    assert b"/api/resources" in patched
    assert b"renewFileBrowserSession" in patched
    assert b"recoverServerReachabilityError" in patched
    assert b"caifuclaw-filebrowser-preview-button" in patched
    assert b"caifuclaw-filebrowser-image-preview" in patched
    assert b"openImagePreviewOverlay" in patched
    assert b"rowPreviewIcon" in patched
    assert b"hideNativeNameIcons" in patched
    assert b"caifuclaw-filebrowser-native-icon-hidden" in patched
    assert b"caifuclaw-filebrowser-preview-frame i::before" in patched
    assert b"dblclick" not in patched
    assert b"caifuclawRowActionBound" in patched
    assert b"runRowPrimaryAction" in patched
    assert b"aria-selected" in patched
    assert b"caifuclaw-filebrowser-download-label" in patched
    assert "下载".encode("utf-8") in patched
    assert "全选当前目录".encode("utf-8") in patched


def test_filebrowser_clean_ui_rewrites_public_base_url():
    html = (
        b"<html><head><script>"
        b'window.FileBrowser = {"BaseURL":"/filebrowser","StaticURL":"/filebrowser/static"};'
        b"</script>"
        b'<script type="module" src="/filebrowser/static/assets/index.js"></script>'
        b'<link rel="stylesheet" href="/filebrowser/static/assets/index.css">'
        b"</head><body></body></html>"
    )

    patched = main_module._inject_filebrowser_clean_ui(html, "text/html")

    assert b'"BaseURL":""' in patched
    assert b'"StaticURL":"/static"' in patched
    assert b'src="/static/assets/index.js"' in patched
    assert b'href="/static/assets/index.css"' in patched
    assert b"/filebrowser/static" not in patched


def test_filebrowser_clean_ui_skips_non_html_content():
    content = b"console.log('asset')"

    assert main_module._inject_filebrowser_clean_ui(content, "application/javascript") == content


def test_filebrowser_download_only_redirects_excel_preview_path_to_raw_download():
    url = main_module._filebrowser_download_only_redirect_url(
        "files/upload_excel/260605/music_103719/Joom Music 260605.xlsx",
        "GET",
    )

    assert url == "/api/raw/upload_excel/260605/music_103719/Joom%20Music%20260605.xlsx"


def test_filebrowser_download_only_keeps_previewable_files_and_non_get_requests():
    assert main_module._filebrowser_download_only_redirect_url("files/upload_excel/260605/label.pdf", "GET") is None
    assert main_module._filebrowser_download_only_redirect_url("files/upload_excel/260605/report.xlsx", "POST") is None


def test_filebrowser_legacy_redirects_remove_filebrowser_prefix():
    assert main_module._filebrowser_legacy_redirect_url("", b"") == "/files/upload_excel/"
    assert (
        main_module._filebrowser_legacy_redirect_url("files/upload_excel/", b"sort=name")
        == "/files/upload_excel/?sort=name"
    )
    assert (
        main_module._filebrowser_legacy_redirect_url("api/raw/upload_excel/report.xlsx", b"download=1")
        == "/api/raw/upload_excel/report.xlsx?download=1"
    )
