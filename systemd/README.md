# systemd units

| File | Install to | Purpose |
|---|---|---|
| `pt35-desktop.service` | `/etc/systemd/system/` | Chinese desktop (sway+foot+fcitx5) |
| `pt35-bootsplash.service` | `/etc/systemd/system/` | CRT-glitch boot animation |
| `10-quiet-console.conf` | `/etc/systemd/system.conf.d/` | Stop systemd scrolling the console |

## Required manual step: mask getty on tty1

```bash
sudo systemctl mask getty@tty1.service
```

**Why `mask` and not `disable`:** `getty@tty1` is pulled in by `getty.target` →
`multi-user.target` → `graphical.target`, so it starts on every boot regardless of
`enable` state. `pt35-desktop.service` declares `Conflicts=kmsconvt@tty1.service`
for tty1, so when getty starts it **stops the running desktop**:

```
17:21:19 Started Getty on tty1.
17:22:04 Stopping Getty on tty1...
17:22:04 Stopping PocketTerm35 Chinese desktop...    ← desktop killed
17:22:04 pt35-desktop.service: Main process exited, status=143
```

`mask` symlinks the unit to `/dev/null`, so nothing can pull it in.

## TTY allocation

| TTY | Owner | Notes |
|---|---|---|
| tty1 | kmscon | Rescue console. Boot animation runs here first, then hands over. |
| tty2 | sway | The desktop. Switch with **Ctrl+Alt+F2**. |
