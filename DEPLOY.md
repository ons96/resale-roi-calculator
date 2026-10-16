# Deploy guide — VPS-40

Target: VPS-40 (`ubuntu@<vps-40-host>`, `~/.ssh/oracle.key`). Python 3.12,
954 MB RAM. Port 8100 is already taken by the existing gateway fixture;
this service binds `127.0.0.1:8101` and stays loopback-only (matches the
gateway's security posture — expose via SSH tunnel or HTTPS reverse proxy
only).

## 1. Upload

```bash
rsync -az --exclude '.venv' --exclude '*.db' --exclude '__pycache__' \
  resale-roi-calculator/ ubuntu@<vps-40-host>:~/resale-roi-calculator/
```

## 2. Install

```bash
ssh ubuntu@<vps-40-host>
cd ~/resale-roi-calculator
python3 -m venv .venv
.venv/bin/pip install -e .
```

(Or use `uv venv && uv pip install -e .` if `uv` is present.)

## 3. Systemd unit (`~/.config/systemd/user/resale-roi.service`)

```ini
[Unit]
Description=resale-roi-calculator FastAPI service
After=network.target

[Service]
WorkingDirectory=%h/resale-roi-calculator
Environment=ROI_DB_PATH=%h/resale-roi-calculator/roi_usage.db
Environment=ROI_HOST=127.0.0.1
Environment=ROI_PORT=8101
ExecStart=%h/resale-roi-calculator/.venv/bin/python -m app.main
Restart=always
RestartSec=5
MemoryMax=128M

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now resale-roi.service
loginctl enable-linger ubuntu   # survive logout
```

## 4. Seed an API key

```bash
cd ~/resale-roi-calculator
.venv/bin/python -c "from app.auth import init_db, create_key; init_db(); print(create_key('free', 'smoke-test'))"
```

## 5. Verify (real curl, from the VPS)

```bash
# 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8101/health
curl -s http://127.0.0.1:8101/v1/roi \
  -H "X-API-Key: roi_YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"buy_price": 100, "sell_price": 150}'

# rate-limit rejection (free plan = 10/min -> 11th call must be 429)
for i in $(seq 1 11); do
  curl -s -o /dev/null -w '%{http_code} ' http://127.0.0.1:8101/v1/roi \
    -H "X-API-Key: roi_YOUR_KEY" -H "Content-Type: application/json" \
    -d '{"buy_price": 1, "sell_price": 2}'
done; echo
```

## 6. Notes

- Loopback-only by design. For remote access use an SSH tunnel:
  `ssh -L 8101:127.0.0.1:8101 ubuntu@<vps-40-host>`.
- Do NOT open a firewall port for this service.
- The SQLite usage DB is one file (`roi_usage.db`); back it up with `cp`.
- Memory cap 128M keeps the 954MB box safe alongside the gateway.
