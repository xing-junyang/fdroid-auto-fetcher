"""
Cleanup manager with multiple cleanup strategies.
"""

import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class CleanupManager:
    """Manages workspace cleanup with multiple strategies."""
    
    def __init__(
        self,
        path_manager,
        database,
        max_repo_size_gb: int = 5,
        inactive_days: int = 90,
        cache_retention_days: int = 30,
        max_consecutive_failures: int = 3
    ):
        """
        Initialize cleanup manager.
        
        Args:
            path_manager: PathManager instance
            database: Database instance
            max_repo_size_gb: Maximum size for single repository
            inactive_days: Days of inactivity before cleanup
            cache_retention_days: Days to keep cache files
            max_consecutive_failures: Failures threshold for cleanup
        """
        self.path_manager = path_manager
        self.db = database
        self.max_repo_size_gb = max_repo_size_gb
        self.inactive_days = inactive_days
        self.cache_retention_days = cache_retention_days
        self.max_consecutive_failures = max_consecutive_failures
    
    def run_cleanup(self, emergency: bool = False) -> Dict[str, Any]:
        """
        Run cleanup operations.
        
        Args:
            emergency: If True, perform aggressive cleanup
            
        Returns:
            Cleanup summary statistics
        """
        logger.info(f"Starting {'emergency' if emergency else 'normal'} cleanup")
        
        summary = {
            'repos_deleted': 0,
            'space_freed_gb': 0,
            'cache_cleaned': False,
            'logs_rotated': False
        }
        
        if emergency:
            summary.update(self._emergency_cleanup())
        else:
            summary.update(self._normal_cleanup())
        
        logger.info(f"Cleanup completed: {summary}")
        return summary
    
    def _normal_cleanup(self) -> Dict[str, Any]:
        """Perform normal cleanup operations."""
        summary = {'repos_deleted': 0, 'space_freed_gb': 0}
        
        # Cleanup failed repos
        failed_cleaned = self._cleanup_failed_repos()
        summary['repos_deleted'] += failed_cleaned['count']
        summary['space_freed_gb'] += failed_cleaned['space_gb']
        
        # Cleanup inactive repos
        inactive_cleaned = self._cleanup_inactive_repos()
        summary['repos_deleted'] += inactive_cleaned['count']
        summary['space_freed_gb'] += inactive_cleaned['space_gb']
        
        # Cleanup oversized repos
        oversized_cleaned = self._cleanup_oversized_repos()
        summary['repos_deleted'] += oversized_cleaned['count']
        summary['space_freed_gb'] += oversized_cleaned['space_gb']
        
        # Clean cache
        summary['cache_cleaned'] = self._cleanup_gradle_cache()
        
        return summary
    
    def _emergency_cleanup(self) -> Dict[str, Any]:
        """Perform aggressive emergency cleanup."""
        logger.warning("Performing emergency cleanup due to low disk space")
        
        summary = {'repos_deleted': 0, 'space_freed_gb': 0}
        
        # Delete ALL failed repos immediately
        all_failed = self._delete_all_failed_repos()
        summary['repos_deleted'] += all_failed['count']
        summary['space_freed_gb'] += all_failed['space_gb']
        
        # Delete largest repos
        largest_cleaned = self._delete_largest_repos()
        summary['repos_deleted'] += largest_cleaned['count']
        summary['space_freed_gb'] += largest_cleaned['space_gb']
        
        # Purge all cache
        summary['cache_cleaned'] = self._purge_all_cache()
        
        return summary
    
    def _cleanup_failed_repos(self) -> Dict[str, Any]:
        """
        Cleanup repositories with consecutive failures.
        
        Returns:
            Dictionary with cleanup statistics
        """
        count = 0
        space_freed = 0
        
        try:
            apps = self.db.get_all_apps()
            cutoff_date = datetime.now() - timedelta(days=30)
            
            for app in apps:
                if (app['consecutive_failures'] >= self.max_consecutive_failures and
                    app['last_attempt_time'] and
                    datetime.fromisoformat(app['last_attempt_time']) < cutoff_date):
                    
                    size = self._delete_app_data(app['app_id'])
                    if size > 0:
                        count += 1
                        space_freed += size
                        logger.info(
                            f"Deleted failed app {app['app_id']} "
                            f"({app['consecutive_failures']} failures)"
                        )
        
        except Exception as e:
            logger.error(f"Failed repos cleanup error: {e}", exc_info=True)
        
        return {'count': count, 'space_gb': space_freed / (1024**3)}
    
    def _cleanup_inactive_repos(self) -> Dict[str, Any]:
        """Cleanup repositories with no recent activity."""
        count = 0
        space_freed = 0
        
        try:
            apps = self.db.get_all_apps()
            cutoff_date = datetime.now() - timedelta(days=self.inactive_days)
            
            for app in apps:
                last_activity = app.get('last_build_time') or app.get('last_attempt_time')
                
                if last_activity and datetime.fromisoformat(last_activity) < cutoff_date:
                    size = self._delete_app_data(app['app_id'])
                    if size > 0:
                        count += 1
                        space_freed += size
                        logger.info(f"Deleted inactive app {app['app_id']}")
        
        except Exception as e:
            logger.error(f"Inactive repos cleanup error: {e}", exc_info=True)
        
        return {'count': count, 'space_gb': space_freed / (1024**3)}
    
    def _cleanup_oversized_repos(self) -> Dict[str, Any]:
        """Cleanup repositories exceeding size limit."""
        count = 0
        space_freed = 0
        
        try:
            apps = self.db.get_all_apps()
            max_size_bytes = self.max_repo_size_gb * (1024**3)
            
            for app in apps:
                if app.get('repo_size') and app['repo_size'] > max_size_bytes:
                    # Only delete if not recently successful
                    if app['build_status'] != 'success' or not app.get('last_build_time'):
                        size = self._delete_app_data(app['app_id'])
                        if size > 0:
                            count += 1
                            space_freed += size
                            size_gb = app['repo_size'] / (1024**3)
                            logger.info(f"Deleted oversized app {app['app_id']} ({size_gb:.2f}GB)")
        
        except Exception as e:
            logger.error(f"Oversized repos cleanup error: {e}", exc_info=True)
        
        return {'count': count, 'space_gb': space_freed / (1024**3)}
    
    def _delete_all_failed_repos(self) -> Dict[str, Any]:
        """Delete ALL repos with failure status."""
        count = 0
        space_freed = 0
        
        try:
            apps = self.db.get_all_apps()
            
            for app in apps:
                if app['build_status'] == 'fail':
                    size = self._delete_app_data(app['app_id'])
                    if size > 0:
                        count += 1
                        space_freed += size
        
        except Exception as e:
            logger.error(f"Delete all failed repos error: {e}", exc_info=True)
        
        return {'count': count, 'space_gb': space_freed / (1024**3)}
    
    def _delete_largest_repos(self, count: int = 10) -> Dict[str, Any]:
        """Delete largest repositories."""
        deleted_count = 0
        space_freed = 0
        
        try:
            apps = self.db.get_all_apps()
            
            # Sort by size descending
            sorted_apps = sorted(
                [a for a in apps if a.get('repo_size')],
                key=lambda x: x['repo_size'],
                reverse=True
            )
            
            for app in sorted_apps[:count]:
                size = self._delete_app_data(app['app_id'])
                if size > 0:
                    deleted_count += 1
                    space_freed += size
                    logger.warning(f"Emergency deleted large repo {app['app_id']}")
        
        except Exception as e:
            logger.error(f"Delete largest repos error: {e}", exc_info=True)
        
        return {'count': deleted_count, 'space_gb': space_freed / (1024**3)}
    
    def _delete_app_data(self, app_id: str) -> int:
        """
        Delete all data for an app.
        
        Returns:
            Size freed in bytes
        """
        total_size = 0
        
        try:
            # Get sizes before deletion
            source_dir = self.path_manager.get_app_source_dir(app_id)
            build_dir = self.path_manager.get_app_build_dir(app_id)
            
            if source_dir.exists():
                total_size += self.path_manager.get_directory_size(source_dir)
                shutil.rmtree(source_dir, ignore_errors=True)
            
            if build_dir.exists():
                total_size += self.path_manager.get_directory_size(build_dir)
                shutil.rmtree(build_dir, ignore_errors=True)
            
            # Delete from database
            self.db.delete_app(app_id)
        
        except Exception as e:
            logger.error(f"Failed to delete app data for {app_id}: {e}")
        
        return total_size
    
    def _cleanup_gradle_cache(self) -> bool:
        """Cleanup old Gradle cache files."""
        try:
            cutoff_time = datetime.now().timestamp() - (self.cache_retention_days * 86400)
            deleted_count = 0
            
            if not self.path_manager.gradle_cache_dir.exists():
                return False
            
            for cache_file in self.path_manager.gradle_cache_dir.rglob('*'):
                if cache_file.is_file():
                    try:
                        if cache_file.stat().st_mtime < cutoff_time:
                            cache_file.unlink()
                            deleted_count += 1
                    except (OSError, PermissionError):
                        continue
            
            logger.info(f"Cleaned {deleted_count} old Gradle cache files")
            return True
        
        except Exception as e:
            logger.error(f"Gradle cache cleanup error: {e}")
            return False
    
    def _purge_all_cache(self) -> bool:
        """Purge entire Gradle cache."""
        try:
            if self.path_manager.gradle_cache_dir.exists():
                shutil.rmtree(self.path_manager.gradle_cache_dir, ignore_errors=True)
                self.path_manager.gradle_cache_dir.mkdir(parents=True, exist_ok=True)
                logger.warning("Purged all Gradle cache")
                return True
        except Exception as e:
            logger.error(f"Gradle cache purge error: {e}")
        
        return False
