web: gunicorn my_profile.wsgi:application \
  --worker-class gthread \
  --workers 1 \
  --threads 8 \
  --timeout 120 \
  --max-requests 1500 \
  --max-requests-jitter 400 \
  --worker-tmp-dir /dev/shm \
  --log-file -
