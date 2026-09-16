from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib import parse, request, error

try:
    from rapidfuzz.fuzz import ratio, token_set_ratio, WRatio
except Exception:  # pragma: no cover
    from difflib import SequenceMatcher

    def ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

    def token_set_ratio(a: str, b: str) -> float:
        sa = set(a.split())
        sb = set(b.split())
        if not sa or not sb:
            return 0.0
        return 100.0 * len(sa & sb) / len(sa | sb)

    def WRatio(a: str, b: str) -> float:
        return ratio(a, b)


@dataclass(frozen=True)
class SpotifyLyricEvidence:
    available: bool
    is_playing: bool
    track_id: str
    track_name: str
    artist_name: str
    progress_ms: int
    duration_ms: int
    lyric_match: float
    time_alignment: float
    phrase_match: float
    token_match: float
    full_track_match: float
    source: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "is_playing": self.is_playing,
            "track_id": self.track_id,
            "track_name": self.track_name,
            "artist_name": self.artist_name,
            "progress_ms": self.progress_ms,
            "duration_ms": self.duration_ms,
            "lyric_match": self.lyric_match,
            "time_alignment": self.time_alignment,
            "phrase_match": self.phrase_match,
            "token_match": self.token_match,
            "full_track_match": self.full_track_match,
            "source": self.source,
            "reason": self.reason,
        }


class SpotifyLyricMatcher:
    """Deterministic Spotify-track/lyrics evidence for ARIA attention detection.

    It never sends lyrics to an LLM.  Lyrics are used locally to compute matching
    evidence against the Whisper transcript.
    """

    API_BASE = "https://lrclib.net/api/get"
    USER_AGENT = "Project-ARIA/1.0 (local desktop assistant)"
    MIN_FETCH_INTERVAL = 0.35

    def __init__(
        self,
        spotify_context: Any,
        *,
        timeout: float = 5.0,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.spotify_context = spotify_context
        self.timeout = float(timeout)
        self.cache_dir = cache_dir or Path(
            os.environ.get("APPDATA", str(Path.home()))
        ) / "ARIA" / "spotify_lyrics_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._track_id = ""
        self._track_meta: dict[str, Any] = {}
        self._plain_lyrics = ""
        self._synced_lines: list[tuple[float, str]] = []
        self._lyrics_loaded = False
        self._lyrics_source = "none"
        self._last_fetch = 0.0
        self._last_playback_poll = 0.0
        self._last_playback = None
        self.poll_interval = 0.9

    # ----------------------------- utilities -----------------------------
    @staticmethod
    def _norm(text: str) -> str:
        value = str(text or "").lower().replace("’", "'")
        value = re.sub(r"\[[^\]]*\]", " ", value)
        value = re.sub(r"[^a-z0-9'\s]", " ", value)
        value = value.replace("'", "")
        return " ".join(value.split())

    @staticmethod
    def _tokens(text: str) -> list[str]:
        normalized = SpotifyLyricMatcher._norm(text)
        return normalized.split() if normalized else []

    @staticmethod
    def _parse_synced_lyrics(text: str) -> list[tuple[float, str]]:
        lines: list[tuple[float, str]] = []
        pattern = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]\s*(.*)$")
        for raw in str(text or "").splitlines():
            m = pattern.match(raw.strip())
            if not m:
                continue
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            fraction = (m.group(3) or "").ljust(3, "0")
            millis = int(fraction[:3]) if fraction else 0
            lyric = m.group(4).strip()
            if lyric:
                lines.append((minutes * 60.0 + seconds + millis / 1000.0, lyric))
        lines.sort(key=lambda item: item[0])
        return lines

    @staticmethod
    def _cache_key(track_id: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", track_id or "unknown")
        return safe + ".json"

    def _cache_path(self, track_id: str) -> Path:
        return self.cache_dir / self._cache_key(track_id)

    def _load_cache(self, track_id: str) -> bool:
        path = self._cache_path(track_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        self._plain_lyrics = str(payload.get("plainLyrics") or "")
        self._synced_lines = [
            (float(t), str(text))
            for t, text in payload.get("synced", [])
            if str(text).strip()
        ]
        self._lyrics_source = str(payload.get("source") or "cache")
        self._lyrics_loaded = bool(self._plain_lyrics or self._synced_lines)
        return self._lyrics_loaded

    def _save_cache(self, track_id: str) -> None:
        try:
            self._cache_path(track_id).write_text(
                json.dumps(
                    {
                        "track_id": track_id,
                        "plainLyrics": self._plain_lyrics,
                        "synced": self._synced_lines,
                        "source": self._lyrics_source,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _fetch_lyrics(self, playback: Any) -> None:
        track_name = str(getattr(playback, "track_name", "") or "")
        artist_names = tuple(getattr(playback, "artist_names", ()) or ())
        artist_name = artist_names[0] if artist_names else ""
        album_name = str(getattr(playback, "album_name", "") or "")
        duration_ms = int(getattr(playback, "duration_ms", 0) or 0)
        duration_s = max(1, round(duration_ms / 1000.0))

        if not track_name or not artist_name:
            self._lyrics_loaded = False
            return

        if self._track_id and self._track_id == getattr(playback, "track_id", ""):
            return

        self._track_id = str(getattr(playback, "track_id", "") or "")
        self._track_meta = {
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": album_name,
        }
        self._plain_lyrics = ""
        self._synced_lines = []
        self._lyrics_loaded = False
        self._lyrics_source = "none"

        if self._track_id and self._load_cache(self._track_id):
            return

        now = time.monotonic()
        wait_for = self.MIN_FETCH_INTERVAL - (now - self._last_fetch)
        if wait_for > 0:
            time.sleep(wait_for)

        params = parse.urlencode(
            {
                "track_name": track_name,
                "artist_name": artist_name,
                "album_name": album_name,
                "duration": duration_s,
            }
        )
        url = f"{self.API_BASE}?{params}"
        req = request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            method="GET",
        )
        self._last_fetch = time.monotonic()
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, ValueError, OSError):
            self._lyrics_source = "unavailable"
            return

        self._plain_lyrics = str(payload.get("plainLyrics") or "")
        self._synced_lines = self._parse_synced_lyrics(payload.get("syncedLyrics") or "")
        self._lyrics_source = "lrclib"
        self._lyrics_loaded = bool(self._plain_lyrics or self._synced_lines)
        if self._track_id and self._lyrics_loaded:
            self._save_cache(self._track_id)

    @staticmethod
    def _best_sequence_match(transcript_tokens: list[str], lyric_text: str) -> float:
        if not transcript_tokens or not lyric_text:
            return 0.0
        lyric_tokens = SpotifyLyricMatcher._tokens(lyric_text)
        if not lyric_tokens:
            return 0.0
        joined_t = " ".join(transcript_tokens)
        best = 0.0
        # Sliding windows around transcript length; capped for efficiency.
        target = len(transcript_tokens)
        for window_len in range(max(3, target - 5), min(len(lyric_tokens), target + 8) + 1):
            step = max(1, window_len // 3)
            for i in range(0, len(lyric_tokens) - window_len + 1, step):
                candidate = " ".join(lyric_tokens[i:i + window_len])
                score = max(
                    ratio(joined_t, candidate) / 100.0,
                    WRatio(joined_t, candidate) / 100.0,
                )
                if score > best:
                    best = score
                if best >= 0.98:
                    return best
        return best

    @staticmethod
    def _token_overlap(transcript_tokens: list[str], lyric_text: str) -> float:
        lyric_tokens = set(SpotifyLyricMatcher._tokens(lyric_text))
        speech_tokens = set(transcript_tokens)
        if not speech_tokens or not lyric_tokens:
            return 0.0
        meaningful = {t for t in speech_tokens if len(t) > 2}
        if not meaningful:
            meaningful = speech_tokens
        return len(meaningful & lyric_tokens) / max(1, len(meaningful))

    @staticmethod
    def _phrase_overlap(transcript: str, lyric_text: str) -> float:
        t = SpotifyLyricMatcher._norm(transcript)
        l = SpotifyLyricMatcher._norm(lyric_text)
        if not t or not l:
            return 0.0
        t_words = t.split()
        if len(t_words) < 3:
            return 0.0
        ngrams = [" ".join(t_words[i:i + 3]) for i in range(len(t_words) - 2)]
        hits = sum(1 for ng in ngrams if ng in l)
        return hits / max(1, len(ngrams))

    def _synced_window(self, start_s: float, end_s: float) -> tuple[str, float]:
        if not self._synced_lines:
            return "", 0.0
        pad = 4.0
        lo = max(0.0, start_s - pad)
        hi = end_s + pad
        selected = [text for ts, text in self._synced_lines if lo <= ts <= hi]
        if not selected:
            nearest = sorted(self._synced_lines, key=lambda item: min(abs(item[0] - start_s), abs(item[0] - end_s)))[:6]
            selected = [text for _, text in nearest]
        return " ".join(selected), 1.0 if selected else 0.0

    def get_evidence(self, transcript: str, capture_duration: float) -> dict[str, Any]:
        """Return lyric evidence without exposing lyric text."""
        base = {
            "available": False,
            "is_playing": False,
            "track_id": "",
            "track_name": "",
            "artist_name": "",
            "lyric_match": 0.0,
            "time_alignment": 0.0,
            "phrase_match": 0.0,
            "token_match": 0.0,
            "full_track_match": 0.0,
            "source": "none",
            "reason": "no_playback",
        }
        if not transcript:
            return base
        try:
            now = time.monotonic()
            if self._last_playback is None or now - self._last_playback_poll >= self.poll_interval:
                self._last_playback = self.spotify_context.get_current_playback()
                self._last_playback_poll = now
            playback = self._last_playback
        except Exception:
            return {**base, "reason": "spotify_unavailable"}

        if playback is None or not bool(getattr(playback, "is_playing", False)):
            return {**base, "reason": "not_playing"}

        base.update({
            "available": True,
            "is_playing": True,
            "track_id": str(getattr(playback, "track_id", "") or ""),
            "track_name": str(getattr(playback, "track_name", "") or ""),
            "artist_name": (tuple(getattr(playback, "artist_names", ()) or ()) or ("",))[0],
        })

        self._fetch_lyrics(playback)
        if not self._lyrics_loaded:
            return {**base, "reason": "lyrics_unavailable"}

        progress_s = float(getattr(playback, "progress_ms", 0) or 0) / 1000.0
        capture = max(0.7, float(capture_duration or 0.0))
        start_s = max(0.0, progress_s - capture)
        window_text, aligned = self._synced_window(start_s, progress_s) if self._synced_lines else (self._plain_lyrics, 0.35)

        tokens = self._tokens(transcript)
        token_match = self._token_overlap(tokens, window_text)
        phrase_match = self._phrase_overlap(transcript, window_text)
        sequence_match = self._best_sequence_match(tokens, window_text)
        full_match = self._best_sequence_match(tokens, self._plain_lyrics) if self._plain_lyrics else sequence_match

        lyric_match = max(
            0.55 * sequence_match + 0.25 * token_match + 0.20 * phrase_match,
            0.50 * full_match + 0.30 * token_match + 0.20 * phrase_match,
        )

        # A genuine time-aligned lyric match is much stronger than a coincidental
        # phrase match somewhere else in the song.
        if self._synced_lines:
            lyric_match *= 0.72 + 0.28 * aligned

        return {
            **base,
            "lyric_match": round(max(0.0, min(1.0, lyric_match)), 3),
            "time_alignment": round(float(aligned), 3),
            "phrase_match": round(float(phrase_match), 3),
            "token_match": round(float(token_match), 3),
            "full_track_match": round(float(full_match), 3),
            "source": self._lyrics_source,
            "reason": "lyrics_match" if lyric_match >= 0.55 else "weak_match",
        }
