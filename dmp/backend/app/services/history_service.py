import json
import logging
from datetime import datetime
from pathlib import Path
from app.models.track import Track, HistoryEntry

logger = logging.getLogger(__name__)

HISTORY_FILE = Path.home() / ".config" / "audiophile-dmp" / "history.json"
MAX_HISTORY = 500  # 最大保持件数


def _ensure_dir():
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_history() -> list[HistoryEntry]:
    _ensure_dir()
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return [HistoryEntry(**entry) for entry in data]
    except Exception as e:
        logger.error(f"履歴読み込みエラー: {e}")
        return []


def save_history(entries: list[HistoryEntry]):
    _ensure_dir()
    try:
        data = [entry.model_dump(mode="json") for entry in entries]
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"履歴保存エラー: {e}")


def add_to_history(track: Track):
    entries = load_history()
    # 直前と同じ曲の連続追加を防ぐ
    if entries and entries[0].track.uri == track.uri:
        return
    entry = HistoryEntry(track=track, played_at=datetime.now())
    entries.insert(0, entry)
    # 上限を超えたら古いものを削除
    entries = entries[:MAX_HISTORY]
    save_history(entries)


def clear_history():
    save_history([])
