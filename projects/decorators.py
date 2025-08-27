from functools import wraps
from .mem_utils import trim_now

def trim_memory_after(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        response = None
        try:
            response = view_func(request, *args, **kwargs)
            return response
        finally:
            # Trim for POSTs (heavy work) or for streaming responses (big GET downloads)
            if request.method == "POST" or getattr(response, "streaming", False):
                trim_now()
    return _wrapped
