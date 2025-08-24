"""
Monte Carlo PDF rendering utilities with *process isolation* to guarantee
that NumPy/Matplotlib memory is returned to the OS after each request.

Public API (drop-in):
- render_probability_pdf(min_val, max_val, n, target, second=None, bins=50) -> io.BytesIO
- render_probability_pdf_isolated(min_val, max_val, n, target, second=None, bins=50, timeout=20) -> bytes

`second` may be:
- None
- dict with keys {"min","max","n","target"} (all numbers)
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Tuple
import io
import os
import gc
import ctypes
import multiprocessing as mp


# -------------------------
# Small helpers / utilities
# -------------------------

def _trim_memory_safely() -> None:
    """Best-effort: collect garbage and ask glibc to return arenas."""
    try:
        gc.collect()
    except Exception:
        pass
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)  # type: ignore[attr-defined]
    except Exception:
        # Not Linux/glibc or symbol not available.
        pass


def _coerce_second(second: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float, int, float]]:
    if not second:
        return None
    # Defensive parsing—ignore if any value missing
    try:
        smin = float(second["min"])
        smax = float(second["max"])
        sn   = int(second["n"])
        star = float(second["target"])
        return (smin, smax, sn, star)
    except Exception:
        return None


# -------------------------
# In-process renderer (kept for compatibility and testing)
# -------------------------

def _build_pdf_bytes_inproc(
    min_val: float,
    max_val: float,
    n: int,
    target: float,
    second: Optional[Dict[str, Any]] = None,
    bins: int = 50,
) -> bytes:
    """
    Heavy work happens here. Runs in the *current* process. Prefer the isolated
    wrapper below in production.
    """
    # Import heavy libs lazily
    # Keep native libs single-threaded by default
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

    import numpy as np  # type: ignore
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore

    # Generate first distribution
    rng = np.random.default_rng()
    d1 = rng.uniform(low=min_val, high=max_val, size=n).astype(np.float64, copy=False)

    # Optional second distribution
    s_tuple = _coerce_second(second)
    if s_tuple is not None:
        smin, smax, sn, star = s_tuple
        d2 = rng.uniform(low=smin, high=smax, size=sn).astype(np.float64, copy=False)
    else:
        d2 = None

    # Figure
    fig, ax = plt.subplots(figsize=(10, 6), dpi=100)

    # Histogram(s)
    ax.hist(d1, bins=bins, alpha=0.6, label=f"Run 1 (n={n:,})")
    if d2 is not None:
        ax.hist(d2, bins=bins, alpha=0.6, label=f"Run 2 (n={sn:,})")

    # Target lines
    ax.axvline(target, linestyle="--", linewidth=1.2, label=f"Target 1: {target:g}")
    if s_tuple is not None:
        ax.axvline(s_tuple[3], linestyle=":", linewidth=1.2, label=f"Target 2: {s_tuple[3]:g}")

    # Probability annotations (>= target)
    p1 = float((d1 >= target).mean())
    ax.text(0.02, 0.95, f"P1(x ≥ {target:g}) = {p1:.3%}", transform=ax.transAxes, va="top", ha="left")
    if d2 is not None:
        p2 = float((d2 >= s_tuple[3]).mean())
        ax.text(0.02, 0.89, f"P2(x ≥ {s_tuple[3]:g}) = {p2:.3%}", transform=ax.transAxes, va="top", ha="left")

    ax.set_title("Monte Carlo Simulation")
    ax.set_xlabel("Value")
    ax.set_ylabel("Frequency")
    ax.legend(loc="best")

    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", bbox_inches="tight")
    plt.close(fig)

    # Release arrays before trimming
    try:
        del d1
    except Exception:
        pass
    try:
        del d2
    except Exception:
        pass

    _trim_memory_safely()
    data = buf.getvalue()
    try:
        buf.close()
    except Exception:
        pass
    return data


def render_probability_pdf(
    min_val: float,
    max_val: float,
    n: int,
    target: float,
    second: Optional[Dict[str, Any]] = None,
    bins: int = 50,
):
    """
    Legacy API: returns a BytesIO for callers that expect a file-like object.
    Prefer `render_probability_pdf_isolated` for web views.
    """
    data = _build_pdf_bytes_inproc(min_val, max_val, n, target, second=second, bins=bins)
    return io.BytesIO(data)


# -------------------------
# Process-isolated renderer
# -------------------------

def _child_render_main(conn, params: Tuple[float, float, int, float, Optional[Dict[str, Any]], int]):
    """
    Child process entry point. Creates the PDF *entirely* in the child, then
    sends raw bytes back through a pipe. This ensures the allocator state that
    NumPy/Matplotlib created dies with the process.
    """
    try:
        # Minimal imports before setting thread caps
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
        os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

        (min_val, max_val, n, target, second, bins) = params
        pdf_bytes = _build_pdf_bytes_inproc(min_val, max_val, n, target, second=second, bins=bins)
        conn.send(pdf_bytes)
        # Explicitly drop reference
        del pdf_bytes
    except Exception as e:
        try:
            conn.send( ("__error__", f"{type(e).__name__}: {e}") )
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
        # Child-side trim before exit (optional)
        _trim_memory_safely()


def render_probability_pdf_isolated(
    min_val: float,
    max_val: float,
    n: int,
    target: float,
    second: Optional[Dict[str, Any]] = None,
    bins: int = 50,
    timeout: int = 20,
) -> bytes:
    """
    Build the PDF in a short-lived child process and return raw bytes.

    If the render exceeds `timeout` seconds, the child is terminated and a
    TimeoutError is raised.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child_render_main,
        args=(child_conn, (float(min_val), float(max_val), int(n), float(target), second, int(bins))),
        daemon=True,
    )
    proc.start()
    child_conn.close()  # parent keeps only parent_conn

    try:
        # Wait for either data to be ready or timeout
        if not parent_conn.poll(timeout):
            # No data in time—terminate
            try:
                proc.terminate()
            finally:
                proc.join(2)
            raise TimeoutError("Monte Carlo rendering timed out.")

        # There is something to read
        data = parent_conn.recv()  # could be bytes or ("__error__", message)
    finally:
        try:
            parent_conn.close()
        except Exception:
            pass
        # Ensure the process is gone
        proc.join(timeout=2)
        if proc.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            proc.join(timeout=2)

    # Error path from child
    if isinstance(data, tuple) and data and data[0] == "__error__":
        raise RuntimeError(data[1])

    # Normal path: data is bytes (from send_bytes or send)
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)

    # Fallback: unexpected type
    raise RuntimeError("Unexpected response type from Monte Carlo renderer.")
