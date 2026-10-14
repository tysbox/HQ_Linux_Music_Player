"""bisen-dspd 制御クライアント + 経路オーケストレーション (Phase 3 Step 3-5/3-6).

bisen-dspd (dmp/bisen-dspd/) は Bisen C++ DSP (Tube / Restore / TruePeakLimiter)
を移植した ALSA デーモン。CamillaDSP の後段に位置する:

    MPD → hw:Loopback,0,0 → CamillaDSP (EQ/IR/crossfeed/キャリブ)
        → hw:Loopback,0,1 → [capture hw:Loopback,1,1] bisen-dspd → DAC

設計原則 (計画書 §9-8):
- デーモンは standby (routing=0) だと ALSA デバイスを一切開かないため
  既存の CamillaDSP 直結構成に無影響。
- デーモン停止時・非応答時は YAML を直結のままにする (無音化フォールバック)。
- Web フレームワーク非依存 (Unix socket のみ。FastAPI 非依存)。

経路切替順序 (呼び出し側は ensure_route_* をこの順で使う):
- ON : begin_routing(output_device) → YAML 再生成 (playback=hw:Loopback,0,1)
       → CDSP ホットリロード (DAC を解放) → wait_routing_active (DAC を掴む)
       → push_params (tube/restore を送る)
- OFF: end_routing (DAC を解放) → YAML 再生成 (直結) → CDSP ホットリロード
"""
import logging
import os
import socket
import time

logger = logging.getLogger(__name__)

DAEMON_SOCKET = os.getenv("BISEN_DPD_SOCKET", "/run/bisen-dspd/control.sock")
_LOOPBACK_PLAYBACK = "hw:Loopback,0,1"   # CDSP → デーモン間 (sub1)
_CMD_TIMEOUT = 1.5


def _cmd(line: str, timeout: float = _CMD_TIMEOUT):
    """デーモンへ 1 コマンド送信。応答テキストを返す (未接続は None)。"""
    s = None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(DAEMON_SOCKET)
        s.sendall((line + "\n").encode())
        resp = s.recv(4096).decode().strip()
        return resp
    except Exception:
        return None
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def _parse_params(resp: str):
    """get params 応答 "key=val ..." を dict に。"""
    out = {}
    for tok in resp.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def is_daemon_alive() -> bool:
    """デーモン起動確認 (ping)。ソケット無し・非応答は False。"""
    return _cmd("ping") == "pong"


def daemon_status() -> dict:
    """get params を dict で返す (未接続は {})。"""
    resp = _cmd("get params")
    return _parse_params(resp) if resp and resp != "ERROR" else {}


def routing_requested(cfg: dict) -> bool:
    """設定がデーモン経路を要求するか (tube / restore のいずれか有効)。"""
    tube = cfg.get("tube") or "none"
    restore = cfg.get("restore") or "none"
    return tube != "none" or restore != "none"


def routing_active(cfg: dict) -> bool:
    """経路要求 かつ デーモン稼働中 かつ BT 出力でない (YAML 生成の分岐単一ソース)。

    - デーモン非応答なら False → YAML は直結のまま (フォールバック = 無音化防止)。
    - Bluetooth (bluealsa) はデーモンが開けない形式になるため除外 (直結維持)。
    """
    if "bluealsa" in (cfg.get("device") or ""):
        return False
    return routing_requested(cfg) and is_daemon_alive()


def push_params(cfg: dict) -> None:
    """tube / restore 設定をデーモンへ反映 (ベストエフォート・例外なし)。"""
    tube = cfg.get("tube") or "none"
    restore = cfg.get("restore") or "none"
    bias = int(cfg.get("tube_bias") or 50)
    bias = max(0, min(100, bias))
    if tube in ("triode", "pentode"):
        _cmd("set tube_enabled 1")
        _cmd(f"set tube_type {'PENTODE' if tube == 'pentode' else 'TRIODE'}")
        _cmd(f"set tube_bias {bias}")
    else:
        _cmd("set tube_enabled 0")
    if restore in ("lossy_standard", "lossy_high", "cd"):
        _cmd("set restore_enabled 1")
        _cmd(f"set restore_mode {restore}")
    else:
        _cmd("set restore_enabled 0")


def begin_routing(output_device: str, cfg: dict) -> bool:
    """デーモン経路の確保を開始 (routing=1)。

    CDSP がまだ DAC を持っている場合、デーモンは内部リトライで待つ。
    呼び出し側は CDSP リロード後に wait_routing_active() で確保を確認する。
    戻り値: コマンド受理なら True (デーモン停止時は False)。
    """
    if not is_daemon_alive():
        logger.warning("bisen-dspd not running — tube/restore bypassed (fallback: direct)")
        return False
    dev = output_device or "plughw:1,0"
    _cmd(f"set output_device {dev}")
    ok = _cmd("set routing 1") == "OK"
    if not ok:
        logger.warning("bisen-dspd routing request failed")
    return ok


def wait_routing_active(timeout: float = 6.0) -> bool:
    """デーモンが DAC を掴む (playback_open=1) のを待つ。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = daemon_status()
        if st.get("routing") == "1" and st.get("playback_open") == "1":
            return True
        time.sleep(0.1)
    return False


def end_routing(wait: bool = True, timeout: float = 4.0) -> bool:
    """デーモン経路の解放 (routing=0)。

    CDSP が直結 YAML で DAC を取り戻す前に必ず呼ぶ (所有権競合防止)。
    """
    if not is_daemon_alive():
        return True  # デーモン停止なら解放不要
    _cmd("set routing 0")
    if not wait:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = daemon_status()
        if st.get("routing") == "0" and st.get("playback_open") == "0":
            return True
        time.sleep(0.1)
    return False


def reconcile_boot() -> None:
    """hq-api 起動時の整合 (ブートギャップ対策)。

    前回 tube/restore 有効のまま再起動した場合、camilladsp は
    playback=hw:Loopback,0,1 の YAML で起動するが、誰も routing=1 を
    送らないと sub1 を読む者がいない (= 無音)。hq-api 起動時に
    last_config を確認してデーモン経路を復元する。
    """
    try:
        from backend.dsp.state_manager import load_last_config
        cfg = load_last_config()
    except Exception:
        return
    if not isinstance(cfg, dict) or not routing_active(cfg):
        return
    dev = cfg.get("device") or "plughw:1,0"
    if begin_routing(dev, cfg):
        wait_routing_active(timeout=8.0)
        push_params(cfg)
        logger.info("bisen-dspd reconciled at boot (device=%s, tube=%s, restore=%s)",
                    dev, cfg.get("tube"), cfg.get("restore"))

