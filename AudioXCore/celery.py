# AudioXCore/celery.py

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
# This is crucial for the celery worker to know how to connect to Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AudioXCore.settings')

# Create the Celery application instance.
# We name it after our project for clarity.
app = Celery('AudioXCore')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# namespace='CELERY' means all celery-related configuration keys
# should have a `CELERY_` prefix in settings.py.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
# Celery will look for a tasks.py file in each app to find task definitions.
app.autodiscover_tasks()

# (Optional) A sample task to test if the worker is running.
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')