"""
Build executor with multi-Java version support and resource monitoring.
"""

import logging
import subprocess
import time
import os
import psutil
import shutil
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class BuildExecutor:
    """Executes Gradle builds with multi-Java version support and monitoring."""
    
    def __init__(
        self,
        build_timeout: int = 1800,  # 30 minutes
        memory_limit_gb: int = 4,
        metaspace_mb: int = 512,
        gradle_cache_dir: Path = None
    ):
        """
        Initialize build executor.
        
        Args:
            build_timeout: Build timeout in seconds
            memory_limit_gb: Memory limit in GB
            metaspace_mb: Metaspace limit in MB
            gradle_cache_dir: Gradle cache directory
        """
        self.build_timeout = build_timeout
        self.memory_limit_gb = memory_limit_gb
        self.metaspace_mb = metaspace_mb
        self.gradle_cache_dir = gradle_cache_dir
        
        # Detect available Java versions
        self.java_versions = self._detect_java_versions()
        logger.info(f"Detected Java versions: {list(self.java_versions.keys())}")
    
    def _detect_java_versions(self) -> Dict[str, str]:
        """
        Detect available Java installations.
        
        Returns:
            Dictionary mapping version names to JAVA_HOME paths
        """
        java_versions = {}
        
        # Check environment variables for specific Java versions
        for version in [8, 11, 17]:
            env_var = f'JAVA{version}_HOME'
            if env_var in os.environ:
                java_home = os.environ[env_var]
                if Path(java_home).exists():
                    java_versions[f'jdk{version}'] = java_home
        
        # Check default JAVA_HOME
        if 'JAVA_HOME' in os.environ:
            java_home = os.environ['JAVA_HOME']
            if Path(java_home).exists():
                java_versions['default'] = java_home
        
        # Try to find Java installations in common locations
        if os.name == 'nt':  # Windows
            common_paths = [
                'C:\\Program Files\\Java',
                'C:\\Program Files (x86)\\Java',
                'D:\\Java',
            ]
        else:  # Linux/Unix
            common_paths = [
                '/usr/lib/jvm',
                '/usr/java',
                '/opt/java',
            ]
        
        for base_path in common_paths:
            if not Path(base_path).exists():
                continue
            
            for entry in Path(base_path).iterdir():
                if entry.is_dir() and 'java' in entry.name.lower():
                    # Try to determine version
                    if 'jdk-17' in entry.name or 'java-17' in entry.name:
                        if 'jdk17' not in java_versions:
                            java_versions['jdk17'] = str(entry)
                    elif 'jdk-11' in entry.name or 'java-11' in entry.name:
                        if 'jdk11' not in java_versions:
                            java_versions['jdk11'] = str(entry)
                    elif 'jdk-8' in entry.name or 'java-8' in entry.name or 'jdk1.8' in entry.name:
                        if 'jdk8' not in java_versions:
                            java_versions['jdk8'] = str(entry)
        
        return java_versions
    
    def build_app(
        self,
        repo_path: Path,
        app_id: str,
        build_log_path: Path
    ) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """
        Build app with multi-Java version fallback.
        
        Args:
            repo_path: Repository directory path
            app_id: Application identifier
            build_log_path: Path to save build log
            
        Returns:
            (success: bool, duration: Optional[int], error_message: Optional[str], java_version: Optional[str])
        """
        # Pre-build checks
        if not self._pre_build_check(repo_path, app_id):
            return False, None, "Pre-build checks failed", None
        
        # Try each Java version
        java_priority = ['jdk17', 'jdk11', 'jdk8', 'default']
        
        for java_version in java_priority:
            if java_version not in self.java_versions:
                continue
            
            java_home = self.java_versions[java_version]
            logger.info(f"[{app_id}] Attempting build with {java_version}: {java_home}")
            
            success, duration, error_msg = self._execute_build(
                repo_path,
                app_id,
                java_home,
                build_log_path
            )
            
            if success:
                return True, duration, None, java_version
            
            # Check if error suggests trying different Java version
            if error_msg and self._should_try_different_java(error_msg):
                logger.info(f"[{app_id}] Java version issue detected, trying next version")
                continue
            else:
                # Other type of error, no point trying different Java
                return False, duration, error_msg, java_version
        
        return False, None, "All Java versions failed", None
    
    def _pre_build_check(self, repo_path: Path, app_id: str) -> bool:
        """
        Perform pre-build environment checks.
        
        Args:
            repo_path: Repository directory path
            app_id: Application identifier
            
        Returns:
            True if checks pass
        """
        # Check gradlew exists (Windows: gradlew.bat, Unix: gradlew)
        if os.name == 'nt':
            gradlew = repo_path / 'gradlew.bat'
        else:
            gradlew = repo_path / 'gradlew'
        
        if not gradlew.exists():
            logger.error(f"[{app_id}] gradlew not found")
            return False
        
        # Make gradlew executable (Unix only)
        if os.name != 'nt':
            try:
                gradlew.chmod(0o755)
            except Exception as e:
                logger.warning(f"[{app_id}] Failed to chmod gradlew: {e}")
        
        # Check build.gradle exists
        build_gradle = repo_path / 'build.gradle'
        build_gradle_kts = repo_path / 'build.gradle.kts'
        
        if not (build_gradle.exists() or build_gradle_kts.exists()):
            logger.error(f"[{app_id}] build.gradle not found")
            return False
        
        return True
    
    def _execute_build(
        self,
        repo_path: Path,
        app_id: str,
        java_home: str,
        build_log_path: Path
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Execute Gradle build with monitoring.
        
        Returns:
            (success: bool, duration: Optional[int], error_message: Optional[str])
        """
        start_time = time.time()
        
        # Prepare environment
        env = os.environ.copy()
        env['JAVA_HOME'] = java_home
        env['GRADLE_OPTS'] = f'-Xmx{self.memory_limit_gb}g -XX:MaxMetaspaceSize={self.metaspace_mb}m'
        
        if self.gradle_cache_dir:
            env['GRADLE_USER_HOME'] = str(self.gradle_cache_dir)
        
        # Build command
        if os.name == 'nt':
            gradlew = repo_path / 'gradlew.bat'
        else:
            gradlew = repo_path / 'gradlew'
        
        cmd = [str(gradlew), 'assembleRelease', '--stacktrace']
        
        # Ensure log directory exists
        build_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(build_log_path, 'w') as log_file:
                logger.info(f"[{app_id}] Starting build, log: {build_log_path}")
                
                process = subprocess.Popen(
                    cmd,
                    cwd=repo_path,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
                # Monitor process
                while True:
                    try:
                        # Wait with timeout
                        returncode = process.wait(timeout=10)
                        
                        # Process completed
                        duration = int(time.time() - start_time)
                        
                        if returncode == 0:
                            logger.info(f"[{app_id}] Build completed successfully in {duration}s")
                            return True, duration, None
                        else:
                            error_msg = f"Build failed with return code {returncode}"
                            logger.error(f"[{app_id}] {error_msg}")
                            
                            # Read last few lines of log for error context
                            error_context = self._extract_error_from_log(build_log_path)
                            
                            return False, duration, error_context or error_msg
                    
                    except subprocess.TimeoutExpired:
                        # Check if we've exceeded total timeout
                        elapsed = time.time() - start_time
                        if elapsed > self.build_timeout:
                            logger.error(f"[{app_id}] Build timeout after {self.build_timeout}s")
                            self._kill_process_tree(process.pid)
                            return False, int(elapsed), "Build timeout"
                        
                        # Check resource usage
                        try:
                            proc = psutil.Process(process.pid)
                            memory_mb = proc.memory_info().rss / (1024 * 1024)
                            
                            if memory_mb > self.memory_limit_gb * 1024 * 1.5:
                                logger.error(f"[{app_id}] Memory limit exceeded: {memory_mb:.0f}MB")
                                self._kill_process_tree(process.pid)
                                return False, int(time.time() - start_time), "Memory limit exceeded"
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
        
        except Exception as e:
            duration = int(time.time() - start_time)
            error_msg = f"Build exception: {e}"
            logger.error(f"[{app_id}] {error_msg}", exc_info=True)
            return False, duration, error_msg
    
    def _kill_process_tree(self, pid: int):
        """Kill process and all its children."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            
            parent.kill()
            parent.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Failed to kill process tree {pid}: {e}")
    
    def _extract_error_from_log(self, log_path: Path, lines: int = 50) -> Optional[str]:
        """Extract error context from build log."""
        try:
            with open(log_path, 'r') as f:
                log_lines = f.readlines()
            
            # Get last N lines
            relevant_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
            return ''.join(relevant_lines)
        
        except Exception as e:
            logger.warning(f"Failed to read build log: {e}")
            return None
    
    def _should_try_different_java(self, error_msg: str) -> bool:
        """
        Determine if error suggests trying a different Java version.
        
        Args:
            error_msg: Error message from build
            
        Returns:
            True if should try different Java version
        """
        java_error_patterns = [
            'unsupported class file major version',
            'requires java',
            'java version',
            'jdk version',
            'compilesdkversion',
        ]
        
        error_lower = error_msg.lower()
        return any(pattern in error_lower for pattern in java_error_patterns)
    
    def find_apk_files(self, repo_path: Path) -> List[Path]:
        """
        Find generated APK files in repository.
        
        Args:
            repo_path: Repository directory path
            
        Returns:
            List of APK file paths
        """
        apk_files = []
        
        # Common APK locations
        search_dirs = [
            repo_path / 'app/build/outputs/apk',
            repo_path / 'build/outputs/apk',
        ]
        
        for search_dir in search_dirs:
            if search_dir.exists():
                apk_files.extend(search_dir.rglob('*.apk'))
        
        # Filter out unaligned/unsigned APKs if release versions exist
        release_apks = [apk for apk in apk_files if 'release' in apk.name.lower()]
        
        return release_apks if release_apks else apk_files
    
    def copy_apk_to_output(self, apk_path: Path, output_dir: Path, app_id: str) -> Optional[Path]:
        """
        Copy APK to output directory.
        
        Args:
            apk_path: Source APK path
            output_dir: Destination directory
            app_id: Application identifier
            
        Returns:
            Destination path if successful
        """
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            dest_path = output_dir / f"{app_id}_{timestamp}.apk"
            
            shutil.copy2(apk_path, dest_path)
            logger.info(f"[{app_id}] APK copied to: {dest_path}")
            
            return dest_path
        
        except Exception as e:
            logger.error(f"[{app_id}] Failed to copy APK: {e}")
            return None
