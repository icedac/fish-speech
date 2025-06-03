"""VoiceReel package."""

import os

from .caption import export_captions

# Configure logging on module import
try:
    from .json_logger import configure_json_logging, get_logger
    
    # Only configure if not already configured
    if not hasattr(configure_json_logging, "_configured"):
        configure_json_logging(
            level=os.getenv("VR_LOG_LEVEL", "INFO"),
            log_file=os.getenv("VR_LOG_FILE"),
            enable_console=os.getenv("VR_LOG_CONSOLE", "true").lower() == "true",
            enable_debug=os.getenv("VR_DEBUG", "false").lower() == "true",
        )
        configure_json_logging._configured = True
        
        # Log initialization
        logger = get_logger("voicereel")
        logger.info(
            "VoiceReel initialized",
            extra={
                "version": "1.0.0",
                "log_level": os.getenv("VR_LOG_LEVEL", "INFO"),
                "debug_mode": os.getenv("VR_DEBUG", "false").lower() == "true",
            }
        )
except ImportError:
    # Logging not available yet
    pass

__all__ = [
    "VoiceReelClient",
    "VoiceReelServer",
    "main",
    "export_captions",
    "create_app",
    "TaskQueue",
    "init_db",
]


def __getattr__(name):
    if name == "VoiceReelClient" or name == "main":
        from .client import VoiceReelClient, main

        globals()["VoiceReelClient"] = VoiceReelClient
        globals()["main"] = main
        return globals()[name]
    if name == "VoiceReelServer":
        from .server import VoiceReelServer

        globals()["VoiceReelServer"] = VoiceReelServer
        return VoiceReelServer
    if name == "create_app":
        from .flask_app import create_app

        globals()["create_app"] = create_app
        return create_app
    if name == "TaskQueue":
        from .task_queue import TaskQueue

        globals()["TaskQueue"] = TaskQueue
        return TaskQueue
    if name == "init_db":
        from .db import init_db

        globals()["init_db"] = init_db
        return init_db
    raise AttributeError(name)
