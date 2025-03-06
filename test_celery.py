#!/usr/bin/env python3
"""Test script for Celery tasks."""

from app.tasks.worker import test_task

if __name__ == "__main__":
    print("Sending test task to Celery...")
    result = test_task.delay()
    print(f"Task ID: {result.id}")
    print("Waiting for result...")
    task_result = result.get(timeout=10)  # Wait up to 10 seconds for result
    print(f"Task result: {task_result}")
    print("Celery is working correctly!") 