"""Browser regression for delayed review responses. Requires playwright and a frontend build."""
import asyncio
import functools
import http.server
import shutil
import threading
from pathlib import Path
from playwright.async_api import async_playwright, expect

BASE_URL = ""

SUBS = [{"id": 7, "start": 5, "end": 9, "original_text": "Original sentence.", "translated_text": "示例配音"}]
INIT = """
localStorage.setItem('vp_deepseek_settings', JSON.stringify({deepseekApiKey:'browser-test'}));
window.__streams = [];
window.EventSource = class {
  constructor(url) { this.url = url; window.__streams.push(this); }
  close() { this.closed = true; }
};
window.__emit = event => window.__streams.at(-1).onmessage({data:JSON.stringify(event)});
"""

async def scenario(browser, mode):
    page = await browser.new_page()
    page.set_default_timeout(5000)
    await page.add_init_script(INIT)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    alerts = []
    async def dialog_handler(dialog):
        alerts.append(dialog.message)
        await dialog.dismiss()
    page.on("dialog", dialog_handler)
    subtitle_release = asyncio.Event()
    confirm_release = asyncio.Event()
    counts = {"subtitles": 0, "confirm": 0}
    stage = "WAITING_REVIEW"

    async def route_handler(route):
        nonlocal stage
        path = route.request.url.removeprefix(BASE_URL)
        data = {}
        if path == "/api/config/options":
            data = {"asr_models": []}
        elif path == "/api/tasks/create":
            data = {"task_id": "browser-test"}
        elif path.endswith("/subtitles/confirm"):
            counts["confirm"] += 1
            await confirm_release.wait()
            stage = "TTS"
            data = {"status": "success", "state": "TTS"}
        elif path.endswith("/subtitles"):
            counts["subtitles"] += 1
            await subtitle_release.wait()
            data = {"state": "WAITING_REVIEW", "subtitles": SUBS}
        elif path.endswith("/status"):
            data = {"task_id": "browser-test", "state": stage, "progress": 0, "message": "测试",
                    "logs": [], "subtitles_count": 1}
        elif path.endswith("/speaker-ref"):
            data = {"speaker_ref": None, "segments": [], "tts_speaking_rate": 3.8}
        else:
            await route.fulfill(status=404, json={})
            return
        await route.fulfill(json=data)

    await page.route("**/api/**", route_handler)
    try:
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.get_by_placeholder("例如:", exact=False).fill("https://example.test/video")
        await page.locator("button[type=submit]").click()
        await page.wait_for_function("window.__streams.length > 0")
        async def emit(event):
            await page.evaluate("event => window.__emit(event)", {"task_id": "browser-test", **event})
        await emit({"type": "init", "state": "WAITING_REVIEW", "progress": 100,
                    "message": "等待校对", "logs": []})
        await page.wait_for_timeout(100)
        await emit({"type": "review_ready", "subtitles": SUBS})
        heading = page.get_by_role("heading", name="在线校对中文字幕与时间轴")
        await expect(heading).to_be_visible()
        if mode == "confirm":
            await page.locator("textarea").fill("编辑后的中文")
            # Additional WAITING_REVIEW events and polls must not replace user's edits.
            await emit({"type": "progress", "stage": "WAITING_REVIEW", "progress": 100,
                        "message": "等待校对"})
            await page.wait_for_timeout(3200)
            await expect(page.locator("textarea")).to_have_value("编辑后的中文")
            # Two same-turn click events exercise the synchronous submission guard.
            await page.get_by_role("button", name="确认字幕并继续生成视频", exact=False).evaluate(
                "button => { button.click(); button.click(); }")
            await page.wait_for_timeout(100)
            assert counts["confirm"] == 1, counts
            confirm_release.set()
            await expect(heading).to_have_count(0)
            await emit({"type": "progress", "stage": "WAITING_REVIEW", "progress": 100,
                        "message": "延迟到达的旧状态"})
            await emit({"type": "review_ready", "subtitles": SUBS})
            subtitle_release.set()
            await page.wait_for_timeout(400)
            await expect(heading).to_have_count(0)
            assert counts["subtitles"] == 1, counts
            stage = "COMPLETED"
            await emit({"type": "completed", "result": {"filename": "test.mp4", "srt_filename": "test.srt",
                "subtitle_mode": "soft", "vtt_filename": "test.vtt", "warnings": ["已改为可切换软字幕"]}})
            track = page.locator("video track")
            await expect(track).to_have_attribute("src", "/outputs/test.vtt")
            await expect(page.get_by_text("已改为可切换软字幕", exact=True)).to_be_visible()
        else:
            stage = "FAILED"
            await emit({"type": "error", "error": "合成测试错误"})
            await expect(heading).to_have_count(0)
            subtitle_release.set()
            await page.wait_for_timeout(400)
            await expect(heading).to_have_count(0)
        assert not alerts, alerts
        assert not errors, errors
        print(f"PASS browser {mode}: {counts}; no stale modal, no alerts, no runtime errors")
    finally:
        subtitle_release.set()
        confirm_release.set()
        await page.close()

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"])
        try:
            await scenario(browser, "confirm")
            await scenario(browser, "failure")
        finally:
            await browser.close()

if __name__ == "__main__":
    dist = Path(__file__).resolve().parents[1] / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Build the frontend first: cd frontend && npm run build")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(QuietHandler, directory=str(dist))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    BASE_URL = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        asyncio.run(main())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

