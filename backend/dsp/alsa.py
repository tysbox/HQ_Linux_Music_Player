"""ALSA カード検出の単一ソース (Single Source of Truth).

2026-10-03 v3.1: 従来 `backend/dsp/yaml_generator.py` と
`hq_api/routers/dsp.py` に同一ロジックが二重実装されていた
(正規表現・キャッシュ仕様が微妙に異なり、片方だけ直し忘れると
USB/PCH 判定がズレる温床だった) ため、本モジュールに集約した。

仕様 (旧 yaml_generator 実装を基準・両方の長所を統合):
  - `aplay -l` を解析して (usb_card, pch_card) のカード番号 (str) を返す
  - HQ_ALSA_CACHE_TTL (既定 60 秒) で結果をキャッシュし
    ダイヤル毎の subprocess 呼び出しを削減
  - aplay 不在時・実行失敗時は (None, None) (ブロックしない)
  - subprocess には timeout=5 と LC_ALL=C を付与 (言語非依染化)
"""

import os
import re
import shutil
import subprocess
import time

# モジュール横断で共有するキャッシュ (プロセス内単一)
_CACHE: tuple[str | None, str | None] | None = None
_CACHE_TS: float = 0.0


def _ttl() -> float:
    try:
        return float(os.getenv("HQ_ALSA_CACHE_TTL", "60"))
    except ValueError:
        return 60.0


def reset_cache() -> None:
    """キャッシュを破棄する (テスト・ホットプラグ検出用)。"""
    global _CACHE, _CACHE_TS
    _CACHE = None
    _CACHE_TS = 0.0


def detect_alsa_cards(force: bool = False) -> tuple[str | None, str | None]:
    """`aplay -l` を解析して (usb_card, pch_card) のカード番号を返す。

    Args:
        force: True でキャッシュを無視して再取得する。

    Returns:
        (usb_card, pch_card): 見つからない要素は None。
        aplay 不在・実行失敗時は (None, None)。
    """
    global _CACHE, _CACHE_TS
    ttl = _ttl()
    now = time.monotonic()
    if not force and _CACHE is not None and (now - _CACHE_TS) < ttl:
        return _CACHE
    if shutil.which("aplay") is None:
        return (None, None)
    usb_card = None
    pch_card = None
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(
            ["aplay", "-l"], capture_output=True, text=True, env=env, timeout=5
        )
        for line in res.stdout.splitlines():
            line_up = line.upper()
            m = re.search(r"(?:card|カード)\s+(\d+)", line, re.IGNORECASE)
            if not m:
                continue
            card_num = m.group(1)
            if "USB" in line_up and usb_card is None:
                usb_card = card_num
            if pch_card is None:
                if "PCH" in line_up or ("HDA" in line_up and "HDMI" not in line_up) or "CS4208" in line_up:
                    pch_card = card_num
    except Exception:
        pass
    _CACHE = (usb_card, pch_card)
    _CACHE_TS = time.monotonic()
    return usb_card, pch_card


def extract_alsa_card_number(device_id: str) -> str | None:
    """`plughw:2,0` / `hw:2,0` 形式からカード番号 (str) を抽出する。"""
    if not device_id:
        return None
    m = re.search(r"(?:^|:)(?:plughw|hw):(\d+),\d+", device_id, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def is_usb_device(device_id: str) -> bool:
    """デバイス ID が USB DAC カードを指すか判定する (見つからなければ False)。"""
    usb_card, _ = detect_alsa_cards()
    selected = extract_alsa_card_number(device_id)
    return bool(usb_card and selected and selected == usb_card)
