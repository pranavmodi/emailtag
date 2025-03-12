#!/usr/bin/env python3
"""Script to inspect Celery worker status and registered tasks."""

import logging
from app.tasks.worker import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Create an inspector to check worker status
    inspector = celery_app.control.inspect()
    
    # Check if workers are online
    active_workers = inspector.active_queues()
    if not active_workers:
        print("❌ No Celery workers are currently running!")
        print("Start a worker with: celery -A app.tasks.worker worker -l info -Q emails,tagging")
        exit(1)
    
    print("\n[Active Workers]")
    for worker_name, queues in active_workers.items():
        print(f"  Worker: {worker_name}")
        print(f"  Listening to queues: {', '.join(q['name'] for q in queues)}")
        print()
    
    # Check registered tasks on each worker
    registered = inspector.registered()
    if registered:
        print("\n[Registered Tasks by Worker]")
        for worker_name, tasks in registered.items():
            print(f"  Worker: {worker_name}")
            for task in sorted(tasks):
                if not task.startswith('celery.'):
                    print(f"    . {task}")
            print()
    
    # Check active tasks
    active_tasks = inspector.active()
    if active_tasks:
        print("\n[Active Tasks]")
        for worker_name, tasks in active_tasks.items():
            if tasks:
                print(f"  Worker: {worker_name}")
                for task in tasks:
                    print(f"    . {task['name']} (id: {task['id']})")
            else:
                print(f"  Worker: {worker_name} - No active tasks")
    else:
        print("\n[Active Tasks]")
        print("  No active tasks")
    
    # Check scheduled tasks
    scheduled = inspector.scheduled()
    if scheduled:
        print("\n[Scheduled Tasks]")
        for worker_name, tasks in scheduled.items():
            if tasks:
                print(f"  Worker: {worker_name}")
                for task in tasks:
                    print(f"    . {task['request']['name']} (id: {task['request']['id']})")
            else:
                print(f"  Worker: {worker_name} - No scheduled tasks")
    else:
        print("\n[Scheduled Tasks]")
        print("  No scheduled tasks")
    
    print("\nCelery inspection completed!") 