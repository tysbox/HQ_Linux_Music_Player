"""_init_vol / _schedule_init_vol の単体テスト (Phase 5-B).

CamillaClient をモックして _init_vol の最小実装 (CamillaDSP への接続 +
main_volume 設定) が正しく動作することを検証する。

Phase 2-A で _init_vol は最小実装に書き換えられた。
- wait_for_restart 引数撤廃
- fade-in シーケンス撤廃
- statefile復元は camilladsp 自身が起動時に実施 (Phase 2-B)

実行:
  PYTHONPATH=/home/tysbox/HQ_Linux_Music_Player ./backend/venv/bin/python3 -m unittest tests.unit.test_init_vol -v
"""
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

_PROJ = "/home/tysbox/HQ_Linux_Music_Player"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

import backend.main as _backend_main  # noqa: E402
from backend.main import _init_vol, _schedule_init_vol  # noqa: E402


class TestInitVolMinimum(unittest.TestCase):
    """_init_vol 最小実装の単体テスト (Phase 2-A)."""

    def test_init_vol_calls_set_main_volume(self):
        """CamillaDSP 接続成功時に main_volume を target 値に設定."""
        with patch.object(_backend_main, "CamillaClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            _init_vol(-7.5)

            mock_client.connect.assert_called_once()
            mock_client.volume.set_main_volume.assert_called_once_with(-7.5)
            mock_client.disconnect.assert_called_once()

    def test_init_vol_retries_on_connection_failure(self):
        """接続失敗時は最大 200 回まで retry (実装不変)."""
        with patch.object(_backend_main, "CamillaClient") as mock_client_cls:
            # 最初の 3 回 connect 失敗、4 回目で成功
            mock_client = MagicMock()
            mock_client_cls.side_effect = [
                ConnectionRefusedError("first"),
                ConnectionRefusedError("second"),
                ConnectionRefusedError("third"),
                mock_client,
            ]

            with patch.object(_backend_main, "time") as mock_time:
                _init_vol(-3.0)

            # 接続試行 4 回 (失敗 3 回 + 成功 1 回)
            self.assertEqual(mock_client_cls.call_count, 4)
            mock_client.volume.set_main_volume.assert_called_once_with(-3.0)

    def test_init_vol_silently_fails_when_always_unreachable(self):
        """接続が永遠に失敗する場合、例外を投げずに終了 (実装不変)."""
        with patch.object(_backend_main, "CamillaClient") as mock_client_cls:
            mock_client_cls.side_effect = ConnectionRefusedError("always")

            with patch.object(_backend_main, "time"):
                # 例外なしで終了するべき
                _init_vol(-3.0)

            # 200 回まで試行
            self.assertEqual(mock_client_cls.call_count, 200)

    def test_schedule_init_vol_runs_in_background(self):
        """_schedule_init_vol はバックグラウンドスレッドで実行."""
        with patch.object(_backend_main, "_init_vol") as mock_init_vol:
            mock_init_vol.return_value = None
            _schedule_init_vol(-5.0)

            # バックグラウンドスレッドで実行されるため少し待つ
            time.sleep(0.1)

            # _init_vol は v のみ引数で呼ばれる (fade_in 引数は削除済み)
            mock_init_vol.assert_called_once_with(-5.0)


if __name__ == "__main__":
    unittest.main()