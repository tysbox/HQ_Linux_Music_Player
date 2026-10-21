"""hq_api メトリクス・健全性ログ (Phase X-4).

リクエスト数・レイテンシ・エラー数の統計を取り、
健全性確認用エンドポイント /health/metrics で公開。

設計:
  - ロックフリーで O(1) 更新
  - 過去 60 秒の統計のみ保持（メモリ効率）
  - プロセス再起動でリセット（永続化なし、軽量優先）
"""
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

logger = logging.getLogger(__name__)

# パスごとの統計: {path: deque[(timestamp, latency_ms, status_code)]}
# 最大 10000 エントリ（古いものから自動削除）
_MAX_ENTRIES_PER_PATH = 1000
_WINDOW_SEC = 300  # 5 分


class Metrics:
    """軽量メトリクスコレクタ."""

    def __init__(self):
        self._stats: Dict[str, Deque[Tuple[float, float, int]]] = defaultdict(
            lambda: deque(maxlen=_MAX_ENTRIES_PER_PATH)
        )
        self._start_time = time.monotonic()
        self._total_requests = 0
        self._total_errors = 0

    def record(self, path: str, latency_ms: float, status_code: int) -> None:
        """リクエスト完了時に呼ぶ."""
        self._total_requests += 1
        if status_code >= 500:
            self._total_errors += 1
        self._stats[path].append((time.monotonic(), latency_ms, status_code))

    def get_path_stats(self, path: str) -> dict:
        """特定パスの統計を返す."""
        now = time.monotonic()
        entries = [
            (ts, lat, code)
            for ts, lat, code in self._stats[path]
            if now - ts < _WINDOW_SEC
        ]
        if not entries:
            return {"path": path, "count": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "error_rate": 0.0}
        latencies = sorted([lat for _, lat, _ in entries])
        n = len(latencies)
        error_count = sum(1 for _, _, code in entries if code >= 500)
        return {
            "path": path,
            "count": n,
            "p50_ms": round(latencies[int(n * 0.50)], 2),
            "p95_ms": round(latencies[int(n * 0.95)], 2),
            "p99_ms": round(latencies[int(n * 0.99)], 2),
            "error_rate": round(error_count / n, 4) if n else 0.0,
        }

    def get_summary(self) -> dict:
        """全パスのサマリ."""
        uptime = time.monotonic() - self._start_time
        paths = sorted(self._stats.keys())
        return {
            "uptime_seconds": round(uptime, 1),
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": round(self._total_errors / self._total_requests, 4)
                if self._total_requests else 0.0,
            "tracked_paths": len(paths),
            "top_paths": [self.get_path_stats(p) for p in paths[:10]],
        }


# グローバルシングルトン
_metrics = Metrics()


def get_metrics() -> Metrics:
    """メトリクスインスタンスを取得."""
    return _metrics
