"""Legacy entrypoint shim — DO NOT USE FOR NEW CODE.

This module exists only for backward compatibility during transition.
All new code should import from backend.dsp.models or hq_api directly.

Use hq_api.main (port 8003) for production API.
"""

from backend.dsp.models import (
    AudioConfig,
    VolumeControl,
    StoredAudioConfig,
    DspParams,
    DEFAULT_DEVICE,
    VOLUME_DEFAULT,
    _default_audio_config,
)

# Re-export for backward compatibility
__all__ = [
    "AudioConfig",
    "VolumeControl",
    "StoredAudioConfig",
    "DspParams",
    "DEFAULT_DEVICE",
    "VOLUME_DEFAULT",
    "_default_audio_config",
]

# Prevent accidental execution as main entrypoint
if __name__ == "__main__":
    raise RuntimeError(
        "backend/main.py is a legacy shim. Use hq_api.main (port 8003) instead."
    )
