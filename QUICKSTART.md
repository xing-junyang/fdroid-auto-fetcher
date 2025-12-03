# F-Droid Auto-Builder - Quick Start Guide

## Windows Quick Start

### 1. Install Prerequisites
```powershell
# Download and install:
# - Python 3.8+ from python.org (install to D:\Python)
# - Git from git-scm.com (install to D:\Git)  
# - Java JDK 8, 11, 17 from adoptium.net (install to D:\Java\jdk-*)
```

### 2. Setup Service
```powershell
# Extract or clone to D:\fdroid-auto-fetcher
cd D:\fdroid-auto-fetcher
pip install -r requirements.txt
```

### 3. Configure
```powershell
notepad config.ini
```
Change:
```ini
[workspace]
root_path = D:/fdroid_workspace
```

### 4. Run
```powershell
python main.py
```

### 5. Check Health (if enabled)
```powershell
Invoke-RestMethod http://localhost:8080/health
```

### 6. Install as Windows Service (Optional)
```powershell
# Download NSSM, then:
nssm install FDroidAutoBuilder D:\Python\python.exe D:\fdroid-auto-fetcher\main.py
nssm set FDroidAutoBuilder AppDirectory D:\fdroid-auto-fetcher
nssm start FDroidAutoBuilder
```

**Full Windows Guide:** [WINDOWS_DEPLOYMENT.md](WINDOWS_DEPLOYMENT.md)

---

## Linux Quick Start

### 1. Run Setup Script
```bash
cd /data/workspace/fdroid-auto-fetcher
./setup.sh
```

### 2. Configure
```bash
nano config.ini
```
Change:
```ini
[workspace]
root_path = /data/fdroid_workspace
```

### 3. Run
```bash
python3 main.py
```

### 4. Check Health (if enabled)
```bash
curl http://localhost:8080/health | jq
```

### 5. Install as Systemd Service (Optional)
```bash
sudo cp fdroid-builder.service /etc/systemd/system/
sudo systemctl enable fdroid-builder
sudo systemctl start fdroid-builder
```

**Full Linux Guide:** [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Health Check Endpoints

### Enable in config.ini
```ini
[health_check]
enable_http_server = true
http_port = 8080
http_host = 0.0.0.0  # Or 127.0.0.1 for localhost only
```

### Endpoints

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `/health` | Service health status | `curl http://localhost:8080/health` |
| `/stats` | Detailed statistics | `curl http://localhost:8080/stats` |
| `/ping` | Simple availability check | `curl http://localhost:8080/ping` |

### Health Response
```json
{
  "status": "healthy",
  "disk_free_gb": 150.5,
  "total_apps": 100,
  "scheduler_running": true
}
```

---

## Common Configuration

### Minimal (4GB RAM, 2 cores)
```ini
[build]
max_concurrent_builds = 1
build_timeout_minutes = 20
gradle_memory_gb = 2
```

### Recommended (8GB+ RAM, 4+ cores)
```ini
[build]
max_concurrent_builds = 3
build_timeout_minutes = 30
gradle_memory_gb = 4
```

### Powerful (16GB+ RAM, 8+ cores)
```ini
[build]
max_concurrent_builds = 5
build_timeout_minutes = 45
gradle_memory_gb = 6
```

---

## Monitoring

### Logs Location
- **Main log:** `{workspace}/logs/service.log`
- **App logs:** `{workspace}/logs/apps/{app_id}.log`
- **Build logs:** `{workspace}/builds/{app_id}/logs/`

### View Logs

**Windows:**
```powershell
Get-Content D:\fdroid_workspace\logs\service.log -Tail 50 -Wait
```

**Linux:**
```bash
tail -f /data/fdroid_workspace/logs/service.log
```

### Database Queries

```bash
sqlite3 {workspace}/database/service_state.db

# App statistics
SELECT build_status, COUNT(*) FROM app_info GROUP BY build_status;

# Recent builds
SELECT app_id, build_time, status FROM build_history ORDER BY build_time DESC LIMIT 10;
```

---

## Troubleshooting

### Service won't start
1. Check Python version: `python --version` (need 3.8+)
2. Check dependencies: `pip install -r requirements.txt`
3. Check logs: See logs location above
4. Verify workspace path exists and is writable

### Builds failing
1. Check Java: `java -version`
2. Check Java environment variables: `JAVA_HOME`, `JAVA8_HOME`, etc.
3. Review build logs in `{workspace}/builds/{app_id}/logs/`
4. Verify gradlew exists in repository

### Health check not working
1. Verify `enable_http_server = true` in config.ini
2. Check port not in use: `netstat -an | findstr 8080` (Windows) or `netstat -ln | grep 8080` (Linux)
3. Check firewall rules
4. Try accessing from localhost first: `http://127.0.0.1:8080/health`

---

## Quick Commands

### Windows
```powershell
# Check service status (if using NSSM)
nssm status FDroidAutoBuilder

# View recent logs
Get-Content D:\fdroid_workspace\logs\service.log -Tail 50

# Check disk space
Get-PSDrive D

# Health check
Invoke-RestMethod http://localhost:8080/health
```

### Linux
```bash
# Check service status (if using systemd)
sudo systemctl status fdroid-builder

# View recent logs
tail -50 /data/fdroid_workspace/logs/service.log

# Check disk space
df -h /data/fdroid_workspace

# Health check
curl http://localhost:8080/health | jq
```

---

## Need Help?

- **Windows deployment:** [WINDOWS_DEPLOYMENT.md](WINDOWS_DEPLOYMENT.md)
- **Linux deployment:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Full documentation:** [README.md](README.md)
- **Recent changes:** [CHANGES.md](CHANGES.md)
