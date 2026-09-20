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

# Stage 2: 自動ヘッドルーム計算のための解析モジュール
from backend.dsp.analysis import max_gain_of_config, filter_dict_to_response

# Stage 3: プロファイル管理
from backend.dsp.profiles import load_profile, profile_to_biquads


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
# Ambience WET calibration
# ─────────────────────────────────────────────────────────────────────────────
# 各 IR の実測 RMS 差を吸収するためのプリセット別 WET トリム。
# ダウンロード版 Bisen IR（192kHz FLOAT32・単純WAVE化済み）を基準とする。
# Symphony Hall（hall: RMS -57.62dBFS）を 0.0dB の基準とし、
# 他プリセットの Wet ミックス割合が Symphony Hall と等しくなるよう調整する。
# 内容（IR 波形・GUI・intensity カーブ）は変更しない。
REVERB_WET_TRIM_DB = {
    "hall": 0.0,
    "jazz_club": -4.3,
    "large_bottle_hall": 1.3,
    "st_nicolaes_church": 4.3,
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
# ヘルパー: 自動ヘッドルーム計算（Stage 2-5）
# ─────────────────────────────────────────────────────────────────────────────
def _calculate_headroom_db(filters_dict: dict, margin_db: float = 0.5) -> float:
    """
    フィルタ辞書から最大ゲインを計算し、必要なヘッドルーム [dB] を返す。

    Args:
        filters_dict: 生成された filters 辞書
        margin_db: 安全マージン [dB]（デフォルト 0.5dB）

    Returns:
        負の値（ヘッドルーム）。最大ゲインが 0dB 以下なら -margin_db を返す。
    """
    max_gain = max_gain_of_config(filters_dict)
    if max_gain > 0:
        # クリッピングリスクあり: -max_gain - margin で 0dB 以下に抑制
        return round(-(max_gain + margin_db), 1)
    else:
        # 余裕あり: 小さなマージンのみ
        return round(-margin_db, 1)


# ─────────────────────────────────────────────────────────────────────────────
# メイン関数: generate_camilladsp_yaml
# ─────────────────────────────────────────────────────────────────────────────
def generate_camilladsp_yaml(config, out_path: str | None = None) -> str:
    """AudioConfig から CamillaDSP 4.1.3 互換 YAML を生成し、ファイルパスを返す。

    Args:
        config: AudioConfig (Pydantic モデル) または同等の属性を持つオブジェクト
            必須属性: mode, device, volume, music_type, eq_output,
                     crossfeed, crossfeed_intensity, hum_noise, reverb, reverb_intensity
        out_path: 出力先パス。None の場合は従来の固定パス `/tmp/camilladsp/active_dsp.yml`

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

    # ─────────────────────────────────────────────────────────────────────
    # Stage 6: 聴感比較基盤 - ティルト EQ、バランス、独立 EQ、ラウドネス補正
    # ─────────────────────────────────────────────────────────────────────
    # ティルト EQ: Lowshelf + Highshelf で全体の傾斜を調整 (-3.0 ~ +3.0 dB)
    if config.tilt != 0.0:
        tilt_gain = max(-3.0, min(3.0, config.tilt))
        # Lowshelf: 低域側、Highshelf: 高域側
        add_f_dry("tilt_low", {"type": "Biquad", "parameters": {"type": "Lowshelf", "freq": 300, "q": 0.707, "gain": -tilt_gain}})
        add_f_dry("tilt_high", {"type": "Biquad", "parameters": {"type": "Highshelf", "freq": 3000, "q": 0.707, "gain": tilt_gain}})

    # 左右バランス: gain を左右で反転適用
    if config.balance != 0.0:
        bal = max(-1.0, min(1.0, config.balance))
        # balance > 0: 右寄り (左を減衰), balance < 0: 左寄り (右を減衰)
        gain_l = -6.0 * max(0.0, -bal)
        gain_r = -6.0 * max(0.0, bal)
        add_f_dry("balance_l", {"type": "Gain", "parameters": {"gain": gain_l, "inverted": False, "mute": False}})
        add_f_dry("balance_r", {"type": "Gain", "parameters": {"gain": gain_r, "inverted": False, "mute": False}})

    # 左右独立 EQ (Peaking フィルタ配列)
    # config.eq_left = [{"freq": 100, "q": 0.7, "gain": 3.0}, ...]
    for i, eq in enumerate(config.eq_left or []):
        add_f_dry(f"eq_l_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq.get("freq", 1000), "q": eq.get("q", 0.707), "gain": eq.get("gain", 0.0)}})
    for i, eq in enumerate(config.eq_right or []):
        add_f_dry(f"eq_r_{i}", {"type": "Biquad", "parameters": {"type": "Peaking", "freq": eq.get("freq", 1000), "q": eq.get("q", 0.707), "gain": eq.get("gain", 0.0)}})

    # ラウドネス補正 (ISO 226:2003 近似)
    # 低音量再生時に低域・高域を補正して聴感上のバランスを維持
    if config.loudness_enabled:
        # 基準ラウドネスからの偏差で補正量を決定
        # 80dB 基準で、再生レベルが下がるほど低域・高域をブースト
        ref = config.loudness_ref
        vol = config.volume  # 負の値 (dB)
        # 簡易モデル: 基準音量からの乖離に比例して補正
        # 例: 80dB基準で -20dB 再生なら 100倍 (40dB) 小さい -> 低域+6dB, 高域+4dB
        delta = (ref + vol)  # 正なら基準より小さい音量
        if delta > 0:
            # 低域補正: 100Hz で最大 +8dB @ delta=40dB
            low_gain = min(8.0, delta * 0.2)
            # 高域補正: 10kHz で最大 +4dB @ delta=40dB
            high_gain = min(4.0, delta * 0.1)
            if low_gain > 0.1:
                add_f_dry("loud_low", {"type": "Biquad", "parameters": {"type": "Lowshelf", "freq": 100, "q": 0.707, "gain": low_gain}})
            if high_gain > 0.1:
                add_f_dry("loud_high", {"type": "Biquad", "parameters": {"type": "Highshelf", "freq": 10000, "q": 0.707, "gain": high_gain}})

    # ─────────────────────────────────────────────────────────────────────
    # Stage 7: CTC (Crosstalk Cancellation) - 4経路配線 + 交差経路 Conv
    # ─────────────────────────────────────────────────────────────────────
    has_ctc = config.ctc != "none"
    if has_ctc:
        # CTC は crossfeed と排他
        if config.crossfeed != "none":
            print(f"Warning: CTC mode enabled, ignoring crossfeed setting")

    # Headroom protection on DRY path - only when NOT using reverb (no parallel processing)
    # When reverb is on, DRY goes through split mixer and headroom is applied AFTER mixing
    # Stage 2-5: 自動ヘッドルーム計算
    if not has_reverb:
        # この時点で filt_dry に含まれるすべてのフィルタから最大ゲインを計算
        dry_filters = {name: y["filters"][name] for name in filt_dry["names"]}
        headroom_db = _calculate_headroom_db(dry_filters)
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

            # WET gain: Stage 5 redesign - audible range for evaluation
            # intensity=0 -> -24dB, intensity=50 -> -15dB, intensity=100 -> -6dB
            # + preset trim: IR RMS 差を吸収して等ラウド化。
            # Symphony Hall（hall）を 0.0dB の基準とし、他3種の Wet 割合を合わせる。
            wet_gain_db = round(-24.0 + (config.reverb_intensity / 100.0) * 18.0, 1)
            wet_gain_db = round(wet_gain_db + REVERB_WET_TRIM_DB.get(config.reverb, 0.0), 1)
            # WET 単体で -30dB より小さくならないよう安全クランプ（可聴範囲維持）
            wet_gain_db = max(-30.0, min(0.0, wet_gain_db))
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
        # ─────────────────────────────────────────────────────────────────────────────
        # CROSSFEED 4-channel wiring (Stage 4: 2→4→2 with ITD + shading)
        # ─────────────────────────────────────────────────────────────────────
    if config.crossfeed != "none":
        # Woodworth ITD calculation (Stage 4-2)
        # ITD = (a/c) * (θ + sin(θ)) where a=0.0875m, c=343m/s
        import math
        angle_map = {"15": 15, "30": 30, "60": 60, "90": 90, "light": 15, "standard": 30}
        angle_deg = angle_map.get(config.crossfeed, 30)
        theta = math.radians(angle_deg)
        a = 0.0875  # head radius [m]
        c = 343.0   # speed of sound [m/s]
        itd_ms = (a / c) * (theta + math.sin(theta)) * 1000  # [ms]

        # Intensity scales only gain, delay stays constant (Stage 4-5)
        intensity = config.crossfeed_intensity
        intensity_pct = max(0.0, min(1.0, intensity / 100.0))

        # Gain table (cross-feed gain at 100% intensity)
        gain_map = {"15": -3.0, "30": -6.0, "60": -10.0, "90": -14.0, "light": -3.0, "standard": -6.0}
        max_cross_gain = gain_map.get(config.crossfeed, -6.0)
        cf_gain_cross = round(max_cross_gain * intensity_pct, 1)
        cf_gain_direct = round(-3.0 * (1 - intensity_pct), 1)  # direct path attenuation

        # Shading filter: Lowpass on cross-feed path (Stage 4-3)
        # Candidate: 700Hz, -6dB at 4kHz
        y["filters"]["cf_shade"] = {
        "type": "Biquad",
        "parameters": {"type": "Lowpass", "freq": 700, "q": 0.707}
        }

        # 4-channel wiring: split4 (2→4) + sum4 (4→2)
        y["mixers"]["split4"] = {
        "channels": {"in": 2, "out": 4},
        "mapping": [
        {"dest": 0, "sources": [{"channel": 0, "gain": 0.0}]},      # direct L
        {"dest": 1, "sources": [{"channel": 1, "gain": 0.0}]},      # direct R
        {"dest": 2, "sources": [{"channel": 0, "gain": 0.0}]},      # L → R (cross)
        {"dest": 3, "sources": [{"channel": 1, "gain": 0.0}]},      # R → L (cross)
        ],
        }
        y["mixers"]["sum4"] = {
        "channels": {"in": 4, "out": 2},
        "mapping": [
        {"dest": 0, "sources": [
        {"channel": 0, "gain": 0.0, "inverted": False},                    # direct L
        {"channel": 3, "gain": cf_gain_cross, "inverted": False},         # R→L cross
        ]},
        {"dest": 1, "sources": [
        {"channel": 1, "gain": 0.0, "inverted": False},                    # direct R
        {"channel": 2, "gain": cf_gain_cross, "inverted": False},         # L→R cross
        ]},
        ],
        }

        # Pipeline: split4 → filter(shade+gain on cross paths) → sum4
        y["pipeline"].insert(0, {"type": "Mixer", "name": "split4"})
        y["pipeline"].insert(1, {
        "type": "Filter",
        "channels": [2, 3],  # cross paths only (ch 2=L→R, ch 3=R→L)
        "names": ["cf_shade", "cf_gain_cross"]
        })
        y["pipeline"].insert(2, {"type": "Mixer", "name": "sum4"})

        # Cross-feed gain filter (applied to cross paths ch 2,3)
        y["filters"]["cf_gain_cross"] = {
        "type": "Gain",
        "parameters": {"gain": cf_gain_cross, "inverted": False, "mute": False}
        }

    # ─────────────────────────────────────────────────────────────────────
    # Stage 7: CTC (Crosstalk Cancellation) - 4経路配線 + 交差経路 Conv
    # ─────────────────────────────────────────────────────────────────────
    if has_ctc:
        # CTC 用の交差経路 IR 読み込み (L→R と R→L が別ファイル)
        ctc_ir_lr = os.path.expanduser(f"~/.config/camilladsp/ir/ctc_lr.wav")
        ctc_ir_rl = os.path.expanduser(f"~/.config/camilladsp/ir/ctc_rl.wav")
        ctc_ir_lr = _ensure_ir_192k(ctc_ir_lr, target_rate=192000)
        ctc_ir_rl = _ensure_ir_192k(ctc_ir_rl, target_rate=192000)

        # 4-channel wiring: split4 (2→4) + sum4 (4→2)
        y["mixers"]["split4"] = {
            "channels": {"in": 2, "out": 4},
            "mapping": [
                {"dest": 0, "sources": [{"channel": 0, "gain": 0.0}]},      # direct L
                {"dest": 1, "sources": [{"channel": 1, "gain": 0.0}]},      # direct R
                {"dest": 2, "sources": [{"channel": 0, "gain": 0.0}]},      # L → R (cross)
                {"dest": 3, "sources": [{"channel": 1, "gain": 0.0}]},      # R → L (cross)
            ],
        }
        y["mixers"]["sum4"] = {
            "channels": {"in": 4, "out": 2},
            "mapping": [
                {"dest": 0, "sources": [
                    {"channel": 0, "gain": 0.0, "inverted": False},                    # direct L
                    {"channel": 3, "gain": 0.0, "inverted": False},         # R→L cross (Conv経由)
                ]},
                {"dest": 1, "sources": [
                    {"channel": 1, "gain": 0.0, "inverted": False},                    # direct R
                    {"channel": 2, "gain": 0.0, "inverted": False},         # L→R cross (Conv経由)
                ]},
            ],
        }

        # CTC 用フィルタ: 交差経路に Conv を適用
        y["filters"]["ctc_lr"] = {
            "type": "Conv",
            "parameters": {"type": "Wav", "filename": ctc_ir_lr}
        }
        y["filters"]["ctc_rl"] = {
            "type": "Conv",
            "parameters": {"type": "Wav", "filename": ctc_ir_rl}
        }

        # CTC 強度に応じたゲイン調整 (Stage 7-5)
        intensity = config.ctc_intensity
        intensity_pct = max(0.0, min(1.0, intensity / 100.0))
        ctc_gain = round(-24.0 + intensity_pct * 18.0, 1)  # 0→-24dB, 50→-15dB, 100→-6dB

        y["filters"]["ctc_gain"] = {
            "type": "Gain",
            "parameters": {"gain": ctc_gain, "inverted": False, "mute": False}
        }

        # Pipeline: split4 → Filter(Conv on ch 2,3 + gain) → sum4
        y["pipeline"].insert(0, {"type": "Mixer", "name": "split4"})
        y["pipeline"].insert(1, {
            "type": "Filter",
            "channels": [2, 3],  # cross paths only (ch 2=L→R, ch 3=R→L)
            "names": ["ctc_lr", "ctc_rl", "ctc_gain"]
        })
        y["pipeline"].insert(2, {"type": "Mixer", "name": "sum4"})

        # CTC ゲインフィルタ (cross paths ch 2,3 に適用)
        y["filters"]["ctc_gain"] = {
            "type": "Gain",
            "parameters": {"gain": ctc_gain, "inverted": False, "mute": False}
        }

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

    # Determine output path
    if out_path is None:
        out_path = "/tmp/camilladsp/active_dsp.yml"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        yaml.dump(y, f, sort_keys=False)
    return out_path
