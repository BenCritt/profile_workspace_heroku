web: gunicorn my_profile.wsgi:application \
  --worker-class gthread \
  --workers 1 \
  --threads 3 \
  --timeout 120 \
  --worker-tmp-dir /tmp \
  --log-file -
