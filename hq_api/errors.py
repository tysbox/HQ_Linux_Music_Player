"""hq_api 統一エラーハンドリング（ADR-005: Phase 3a-5 Task 3）.

全てのエラーを以下の形式に統一:
{
  "error": {
    "code": "MPD_OFFLINE",
    "message": "MPD サーバーに接続できません",
    "details": { ... }   # オプション
  }
}

注:
- 既存 DSP/DMP 側のエンドポイントは旧形式を維持
- hq_api 側のみで新形式を返す
- HTTP ステータスコードは変えない（後方互換）
"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class HQError(HTTPException):
    """hq_api 統一エラー."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict | None = None,
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details or {},
            },
        )


def mpd_offline(detail: str = "MPD サーバーに接続できません") -> HQError:
    """MPD 切断エラー (HTTP 503)."""
    return HQError("MPD_OFFLINE", detail, status_code=503)


def dsp_offline(detail: str = "CamillaDSP が起動していません") -> HQError:
    """DSP 切断エラー (HTTP 503)."""
    return HQError("DSP_OFFLINE", detail, status_code=503)


def resource_not_found(detail: str = "リソースが見つかりません") -> HQError:
    """リソース不在 (HTTP 404)."""
    return HQError("RESOURCE_NOT_FOUND", detail, status_code=404)


def validation_error(detail: str = "リクエストが不正です") -> HQError:
    """バリデーションエラー (HTTP 422)."""
    return HQError("VALIDATION_ERROR", detail, status_code=422)


def internal_error(detail: str = "内部エラーが発生しました") -> HQError:
    """内部エラー (HTTP 500)."""
    return HQError("INTERNAL_ERROR", detail, status_code=500)


async def safe_mpd_call(coro, error_message: str = "MPD 操作に失敗しました"):
    """MPD 関連コルーチンを安全実行.

    ConnectionError は mpd_offline() に変換。
    その他は internal_error() に変換。
    """
    try:
        return await coro
    except ConnectionError as e:
        raise mpd_offline(f"{error_message}: {e}") from e
    except Exception as e:
        raise internal_error(f"{error_message}: {e}") from e


def install_error_handlers(app):
    """FastAPI アプリに統一エラーハンドラを登録."""

    @app.exception_handler(HQError)
    async def hq_error_handler(request: Request, exc: HQError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        # FastAPI の標準 HTTPException を統一形式に変換
        # detail が dict 形式（HQError.detail 由来）の場合はそのまま包む
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                    "details": {},
                }
            },
        )
