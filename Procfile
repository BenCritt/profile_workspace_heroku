web: gunicorn my_profile.wsgi:application --worker-class gthread --workers 2 --threads 4 --timeout 120 --max-requests 10000 --max-requests-jitter 2000 --log-file -
