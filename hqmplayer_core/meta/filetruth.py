"""ファイル真理 (File Truth) — ffprobe によるファイル原本の解析 (決定 D-7).

MPD の `audio: "44100:16:2"` はデコード後の値であり、ファイル原本の値ではない:
- DSD64 (.dsf) は DoP 変換後の PCM 表記になる (ネイティブ解像度が見えない)
- MP3 320kbps は「44.1kHz/16bit」になる (ビット深度は本来無意味で、
  ビットレートこそが真理)
- 拡張子からの推測 (GUI sigCodec) は偽装・誤命名ファイルで嘘をつく

ffprobe はコンテナ・ストリームを実際に解析するため、これらを解決する
(計画書 §3-D「ファイル真理 (Bisen 超え)」)。

設計 (R-11 対策):
- ffmpeg CLI 未導入環境では available=False を返し、呼び出し側は当該表示を
  自動省略する (他機能への影響ゼロ)。
- 解析結果はファイルパス + mtime のハッシュで永続キャッシュ
  (同一ファイルの再解析を回避 — ffprobe 起動は ~50ms かかる)。
- UPnP (http://) はローカルファイルでないため対象外 (None)。
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# MPD music_directory (mpd.conf の値。環境差異は env で上書き可)
MUSIC_DIR = os.getenv("MPD_MUSIC_DIR", "/var/lib/mpd/music")

_CACHE_DIR = Path(os.path.expanduser("~/.cache/audiophile/filetruth"))
_PROBE_TIMEOUT = 10.0


def ffprobe_available() -> bool:
    """ffprobe CLI が導入済みか (未導入なら機能全体を静かに無効化)."""
    return shutil.which("ffprobe") is not None


def _resolve_local_path(uri: str) -> Optional[str]:
    """MPD の file URI → ローカル絶対パス。

    MPD は music_directory 相対パスを返すため結合する。
    http(s):// (UPnP) は対象外。絶対パスで存在するものはそのまま。
    """
    if not uri or uri.startswith(("http://", "https://")):
        return None
    if os.path.isabs(uri):
        return uri if os.path.exists(uri) else None
    full = os.path.join(MUSIC_DIR, uri)
    return full if os.path.exists(full) else None


def _cache_path(abs_path: str) -> Path:
    """キャッシュファイルパス (abs_path の sha256)。"""
    key = hashlib.sha256(abs_path.encode()).hexdigest()[:24]
    return _CACHE_DIR / f"{key}.json"


def _load_cache(abs_path: str) -> Optional[dict]:
    """キャッシュ読み込み (mtime 一致時のみ有効)。"""
    cp = _cache_path(abs_path)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text())
        if data.get("_mtime") == os.path.getmtime(abs_path):
            return data
    except Exception:
        pass
    return None


def _save_cache(abs_path: str, data: dict) -> None:
    """キャッシュ保存 (ベストエフォート — 失敗は握り潰す)。"""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data["_mtime"] = os.path.getmtime(abs_path)
        tmp = _CACHE_DIR / f"{cp.name}.tmp" if (cp := _cache_path(abs_path)) else None
        if tmp is None:
            return
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(tmp, cp)
    except Exception:
        logger.debug("filetruth cache write failed", exc_info=True)


def _run_ffprobe(abs_path: str) -> Optional[dict]:
    """ffprobe -show_format -show_streams を実行して最初の音声ストリームを抽出。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-select_streams", "a:0",
        "-of", "json", abs_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=_PROBE_TIMEOUT)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def _parse_probe(probe: dict) -> dict:
    """ffprobe JSON → ファイル真理 dict (GUI 表示用の正規化)。"""
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    codec = stream.get("codec_name", "") or fmt.get("format_name", "")
    # DSD 判定: .dsf/.dff は codec が dsd で返る。コンテナ名でも判定
    is_dsd = codec == "dsd" or "dsf" in (fmt.get("format_name") or "") \
        or "dff" in (fmt.get("format_name") or "")

    sample_rate = stream.get("sample_rate")
    bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")
    bit_rate = stream.get("bit_rate") or fmt.get("bit_rate")
    channels = stream.get("channels")

    out = {
        "codec": codec,
        "codec_long": stream.get("codec_long_name", ""),
        "container": fmt.get("format_name", ""),
        "is_dsd": is_dsd,
        "sample_rate_hz": int(sample_rate) if sample_rate else None,
        "bits": int(bits) if bits else None,
        "bit_rate": int(bit_rate) if bit_rate else None,
        "channels": int(channels) if channels else None,
        "duration_s": float(fmt.get("duration", 0) or 0) or None,
        "tags": {
            k.lower(): v for k, v in (fmt.get("tags") or {}).items()
            if k.upper() in ("ENCODER", "LANGUAGE", "TITLE", "ARTIST", "ALBUM")
        },
    }
    return out


def probe_file(uri: str) -> Optional[dict]:
    """MPD file URI → ファイル真理 dict。

    Returns:
        解析結果 dict。以下の場合は None (呼び出し側は表示省略):
        - ffprobe 未導入 (R-11: 機能欠落ではなく静かな省略)
        - UPnP (http) / ファイル不在 / 解析失敗
    """
    if not ffprobe_available():
        return None
    abs_path = _resolve_local_path(uri)
    if abs_path is None:
        return None

    cached = _load_cache(abs_path)
    if cached is not None:
        return cached

    probe = _run_ffprobe(abs_path)
    if probe is None:
        return None
    data = _parse_probe(probe)
    _save_cache(abs_path, data)
    return data


def format_file_truth(truth: Optional[dict]) -> str:
    """ファイル真理 dict → GUI 表示文字列 (1 行サマリ)。

    例:
      "FLAC 96.0kHz / 24-bit"
      "DSD64 2.8MHz / 1-bit"
      "MP3 320 kbps"
    """
    if not truth:
        return ""
    codec = (truth.get("codec") or "").upper()
    if truth.get("is_dsd"):
        sr = truth.get("sample_rate_hz") or 0
        # DSD レート表記: 2.8224MHz = DSD64, 5.6448MHz = DSD128
        dsd_name = "DSD64" if sr <= 3_000_000 else (
            "DSD128" if sr <= 6_000_000 else "DSD")
        return f"{dsd_name} {sr/1_000_000:.2f}MHz / 1-bit"
    br = truth.get("bit_rate")
    if codec in ("MP3", "AAC", "OGG", "OPUS", "WMA") and br:
        return f"{codec} {br//1000} kbps"
    sr = truth.get("sample_rate_hz")
    bits = truth.get("bits")
    if sr and bits:
        sr_s = f"{sr/1000:.1f}kHz".replace(".0kHz", "kHz")
        return f"{codec} {sr_s} / {bits}-bit"
    if sr:
        return f"{codec} {sr/1000:.1f}kHz"
    return codec or ""
