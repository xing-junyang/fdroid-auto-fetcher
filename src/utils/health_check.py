"""
Health check HTTP server for monitoring service status.
"""

import logging
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify
from typing import Optional

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """HTTP server for health check endpoint."""
    
    def __init__(
        self,
        path_manager,
        database,
        scheduler,
        host: str = '0.0.0.0',
        port: int = 8080
    ):
        """
        Initialize health check server.
        
        Args:
            path_manager: PathManager instance
            database: Database instance
            scheduler: APScheduler instance
            host: Host to bind to
            port: Port to listen on
        """
        self.path_manager = path_manager
        self.db = database
        self.scheduler = scheduler
        self.host = host
        self.port = port
        
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)  # Reduce Flask logging noise
        
        self._setup_routes()
        self.server_thread: Optional[Thread] = None
    
    def _setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """
            Health check endpoint.
            
            Returns health status, disk usage, and service statistics.
            """
            try:
                # Get disk usage
                disk_usage = self.path_manager.get_disk_usage()
                
                # Get database statistics
                stats = self.db.get_statistics()
                
                # Determine health status
                if disk_usage['usage_percent'] >= 95:
                    status = 'unhealthy'
                elif disk_usage['usage_percent'] >= 85:
                    status = 'degraded'
                else:
                    status = 'healthy'
                
                # Check scheduler status
                scheduler_running = self.scheduler.running if self.scheduler else False
                
                if not scheduler_running:
                    status = 'unhealthy'
                
                # Get last metadata fetch time
                last_metadata_fetch = None
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT end_time FROM task_execution_log 
                            WHERE task_name = 'fetch_metadata' 
                            AND status = 'completed'
                            ORDER BY end_time DESC LIMIT 1
                        """)
                        row = cursor.fetchone()
                        if row:
                            last_metadata_fetch = row[0]
                except Exception as e:
                    logger.warning(f"Failed to get last metadata fetch: {e}")
                
                response = {
                    'status': status,
                    'timestamp': datetime.now().isoformat(),
                    'workspace_root': str(self.path_manager.workspace_root),
                    'disk_free_gb': round(disk_usage['free_gb'], 2),
                    'disk_usage_percent': round(disk_usage['usage_percent'], 2),
                    'total_apps': stats.get('total_apps', 0),
                    'status_counts': stats.get('status_counts', {}),
                    'recent_successful_builds': stats.get('recent_successful_builds', 0),
                    'scheduler_running': scheduler_running,
                    'last_metadata_fetch': last_metadata_fetch
                }
                
                http_status = 200 if status == 'healthy' else 503
                return jsonify(response), http_status
            
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }), 500
        
        @self.app.route('/stats', methods=['GET'])
        def stats():
            """
            Detailed statistics endpoint.
            
            Returns comprehensive service statistics.
            """
            try:
                stats = self.db.get_statistics()
                disk_usage = self.path_manager.get_disk_usage()
                
                # Get recent task executions
                recent_tasks = []
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT task_name, start_time, end_time, status
                            FROM task_execution_log 
                            ORDER BY start_time DESC LIMIT 10
                        """)
                        for row in cursor.fetchall():
                            recent_tasks.append({
                                'task_name': row[0],
                                'start_time': row[1],
                                'end_time': row[2],
                                'status': row[3]
                            })
                except Exception as e:
                    logger.warning(f"Failed to get recent tasks: {e}")
                
                # Get failed apps
                failed_apps = []
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT app_id, consecutive_failures, last_attempt_time
                            FROM app_info 
                            WHERE build_status = 'fail'
                            ORDER BY consecutive_failures DESC LIMIT 10
                        """)
                        for row in cursor.fetchall():
                            failed_apps.append({
                                'app_id': row[0],
                                'consecutive_failures': row[1],
                                'last_attempt_time': row[2]
                            })
                except Exception as e:
                    logger.warning(f"Failed to get failed apps: {e}")
                
                response = {
                    'timestamp': datetime.now().isoformat(),
                    'workspace': {
                        'root': str(self.path_manager.workspace_root),
                        'disk_total_gb': round(disk_usage['total_gb'], 2),
                        'disk_used_gb': round(disk_usage['used_gb'], 2),
                        'disk_free_gb': round(disk_usage['free_gb'], 2),
                        'disk_usage_percent': round(disk_usage['usage_percent'], 2)
                    },
                    'apps': {
                        'total': stats.get('total_apps', 0),
                        'by_status': stats.get('status_counts', {}),
                        'recent_builds': stats.get('recent_successful_builds', 0)
                    },
                    'recent_tasks': recent_tasks,
                    'failed_apps': failed_apps,
                    'scheduler': {
                        'running': self.scheduler.running if self.scheduler else False,
                        'jobs': len(self.scheduler.get_jobs()) if self.scheduler else 0
                    }
                }
                
                return jsonify(response), 200
            
            except Exception as e:
                logger.error(f"Stats endpoint error: {e}", exc_info=True)
                return jsonify({
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }), 500
        
        @self.app.route('/ping', methods=['GET'])
        def ping():
            """Simple ping endpoint."""
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200
    
    def start(self):
        """Start health check server in background thread."""
        def run_server():
            try:
                logger.info(f"Starting health check server on {self.host}:{self.port}")
                self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True
                )
            except Exception as e:
                logger.error(f"Health check server error: {e}", exc_info=True)
        
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"Health check server started at http://{self.host}:{self.port}/health")
    
    def stop(self):
        """Stop health check server."""
        # Flask's built-in server doesn't have a clean shutdown method
        # Since we're using a daemon thread, it will terminate when main program exits
        logger.info("Health check server stopping...")
