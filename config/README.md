# MBusReader API token in prduction Pi

## Generate the token

Run this command:
```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Save the token

Save generated token to `/etc/mbusreader/mbusreader.env` for production:
```
MBR_API_TOKEN=PASTE_A_RANDOM_TOKEN_HERE
```

Terminal commands for generating `/etc/mbusreader/mbusreader.env` file with root access:
```
sudo install -d -m 0750 -o root -g kasutaja /etc/mbusreader
sudo sh -c 'umask 077; cat > /etc/mbusreader/mbusreader.env <<EOF
MBR_API_TOKEN=PASTE_PROD_TOKEN_HERE
EOF'
sudo chmod 640 /etc/mbusreader/mbusreader.env
```

For development, I add `MBR_API_TOKEN=xxx` to Intellij terminal's Settings > Environment variables.

Other environment variables will be added later.

# MBusReader SSL setup in prduction Pi

TODO: Creation of server.crt and server.key files are covered in main README.md and should be brought here.

Create directory for SSL files and copy them there:
```
sudo install -d -m 0750 -o root -g kasutaja /etc/mbusreader/tls

sudo cp server.crt /etc/mbusreader/tls/server.crt
sudo cp server.key /etc/mbusreader/tls/server.key
```
Lock down permissions and allow kasutaja to read `server.key`:
```
sudo chown root:root /etc/mbusreader/tls/server.*
sudo chmod 644 /etc/mbusreader/tls/server.crt

sudo chgrp kasutaja /etc/mbusreader/tls/server.key
sudo chmod 640 /etc/mbusreader/tls/server.key
```

# MBusReader systemd service setup in prduction Pi

Create `/etc/systemd/system/mbusreader.service`:

```
sudo tee /etc/systemd/system/mbusreader.service > /dev/null <<'EOF'
# Copy this file to /etc/systemd/system folder and execute "sudo systemctl daemon-reload".
# Each time changes are made to this file, then "sudo systemctl daemon-reload" must be executed again.
# In order for service to autostart with the computer, execute "sudo systemctl enable --now mbusreader.service"
# Service control commands:     "sudo systemctl start mbusreader.service --no-pager"
#                               "sudo systemctl stop mbusreader.service --no-pager"
#                               "sudo systemctl restart mbusreader.service --no-pager"
#                               "sudo systemctl status mbusreader.service --no-pager"
#
# Service logs can be viewed by "journalctl -u mbusreader.service -f"
#                               "journalctl -u mbusreader.service -n 200 -f"                        - for 200 lines
#                               "journalctl -u mbusreader.service -b -f"                            - for everything since boot
#                               "journalctl -u mbusreader.service --since "2026-01-14 00:00:00" -f" - from specific time

[Unit]
Description=MBus Reader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kasutaja
Group=kasutaja

WorkingDirectory=/home/kasutaja/git/mbusreader
EnvironmentFile=/etc/mbusreader/mbusreader.env

# Good defaults for services
Environment=PYTHONUNBUFFERED=1

ExecStart=/home/kasutaja/git/mbusreader/.venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8443 \
  --ssl-certfile /etc/mbusreader/tls/server.crt \
  --ssl-keyfile /etc/mbusreader/tls/server.key \
  --proxy-headers

Restart=on-failure
RestartSec=2
StartLimitIntervalSec=60
StartLimitBurst=10

# If you ever see "address already in use" on restart, consider:
# ExecStopPost=/bin/sleep 1

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start:
```
sudo systemctl daemon-reload
sudo systemctl enable --now mbusreader.service
```

