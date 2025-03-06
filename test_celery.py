#!/usr/bin/env python3
"""Test script for Celery tasks."""

import logging
import sys
import time
from app.tasks.worker import test_task

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Sending test task to Celery...")
        result = test_task.delay()
        logger.info(f"Task ID: {result.id}")
        logger.info("Waiting for result...")
        
        # First check if the task is pending to confirm the worker received it
        logger.info(f"Task state: {result.state}")
        
        # Wait for the result with a timeout
        timeout = 30  # 30 seconds
        start_time = time.time()
        while not result.ready():
            if time.time() - start_time > timeout:
                raise Exception("Task timed out")
            logger.info(f"Task state: {result.state}")
            time.sleep(1)
            
        task_result = result.get()
        logger.info(f"Task result: {task_result}")
        logger.info("Celery is working correctly!")
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error("Check that the worker is running and listening to the right queues.")
        sys.exit(1) 