#!/usr/bin/env python3
"""Script to list all registered Celery tasks."""

import logging
import importlib

# First, import the Celery app
from app.tasks.worker import celery_app

# Explicitly import task modules to ensure they're registered
import app.tasks.email

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Get all registered tasks
    registered_tasks = list(sorted(celery_app.tasks.keys()))
    
    # Filter out internal Celery tasks (those starting with "celery.")
    app_tasks = [task for task in registered_tasks if not task.startswith('celery.')]
    
    # Print the tasks
    print("\n[Registered Tasks]")
    for task in app_tasks:
        print(f"  . {task}")
    
    # Print task routes
    print("\n[Task Routes]")
    for task_name, route_info in celery_app.conf.task_routes.items():
        queue = route_info.get('queue', 'default')
        # Check if this task is actually registered
        is_registered = task_name in registered_tasks
        status = "✅ registered" if is_registered else "❌ not registered"
        print(f"  . {task_name} -> queue: {queue} ({status})")
    
    # Print modules that have been imported
    print("\n[Imported Task Modules]")
    for module_name in ["app.tasks.worker", "app.tasks.email"]:
        module = importlib.import_module(module_name)
        print(f"  . {module_name} - {getattr(module, '__file__', 'Unknown location')}")
    
    print(f"\nTotal: {len(app_tasks)} application tasks registered") 