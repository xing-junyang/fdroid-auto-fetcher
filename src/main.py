"""
Main service controller for F-Droid Auto-Builder.
"""

import logging
import random
import signal
import sys
import configparser
import time
from pathlib import Path
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from core.path_manager import PathManager
from core.database import Database
from core.logger import setup_logging
from tasks.metadata_fetcher import MetadataFetcher
from tasks.repository_manager import RepositoryManager
from tasks.build_executor import BuildExecutor
from tasks.cleanup_manager import CleanupManager
from utils.health_check import HealthCheckServer

logger = logging.getLogger(__name__)


class FDroidAutoBuilder:
    """Main service controller."""
    
    def __init__(self, config_path: str = 'config.ini'):
        """
        Initialize service.
        
        Args:
            config_path: Path to configuration file
        """
        self.running = False
        self.scheduler = None
        self.health_server = None
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize components
        self._initialize_components()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("F-Droid Auto-Builder initialized")
    
    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        """Load configuration from INI file."""
        config = configparser.ConfigParser()
        config.read(config_path)
        return config
    
    def _initialize_components(self):
        """Initialize all service components."""
        # Path Manager
        workspace_root = self.config.get('workspace', 'root_path', fallback='/data/fdroid_workspace')
        validate_non_c = self.config.getboolean('workspace', 'validate_non_c_drive', fallback=False)
        
        self.path_manager = PathManager(workspace_root, validate_non_c)
        self.path_manager.initialize_directories()
        
        # Setup logging
        log_level = self.config.get('logging', 'log_level', fallback='INFO')
        max_log_mb = self.config.getint('logging', 'max_log_file_mb', fallback=50)
        backup_count = self.config.getint('logging', 'log_backup_count', fallback=10)
        json_format = self.config.getboolean('logging', 'json_format', fallback=True)
        
        setup_logging(
            self.path_manager.service_log_path,
            log_level=log_level,
            max_bytes=max_log_mb * 1024 * 1024,
            backup_count=backup_count,
            json_format=json_format,
            console_output=True
        )
        
        # Database
        self.db = Database(self.path_manager.service_db_path)
        
        # Task components
        self.metadata_fetcher = MetadataFetcher(
            index_url=self.config.get('fdroid', 'index_url'),
            mirror_url=self.config.get('fdroid', 'mirror_url', fallback=None),
            git_only=self.config.getboolean('fdroid', 'git_only', fallback=True)
        )
        
        self.repo_manager = RepositoryManager(
            clone_timeout=self.config.getint('git', 'clone_timeout', fallback=600),
            fetch_timeout=self.config.getint('git', 'fetch_timeout', fallback=300),
            shallow_clone=self.config.getboolean('git', 'shallow_clone', fallback=True),
            max_retries=self.config.getint('git', 'max_retries', fallback=3)
        )
        
        self.build_executor = BuildExecutor(
            build_timeout=self.config.getint('build', 'build_timeout_minutes', fallback=30) * 60,
            memory_limit_gb=self.config.getint('build', 'gradle_memory_gb', fallback=4),
            metaspace_mb=self.config.getint('build', 'gradle_metaspace_mb', fallback=512),
            gradle_cache_dir=self.path_manager.gradle_cache_dir
        )
        
        self.cleanup_manager = CleanupManager(
            path_manager=self.path_manager,
            database=self.db,
            max_repo_size_gb=self.config.getint('cleanup', 'max_repo_size_gb', fallback=5),
            inactive_days=self.config.getint('cleanup', 'inactive_days', fallback=90),
            cache_retention_days=self.config.getint('cleanup', 'gradle_cache_retention_days', fallback=30),
            max_consecutive_failures=self.config.getint('build', 'max_consecutive_failures', fallback=3)
        )
        
        # Health check server (optional)
        if self.config.getboolean('health_check', 'enable_http_server', fallback=False):
            self.health_server = HealthCheckServer(
                path_manager=self.path_manager,
                database=self.db,
                scheduler=None,  # Will be set after scheduler is created
                host=self.config.get('health_check', 'http_host', fallback='0.0.0.0'),
                port=self.config.getint('health_check', 'http_port', fallback=8080)
            )
            logger.info("Health check server configured")
    
    def _setup_scheduler(self):
        """Setup APScheduler with job store."""
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 3600,
            }
        )
        
        # Add scheduled jobs
        self.scheduler.add_job(
            self.task_fetch_metadata,
            'interval',
            hours=self.config.getint('scheduler', 'fetch_metadata_interval_hours', fallback=24),
            id='fetch_metadata',
            name='Fetch F-Droid Metadata',
            replace_existing=True,
            next_run_time=datetime.now()  # 立即执行
        )
        
        self.scheduler.add_job(
            self.task_clone_repos,
            'interval',
            hours=self.config.getint('scheduler', 'clone_repos_interval_hours', fallback=6),
            id='clone_repos',
            name='Clone New Repositories',
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(seconds=30)  # 30秒后执行
        )
        
        self.scheduler.add_job(
            self.task_update_repos,
            'interval',
            hours=self.config.getint('scheduler', 'update_repos_interval_hours', fallback=12),
            id='update_repos',
            name='Update Repositories',
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(minutes=1)  # 1分钟后执行
        )
        
        self.scheduler.add_job(
            self.task_build_apps,
            'interval',
            hours=self.config.getint('scheduler', 'build_interval_hours', fallback=6),
            id='build_apps',
            name='Build Applications',
            max_instances=self.config.getint('build', 'max_concurrent_builds', fallback=3),
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(minutes=2)  # 2分钟后执行
        )
        
        self.scheduler.add_job(
            self.task_cleanup,
            'cron',
            day_of_week=self.config.getint('scheduler', 'cleanup_day_of_week', fallback=6),
            hour=self.config.getint('scheduler', 'cleanup_hour', fallback=2),
            id='cleanup',
            name='Cleanup Resources',
            replace_existing=True
        )
        
        self.scheduler.add_job(
            self.task_backup_database,
            'cron',
            hour=self.config.getint('scheduler', 'backup_hour', fallback=3),
            id='backup_database',
            name='Backup Database',
            replace_existing=True
        )
        
        logger.info("Scheduler configured with jobs")
    
    # Task implementations
    
    def task_fetch_metadata(self):
        """Fetch and update F-Droid metadata."""
        task_id = self.db.start_task_execution('fetch_metadata')
        try:
            logger.info("Starting metadata fetch task")
            
            index_data = self.metadata_fetcher.fetch_index()
            if not index_data:
                raise Exception("Failed to fetch index")
            
            apps = self.metadata_fetcher.extract_apps(index_data)
            
            new_count = 0
            updated_count = 0
            
            for app in apps:
                if not self.metadata_fetcher.validate_url(app['git_url']):
                    continue
                
                existing = self.db.get_app_info(app['app_id'])
                
                if existing:
                    if existing['git_url'] != app['git_url']:
                        self.db.update_app_git_url(app['app_id'], app['git_url'])
                        updated_count += 1
                else:
                    self.db.insert_app(app['app_id'], app['git_url'])
                    new_count += 1
            
            result_summary = {
                'total_apps': len(apps),
                'new_apps': new_count,
                'updated_apps': updated_count
            }
            
            self.db.end_task_execution(task_id, 'completed', result_summary)
            logger.info(f"Metadata fetch completed: {result_summary}")
        
        except Exception as e:
            logger.error(f"Metadata fetch failed: {e}", exc_info=True)
            if task_id:
                self.db.end_task_execution(task_id, 'failed', {'error': str(e)})
    
    def task_clone_repos(self):
        """Clone new repositories."""
        task_id = self.db.start_task_execution('clone_repos')
        try:
            logger.info("Starting clone repos task")
            
            apps = self.db.get_all_apps()
            success_count = 0
            failed_count = 0
            
            for app in apps:
                # Skip if already cloned
                source_dir = self.path_manager.get_app_source_dir(app['app_id'])
                if source_dir.exists():
                    continue
                
                try:
                    success, error = self.repo_manager.clone_repository(
                        app['git_url'],
                        source_dir,
                        app['app_id']
                    )
                    
                    if success:
                        repo_size = self.repo_manager.get_repository_size(source_dir)
                        self.db.update_app_fetch_time(app['app_id'], repo_size)
                        success_count += 1
                    else:
                        failed_count += 1
                
                except Exception as e:
                    logger.error(f"Clone error for {app['app_id']}: {e}", exc_info=True)
                    failed_count += 1

                time.sleep(random.uniform(1, 5))
            
            result_summary = {'success': success_count, 'failed': failed_count}
            self.db.end_task_execution(task_id, 'completed', result_summary)
            logger.info(f"Clone repos completed: {result_summary}")
        
        except Exception as e:
            logger.error(f"Clone repos task failed: {e}", exc_info=True)
            if task_id:
                self.db.end_task_execution(task_id, 'failed', {'error': str(e)})
    
    def task_update_repos(self):
        """Update existing repositories."""
        task_id = self.db.start_task_execution('update_repos')
        try:
            logger.info("Starting update repos task")
            
            apps = self.db.get_all_apps()
            success_count = 0
            failed_count = 0
            
            for app in apps:
                source_dir = self.path_manager.get_app_source_dir(app['app_id'])
                if not source_dir.exists():
                    continue
                
                try:
                    success, error = self.repo_manager.update_repository(
                        source_dir,
                        app['app_id']
                    )
                    
                    if success:
                        repo_size = self.repo_manager.get_repository_size(source_dir)
                        self.db.update_app_fetch_time(app['app_id'], repo_size)
                        success_count += 1
                    else:
                        failed_count += 1
                
                except Exception as e:
                    logger.error(f"Update error for {app['app_id']}: {e}", exc_info=True)
                    failed_count += 1

                time.sleep(random.uniform(1, 5))
            
            result_summary = {'success': success_count, 'failed': failed_count}
            self.db.end_task_execution(task_id, 'completed', result_summary)
            logger.info(f"Update repos completed: {result_summary}")
        
        except Exception as e:
            logger.error(f"Update repos task failed: {e}", exc_info=True)
            if task_id:
                self.db.end_task_execution(task_id, 'failed', {'error': str(e)})
    
    def task_build_apps(self):
        """Build applications."""
        task_id = self.db.start_task_execution('build_apps')
        try:
            logger.info("Starting build apps task")
            
            max_failures = self.config.getint('build', 'max_consecutive_failures', fallback=3)
            apps = self.db.get_apps_for_build(max_failures)
            
            success_count = 0
            failed_count = 0
            
            for app in apps:
                source_dir = self.path_manager.get_app_source_dir(app['app_id'])
                if not source_dir.exists():
                    logger.warning(f"Source not found for {app['app_id']}, skipping build")
                    continue
                
                try:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    build_log_path = self.path_manager.get_build_log_path(app['app_id'], timestamp)
                    
                    success, duration, error_msg, java_version = self.build_executor.build_app(
                        source_dir,
                        app['app_id'],
                        build_log_path
                    )
                    
                    if success:
                        # Find and copy APK files
                        apks = self.build_executor.find_apk_files(source_dir)
                        apk_size = None
                        
                        if apks:
                            apk_dir = self.path_manager.get_app_apk_dir(app['app_id'])
                            dest = self.build_executor.copy_apk_to_output(apks[0], apk_dir, app['app_id'])
                            if dest:
                                apk_size = dest.stat().st_size
                        
                        self.db.update_build_result(app['app_id'], True, duration)
                        self.db.insert_build_history(
                            app['app_id'],
                            'success',
                            duration,
                            str(build_log_path.relative_to(self.path_manager.workspace_root)),
                            apk_size,
                            java_version=java_version
                        )
                        success_count += 1
                    else:
                        self.db.update_build_result(app['app_id'], False, duration, error_msg)
                        self.db.insert_build_history(
                            app['app_id'],
                            'fail',
                            duration,
                            str(build_log_path.relative_to(self.path_manager.workspace_root)),
                            error_message=error_msg,
                            java_version=java_version
                        )
                        failed_count += 1
                
                except Exception as e:
                    logger.error(f"Build error for {app['app_id']}: {e}", exc_info=True)
                    self.db.update_build_result(app['app_id'], False, error_message=str(e))
                    failed_count += 1
            
            result_summary = {'success': success_count, 'failed': failed_count}
            self.db.end_task_execution(task_id, 'completed', result_summary)
            logger.info(f"Build apps completed: {result_summary}")
        
        except Exception as e:
            logger.error(f"Build apps task failed: {e}", exc_info=True)
            if task_id:
                self.db.end_task_execution(task_id, 'failed', {'error': str(e)})
    
    def task_cleanup(self):
        """Cleanup workspace."""
        task_id = self.db.start_task_execution('cleanup')
        try:
            logger.info("Starting cleanup task")
            
            # Check disk usage
            disk_usage = self.path_manager.get_disk_usage()
            emergency_threshold = self.config.getint('cleanup', 'emergency_cleanup_threshold', fallback=95)
            
            emergency = disk_usage['usage_percent'] >= emergency_threshold
            
            summary = self.cleanup_manager.run_cleanup(emergency)
            
            self.db.end_task_execution(task_id, 'completed', summary)
            logger.info(f"Cleanup completed: {summary}")
        
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}", exc_info=True)
            if task_id:
                self.db.end_task_execution(task_id, 'failed', {'error': str(e)})
    
    def task_backup_database(self):
        """Backup database."""
        try:
            logger.info("Starting database backup")
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = self.path_manager.database_backup_dir / f"service_state_{timestamp}.db"
            
            success = self.db.backup(backup_path)
            
            if success:
                logger.info(f"Database backup successful: {backup_path}")
            else:
                logger.error("Database backup failed")
        
        except Exception as e:
            logger.error(f"Database backup error: {e}", exc_info=True)
    
    def start(self):
        """Start the service."""
        logger.info("Starting F-Droid Auto-Builder service")
        self.running = True
        
        self._setup_scheduler()
        
        # Update health server with scheduler reference
        if self.health_server:
            self.health_server.scheduler = self.scheduler
            self.health_server.start()
        
        self.scheduler.start()
        
        logger.info("Service started successfully")

        logger.info(f"Scheduler state: {self.scheduler.state}")
        logger.info(f"Number of scheduled jobs: {len(self.scheduler.get_jobs())}")
        
        logger.info("Service started successfully")
        
        # Keep service running
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        
        self.stop()
    
    def stop(self):
        """Stop the service gracefully."""
        logger.info("Stopping service...")
        self.running = False
        
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")
        
        if self.health_server:
            self.health_server.stop()
            logger.info("Health check server stopped")
        
        logger.info("Service stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {signum}")
        self.stop()
        sys.exit(0)


def main():
    """Main entry point."""
    import sys
    
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.ini'
    
    service = FDroidAutoBuilder(config_path)
    service.start()


if __name__ == '__main__':
    main()
