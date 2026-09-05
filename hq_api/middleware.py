"""hq_api リクエスト計測ミドルウェア (Phase X-4).

全リクエストのレイテンシ・ステータスコードを記録し、
/health/metrics で集計結果を公開する。
"""
import logging
import time

from fastapi import Request

from hq_api.metrics import get_metrics

logger = logging.getLogger(__name__)


async def metrics_middleware(request: Request, call_next):
    """リクエスト処理時間を計測して記録."""
    start = time.monotonic()
    status_code = 500  # デフォルト（例外時の値）
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        # 例外時は 500 として記録
        raise
    finally:
        latency_ms = (time.monotonic() - start) * 1000
        get_metrics().record(
            path=request.url.path,
            latency_ms=latency_ms,
            status_code=status_code,
        )
        # 遅いリクエスト・5xx をログ
        if latency_ms > 1000 or status_code >= 500:
            logger.warning(
                "slow_request path=%s latency=%.1fms status=%d",
                request.url.path, latency_ms, status_code,
            )
