# F-Droid Auto-Builder - Windows Deployment Guide

## Windows Environment Requirements

### Prerequisites

**Required:**
- Python 3.8+ (64-bit recommended)
- Git for Windows 2.30+
- 200GB+ disk space (non-C drive recommended)

**Recommended:**
- Java JDK 8, 11, and 17 (for building Android apps)
- 8GB+ RAM
- Multi-core CPU
- Windows Server 2016+ or Windows 10/11

### Installation Steps

#### 1. Install Python

Download from https://www.python.org/downloads/

**Important:**
- Choose "Custom installation"
- Check "Add Python to PATH"
- Install to **D:\Python** (not C:\Program Files)
- Enable "Install for all users"

Verify installation:
```powershell
python --version
pip --version
```

#### 2. Install Git for Windows

Download from https://git-scm.com/download/win

**Important:**
- Install to **D:\Git** (not C:\Program Files)
- Select "Git from the command line and also from 3rd-party software"
- Choose "Use Windows' default console window"

Verify installation:
```powershell
git --version
```

#### 3. Install Java JDKs

Download from:
- JDK 8: https://adoptium.net/temurin/releases/?version=8
- JDK 11: https://adoptium.net/temurin/releases/?version=11
- JDK 17: https://adoptium.net/temurin/releases/?version=17

**Important:**
- Install to **D:\Java\jdk-8**, **D:\Java\jdk-11**, **D:\Java\jdk-17**
- Set environment variables:

```powershell
[System.Environment]::SetEnvironmentVariable('JAVA_HOME', 'D:\Java\jdk-11', 'Machine')
[System.Environment]::SetEnvironmentVariable('JAVA8_HOME', 'D:\Java\jdk-8', 'Machine')
[System.Environment]::SetEnvironmentVariable('JAVA11_HOME', 'D:\Java\jdk-11', 'Machine')
[System.Environment]::SetEnvironmentVariable('JAVA17_HOME', 'D:\Java\jdk-17', 'Machine')
```

Verify installation:
```powershell
java -version
```

#### 4. Setup Service Directory

```powershell
# Create workspace directory
mkdir D:\fdroid_workspace

# Clone or extract service
cd D:\
git clone <repository-url> fdroid-auto-fetcher
# Or extract ZIP to D:\fdroid-auto-fetcher
```

#### 5. Install Python Dependencies

```powershell
cd D:\fdroid-auto-fetcher
pip install -r requirements.txt
```

#### 6. Configure Service

Edit `config.ini`:

```powershell
notepad config.ini
```

**Key Windows Settings:**

```ini
[workspace]
# Use forward slashes or escaped backslashes
root_path = D:/fdroid_workspace
# OR
root_path = D:\\fdroid_workspace
validate_non_c_drive = true

[build]
max_concurrent_builds = 3
build_timeout_minutes = 30
gradle_memory_gb = 4

[health_check]
enable_http_server = true
http_port = 8080
http_host = 0.0.0.0
```

#### 7. Test Run

```powershell
cd D:\fdroid-auto-fetcher
python main.py
```

Press `Ctrl+C` to stop.

## Windows Service Deployment with NSSM

### Install NSSM (Non-Sucking Service Manager)

1. Download NSSM from https://nssm.cc/download
2. Extract to **D:\nssm**
3. Add to PATH or use full path

### Register Service

**PowerShell (Run as Administrator):**

```powershell
# Navigate to NSSM directory
cd D:\nssm\win64

# Install service
.\nssm install FDroidAutoBuilder D:\Python\python.exe D:\fdroid-auto-fetcher\main.py

# Set working directory
.\nssm set FDroidAutoBuilder AppDirectory D:\fdroid-auto-fetcher

# Set stdout/stderr logs
.\nssm set FDroidAutoBuilder AppStdout D:\fdroid_workspace\logs\service.stdout.log
.\nssm set FDroidAutoBuilder AppStderr D:\fdroid_workspace\logs\service.stderr.log

# Set restart options
.\nssm set FDroidAutoBuilder AppExit Default Restart
.\nssm set FDroidAutoBuilder AppRestartDelay 5000

# Set startup type
.\nssm set FDroidAutoBuilder Start SERVICE_AUTO_START

# Start service
.\nssm start FDroidAutoBuilder
```

### Manage Service

```powershell
# Check status
.\nssm status FDroidAutoBuilder

# Stop service
.\nssm stop FDroidAutoBuilder

# Restart service
.\nssm restart FDroidAutoBuilder

# View service details
.\nssm edit FDroidAutoBuilder

# Remove service (if needed)
.\nssm remove FDroidAutoBuilder confirm
```

### Using Windows Services Manager

1. Press `Win+R`, type `services.msc`, press Enter
2. Find "FDroidAutoBuilder"
3. Right-click → Start/Stop/Restart

## Health Check Endpoints

Once the service is running with health check enabled:

### Check Service Health

```powershell
# Using PowerShell
Invoke-RestMethod -Uri http://localhost:8080/health | ConvertTo-Json

# Using curl (if installed)
curl http://localhost:8080/health
```

**Response Example:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "workspace_root": "D:\\fdroid_workspace",
  "disk_free_gb": 150.5,
  "disk_usage_percent": 25.3,
  "total_apps": 100,
  "status_counts": {
    "success": 45,
    "fail": 10,
    "never_built": 45
  },
  "recent_successful_builds": 5,
  "scheduler_running": true,
  "last_metadata_fetch": "2024-01-01T10:00:00"
}
```

### Detailed Statistics

```powershell
Invoke-RestMethod -Uri http://localhost:8080/stats | ConvertTo-Json
```

### Simple Ping

```powershell
Invoke-RestMethod -Uri http://localhost:8080/ping
```

## Monitoring on Windows

### View Logs

**Main Service Log:**
```powershell
Get-Content D:\fdroid_workspace\logs\service.log -Tail 50 -Wait
```

**App-Specific Logs:**
```powershell
Get-ChildItem D:\fdroid_workspace\logs\apps\
Get-Content D:\fdroid_workspace\logs\apps\com.example.app.log -Tail 50
```

**NSSM Logs:**
```powershell
Get-Content D:\fdroid_workspace\logs\service.stdout.log -Tail 50
Get-Content D:\fdroid_workspace\logs\service.stderr.log -Tail 50
```

### Database Queries (PowerShell)

**Install SQLite if not available:**
```powershell
# Using Chocolatey
choco install sqlite

# Or download from https://www.sqlite.org/download.html
```

**Query Database:**
```powershell
# App statistics
sqlite3 D:\fdroid_workspace\database\service_state.db "SELECT build_status, COUNT(*) FROM app_info GROUP BY build_status;"

# Recent builds
sqlite3 D:\fdroid_workspace\database\service_state.db "SELECT app_id, build_time, status FROM build_history ORDER BY build_time DESC LIMIT 10;"

# Failed apps
sqlite3 D:\fdroid_workspace\database\service_state.db "SELECT app_id, consecutive_failures FROM app_info WHERE build_status='fail' ORDER BY consecutive_failures DESC;"
```

### Disk Usage

```powershell
# Overall workspace size
Get-ChildItem D:\fdroid_workspace -Recurse | Measure-Object -Property Length -Sum | Select-Object @{Name="Size(GB)";Expression={$_.Sum / 1GB}}

# Per-directory size
Get-ChildItem D:\fdroid_workspace | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
    [PSCustomObject]@{
        Directory = $_.Name
        SizeGB = [math]::Round($size, 2)
    }
} | Sort-Object SizeGB -Descending
```

## Windows Firewall Configuration

If health check server is enabled and you need external access:

```powershell
# Allow inbound on port 8080
New-NetFirewallRule -DisplayName "FDroid Auto-Builder Health Check" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow

# Or use Windows Defender Firewall GUI:
# 1. Open "Windows Defender Firewall with Advanced Security"
# 2. Click "Inbound Rules" → "New Rule"
# 3. Select "Port" → TCP → 8080
# 4. Allow the connection
# 5. Name it "FDroid Auto-Builder Health Check"
```

## Troubleshooting Windows-Specific Issues

### Service Won't Start

**Check Event Viewer:**
```powershell
# Open Event Viewer
eventvwr.msc

# Navigate to: Windows Logs → Application
# Look for errors from "FDroidAutoBuilder"
```

**Common Issues:**

1. **Python not found:**
   - Verify Python path in NSSM: `nssm edit FDroidAutoBuilder`
   - Check PATH environment variable

2. **Permission denied:**
   - Ensure service has write access to D:\fdroid_workspace
   - Run: `icacls D:\fdroid_workspace /grant Everyone:(OI)(CI)F`

3. **Import errors:**
   - Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`

### Gradlew Not Found

The service automatically looks for `gradlew.bat` on Windows:

```powershell
# Verify gradlew.bat exists in repositories
Get-ChildItem D:\fdroid_workspace\sources\*\gradlew.bat
```

### Java Version Issues

**Verify Java installations:**
```powershell
# Check environment variables
[System.Environment]::GetEnvironmentVariable('JAVA_HOME', 'Machine')
[System.Environment]::GetEnvironmentVariable('JAVA8_HOME', 'Machine')
[System.Environment]::GetEnvironmentVariable('JAVA11_HOME', 'Machine')
[System.Environment]::GetEnvironmentVariable('JAVA17_HOME', 'Machine')

# Test each Java version
D:\Java\jdk-8\bin\java -version
D:\Java\jdk-11\bin\java -version
D:\Java\jdk-17\bin\java -version
```

### Gradle Cache Issues

**Clear Gradle cache:**
```powershell
Remove-Item -Recurse -Force D:\fdroid_workspace\cache\gradle\*
```

### Network/Git Issues

**Test Git connectivity:**
```powershell
git clone --depth=1 https://github.com/test/test.git D:\temp\test
Remove-Item -Recurse -Force D:\temp\test
```

**Configure Git proxy (if behind corporate firewall):**
```powershell
git config --global http.proxy http://proxy.company.com:8080
git config --global https.proxy https://proxy.company.com:8080
```

## Performance Tuning for Windows

### For Limited Resources (4GB RAM, 2 cores)

```ini
[build]
max_concurrent_builds = 1
build_timeout_minutes = 20
gradle_memory_gb = 2
```

### For Powerful Server (16GB+ RAM, 8+ cores)

```ini
[build]
max_concurrent_builds = 5
build_timeout_minutes = 45
gradle_memory_gb = 6
```

### For SSD Storage

```ini
[cleanup]
max_repo_size_gb = 10
gradle_cache_retention_days = 60
```

## Automated Backup Script

Create `backup.ps1`:

```powershell
# Backup database
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "D:\fdroid_workspace\database\backups\manual_$timestamp.db"
Copy-Item D:\fdroid_workspace\database\service_state.db $backupPath

# Compress old backups
Get-ChildItem D:\fdroid_workspace\database\backups\*.db | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7)
} | ForEach-Object {
    Compress-Archive -Path $_.FullName -DestinationPath "$($_.FullName).zip"
    Remove-Item $_.FullName
}

Write-Host "Backup completed: $backupPath"
```

**Schedule with Task Scheduler:**
```powershell
# Create scheduled task for daily backup at 3 AM
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument '-File D:\fdroid-auto-fetcher\backup.ps1'
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "FDroidAutoBuilder-Backup" -Action $action -Trigger $trigger -RunLevel Highest
```

## Update Service

```powershell
# Stop service
nssm stop FDroidAutoBuilder

# Update code (if from git)
cd D:\fdroid-auto-fetcher
git pull

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart service
nssm start FDroidAutoBuilder
```

## Complete Uninstall

```powershell
# Stop and remove service
nssm stop FDroidAutoBuilder
nssm remove FDroidAutoBuilder confirm

# Remove workspace
Remove-Item -Recurse -Force D:\fdroid_workspace

# Remove service files
Remove-Item -Recurse -Force D:\fdroid-auto-fetcher

# Optional: Remove Java, Python, Git if no longer needed
```

## Support and Logs

For troubleshooting:

1. Check NSSM logs: `D:\fdroid_workspace\logs\service.stdout.log`
2. Check service logs: `D:\fdroid_workspace\logs\service.log`
3. Check Windows Event Viewer: `eventvwr.msc`
4. Check health endpoint: `http://localhost:8080/health`
5. Review build logs: `D:\fdroid_workspace\builds\{app_id}\logs\`

## Security Best Practices

1. **Use non-admin account for service:**
   ```powershell
   # Create service account
   net user fdroid_svc <password> /add
   net localgroup Users fdroid_svc /add
   
   # Grant permissions
   icacls D:\fdroid_workspace /grant fdroid_svc:(OI)(CI)F
   icacls D:\fdroid-auto-fetcher /grant fdroid_svc:(OI)(CI)RX
   
   # Set service to run as this user
   nssm set FDroidAutoBuilder ObjectName .\fdroid_svc <password>
   ```

2. **Restrict health check access:**
   - Change `http_host = 127.0.0.1` in config.ini for localhost only
   - Use firewall rules to limit access

3. **Regular updates:**
   - Keep Python, Git, Java updated
   - Update Python packages monthly: `pip install -r requirements.txt --upgrade`
