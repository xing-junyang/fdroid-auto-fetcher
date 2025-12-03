"""
F-Droid metadata fetcher - Downloads and parses F-Droid index.
"""

import logging
import hashlib
import requests
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class MetadataFetcher:
    """Fetches and parses F-Droid application metadata."""
    
    def __init__(
        self,
        index_url: str,
        mirror_url: Optional[str] = None,
        timeout: tuple = (30, 60),
        git_only: bool = True
    ):
        """
        Initialize metadata fetcher.
        
        Args:
            index_url: F-Droid index URL
            mirror_url: Backup mirror URL
            timeout: Request timeout (connection, read)
            git_only: Only process apps with Git repositories
        """
        self.index_url = index_url
        self.mirror_url = mirror_url
        self.timeout = timeout
        self.git_only = git_only
    
    def fetch_index(self) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse F-Droid index.
        
        Returns:
            Parsed index data or None if failed
        """
        # Try primary URL
        index_data = self._download_index(self.index_url)
        
        # Try mirror if primary fails
        if not index_data and self.mirror_url:
            logger.warning("Primary index fetch failed, trying mirror")
            index_data = self._download_index(self.mirror_url)
        
        return index_data
    
    def _download_index(self, url: str) -> Optional[Dict[str, Any]]:
        """Download and parse index from URL."""
        try:
            logger.info(f"Downloading F-Droid index from: {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            index_data = response.json()
            logger.info(f"Successfully downloaded index with {len(index_data.get('apps', []))} apps")
            return index_data
        
        except requests.RequestException as e:
            logger.error(f"Failed to download index from {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON index: {e}")
            return None
    
    def extract_apps(self, index_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract app metadata from index.
        
        Args:
            index_data: Parsed F-Droid index
            
        Returns:
            List of app dictionaries with app_id and git_url
        """
        apps = []
        packages = index_data.get('packages', {})
        
        for package_name, versions in packages.items():
            if not versions:
                continue
            
            # Get latest version
            latest = versions[0] if isinstance(versions, list) else versions
            
            # Extract source code URL
            source_url = latest.get('sourceCode') or latest.get('webSite')
            
            if not source_url:
                continue
            
            # Filter for Git repositories if git_only is True
            if self.git_only:
                if not self._is_git_url(source_url):
                    continue
            
            apps.append({
                'app_id': package_name,
                'git_url': source_url
            })
        
        logger.info(f"Extracted {len(apps)} apps with source code URLs")
        return apps
    
    def _is_git_url(self, url: str) -> bool:
        """Check if URL is a Git repository."""
        git_indicators = [
            'github.com',
            'gitlab.com',
            'codeberg.org',
            'git.',
            '.git',
            '/git/',
        ]
        url_lower = url.lower()
        return any(indicator in url_lower for indicator in git_indicators)
    
    def validate_url(self, url: str) -> bool:
        """
        Validate Git URL format and security.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid
        """
        import re
        
        # Whitelist protocols
        if not re.match(r'^(https?|git)://', url, re.IGNORECASE):
            logger.warning(f"Invalid protocol in URL: {url}")
            return False
        
        # Check length
        if len(url) > 2048:
            logger.warning(f"URL too long: {url}")
            return False
        
        # Check for suspicious characters
        if any(char in url for char in ['<', '>', '"', '{', '}']):
            logger.warning(f"Suspicious characters in URL: {url}")
            return False
        
        return True
