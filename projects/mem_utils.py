from __future__ import annotations
import gc

def trim_now() -> None:
    """Force a GC and ask glibc to release arenas back to the OS."""
    try:
        gc.collect()
    except Exception:
        pass
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        # Not fatal on non-glibc platforms
        pass
