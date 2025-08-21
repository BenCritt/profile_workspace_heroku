web: gunicorn my_profile.wsgi:application --log-file - --workers ${WEB_CONCURRENCY:-1} --max-requests 200 --max-requests-jitter 40 --worker-tmp-dir /dev/shm
