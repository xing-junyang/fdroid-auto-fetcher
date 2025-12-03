# F-Droid Auto-Builder Service

A robust, long-running service that automatically fetches F-Droid app source code and performs local Gradle builds with comprehensive error handling and multi-Java version support.

**✨ Fully supports both Windows and Linux!**

## Features

✅ **Automated F-Droid Metadata Fetching** - Downloads and parses F-Droid app index  
✅ **Robust Repository Management** - Multi-protocol Git cloning with retry logic  
✅ **Multi-Java Version Support** - Automatically tries JDK 8, 11, and 17  
✅ **Resource Monitoring** - Build timeout, memory limits, and disk usage monitoring  
✅ **Intelligent Cleanup** - Multiple cleanup strategies based on failures, inactivity, and size  
✅ **Structured Logging** - JSON-formatted logs with rotation  
✅ **Task Scheduling** - APScheduler with SQLite persistence  
✅ **Error Isolation** - Individual app failures never interrupt the main workflow  
✅ **Configurable Workspace** - All resources stored in configured directory (non-C drive for Windows)  
✅ **Health Check HTTP Server** - REST API endpoints for monitoring service status  
✅ **Cross-Platform** - Windows (gradlew.bat) and Linux (gradlew) support  

## Architecture

```
Service Layer
├── Service Controller (main.py)
├── Task Scheduler (APScheduler)
└── Health Check (optional)

Business Logic Layer
├── F-Droid Metadata Fetcher
├── Repository Manager (Git operations)
├── Build Executor (Gradle builds)
└── Cleanup Manager

Data Layer
├── SQLite Database
├── File System
└── Path Manager
```

## Quick Start

### Windows Users

**See detailed guide:** [WINDOWS_DEPLOYMENT.md](WINDOWS_DEPLOYMENT.md)

```powershell
# 1. Install dependencies (Python 3.8+, Git, Java)
# 2. Clone or extract service to D:\fdroid-auto-fetcher
cd D:\fdroid-auto-fetcher
pip install -r requirements.txt

# 3. Edit config.ini
notepad config.ini

# 4. Run service
python main.py
```

### Linux Users

**See detailed guide:** [DEPLOYMENT.md](DEPLOYMENT.md)

```bash
# 1. Install dependencies
cd /data/workspace/fdroid-auto-fetcher
./setup.sh

# 2. Edit config.ini
nano config.ini

# 3. Run service
python3 main.py
```

## Configuration

All configuration is in `config.ini`. Key sections:

### Workspace
- `root_path`: Workspace root directory (default: `/data/fdroid_workspace`)
- `validate_non_c_drive`: Enforce non-C drive on Windows (default: `false`)

### Scheduler
- `fetch_metadata_interval_hours`: Metadata fetch interval (default: `24`)
- `build_interval_hours`: Build cycle interval (default: `6`)
- `cleanup_day_of_week`: Cleanup day 0-6 (default: `6` = Sunday)

### Build
- `max_concurrent_builds`: Parallel build limit (default: `3`)
- `build_timeout_minutes`: Per-build timeout (default: `30`)
- `max_consecutive_failures`: Failure threshold (default: `3`)
- `gradle_memory_gb`: Gradle JVM memory (default: `4`)

### Cleanup
- `max_repo_size_gb`: Max single repo size (default: `5`)
- `inactive_days`: Inactivity threshold (default: `90`)
- `gradle_cache_retention_days`: Cache retention (default: `30`)

## Health Check Endpoints

When health check is enabled in `config.ini`:

```ini
[health_check]
enable_http_server = true
http_port = 8080
```

### Available Endpoints

**Health Status:**
```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "disk_free_gb": 150.5,
  "disk_usage_percent": 25.3,
  "total_apps": 100,
  "scheduler_running": true
}
```

**Detailed Statistics:**
```bash
curl http://localhost:8080/stats
```

**Simple Ping:**
```bash
curl http://localhost:8080/ping
```

## Platform-Specific Notes

### Windows
- Uses `gradlew.bat` for builds
- Detects Java in `C:\Program Files\Java` and `D:\Java`
- Supports NSSM for service management
- See [WINDOWS_DEPLOYMENT.md](WINDOWS_DEPLOYMENT.md) for complete guide

### Linux
- Uses `gradlew` (chmod +x applied automatically)
- Detects Java in `/usr/lib/jvm`, `/usr/java`, `/opt/java`
- Supports systemd for service management
- See [DEPLOYMENT.md](DEPLOYMENT.md) for complete guide

## Directory Structure

```
/data/fdroid_workspace/
├── sources/              # Git repositories
│   └── com.example.app/
├── builds/               # Build outputs
│   └── com.example.app/
│       ├── apks/        # Generated APK files
│       └── logs/        # Per-build logs
├── cache/
│   └── gradle/          # Gradle cache (GRADLE_USER_HOME)
├── logs/
│   ├── service.log      # Main service log
│   └── apps/            # Per-app logs
├── database/
│   ├── service_state.db # Main database
│   ├── scheduler.db     # Scheduler state
│   └── backups/         # Database backups
└── temp/                # Temporary files
```

## Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| fetch_metadata | Every 24 hours | Download F-Droid app index |
| clone_repos | Every 6 hours | Clone new repositories |
| update_repos | Every 12 hours | Update existing repositories |
| build_apps | Every 6 hours | Build applications |
| cleanup | Sunday 2:00 AM | Cleanup old/failed data |
| backup_database | Daily 3:00 AM | Backup database |

## Error Handling

### Repository Cloning
- **Multi-protocol retry**: HTTPS → SSH → Git protocol
- **Exponential backoff**: 5s, 10s, 20s between retries
- **Timeout handling**: 10 minutes per attempt, 45 minutes total
- **Validation**: Checks .git directory and commit history

### Build Execution
- **Multi-Java version**: Tries JDK 17 → 11 → 8 → default
- **Resource limits**: 4GB memory, 30-minute timeout
- **Process monitoring**: Kills hung builds automatically
- **Error classification**: Determines if different Java version might help

### Task Isolation
- Individual app failures logged and skipped
- Task failures don't stop scheduler
- Database transaction failures rolled back safely
- Resource exhaustion triggers emergency cleanup

## Monitoring

### Logs
- **Main log**: `/data/fdroid_workspace/logs/service.log`
- **Per-app logs**: `/data/fdroid_workspace/logs/apps/{app_id}.log`
- **Build logs**: `/data/fdroid_workspace/builds/{app_id}/logs/`

### Database Queries

Check service statistics:
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db "SELECT build_status, COUNT(*) FROM app_info GROUP BY build_status;"
```

View recent builds:
```bash
sqlite3 /data/fdroid_workspace/database/service_state.db "SELECT app_id, build_time, status FROM build_history ORDER BY build_time DESC LIMIT 10;"
```

## Troubleshooting

### Service won't start
- Check Python dependencies: `pip install -r requirements.txt`
- Verify workspace path exists and is writable
- Check logs: `tail -f /data/fdroid_workspace/logs/service.log`

### Builds failing
- Verify Java installed: `java -version`
- Check available disk space: `df -h`
- Review build log in `builds/{app_id}/logs/`
- Ensure gradlew is executable

### High disk usage
- Trigger manual cleanup: Modify config to lower thresholds
- Check large repositories: `SELECT app_id, repo_size FROM app_info ORDER BY repo_size DESC LIMIT 10;`
- Purge Gradle cache: `rm -rf /data/fdroid_workspace/cache/gradle/*`

## Security Considerations

- **URL validation**: Whitelists protocols, rejects suspicious characters
- **App ID validation**: Prevents path traversal attacks
- **Path validation**: Ensures all operations within workspace
- **Process isolation**: Builds run in separate processes
- **No elevated privileges**: Service runs as regular user

## Performance Tuning

### For limited resources:
```ini
[build]
max_concurrent_builds = 1
build_timeout_minutes = 20
gradle_memory_gb = 2
```

### For powerful servers:
```ini
[build]
max_concurrent_builds = 5
build_timeout_minutes = 45
gradle_memory_gb = 8
```

## License

This service is provided as-is for educational and personal use.

## Support

For issues, questions, or contributions, please refer to the design document or service logs for debugging information.
