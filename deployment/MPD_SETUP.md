MPD port / socket consistency
=============================

This repository includes measures to prevent MPD port mismatch causing backend failures.

Included files:

- `deployment/systemd/audiophile-backend.service.d/override.conf` — systemd drop-in template that sets `MPD_PORT=6600` for the backend service.
- `backend/scripts/check_mpd_socket.sh` — boot-time/scriptable check that compares `backend/.env` (or `MPD_PORT` env) with `mpd.socket` ListenStream.

Recommended installation steps on the host (requires sudo):

```bash
# install drop-in
sudo mkdir -p /etc/systemd/system/audiophile-backend.service.d
sudo cp deployment/systemd/audiophile-backend.service.d/override.conf /etc/systemd/system/audiophile-backend.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart audiophile-backend

# optionally run the check script to verify
sudo /home/tysbox/HQ_Linux_Music_Player/backend/scripts/check_mpd_socket.sh
```

Optional: run `check_mpd_socket.sh` as a oneshot systemd service at boot to warn about mismatches.
