# F-Droid 自动构建服务最终方案（Windows Server 非C盘部署版）

## 🎯 服务目标
长期稳定运行在 Windows Server 上，自动拉取 F-Droid App 源码并本地 Gradle 编译，所有资源文件明确避开 C 盘存储。

## 📁 核心目录结构

```
D:\fdroid_workspace\          # 工作空间根目录（可通过环境变量配置）
├── sources\                  # 源码目录
│   ├── com.example.app1\    
│   └── com.example.app2\    
├── builds\                   # 构建输出
│   ├── com.example.app1\
│   │   ├── apks\           # 生成的APK文件
│   │   └── logs\           # 单次构建日志
├── cache\                    # 缓存目录
│   └── gradle\              # ⭐专门的Gradle缓存
│       ├── caches\          # Gradle构建缓存
│       └── wrapper\dists\   # Gradle版本分发
├── logs\                     # 服务日志
│   ├── service.log          # 主服务日志
│   ├── apps\                # 各app构建历史日志
│   └── service.stdout.log   # NSSM标准输出
├── database\                 # 数据库文件
│   └── service_state.db     # SQLite数据库
└── temp\                     # 临时文件
```

## 🏗️ 系统架构

### 核心流程
```
F-Droid元数据获取 → 仓库管理 → Gradle构建 → 结果分类 → 定期清理
```

### 架构图
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  任务调度中心    │    │  数据存储层     │    │  外部依赖       │
│  - APScheduler  │◄──►│  - SQLite      │◄──►│  - Git         │
│  - 任务队列     │    │  - 文件系统     │    │  - Gradle      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                         │                      │
         ▼                         ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   核心业务处理层                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │仓库管理器   │  │构建执行器   │  │清理模块     │         │
│  │- clone     │  │- gradle构建 │  │- 空间清理   │         │
│  │- update    │  │- 超时控制   │  │- 失败清理   │         │
│  │- 状态检查  │  │- 资源监控   │  │- 日志清理   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 技术栈详述

| 组件 | 选型 | 配置说明 |
|------|------|----------|
| **任务调度** | APScheduler | BackgroundScheduler + SQLite持久化 |
| **数据存储** | SQLite + 文件系统 | 元数据存数据库，源码和日志存文件系统 |
| **Git操作** | GitPython + subprocess | GitPython主用，subprocess备用 |
| **构建执行** | subprocess + psutil | 子进程执行 + 资源监控 |
| **路径管理** | 自定义PathManager | 集中管理所有路径，强制非C盘 |
| **日志系统** | logging + RotatingFileHandler | 结构化日志，JSON格式输出 |
| **服务管理** | NSSM | 自动重启，故障恢复 |

## 📋 核心模块设计

### 1. 路径管理器 (PathManager)
```python
# 核心功能：统一管理所有资源路径，确保零C盘占用
class PathManager:
    def __init__(self, workspace_root='D:\\fdroid_workspace'):
        self.workspace_root = Path(workspace_root)
        # 设置GRADLE_USER_HOME环境变量
        os.environ['GRADLE_USER_HOME'] = str(self.gradle_cache)
```

### 2. 增强型任务调度器
```python
scheduler_config = {
    'fetch_repos': {
        'trigger': 'interval',
        'hours': 24,
        'max_instances': 1
    },
    'build_test': {
        'trigger': 'interval', 
        'hours': 6,
        'max_instances': 3  # 允许并行构建
    },
    'cleanup': {
        'trigger': 'cron',
        'day_of_week': 'sun',  # 每周日执行
        'hour': 2
    }
}
```

### 3. 智能仓库获取器
- **数据源**：F-Droid官方索引 + 备用镜像
- **验证机制**：SHA256校验，防数据篡改
- **URL提取**：Git > SVN > 其他 的优先级策略

### 4. 健壮仓库管理器
**错误处理策略：**
- Clone失败：3次重试，指数退避
- Update冲突：备份冲突文件，强制更新
- 网络问题：自动切换镜像源

### 5. Gradle构建执行器
**关键特性：**
- 环境预检（gradlew、build.gradle、Java版本）
- 资源限制（CPU、内存、超时控制）
- 专用缓存路径（强制使用D:\fdroid_workspace\cache\gradle）

### 6. 状态数据库设计
```sql
-- 主表：app_info
CREATE TABLE app_info (
    app_id TEXT PRIMARY KEY,
    git_url TEXT,
    last_fetch_time DATETIME,
    last_build_time DATETIME,
    build_status TEXT,  # success/fail/pending
    consecutive_failures INTEGER,
    repo_size INTEGER,
    last_attempt_time DATETIME,
    build_duration INTEGER
);

-- 历史表：build_history
CREATE TABLE build_history (
    id INTEGER PRIMARY KEY,
    app_id TEXT,
    build_time DATETIME,
    status TEXT,
    duration INTEGER,
    log_path TEXT,
    apk_size INTEGER
);
```

## ⚙️ 任务流程详解

### 1. 仓库获取与克隆流程
```
开始 → 下载F-Droid索引 → 解析app列表 → 过滤已有app
     → 对新app尝试克隆 → 验证仓库完整性 → 更新数据库 → 结束
```

**克隆优化：**
- 使用`--depth=1`浅克隆加速
- 失败时尝试不同协议(https/ssh)

### 2. 构建执行流程
```
开始 → 环境检查 → 依赖预下载 → 执行构建 → 监控资源
     → 超时处理 → 结果收集 → 数据库更新 → 结束
```

### 3. 智能清理流程
```python
cleanup_strategies = {
    'failure_based': {
        'max_consecutive_failures': 3,
        'failure_period_days': 30
    },
    'time_based': {
        'inactive_days': 30,
        'last_success_days': 90
    },
    'space_based': {
        'max_repo_size_gb': 5,
        'total_workspace_size_gb': 100
    },
    'cache_cleanup': {
        'gradle_cache_retention_days': 30
    }
}
```

## 🚀 Windows Server 部署方案

### 1. NSSM服务配置 (推荐)
```ini
; service_config.ini
[Service]
Application=%PYTHON_PATH%\python.exe
Arguments=main.py
WorkingDirectory=D:\fdroid_workspace  # 明确指定
AppStdout=D:\fdroid_workspace\logs\service.stdout.log
AppStderr=D:\fdroid_workspace\logs\service.stderr.log
AppExit: Default=Restart
AppRestartDelay=5000
```

### 2. 环境准备清单
**前置依赖：**
- [ ] Git for Windows 2.30+ (安装时选择非C盘路径)
- [ ] Java JDK 8/11/17 (安装到D盘)
- [ ] Python 3.8+ (安装到D盘)
- [ ] 磁盘空间：200GB+ 推荐

### 3. 部署脚本
```batch
@echo off
REM deployment_setup.bat
set FDROID_WORKSPACE=D:\fdroid_workspace
set GRADLE_USER_HOME=D:\fdroid_workspace\cache\gradle

REM 注册服务
nssm install FDroidBuilder D:\Python\python.exe main.py
nssm set FDroidBuilder AppDirectory D:\fdroid_workspace
```

## 📊 监控与运维

### 1. 健康检查
```python
@app.route('/health')
def health_check():
    return {
        'status': 'healthy',
        'timestamp': datetime.now(),
        'workspace': str(path_mgr.workspace_root),
        'disk_free_gb': get_disk_usage(),
        'active_apps': get_active_app_count()
    }
```

### 2. 日志系统
- **格式**：结构化JSON日志
- **轮转**：按大小和时间自动轮转
- **存储**：所有日志文件位于D:\fdroid_workspace\logs\

### 3. 预警机制
**触发条件：**
- 磁盘空间 < 15%

## 🔒 安全与维护

### 1. 安全措施
- 定期依赖版本检查
- 输入数据验证和过滤
- 构建环境隔离

### 2. 数据备份
- 数据库：每日自动备份
- 配置：版本控制管理
- 构建结果：选择性归档

## ✅ 方案优势总结

该最终方案确保：

✔ **零C盘占用**：所有资源明确指定非系统盘路径  
✔ **长期稳定**：NSSM服务管理，自动重启  
✔ **资源可控**：Gradle缓存集中管理，定期清理  
✔ **错误容忍**：智能重试机制，优雅降级  
✔ **易于运维**：结构化日志，健康检查，预警机制  
✔ **可扩展性**：模块化设计，支持未来功能扩展  
✔ **部署友好**：环境变量配置，适应不同服务器环境  

这个方案完全满足您的工程化需求，可以在 Windows Server 上长期稳定运行，同时确保系统盘的纯净。
