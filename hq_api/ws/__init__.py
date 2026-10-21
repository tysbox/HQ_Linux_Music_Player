"""hq_api WebSocket ルータ (Phase X-2).

DSP の /ws/now_playing と DMP の /ws/status を hq_api に移植。
ADR-003 に基づき、/ws/all で統合 push も提供する。

エンドポイント:
- /ws/now_playing: DSP 互換 (2 秒 polling)
- /ws/status:      DMP 互換 (idle() イベント駆動)
- /ws/all:         統合 push (DSP+DMP を1接続で受信)
"""
