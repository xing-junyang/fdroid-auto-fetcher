# F-Droid Auto-Builder Service

A robust, long-running service that automatically fetches F-Droid app source code and performs local Gradle builds with comprehensive error handling and multi-Java version support.

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

## Installation

### Prerequisites

- Python 3.8+
- Git 2.30+
- Java JDK (8, 11, and/or 17 recommended)
- Minimum 200GB disk space

### Setup Steps

1. **Clone or extract the service:**
   ```bash
   cd /data/workspace/fdroid-auto-fetcher
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the service:**
   Edit `config.ini` to set your workspace path and preferences:
   ```ini
   [workspace]
   root_path = /data/fdroid_workspace
   ```

4. **Initialize workspace:**
   The service will automatically create the directory structure on first run.

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

## Usage

### Running the Service

**Direct execution:**
```bash
python main.py
```

**With custom config:**
```bash
python main.py /path/to/custom/config.ini
```

### Running as a Systemd Service (Linux)

1. Create service file `/etc/systemd/system/fdroid-builder.service`:
   ```ini
   [Unit]
   Description=F-Droid Auto-Builder Service
   After=network.target

   [Service]
   Type=simple
   User=fdroid
   WorkingDirectory=/data/workspace/fdroid-auto-fetcher
   ExecStart=/usr/bin/python3 main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable fdroid-builder
   sudo systemctl start fdroid-builder
   ```

3. Check status:
   ```bash
   sudo systemctl status fdroid-builder
   ```

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
