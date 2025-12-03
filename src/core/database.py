"""
Database layer for F-Droid auto-builder service.
Handles all database operations with connection pooling and error handling.
"""

import sqlite3
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager with connection pooling and error handling."""
    
    # Database schema version
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Path):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Enable WAL mode for better concurrent access
        self._enable_wal_mode()
        
        # Initialize schema
        self._initialize_schema()
        
        logger.info(f"Database initialized at: {self.db_path}")
    
    def _enable_wal_mode(self):
        """Enable Write-Ahead Logging mode for better concurrency."""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
            logger.debug("WAL mode enabled")
        except sqlite3.Error as e:
            logger.warning(f"Failed to enable WAL mode: {e}")
    
    @contextmanager
    def get_connection(self, timeout: float = 30.0):
        """
        Context manager for database connections with automatic cleanup.
        
        Args:
            timeout: Connection timeout in seconds
            
        Yields:
            SQLite connection object
        """
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=timeout)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_with_retry(self, query: str, params: tuple = (), max_retries: int = 3) -> Any:
        """
        Execute query with retry logic for locked database scenarios.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            max_retries: Maximum number of retry attempts
            
        Returns:
            Query result
            
        Raises:
            sqlite3.Error: If query fails after all retries
        """
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    result = cursor.execute(query, params)
                    return result.fetchall() if query.strip().upper().startswith('SELECT') else None
            except sqlite3.OperationalError as e:
                if 'locked' in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
    
    def _initialize_schema(self):
        """Initialize database schema if not exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create app_info table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_info (
                    app_id TEXT PRIMARY KEY,
                    git_url TEXT NOT NULL,
                    last_fetch_time DATETIME,
                    last_build_time DATETIME,
                    build_status TEXT NOT NULL DEFAULT 'never_built',
                    consecutive_failures INTEGER DEFAULT 0,
                    repo_size INTEGER,
                    last_attempt_time DATETIME,
                    build_duration INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create build_history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS build_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    build_time DATETIME NOT NULL,
                    status TEXT NOT NULL,
                    duration INTEGER,
                    log_path TEXT,
                    apk_size INTEGER,
                    error_message TEXT,
                    gradle_version TEXT,
                    java_version TEXT,
                    FOREIGN KEY (app_id) REFERENCES app_info(app_id)
                )
            """)
            
            # Create task_execution_log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    status TEXT NOT NULL,
                    result_summary TEXT
                )
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_app_build_status 
                ON app_info(build_status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_app_last_build_time 
                ON app_info(last_build_time)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_build_history_app_id 
                ON build_history(app_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_build_history_time 
                ON build_history(build_time)
            """)
            
            logger.debug("Database schema initialized")
    
    # App Info operations
    
    def insert_app(self, app_id: str, git_url: str) -> bool:
        """
        Insert new app into database.
        
        Args:
            app_id: Application identifier
            git_url: Git repository URL
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_info (app_id, git_url, build_status)
                    VALUES (?, ?, 'never_built')
                    """,
                    (app_id, git_url)
                )
            logger.debug(f"Inserted app: {app_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to insert app {app_id}: {e}")
            return False
    
    def update_app_git_url(self, app_id: str, git_url: str) -> bool:
        """Update Git URL for an app."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE app_info 
                    SET git_url = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE app_id = ?
                    """,
                    (git_url, app_id)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update git_url for {app_id}: {e}")
            return False
    
    def update_app_fetch_time(self, app_id: str, repo_size: Optional[int] = None) -> bool:
        """Update last fetch time and optionally repo size."""
        try:
            with self.get_connection() as conn:
                if repo_size is not None:
                    conn.execute(
                        """
                        UPDATE app_info 
                        SET last_fetch_time = CURRENT_TIMESTAMP, 
                            repo_size = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE app_id = ?
                        """,
                        (repo_size, app_id)
                    )
                else:
                    conn.execute(
                        """
                        UPDATE app_info 
                        SET last_fetch_time = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE app_id = ?
                        """,
                        (app_id,)
                    )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update fetch time for {app_id}: {e}")
            return False
    
    def update_build_result(
        self,
        app_id: str,
        success: bool,
        duration: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update build result for an app.
        
        Args:
            app_id: Application identifier
            success: Whether build was successful
            duration: Build duration in seconds
            error_message: Error message if build failed
            
        Returns:
            True if successful
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get current consecutive failures
                cursor.execute(
                    "SELECT consecutive_failures FROM app_info WHERE app_id = ?",
                    (app_id,)
                )
                row = cursor.fetchone()
                current_failures = row[0] if row else 0
                
                if success:
                    new_status = 'success'
                    new_failures = 0
                    conn.execute(
                        """
                        UPDATE app_info 
                        SET build_status = ?,
                            consecutive_failures = ?,
                            last_build_time = CURRENT_TIMESTAMP,
                            last_attempt_time = CURRENT_TIMESTAMP,
                            build_duration = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE app_id = ?
                        """,
                        (new_status, new_failures, duration, app_id)
                    )
                else:
                    new_status = 'fail'
                    new_failures = current_failures + 1
                    conn.execute(
                        """
                        UPDATE app_info 
                        SET build_status = ?,
                            consecutive_failures = ?,
                            last_attempt_time = CURRENT_TIMESTAMP,
                            build_duration = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE app_id = ?
                        """,
                        (new_status, new_failures, duration, app_id)
                    )
            
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update build result for {app_id}: {e}")
            return False
    
    def get_app_info(self, app_id: str) -> Optional[Dict[str, Any]]:
        """Get app information from database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM app_info WHERE app_id = ?", (app_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get app info for {app_id}: {e}")
            return None
    
    def get_all_apps(self) -> List[Dict[str, Any]]:
        """Get all apps from database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM app_info ORDER BY app_id")
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all apps: {e}")
            return []
    
    def get_apps_for_build(self, max_consecutive_failures: int = 3) -> List[Dict[str, Any]]:
        """
        Get apps that should be built based on selection criteria.
        
        Priority:
        1. Apps never built before
        2. Apps with successful builds older than 7 days
        3. Apps with failed builds where consecutive_failures < max
        
        Args:
            max_consecutive_failures: Maximum failures before skipping app
            
        Returns:
            List of app dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM app_info 
                    WHERE (
                        build_status = 'never_built'
                        OR (build_status = 'success' AND 
                            (last_build_time IS NULL OR 
                             julianday('now') - julianday(last_build_time) > 7))
                        OR (build_status = 'fail' AND consecutive_failures < ?)
                    )
                    ORDER BY 
                        CASE build_status
                            WHEN 'never_built' THEN 1
                            WHEN 'success' THEN 2
                            WHEN 'fail' THEN 3
                            ELSE 4
                        END,
                        last_attempt_time ASC NULLS FIRST
                    """,
                    (max_consecutive_failures,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get apps for build: {e}")
            return []
    
    def delete_app(self, app_id: str) -> bool:
        """Delete app from database (cascades to build history)."""
        try:
            with self.get_connection() as conn:
                conn.execute("DELETE FROM build_history WHERE app_id = ?", (app_id,))
                conn.execute("DELETE FROM app_info WHERE app_id = ?", (app_id,))
            logger.info(f"Deleted app: {app_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to delete app {app_id}: {e}")
            return False
    
    # Build History operations
    
    def insert_build_history(
        self,
        app_id: str,
        status: str,
        duration: Optional[int] = None,
        log_path: Optional[str] = None,
        apk_size: Optional[int] = None,
        error_message: Optional[str] = None,
        gradle_version: Optional[str] = None,
        java_version: Optional[str] = None
    ) -> bool:
        """Insert build history record."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO build_history 
                    (app_id, build_time, status, duration, log_path, apk_size, 
                     error_message, gradle_version, java_version)
                    VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (app_id, status, duration, log_path, apk_size, error_message, 
                     gradle_version, java_version)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to insert build history for {app_id}: {e}")
            return False
    
    def get_build_history(self, app_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get build history for an app."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM build_history 
                    WHERE app_id = ? 
                    ORDER BY build_time DESC 
                    LIMIT ?
                    """,
                    (app_id, limit)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get build history for {app_id}: {e}")
            return []
    
    # Task Execution Log operations
    
    def start_task_execution(self, task_name: str) -> Optional[int]:
        """Record task execution start and return task execution ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO task_execution_log (task_name, start_time, status)
                    VALUES (?, CURRENT_TIMESTAMP, 'running')
                    """,
                    (task_name,)
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to start task execution for {task_name}: {e}")
            return None
    
    def end_task_execution(
        self,
        task_id: int,
        status: str,
        result_summary: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record task execution end."""
        try:
            summary_json = json.dumps(result_summary) if result_summary else None
            with self.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE task_execution_log 
                    SET end_time = CURRENT_TIMESTAMP, status = ?, result_summary = ?
                    WHERE id = ?
                    """,
                    (status, summary_json, task_id)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to end task execution {task_id}: {e}")
            return False
    
    # Statistics and reporting
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total apps
                cursor.execute("SELECT COUNT(*) FROM app_info")
                total_apps = cursor.fetchone()[0]
                
                # Apps by status
                cursor.execute("""
                    SELECT build_status, COUNT(*) 
                    FROM app_info 
                    GROUP BY build_status
                """)
                status_counts = dict(cursor.fetchall())
                
                # Successful builds in last 24 hours
                cursor.execute("""
                    SELECT COUNT(*) FROM build_history 
                    WHERE status = 'success' 
                    AND julianday('now') - julianday(build_time) < 1
                """)
                recent_builds = cursor.fetchone()[0]
                
                return {
                    'total_apps': total_apps,
                    'status_counts': status_counts,
                    'recent_successful_builds': recent_builds
                }
        except sqlite3.Error as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def backup(self, backup_path: Path) -> bool:
        """
        Create database backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if successful
        """
        try:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self.get_connection() as source:
                with sqlite3.connect(str(backup_path)) as dest:
                    source.backup(dest)
            
            logger.info(f"Database backed up to: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            return False
