"""MPD クライアント実装（Phase 1a で実装予定）.

Phase 0 では docstring のみ。中身は Phase 1a で
dmp/backend/app/services/mpd_service.py から移植する。

設計方針:
  - プロセス全体で 1 本の非同期接続を保持する
  - asyncio.Lock で多重呼び出しを防ぐ（python-mpd2 は async セーフではない）
  - 接続断時は ping() 失敗をトリガに自動再接続する
  - 環境変数 MPD_HOST / MPD_PORT で接続先を上書き可能
"""