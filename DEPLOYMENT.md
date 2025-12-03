# F-Droid Auto-Builder - Deployment Guide

## Quick Start

### 1. Prerequisites Check

**Required:**
- Python 3.8+
- Git 2.30+
- 200GB+ disk space

**Recommended:**
- Java JDK 8, 11, and 17 (for building Android apps)
- 8GB+ RAM
- Multi-core CPU

### 2. Installation

Run the setup script:
```bash
cd /data/workspace/fdroid-auto-fetcher
chmod +x setup.sh
./setup.sh
```

Or install manually:
```bash
pip install -r requirements.txt
```

### 3. Configuration

Edit `config.ini`:
```bash
nano config.ini
```

**Minimum required changes:**
```ini
[workspace]
root_path = /data/fdroid_workspace  # Change to your desired path

[build]
max_concurrent_builds = 3  # Adjust based on CPU cores
```

### 4. Test Run

Run service directly to test:
```bash
python3 main.py
```

Press Ctrl+C to stop.

## Production Deployment

### Option 1: Systemd Service (Recommended for Linux)

1. **Create service user:**
   ```bash
   sudo useradd -r -s /bin/false fdroid
   ```

2. **Set permissions:**
   ```bash
   sudo chown -R fdroid:fdroid /data/workspace/fdroid-auto-fetcher
   sudo chown -R fdroid:fdroid /data/fdroid_workspace
   ```

3. **Install service:**
   ```bash
   sudo cp fdroid-builder.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

4. **Enable and start:**
   ```bash
   sudo systemctl enable fdroid-builder
   sudo systemctl start fdroid-builder
   ```

5. **Check status:**
   ```bash
   sudo systemctl status fdroid-builder
   sudo journalctl -u fdroid-builder -f
   ```

### Option 2: Screen/Tmux (Quick Testing)

```bash
screen -S fdroid-builder
python3 main.py
# Press Ctrl+A, then D to detach
# Reattach: screen -r fdroid-builder
```

### Option 3: Docker (Advanced)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    openjdk-11-jdk \
    openjdk-17-jdk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
VOLUME ["/data/fdroid_workspace"]

CMD ["python3", "main.py"]
```

Build and run:
```bash
docker build -t fdroid-builder .
docker run -d --name fdroid-builder \
  -v /data/fdroid_workspace:/data/fdroid_workspace \
  --restart unless-stopped \
  fdroid-builder
```

## Monitoring

### Log Files

**Main service log:**
```bash
tail -f /data/fdroid_workspace/logs/service.log
```

**App-specific logs:**
```bash
ls /data/fdroid_workspace/logs/apps/
tail -f /data/fdroid_workspace/logs/apps/com.example.app.log
```

**Build logs:**
```bash
ls /data/fdroid_workspace/builds/*/logs/
```

### Database Queries

**Service statistics:**
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db
```

```sql
-- App count by status
SELECT build_status, COUNT(*) FROM app_info GROUP BY build_status;

-- Recent builds
SELECT app_id, build_time, status, duration 
FROM build_history 
ORDER BY build_time DESC 
LIMIT 20;

-- Failed apps
SELECT app_id, consecutive_failures, last_attempt_time 
FROM app_info 
WHERE build_status = 'fail' 
ORDER BY consecutive_failures DESC;

-- Largest repositories
SELECT app_id, ROUND(repo_size/1024.0/1024.0/1024.0, 2) as size_gb 
FROM app_info 
WHERE repo_size IS NOT NULL 
ORDER BY repo_size DESC 
LIMIT 10;
```

### Disk Usage

```bash
# Overall workspace usage
du -sh /data/fdroid_workspace/*

# Per-app source size
du -sh /data/fdroid_workspace/sources/* | sort -h | tail -20

# Gradle cache size
du -sh /data/fdroid_workspace/cache/gradle
```

## Maintenance

### Manual Cleanup

**Trigger cleanup immediately:**
```bash
# Edit config.ini to lower thresholds temporarily
[cleanup]
inactive_days = 30
max_consecutive_failures = 2

# Restart service
sudo systemctl restart fdroid-builder
```

**Purge Gradle cache:**
```bash
rm -rf /data/fdroid_workspace/cache/gradle/*
```

**Delete specific app:**
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db \
  "DELETE FROM app_info WHERE app_id='com.example.problem.app';"
rm -rf /data/fdroid_workspace/sources/com.example.problem.app
rm -rf /data/fdroid_workspace/builds/com.example.problem.app
```

### Database Backup

**Manual backup:**
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db \
  ".backup /data/fdroid_workspace/database/backups/manual_$(date +%Y%m%d).db"
```

**Restore from backup:**
```bash
# Stop service
sudo systemctl stop fdroid-builder

# Restore
cp /data/fdroid_workspace/database/backups/service_state_20231201.db \
   /data/fdroid_workspace/database/service_state.db

# Restart
sudo systemctl start fdroid-builder
```

### Update Service

```bash
# Stop service
sudo systemctl stop fdroid-builder

# Update code (if from git)
cd /data/workspace/fdroid-auto-fetcher
git pull

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart service
sudo systemctl start fdroid-builder
```

## Troubleshooting

### Service won't start

**Check logs:**
```bash
sudo journalctl -u fdroid-builder -n 50
tail -f /data/fdroid_workspace/logs/service.log
```

**Common issues:**
- Workspace path doesn't exist: `mkdir -p /data/fdroid_workspace`
- Permission denied: `sudo chown -R fdroid:fdroid /data/fdroid_workspace`
- Python dependencies missing: `pip install -r requirements.txt`
- Port already in use (if health check enabled): Change port in config.ini

### Builds failing

**Check Java installation:**
```bash
java -version
which java

# Set JAVA_HOME if needed
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
```

**Check gradlew permissions:**
```bash
# Service should handle this automatically, but verify:
find /data/fdroid_workspace/sources -name gradlew -exec chmod +x {} \;
```

**Review build log:**
```bash
# Find latest build log for an app
ls -lt /data/fdroid_workspace/builds/com.example.app/logs/ | head -1
```

### High resource usage

**Reduce concurrent builds:**
```ini
[build]
max_concurrent_builds = 1
gradle_memory_gb = 2
```

**Increase cleanup frequency:**
```ini
[scheduler]
cleanup_day_of_week = 0,3,6  # Mon, Wed, Sun
```

### Disk space issues

**Emergency cleanup:**
```bash
# Delete all failed repos
sqlite3 /data/fdroid_workspace/database/service_state.db \
  "SELECT app_id FROM app_info WHERE build_status='fail';" | \
  while read app; do
    rm -rf /data/fdroid_workspace/sources/$app
    rm -rf /data/fdroid_workspace/builds/$app
  done

# Purge cache
rm -rf /data/fdroid_workspace/cache/gradle/*
```

## Performance Tuning

### For 4GB RAM, 2 CPU cores:
```ini
[build]
max_concurrent_builds = 1
build_timeout_minutes = 20
gradle_memory_gb = 2
```

### For 16GB RAM, 8 CPU cores:
```ini
[build]
max_concurrent_builds = 5
build_timeout_minutes = 45
gradle_memory_gb = 6
```

### For limited disk space (100GB):
```ini
[cleanup]
max_repo_size_gb = 2
inactive_days = 30
gradle_cache_retention_days = 7
max_workspace_size_gb = 80
```

## Security Hardening

### File Permissions
```bash
# Restrict service files
chmod 750 /data/workspace/fdroid-auto-fetcher
chmod 640 /data/workspace/fdroid-auto-fetcher/config.ini

# Workspace permissions
chmod 750 /data/fdroid_workspace
chown -R fdroid:fdroid /data/fdroid_workspace
```

### Firewall (if health check HTTP server enabled)
```bash
# Allow only localhost access
sudo ufw allow from 127.0.0.1 to any port 8080
```

### SELinux (if enabled)
```bash
# Set context for workspace
sudo semanage fcontext -a -t user_home_t "/data/fdroid_workspace(/.*)?"
sudo restorecon -R /data/fdroid_workspace
```

## Health Checks

### Service Health
```bash
# Systemd status
sudo systemctl is-active fdroid-builder

# Process check
pgrep -f "python.*main.py"

# Recent activity
sqlite3 /data/fdroid_workspace/database/service_state.db \
  "SELECT * FROM task_execution_log ORDER BY start_time DESC LIMIT 5;"
```

### Build Success Rate
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db << EOF
SELECT 
  COUNT(CASE WHEN status='success' THEN 1 END) as successful,
  COUNT(CASE WHEN status='fail' THEN 1 END) as failed,
  ROUND(100.0 * COUNT(CASE WHEN status='success' THEN 1 END) / COUNT(*), 2) as success_rate
FROM build_history
WHERE build_time > datetime('now', '-7 days');
EOF
```

## Support

For issues not covered in this guide:

1. Check service logs: `/data/fdroid_workspace/logs/service.log`
2. Review app-specific logs in `/data/fdroid_workspace/logs/apps/`
3. Check database state with SQL queries above
4. Review design document for architecture details

## Version Information

Service Version: 1.0.0  
Database Schema Version: 1  
Configuration Version: 1.0
