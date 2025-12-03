"""
Logging system with structured JSON formatter and rotation support.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: LogRecord to format
            
        Returns:
            JSON-formatted log string
        """
        log_data = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add optional fields if present
        if hasattr(record, 'app_id'):
            log_data['app_id'] = record.app_id
        
        if hasattr(record, 'task_name'):
            log_data['task_name'] = record.task_name
        
        if hasattr(record, 'duration'):
            log_data['duration'] = record.duration
        
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
        
        if hasattr(record, 'error_type'):
            log_data['error_type'] = record.error_type
        
        if hasattr(record, 'retry_count'):
            log_data['retry_count'] = record.retry_count
        
        if hasattr(record, 'context'):
            log_data['context'] = record.context
        
        if hasattr(record, 'recovery_action'):
            log_data['recovery_action'] = record.recovery_action
        
        # Add exception information if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'stack_info') and record.stack_info:
            log_data['stack_trace'] = self.formatStack(record.stack_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Plain text formatter for non-JSON logging."""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_logging(
    log_file_path: Path,
    log_level: str = 'INFO',
    max_bytes: int = 50 * 1024 * 1024,  # 50MB
    backup_count: int = 10,
    json_format: bool = True,
    console_output: bool = True
) -> logging.Logger:
    """
    Setup logging configuration with rotation.
    
    Args:
        log_file_path: Path to main log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        json_format: Use JSON formatter if True, plain text otherwise
        console_output: Enable console logging if True
        
    Returns:
        Configured root logger
    """
    # Ensure log directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = PlainFormatter()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler (always use plain format for readability)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(PlainFormatter())
        root_logger.addHandler(console_handler)
    
    return root_logger


def get_app_logger(
    app_id: str,
    log_file_path: Path,
    log_level: str = 'INFO',
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = True
) -> logging.Logger:
    """
    Get or create a logger for a specific app.
    
    Args:
        app_id: Application identifier
        log_file_path: Path to app-specific log file
        log_level: Logging level
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        json_format: Use JSON formatter if True
        
    Returns:
        Logger instance for the app
    """
    # Ensure log directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create logger with app-specific name
    logger = logging.getLogger(f'app.{app_id}')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Check if logger already has handlers
    if logger.handlers:
        return logger
    
    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
    
    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = PlainFormatter()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


class LoggerAdapter(logging.LoggerAdapter):
    """Adapter to add contextual information to log records."""
    
    def process(self, msg, kwargs):
        """Add extra fields to log record."""
        # Merge extra fields from both adapter and call
        extra = self.extra.copy()
        if 'extra' in kwargs:
            extra.update(kwargs['extra'])
            kwargs['extra'] = extra
        else:
            kwargs['extra'] = extra
        return msg, kwargs


def get_logger_with_context(name: str, **context) -> LoggerAdapter:
    """
    Get a logger with predefined context fields.
    
    Args:
        name: Logger name
        **context: Context fields to include in all log records
        
    Returns:
        LoggerAdapter with context
    """
    logger = logging.getLogger(name)
    return LoggerAdapter(logger, context)
