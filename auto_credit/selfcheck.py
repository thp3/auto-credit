"""Opt-in diagnostic for verifying an installed/frozen application end to end."""
import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from .artwork import composite, end_card, overlay
from .engine import executable, export_video, frame, probe, run_process
from .models import Credit
from .logos import platform_logo


def run_self_check(folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    report = {}
    window = None
    try:
        # A fresh subdirectory avoids overwriting previous diagnostic outputs.
        import tempfile
        run = Path(tempfile.mkdtemp(prefix="check-", dir=folder))
        report["artifacts"] = str(run)
        report["ffmpeg"] = executable("ffmpeg")
        report["ffprobe"] = executable("ffprobe")
        source = run / "source.mp4"
        target = run / "測試影片 (1)_credit.mp4"
        run_process([executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
                     "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=1",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], Event())
        credit = Credit("YouTube", "@原作者_test", "https://example.com/original", 1)
        for platform in ("YouTube", "Bilibili", "TikTok"):
            if platform_logo(platform) is None:
                raise ValueError(f"Missing platform logo: {platform}")
            card = end_card(Credit(platform, credit.author, credit.url, 1), 640, 360)
            if not card.save(str(run / f"end-{platform.lower()}.png")):
                raise ValueError(f"Cannot save platform end card: {platform}")
        report["logos"] = ["YouTube", "Bilibili", "TikTok"]
        from .app import Window, create_save_dialog
        settings = QSettings(str(run / "settings.ini"), QSettings.Format.IniFormat)
        window = Window(settings)
        dialog = create_save_dialog(window, target)
        def accept_destination():
            dialog.grab().save(str(run / "save-dialog.png"))
            dialog.accept()
        watchdog = QTimer(dialog)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(dialog.reject)
        watchdog.start(5000)
        QTimer.singleShot(50, accept_destination)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                raise ValueError("Save dialog did not accept a new output filename")
            if [Path(value) for value in dialog.selectedFiles()] != [target] or target.exists():
                raise ValueError("Save dialog did not return the expected new output path")
            report["save_dialog_accepts_new_file"] = True
        finally:
            watchdog.stop()
            dialog.deleteLater()
        result = export_video(source, target, credit, Event())
        window.author.setText(credit.author)
        window.url.setText(credit.url)
        window.seconds.setValue(1)
        info = probe(source)
        raw = frame(source, info, .5, Event())
        window.source_loaded((source, info, raw))
        window.preview_ready((composite(raw, overlay(credit, info.width, info.height)),
                              end_card(credit, info.width, info.height)))
        window.show()
        QApplication.processEvents()
        window.grab().save(str(run / "window.png"))
        frame(target, result, 1.5, Event()).save(str(run / "encoded-end.png"))
        report.update(ok=True, width=result.width, height=result.height, duration=result.duration)
    except Exception as error:
        report.update(ok=False, error=str(error))
    finally:
        if window:
            window.close()
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
