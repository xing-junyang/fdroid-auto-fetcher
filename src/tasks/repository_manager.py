"""
Repository manager with robust error handling and retry logic.
"""

import logging
import subprocess
import time
import shutil
from pathlib import Path
from typing import Optional, Tuple
from git import Repo, GitCommandError
import git

logger = logging.getLogger(__name__)


class RepositoryManager:
    """Manages Git repository operations with robust error handling."""
    
    def __init__(
        self,
        clone_timeout: int = 600,
        fetch_timeout: int = 300,
        shallow_clone: bool = True,
        max_retries: int = 3
    ):
        """
        Initialize repository manager.
        
        Args:
            clone_timeout: Timeout for clone operations in seconds
            fetch_timeout: Timeout for fetch operations in seconds
            shallow_clone: Use shallow clone (--depth=1)
            max_retries: Maximum retry attempts
        """
        self.clone_timeout = clone_timeout
        self.fetch_timeout = fetch_timeout
        self.shallow_clone = shallow_clone
        self.max_retries = max_retries
    
    def clone_repository(
        self,
        git_url: str,
        dest_path: Path,
        app_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Clone repository with multi-protocol retry strategy.
        
        Args:
            git_url: Git repository URL
            dest_path: Destination directory
            app_id: Application identifier
            
        Returns:
            (success: bool, error_message: Optional[str])
        """
        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # If directory already exists, remove it
        if dest_path.exists():
            logger.warning(f"Destination already exists, removing: {dest_path}")
            shutil.rmtree(dest_path, ignore_errors=True)
        
        # Try different protocols
        protocols = [git_url]
        
        # Generate alternative URLs
        if 'https://' in git_url:
            # Try SSH alternative
            ssh_url = git_url.replace('https://github.com/', 'git@github.com:')
            if ssh_url != git_url:
                protocols.append(ssh_url)
        
        for attempt in range(self.max_retries):
            for protocol_idx, url in enumerate(protocols):
                try:
                    logger.info(
                        f"[{app_id}] Clone attempt {attempt + 1}/{self.max_retries}, "
                        f"protocol {protocol_idx + 1}/{len(protocols)}: {url}"
                    )
                    
                    # Build clone command
                    cmd = ['git', 'clone']
                    if self.shallow_clone:
                        cmd.extend(['--depth', '1'])
                    cmd.extend([url, str(dest_path)])
                    
                    # Execute with timeout
                    result = subprocess.run(
                        cmd,
                        timeout=self.clone_timeout,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        # Validate repository
                        if self._validate_repository(dest_path):
                            logger.info(f"[{app_id}] Successfully cloned repository")
                            return True, None
                        else:
                            error_msg = "Repository validation failed"
                            logger.error(f"[{app_id}] {error_msg}")
                            shutil.rmtree(dest_path, ignore_errors=True)
                            return False, error_msg
                    else:
                        logger.warning(
                            f"[{app_id}] Clone failed: {result.stderr}"
                        )
                
                except subprocess.TimeoutExpired:
                    logger.warning(f"[{app_id}] Clone timeout after {self.clone_timeout}s")
                    # Kill any remaining git processes (cross-platform)
                    try:
                        import psutil
                        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                            try:
                                if proc.info['name'] and 'git' in proc.info['name'].lower():
                                    if proc.info['cmdline'] and app_id in ' '.join(proc.info['cmdline']):
                                        proc.kill()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                    except:
                        pass
                
                except Exception as e:
                    logger.error(f"[{app_id}] Clone exception: {e}", exc_info=True)
                
                # Exponential backoff between attempts
                if attempt < self.max_retries - 1 or protocol_idx < len(protocols) - 1:
                    backoff = 5 * (2 ** attempt)
                    logger.debug(f"[{app_id}] Waiting {backoff}s before retry")
                    time.sleep(backoff)
        
        error_msg = f"Failed to clone after {self.max_retries} attempts with {len(protocols)} protocols"
        logger.error(f"[{app_id}] {error_msg}")
        return False, error_msg
    
    def update_repository(
        self,
        repo_path: Path,
        app_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update repository with conflict resolution.
        
        Args:
            repo_path: Repository directory path
            app_id: Application identifier
            
        Returns:
            (success: bool, error_message: Optional[str])
        """
        if not repo_path.exists():
            return False, "Repository does not exist"
        
        try:
            repo = Repo(repo_path)
            
            # Fetch with retry
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"[{app_id}] Fetching updates (attempt {attempt + 1}/{self.max_retries})")
                    
                    # Fetch from origin
                    origin = repo.remotes.origin
                    origin.fetch(kill_after_timeout=self.fetch_timeout)
                    
                    # Check for local changes
                    if repo.is_dirty() or repo.untracked_files:
                        logger.warning(f"[{app_id}] Local changes detected, resetting")
                        repo.git.reset('--hard', 'origin/HEAD')
                    
                    # Pull changes
                    origin.pull(kill_after_timeout=self.fetch_timeout)
                    
                    logger.info(f"[{app_id}] Successfully updated repository")
                    return True, None
                
                except GitCommandError as e:
                    logger.warning(f"[{app_id}] Update failed: {e}")
                    
                    # Try force reset
                    try:
                        logger.info(f"[{app_id}] Attempting force reset")
                        repo.git.reset('--hard', 'origin/HEAD')
                        return True, None
                    except Exception as reset_error:
                        logger.error(f"[{app_id}] Force reset failed: {reset_error}")
                
                except Exception as e:
                    logger.error(f"[{app_id}] Update exception: {e}", exc_info=True)
                
                # Wait before retry
                if attempt < self.max_retries - 1:
                    time.sleep(5)
            
            error_msg = f"Failed to update after {self.max_retries} attempts"
            logger.error(f"[{app_id}] {error_msg}")
            return False, error_msg
        
        except Exception as e:
            error_msg = f"Repository operation failed: {e}"
            logger.error(f"[{app_id}] {error_msg}", exc_info=True)
            return False, error_msg
    
    def _validate_repository(self, repo_path: Path) -> bool:
        """
        Validate repository integrity.
        
        Args:
            repo_path: Repository directory path
            
        Returns:
            True if valid
        """
        try:
            # Check .git directory exists
            git_dir = repo_path / '.git'
            if not git_dir.exists():
                logger.error(f"No .git directory found in {repo_path}")
                return False
            
            # Try to open repository
            repo = Repo(repo_path)
            
            # Check if repository has commits
            try:
                repo.head.commit
            except ValueError:
                logger.error(f"Repository has no commits: {repo_path}")
                return False
            
            logger.debug(f"Repository validation passed: {repo_path}")
            return True
        
        except Exception as e:
            logger.error(f"Repository validation failed: {e}")
            return False
    
    def get_repository_size(self, repo_path: Path) -> int:
        """
        Calculate repository size.
        
        Args:
            repo_path: Repository directory path
            
        Returns:
            Size in bytes
        """
        total_size = 0
        try:
            for entry in repo_path.rglob('*'):
                if entry.is_file():
                    try:
                        total_size += entry.stat().st_size
                    except (OSError, PermissionError):
                        continue
        except Exception as e:
            logger.warning(f"Failed to calculate repository size: {e}")
        
        return total_size
    
    def delete_repository(self, repo_path: Path, app_id: str) -> bool:
        """
        Delete repository directory.
        
        Args:
            repo_path: Repository directory path
            app_id: Application identifier
            
        Returns:
            True if successful
        """
        try:
            if repo_path.exists():
                shutil.rmtree(repo_path)
                logger.info(f"[{app_id}] Deleted repository: {repo_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"[{app_id}] Failed to delete repository: {e}")
            return False
