from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Credit:
    platform: str
    author: str
    url: str
    outro_seconds: float = 4.0
    font_percent: float = 3.0

    def validate(self) -> None:
        for label, value, limit in (
            ("平台", self.platform, 80), ("作者 ID", self.author, 160),
            ("原片連結", self.url, 2048),
        ):
            if not value.strip():
                raise ValueError(f"請填寫{label}。")
            if len(value) > limit:
                raise ValueError(f"{label}最多接受 {limit} 個字元。")
            if any(ord(c) < 32 for c in value):
                raise ValueError(f"{label}不能包含換行或控制字元。")
        try:
            parts = urlsplit(self.url)
            valid = parts.scheme in ("https", "http") and bool(parts.hostname)
            valid = valid and not parts.username and not parts.password
            _ = parts.port
        except ValueError:
            valid = False
        if not valid or any(c.isspace() for c in self.url):
            raise ValueError("請填寫完整的 http:// 或 https:// 原片連結，且不能包含空白。")
        if not 1 <= self.outro_seconds <= 30:
            raise ValueError("結尾長度須介於 1 至 30 秒。")
        if not 1.5 <= self.font_percent <= 5:
            raise ValueError("標註字級須介於短邊的 1.5% 至 5%。")

    @property
    def overlay_text(self) -> str:
        author = self.author.strip().lstrip("@").strip()
        return f"Credit:{self.platform.strip()}@{author}"

    @property
    def caption(self) -> str:
        return f"影片來源：{self.platform}\n原作者：{self.author}\n原片連結：{self.url}"


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    audio_offset: float = 0.0
