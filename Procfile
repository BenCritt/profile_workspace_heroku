web: gunicorn my_profile.wsgi:application \
  --worker-class gthread \
  --workers 1 \
  --threads 12 \
  --timeout 120 \
  --worker-tmp-dir /dev/shm \
  --log-file -
