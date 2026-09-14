"""DSP YAML 生成モジュール（D-2 分離）.

backend/main.py から generate_camilladsp_yaml() とその依存関数・定数を移植。
CamillaDSP 4.1.3 対応 YAML を生成する純粋関数群。
FastAPI 等の Web フレームワーク非依存（純粋ロジック）。
"""

import os
import re
import shutil
import subprocess
import time
import wave
import yaml

# ─────────────────────────────────────────────────────────────────────────────
# 定数定義（backend/main.py から移植）
# ─────────────────────────────────────────────────────────────────────────────
MUSIC_EQ = {
    "none": [],
    "jazz": [{"freq": 80, "q": 0.9, "gain": 2.5}, {"freq": 300, "q": 1.0, "gain": 1.0}, {"freq": 7000, "q": 0.8, "gain": 0.7}],
    "classical": [{"freq": 60, "q": 0.7, "gain": 1.0}, {"freq": 400, "q": 0.9, "gain": -0.5}, {"freq": 8000, "q": 0.8, "gain": 1.0}],
    "electronic": [{"freq": 50, "q": 0.8, "gain": 4.0}, {"freq": 400, "q": 1.2, "gain": -2.0}, {"freq": 10000, "q": 0.9, "gain": 2.5}],
    "vocal": [{"freq": 150, "q": 1.0, "gain": -1.0}, {"freq": 1000, "q": 0.8, "gain": 3.0}, {"freq": 3000, "q": 0.9, "gain": 2.0}],
}

OUTPUT_EQ = {
    "none": [],
    "studio-monitors": [{"freq": 80, "q": 0.8, "gain": 3.0}, {"freq": 2500, "q": 1.0, "gain": -0.8}, {"freq": 20000, "q": 1.0, "gain": 3.0}],
    "JBL-Speakers": [{"freq": 70, "q": 0.7, "gain": 3.0}, {"freq": 1200, "q": 1.0, "gain": -2.0}, {"freq": 13000, "q": 0.8, "gain": 5.0}],
    "planar-magnetic": [{"freq": 30, "q": 0.7, "gain": 1.0}, {"freq": 180, "q": 0.9, "gain": -1.0}, {"freq": 15000, "q": 0.8, "gain": 1.0}],
    "loud-speaker": [{"freq": 70, "q": 0.7, "gain": 4.0}, {"freq": 300, "q": 1.0, "gain": 1.0}, {"freq": 8000, "q": 0.7, "gain": 4.0}, {"freq": 16000, "q": 0.9, "gain": 2.5}],
    "Tube-Warmth": [{"freq": 200, "q": 0.8, "gain": 2.5}, {"freq": 4000, "q": 1.0, "gain": -1.5}, {"freq": 10000, "q": 0.8, "gain": -2.0}],
    "Crystal-Clarity": [{"freq": 100, "q": 1.2, "gain": -2.0}, {"freq": 8000, "q": 0.7, "gain": 4.0}, {"freq": 16000, "q": 0.9, "gain": 2.5}],
}


# ─────────────────────────────────────────────────────────────────────────────
# 内部ヘルパー関数（backend/main.py から移植）
# ─────────────────────────────────────────────────────────────────────────────
def _detect_alsa_cards() -> tuple[str | None, str | None]:
    """aplay -l を解析して (usb_card, pch_card) のカード番号を返す。"""
    usb_card = None
    pch_card = None
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, env=env)
        for line in res.stdout.splitlines():
            line_up = line.upper()
            m = re.search(r'(?:card|カード)\s+(\d+)', line, re.IGNORECASE)
            if not m:
                continue
            card_num = m.group(1)
            if "USB" in line_up and usb_card is None:
                usb_card = card_num
            if pch_card is None:
                if ("PCH" in line_up or ("HDA" in line_up and "HDMI" not in line_up) or "CS4208" in line_up):
                    pch_card = card_num
    except Exception:
        pass
    return usb_card, pch_card


def _extract_alsa_card_number(device_id: str) -> str | None:
    """Extract ALSA card number from device ids like plughw:2,0 / hw:2,0."""
    if not device_id:
        return None
    m = re.search(r"(?:^|:)(?:plughw|hw):(\d+),\d+", device_id, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _ensure_ir_192k(ir_path: str, target_rate: int = 192000) -> str:
    """IR ファイルが target_rate でなければ SoX で変換してキャッシュに保存し、キャッシュパスを返す。

    - 192kHz 済みなら即リターン（ゼロコスト）
    - 変換済みキャッシュがあればそれを返す
    - SoX があれば自動変換してキャッシュに保存
    - SoX がなければ手動変換コマンドを示して RuntimeError
    """
    try:
        with wave.open(ir_path, "r") as wf:
            rate = wf.getframerate()
    except Exception:
        return ir_path  # ヘッダが読めない場合は元のパスを返す（CamillaDSP に任せる）

    if rate == target_rate:
        return ir_path  # 既に目標レート

    # キャッシュディレクトリ
    cache_dir = os.path.expanduser("~/.cache/audiophile/ir")
    os.makedirs(cache_dir, exist_ok=True)

    # キャッシュファイル名（元ファイル名 + ターゲットレート）
    basename = os.path.basename(ir_path)
    name, ext = os.path.splitext(basename)
    cache_path = os.path.join(cache_dir, f"{name}_{target_rate}{ext}")

    # キャッシュが存在し、元ファイルより新しければキャッシュを返す
    if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= os.path.getmtime(ir_path):
        return cache_path

    # 変換が必要
    if not shutil.which("sox"):
        raise RuntimeError(
            f"IR ファイル {ir_path} は {rate}Hz です（{target_rate}Hz 必要）。\n"
            f"一度だけ以下を実行してください:\n"
            f"  sox '{ir_path}' -r {target_rate} '{cache_path}'"
        )

    tmp = cache_path + "._converting.wav"
    try:
        subprocess.run(["sox", ir_path, "-r", str(target_rate), tmp],
                       check=True, capture_output=True)
        os.replace(tmp, cache_path)  # アトミックにキャッシュ保存
        return cache_path
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"IR 変換失敗 ({rate}Hz → {target_rate}Hz): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# メイン関数: generate_camilladsp_yaml
# ─────────────────────────────────────────────────────────────────────────────
def generate_camilladsp_yaml(config) -> str:
    """AudioConfig から CamillaDSP 4.1.3 互換 YAML を生成し、ファイルパスを返す。

    Args:
        config: AudioConfig (Pydantic モデル) または同等の属性を持つオブジェクト
            必須属性: mode, device, volume, music_type, eq_output,
                     crossfeed, crossfeed_intensity, hum_noise, reverb, reverb_intensity

    Returns:
        生成された YAML ファイルのパス (通常: /tmp/camilladsp/active_dsp.yml)
    """
    is_bt = "bluealsa" in config.device
    usb_card, _ = _detect_alsa_cards()
    selected_card = _extract_alsa_card_number(config.device)
    is_usb = bool(usb_card and selected_card and selected_card == usb_card)

    samplerate = 192000
    pb_format = "S16_LE" if (is_usb or is_bt) else "S32_LE"
    cap_format = "S32_LE"

    pb_device = config.device.replace("hw:", "plughw:") if config.device.startswith("hw:") else config.device

    devices_block = {
        "samplerate": samplerate,
        "enable_rate_adjust": True,
        "chunksize": 4096,
        "capture": {"type": "Alsa", "channels": 2, "device": "hw:Loopback,1,0", "format": cap_format},
        "playback": {"type": "Alsa", "channels": 2, "device": pb_device, "format": pb_format},
    }
    capture_samplerate = 192000
    if capture_samplerate != samplerate:
        devices_block["capture_samplerate"] = capture_samplerate
        devices_block["resampler"] = {"type": "AsyncPoly", "interpolation": "Cubic"}

    y = {"devices": devices_block, "filters": {}, "pipeline": [], "mixers": {}}

    # Determine if we need parallel DRY/WET paths (reverb enabled)
    has_reverb = config.reverb != "none" and config.reverb_intensity > 0

    # ─────────────────────────────────────────────────────────────────────
    # MIXER: Split input to DRY (ch 0-1) and WET (ch 2-3) if reverb enabled
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        y["mixers"]["split"] = {
            "channels": {"in": 2, "out": 4},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},  # DRY L: UNCHANGED - preserve signal quality
                {"dest": 1, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},  # DRY R: UNCHANGED
                {"dest": 2, "sources": [{"channel": 0, "gain": 0.0, "inverted": False}]},  # WET L input: full level to Conv
                {"dest": 3, "sources": [{"channel": 1, "gain": 0.0, "inverted": False}]},  # WET R input: full level to Conv
            ],
        }
        y["pipeline"].append({"type": "Mixer", "name": "split"})

    # ─────────────────────────────────────────────────────────────────────
    # FILTER: Main DRY path (ch 0-1) or monolithic path (no reverb)
    # ─────────────────────────────────────────────────────────────────────
    filt_dry = {"type": "Filter", "channels": [0, 1] if has_reverb else [0, 1], "names": []}

    def add_f_dry(n, d):
        y["filters"][n] = d
        filt_dry["names"].append(n)

    if config.hum_noise in ["50hz", "60hz"] and config.hum_noise != "none":
        add_f_dry("rumble_cut", {"type": "Biquad", "parameters": {"type": "HighpassFO", "freq": 15}})
        freq = 50 if config.hum_noise == "50hz" else 60
        add_f_dry("hum", {"type": "Biquad", "parameters": {"type": "Notch", "freq": freq, "q": 30.0}})

    for i, eq in enumerate(MUSIC_EQ.get(config.music_type, [])):
        add_f_dry(f"m_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})
    for i, eq in enumerate(OUTPUT_EQ.get(config.eq_output, [])):
        add_f_dry(f"o_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq["freq"], "q": eq["q"], "gain": eq["gain"]}})

    # Headroom protection on DRY path - only when NOT using reverb (no parallel processing)
    # When reverb is on, DRY goes through split mixer and headroom is applied AFTER mixing
    if not has_reverb:
        headroom_db = -4.0
        if config.music_type != "none" or config.eq_output != "none":
            add_f_dry("headroom", {"type": "Gain", "parameters": {"gain": headroom_db, "inverted": False, "mute": False}})

    if filt_dry["names"]:
        y["pipeline"].append(filt_dry)

    # ─────────────────────────────────────────────────────────────────────
    # FILTER: WET path (ch 2-3) - Conv + WET gain
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        src_ir = os.path.expanduser(f"~/.config/camilladsp/ir/{config.reverb}.wav")
        try:
            if not os.path.exists(src_ir):
                raise FileNotFoundError(f"IR source missing: {src_ir}")

            # WET path filters: Conv + Gain (on channels 2-3)
            filt_wet = {"type": "Filter", "channels": [2, 3], "names": []}

            def add_f_wet(n, d):
                y["filters"][n] = d
                filt_wet["names"].append(n)

            # IR を 192kHz に変換（既に 192kHz なら即リターン、キャッシュパスを返す）
            cache_ir = _ensure_ir_192k(src_ir, target_rate=192000)

            # Conv: 192kHz に変換済みの IR を直接参照
            add_f_wet("rev", {"type": "Conv", "parameters": {
                "type": "Wav",
                "filename": cache_ir,
            }})

            # WET gain: VERY conservative to avoid clipping when mixed with full-level DRY
            # intensity=50 -> -44dB (extremely subtle), intensity=100 -> -32dB (very subtle)
            wet_gain_db = round(-50.0 + (config.reverb_intensity / 100.0) * 18.0, 1)
            add_f_wet("rev_out", {"type": "Gain", "parameters": {"gain": wet_gain_db, "inverted": False, "mute": False}})

            y["pipeline"].append(filt_wet)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                with open("/tmp/hq_api_apply.log", "a") as lof:
                    lof.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to process IR {config.reverb}: {str(e)}\n")
                    lof.write(tb + "\n")
            except Exception:
                pass
            # ④ Fallback: エラー時に split/mix Mixer が残らないよう、
            # pipeline から split Mixer と後続の mix Mixer を除去してから reverb を無効化
            y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Mixer" and p.get("name") in ("split", "mix"))]
            y["mixers"].pop("split", None)
            y["mixers"].pop("mix", None)
            config.reverb = "none"
            print(f"Ambience error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # CROSSFEED mixer (before splitting, so applies to all signals)
    # ─────────────────────────────────────────────────────────────────────
    if config.crossfeed != "none":
        intensity = config.crossfeed_intensity
        intensity_pct = max(0.01, min(1.0, intensity / 100.0))
        if config.crossfeed == "light":
            cf_gain_cross = round(-20 + 6 * intensity_pct, 1)
            cf_gain_direct = round(-1.5 * (1 - intensity_pct), 1)
        else:
            cf_gain_cross = round(-20 + 10.5 * intensity_pct, 1)
            cf_gain_direct = round(-3.5 * (1 - intensity_pct), 1)

        y["mixers"]["cf"] = {
            "channels": {"in": 2, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": cf_gain_direct, "inverted": False}, {"channel": 1, "gain": cf_gain_cross, "inverted": False}]},
                {"dest": 1, "sources": [{"channel": 1, "gain": cf_gain_direct, "inverted": False}, {"channel": 0, "gain": cf_gain_cross, "inverted": False}]},
            ],
        }
        y["pipeline"].insert(0, {"type": "Mixer", "name": "cf"})

    # ─────────────────────────────────────────────────────────────────────
    # MIXER: Recombine DRY (ch 0-1) + WET (ch 2-3) back to output (ch 0-1)
    # ─────────────────────────────────────────────────────────────────────
    if has_reverb:
        y["mixers"]["mix"] = {
            "channels": {"in": 4, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [
                    {"channel": 0, "gain": 0.0, "inverted": False},  # DRY L
                    {"channel": 2, "gain": 0.0, "inverted": False},  # WET L
                ]},
                {"dest": 1, "sources": [
                    {"channel": 1, "gain": 0.0, "inverted": False},  # DRY R
                    {"channel": 3, "gain": 0.0, "inverted": False},  # WET R
                ]},
            ],
        }
        y["pipeline"].append({"type": "Mixer", "name": "mix"})

        # Final headroom after mixing DRY + WET to prevent clipping
        y["filters"]["final_headroom"] = {
            "type": "Gain",
            "parameters": {"gain": -3.0, "inverted": False, "mute": False}
        }
        y["pipeline"].append({
            "type": "Filter",
            "channels": [0, 1],
            "names": ["final_headroom"]
        })

    # Remove empty pipelines
    y["pipeline"] = [p for p in y["pipeline"] if not (p.get("type") == "Filter" and len(p.get("names", [])) == 0)]

    # Fallback: ensure at least dummy filter
    if not y["pipeline"]:
        y["filters"]["dummy"] = {"type": "Gain", "parameters": {"gain": 0.0, "inverted": False, "mute": False}}
        y["pipeline"] = [{"type": "Filter", "channels": [0, 1], "names": ["dummy"]}]

    os.makedirs("/tmp/camilladsp", exist_ok=True)
    with open("/tmp/camilladsp/active_dsp.yml", "w") as f:
        yaml.dump(y, f, sort_keys=False)
    return "/tmp/camilladsp/active_dsp.yml"
