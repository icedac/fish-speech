"""Debug mode configuration for VoiceReel development."""

import os
from typing import Any, Dict, Optional

from loguru import logger


class DebugConfig:
    """Debug configuration manager for VoiceReel."""
    
    # Debug feature flags
    FEATURES = {
        "verbose_logging": "Enable verbose debug logging",
        "sql_echo": "Echo all SQL queries",
        "request_body_logging": "Log request bodies (security risk!)",
        "response_body_logging": "Log response bodies",
        "traceback_in_errors": "Include traceback in error responses",
        "disable_rate_limiting": "Disable rate limiting",
        "disable_auth": "Disable authentication (dangerous!)",
        "profile_requests": "Profile request performance",
        "memory_profiling": "Enable memory profiling",
        "gpu_monitoring": "Monitor GPU usage",
    }
    
    def __init__(self):
        """Initialize debug configuration."""
        self._config = {}
        self._load_from_env()
    
    def _load_from_env(self):
        """Load debug configuration from environment variables."""
        # Master debug switch
        self._config["enabled"] = os.getenv("VR_DEBUG", "false").lower() == "true"
        
        # Individual feature flags
        for feature in self.FEATURES:
            env_var = f"VR_DEBUG_{feature.upper()}"
            self._config[feature] = os.getenv(env_var, "false").lower() == "true"
        
        # Debug-specific settings
        self._config["log_level"] = os.getenv("VR_DEBUG_LOG_LEVEL", "DEBUG")
        self._config["profile_slow_requests"] = int(os.getenv("VR_DEBUG_SLOW_REQUEST_MS", "1000"))
        self._config["max_request_log_size"] = int(os.getenv("VR_DEBUG_MAX_REQUEST_LOG_SIZE", "10000"))
    
    @property
    def enabled(self) -> bool:
        """Check if debug mode is enabled."""
        return self._config["enabled"]
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific debug feature is enabled.
        
        Args:
            feature: Feature name from FEATURES
            
        Returns:
            Whether the feature is enabled
        """
        if not self.enabled:
            return False
        return self._config.get(feature, False)
    
    def get_config(self) -> Dict[str, Any]:
        """Get full debug configuration."""
        return self._config.copy()
    
    def log_configuration(self):
        """Log current debug configuration."""
        if not self.enabled:
            logger.info("Debug mode is disabled")
            return
        
        logger.warning("Debug mode is ENABLED - not for production use!")
        
        # Log enabled features
        enabled_features = [
            feature for feature in self.FEATURES
            if self.is_feature_enabled(feature)
        ]
        
        if enabled_features:
            logger.warning(
                f"Debug features enabled: {', '.join(enabled_features)}",
                extra={"debug_features": enabled_features}
            )
        
        # Security warnings
        if self.is_feature_enabled("disable_auth"):
            logger.critical("Authentication is DISABLED - server is unsecured!")
        if self.is_feature_enabled("request_body_logging"):
            logger.warning("Request body logging enabled - may expose sensitive data!")
    
    def apply_to_app(self, app):
        """Apply debug configuration to Flask app.
        
        Args:
            app: Flask application instance
        """
        if not self.enabled:
            return
        
        # Set Flask debug mode
        app.debug = True
        
        # Configure based on features
        if self.is_feature_enabled("disable_rate_limiting"):
            app.config["RATELIMIT_ENABLED"] = False
        
        if self.is_feature_enabled("verbose_logging"):
            app.config["PROPAGATE_EXCEPTIONS"] = True
        
        # Add debug toolbar if available
        try:
            from flask_debugtoolbar import DebugToolbarExtension
            app.config["DEBUG_TB_ENABLED"] = True
            app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
            DebugToolbarExtension(app)
            logger.info("Flask debug toolbar enabled")
        except ImportError:
            pass
    
    def apply_to_database(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply debug configuration to database settings.
        
        Args:
            db_config: Database configuration dictionary
            
        Returns:
            Modified database configuration
        """
        if not self.enabled:
            return db_config
        
        if self.is_feature_enabled("sql_echo"):
            db_config["echo"] = True
            db_config["echo_pool"] = True
        
        return db_config
    
    def create_debug_middleware(self):
        """Create debug middleware for request profiling."""
        
        class DebugMiddleware:
            """Middleware for debug profiling."""
            
            def __init__(self, app):
                self.app = app
                self.config = DebugConfig()
            
            def __call__(self, environ, start_response):
                if not self.config.is_feature_enabled("profile_requests"):
                    return self.app(environ, start_response)
                
                import cProfile
                import io
                import pstats
                
                profiler = cProfile.Profile()
                profiler.enable()
                
                try:
                    result = self.app(environ, start_response)
                    return result
                finally:
                    profiler.disable()
                    
                    # Log profile results
                    s = io.StringIO()
                    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
                    ps.print_stats(20)  # Top 20 functions
                    
                    logger.debug(
                        "Request profile",
                        extra={
                            "profile": s.getvalue(),
                            "path": environ.get("PATH_INFO"),
                            "method": environ.get("REQUEST_METHOD"),
                        }
                    )
        
        return DebugMiddleware


class DebugDecorators:
    """Debug decorators for development."""
    
    @staticmethod
    def profile_function(func):
        """Profile function execution time.
        
        Args:
            func: Function to profile
            
        Returns:
            Wrapped function
        """
        import functools
        import time
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not DebugConfig().is_feature_enabled("profile_requests"):
                return func(*args, **kwargs)
            
            start_time = time.time()
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            
            logger.debug(
                f"Function {func.__name__} took {duration_ms:.2f}ms",
                extra={
                    "function": func.__name__,
                    "duration_ms": duration_ms,
                }
            )
            
            return result
        
        return wrapper
    
    @staticmethod
    def trace_calls(func):
        """Trace function calls with arguments.
        
        Args:
            func: Function to trace
            
        Returns:
            Wrapped function
        """
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not DebugConfig().is_feature_enabled("verbose_logging"):
                return func(*args, **kwargs)
            
            logger.debug(
                f"Calling {func.__name__}",
                extra={
                    "function": func.__name__,
                    "args": str(args)[:200],  # Truncate long args
                    "kwargs": str(kwargs)[:200],
                }
            )
            
            try:
                result = func(*args, **kwargs)
                logger.debug(
                    f"{func.__name__} returned",
                    extra={
                        "function": func.__name__,
                        "result_type": type(result).__name__,
                    }
                )
                return result
            except Exception as e:
                logger.error(
                    f"{func.__name__} raised exception",
                    extra={
                        "function": func.__name__,
                        "exception": type(e).__name__,
                    },
                    exc_info=True
                )
                raise
        
        return wrapper


def setup_debug_endpoints(app):
    """Add debug endpoints to Flask app.
    
    Args:
        app: Flask application instance
    """
    config = DebugConfig()
    
    if not config.enabled:
        return
    
    @app.route("/_debug/config")
    def debug_config():
        """Show debug configuration."""
        if not config.is_feature_enabled("verbose_logging"):
            return {"error": "Debug endpoints disabled"}, 403
        
        return {
            "debug": config.get_config(),
            "features": {
                feature: {
                    "enabled": config.is_feature_enabled(feature),
                    "description": desc
                }
                for feature, desc in DebugConfig.FEATURES.items()
            }
        }
    
    @app.route("/_debug/health")
    def debug_health():
        """Detailed health check."""
        import psutil
        
        health = {
            "status": "ok",
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
            },
            "memory": {
                "percent": psutil.virtual_memory().percent,
                "available_mb": psutil.virtual_memory().available / 1024 / 1024,
            },
            "disk": {
                "percent": psutil.disk_usage("/").percent,
                "free_gb": psutil.disk_usage("/").free / 1024 / 1024 / 1024,
            },
        }
        
        # Add GPU info if available
        if config.is_feature_enabled("gpu_monitoring"):
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                health["gpu"] = [
                    {
                        "id": gpu.id,
                        "name": gpu.name,
                        "load": gpu.load * 100,
                        "memory_used": gpu.memoryUsed,
                        "memory_total": gpu.memoryTotal,
                        "temperature": gpu.temperature,
                    }
                    for gpu in gpus
                ]
            except:
                health["gpu"] = "Not available"
        
        return health
    
    logger.info("Debug endpoints added: /_debug/config, /_debug/health")


# Singleton instance
_debug_config = None


def get_debug_config() -> DebugConfig:
    """Get debug configuration singleton.
    
    Returns:
        Debug configuration instance
    """
    global _debug_config
    if _debug_config is None:
        _debug_config = DebugConfig()
        _debug_config.log_configuration()
    return _debug_config


# Export debug components
__all__ = [
    "DebugConfig",
    "DebugDecorators", 
    "setup_debug_endpoints",
    "get_debug_config",
]