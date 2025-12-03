"""
Path Manager - Centralized path management for all workspace resources.
Ensures all file operations occur in the configured workspace directory.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PathManager:
    """Manages all file paths for the F-Droid auto-builder service."""
    
    def __init__(self, workspace_root: str, validate_non_c_drive: bool = True):
        """
        Initialize PathManager with workspace root.
        
        Args:
            workspace_root: Absolute path to workspace root directory
            validate_non_c_drive: If True, validates workspace is not on C: drive (Windows only)
        
        Raises:
            ValueError: If workspace_root is on C: drive and validation is enabled
        """
        self.workspace_root = Path(workspace_root).resolve()
        
        # Validate non-C drive requirement for Windows
        if validate_non_c_drive and os.name == 'nt':
            drive_letter = str(self.workspace_root.drive).upper()
            if drive_letter == 'C:':
                raise ValueError(
                    f"Workspace root cannot be on C: drive. "
                    f"Current path: {self.workspace_root}"
                )
        
        # Define all directory paths
        self.sources_dir = self.workspace_root / 'sources'
        self.builds_dir = self.workspace_root / 'builds'
        self.cache_dir = self.workspace_root / 'cache'
        self.gradle_cache_dir = self.cache_dir / 'gradle'
        self.logs_dir = self.workspace_root / 'logs'
        self.database_dir = self.workspace_root / 'database'
        self.temp_dir = self.workspace_root / 'temp'
        
        # App-specific log directory
        self.app_logs_dir = self.logs_dir / 'apps'
        
        # Database files
        self.service_db_path = self.database_dir / 'service_state.db'
        self.scheduler_db_path = self.database_dir / 'scheduler.db'
        self.database_backup_dir = self.database_dir / 'backups'
        
        # Main service logs
        self.service_log_path = self.logs_dir / 'service.log'
        self.service_stdout_log = self.logs_dir / 'service.stdout.log'
        self.service_stderr_log = self.logs_dir / 'service.stderr.log'
        
        # Set GRADLE_USER_HOME environment variable
        os.environ['GRADLE_USER_HOME'] = str(self.gradle_cache_dir)
        
        logger.info(f"PathManager initialized with workspace: {self.workspace_root}")
        logger.info(f"GRADLE_USER_HOME set to: {self.gradle_cache_dir}")
    
    def initialize_directories(self):
        """Create all required directories if they don't exist."""
        directories = [
            self.workspace_root,
            self.sources_dir,
            self.builds_dir,
            self.cache_dir,
            self.gradle_cache_dir,
            self.logs_dir,
            self.app_logs_dir,
            self.database_dir,
            self.database_backup_dir,
            self.temp_dir,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
        
        logger.info("All workspace directories initialized")
    
    def get_app_source_dir(self, app_id: str) -> Path:
        """Get source directory path for a specific app."""
        self._validate_app_id(app_id)
        return self.sources_dir / app_id
    
    def get_app_build_dir(self, app_id: str) -> Path:
        """Get build output directory for a specific app."""
        self._validate_app_id(app_id)
        return self.builds_dir / app_id
    
    def get_app_apk_dir(self, app_id: str) -> Path:
        """Get APK output directory for a specific app."""
        self._validate_app_id(app_id)
        apk_dir = self.builds_dir / app_id / 'apks'
        apk_dir.mkdir(parents=True, exist_ok=True)
        return apk_dir
    
    def get_app_build_logs_dir(self, app_id: str) -> Path:
        """Get build logs directory for a specific app."""
        self._validate_app_id(app_id)
        log_dir = self.builds_dir / app_id / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def get_app_log_file(self, app_id: str) -> Path:
        """Get app-specific log file path."""
        self._validate_app_id(app_id)
        self.app_logs_dir.mkdir(parents=True, exist_ok=True)
        return self.app_logs_dir / f"{app_id}.log"
    
    def get_build_log_path(self, app_id: str, timestamp: str) -> Path:
        """Get path for a specific build log file."""
        self._validate_app_id(app_id)
        return self.get_app_build_logs_dir(app_id) / f"build_{timestamp}.log"
    
    def validate_path_in_workspace(self, path: Path) -> bool:
        """
        Validate that a path is within the workspace directory.
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is within workspace, False otherwise
        """
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(self.workspace_root)
            return True
        except (ValueError, RuntimeError):
            return False
    
    def _validate_app_id(self, app_id: str):
        """
        Validate app ID to prevent path traversal attacks.
        
        Args:
            app_id: Application identifier to validate
            
        Raises:
            ValueError: If app_id contains invalid characters
        """
        import re
        
        # Allow only alphanumeric, dots, underscores, and hyphens
        if not re.match(r'^[a-zA-Z0-9._-]+$', app_id):
            raise ValueError(
                f"Invalid app_id: {app_id}. "
                f"Only alphanumeric characters, dots, underscores, and hyphens are allowed."
            )
        
        # Reject path traversal attempts
        if '..' in app_id or '/' in app_id or '\\' in app_id:
            raise ValueError(
                f"Invalid app_id: {app_id}. "
                f"Path traversal attempts are not allowed."
            )
        
        # Maximum length check
        if len(app_id) > 255:
            raise ValueError(
                f"Invalid app_id: {app_id}. "
                f"Maximum length is 255 characters."
            )
    
    def get_disk_usage(self) -> dict:
        """
        Get disk usage information for the workspace.
        
        Returns:
            Dictionary with total, used, free space in GB and usage percentage
        """
        import shutil
        
        usage = shutil.disk_usage(self.workspace_root)
        
        return {
            'total_gb': usage.total / (1024**3),
            'used_gb': usage.used / (1024**3),
            'free_gb': usage.free / (1024**3),
            'usage_percent': (usage.used / usage.total) * 100
        }
    
    def get_directory_size(self, directory: Path) -> int:
        """
        Calculate total size of a directory recursively.
        
        Args:
            directory: Directory to calculate size for
            
        Returns:
            Size in bytes
        """
        total_size = 0
        try:
            for entry in directory.rglob('*'):
                if entry.is_file():
                    try:
                        total_size += entry.stat().st_size
                    except (OSError, PermissionError):
                        # Skip files we can't access
                        continue
        except (OSError, PermissionError):
            logger.warning(f"Could not calculate size for directory: {directory}")
        
        return total_size
    
    def __str__(self) -> str:
        return f"PathManager(workspace={self.workspace_root})"
    
    def __repr__(self) -> str:
        return self.__str__()
