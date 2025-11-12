from celery import Celery
import os

# Create Celery instance
celery_app = Celery('trevnoctilla_api')

# Configuration
celery_app.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Optional configuration for better performance
celery_app.conf.update(
    task_routes={
        'trevnoctilla_backend.tasks.convert_video_async': {'queue': 'video'},
        'trevnoctilla_backend.tasks.convert_audio_async': {'queue': 'audio'},
        'trevnoctilla_backend.tasks.convert_image_async': {'queue': 'image'},
        'trevnoctilla_backend.tasks.process_pdf_async': {'queue': 'pdf'},
    },
    task_default_queue='default',
    task_queues={
        'default': {
            'exchange': 'default',
            'routing_key': 'default',
        },
        'video': {
            'exchange': 'video',
            'routing_key': 'video',
        },
        'audio': {
            'exchange': 'audio',
            'routing_key': 'audio',
        },
        'image': {
            'exchange': 'image',
            'routing_key': 'image',
        },
        'pdf': {
            'exchange': 'pdf',
            'routing_key': 'pdf',
        },
    }
)

if __name__ == '__main__':
    celery_app.start()
