"""
Utilities for the Monte Carlo Simulator.

Memory goals:
- Import heavy libs (numpy/matplotlib) only when needed.
- Stream / chunk random generation to avoid large arrays.
- Render PDF in memory (BytesIO), not to disk.
- Close figures, GC, and trim arenas after work.
"""

from typing import Optional, Dict, Any


def _trim_memory_safely() -> None:
    """Best-effort: force GC and ask glibc to return memory to the OS."""
    try:
        import gc, ctypes
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def render_probability_pdf(
    min1: float,
    max1: float,
    n1: int,
    target1: Optional[float] = None,
    second: Optional[Dict[str, Any]] = None,
    *,
    bins: int = 50,
    chunk_size: int = 200_000,
) -> bytes:
    """
    Generate a probability histogram PDF (single or dual simulation) and return raw bytes.

    Args:
        min1, max1, n1: range and sample size for the first simulation.
        target1: optional vertical reference line for the first simulation.
        second: optional dict with keys:
            - 'min' (float), 'max' (float), 'n' (int), and optional 'target' (float)
        bins: number of histogram bins (fixed so we can stream counts).
        chunk_size: how many random values to draw per chunk.

    Returns:
        PDF bytes suitable for an HttpResponse with content_type="application/pdf".
    """
    # Heavy imports stay inside for better idle memory
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")  # non-GUI backend
    import matplotlib.pyplot as plt
    from io import BytesIO

    rng = np.random.default_rng()

    # If a second distribution is provided, use a common binning range so plots align
    if second is not None:
        min2 = float(second["min"])
        max2 = float(second["max"])
        low, high = min(min1, min2), max(max1, max2)
    else:
        low, high = min1, max1

    # Fixed, uniform-width bins (enables streaming/aggregation)
    edges = np.linspace(low, high, bins + 1, dtype=np.float64)
    bin_width = float(edges[1] - edges[0])

    def _density_stream_uniform(a: float, b: float, n: int) -> "np.ndarray":
        """Stream random draws in chunks and build a density histogram with fixed edges."""
        counts = np.zeros(bins, dtype=np.float64)
        remaining = int(n)
        while remaining > 0:
            m = chunk_size if remaining > chunk_size else remaining
            # Draw m samples and update bin counts
            vals = rng.uniform(a, b, m)
            c, _ = np.histogram(vals, bins=edges)
            counts += c
            # free chunk
            del vals
            remaining -= m
        # convert to density: counts / (N * bin_width)
        total = counts.sum()
        if total > 0:
            counts /= (total * bin_width)
        return counts

    # Build densities
    d1 = _density_stream_uniform(min1, max1, n1)
    d2 = None
    target2 = None
    if second is not None:
        d2 = _density_stream_uniform(float(second["min"]), float(second["max"]), int(second["n"]))
        target2 = second.get("target", None)

    # Plot
    fig, ax = plt.subplots()
    # Use bin centers for bar plot
    centers = (edges[:-1] + edges[1:]) / 2.0

    # First histogram
    ax.bar(centers, d1, width=bin_width, edgecolor="white")
    if target1 is not None:
        ax.axvline(float(target1), color="r")

    # Optional second histogram overlay
    if d2 is not None:
        ax.bar(centers, d2, width=bin_width, edgecolor="white", alpha=0.5)
        if target2 is not None:
            ax.axvline(float(target2), color="b")

    ax.set_xlabel("Value")
    ax.set_ylabel("Density")
    ax.set_title("Monte Carlo Simulation")

    # Save to bytes
    buf = BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)

    # Clean up large arrays before returning
    try:
        del d1, d2, centers, edges
    except Exception:
        pass

    _trim_memory_safely()
    return buf.getvalue()

from typing import Optional, Dict, Any, Tuple
from multiprocessing import get_context

def _child_render_main(conn, params: Tuple):
    """Runs in a child process so heavy libs never load in the parent."""
    try:
        (min1, max1, n1, target1, second, bins, chunk_size) = params

        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from io import BytesIO

        rng = np.random.default_rng()

        # Common bin range
        if second is not None:
            low = min(min1, float(second["min"]))
            high = max(max1, float(second["max"]))
        else:
            low, high = min1, max1

        edges = np.linspace(low, high, bins + 1, dtype=np.float64)
        bin_width = float(edges[1] - edges[0])

        def _density_stream_uniform(a: float, b: float, n: int) -> "np.ndarray":
            counts = np.zeros(bins, dtype=np.float64)
            remaining = int(n)
            while remaining > 0:
                m = chunk_size if remaining > chunk_size else remaining
                vals = rng.uniform(a, b, m)
                c, _ = np.histogram(vals, bins=edges)
                counts += c
                del vals
                remaining -= m
            total = counts.sum()
            if total > 0:
                counts /= (total * bin_width)
            return counts

        d1 = _density_stream_uniform(min1, max1, n1)
        d2 = None
        target2 = None
        if second is not None:
            d2 = _density_stream_uniform(float(second["min"]), float(second["max"]), int(second["n"]))
            target2 = second.get("target", None)

        centers = (edges[:-1] + edges[1:]) / 2.0
        fig, ax = plt.subplots()
        ax.bar(centers, d1, width=bin_width, edgecolor="white")
        if target1 is not None:
            ax.axvline(float(target1), color="r")
        if d2 is not None:
            ax.bar(centers, d2, width=bin_width, edgecolor="white", alpha=0.5)
            if target2 is not None:
                ax.axvline(float(target2), color="b")
        ax.set_xlabel("Value")
        ax.set_ylabel("Density")
        ax.set_title("Monte Carlo Simulation")

        buf = BytesIO()
        fig.savefig(buf, format="pdf")
        plt.close(fig)

        pdf_bytes = buf.getvalue()
        conn.send(pdf_bytes)
    except Exception as e:
        conn.send(("__error__", str(e)))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def render_probability_pdf_isolated(
    min1: float,
    max1: float,
    n1: int,
    target1: Optional[float] = None,
    second: Optional[Dict[str, Any]] = None,
    *,
    bins: int = 50,
    chunk_size: int = 200_000,
    timeout: int = 20,
) -> bytes:
    """
    Run the heavy rendering in a short-lived child process.
    Parent never imports numpy/matplotlib, so no resident 200 MB.
    """
    ctx = get_context("spawn")  # ensure clean child without inheriting parent state
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    params = (min1, max1, n1, target1, second, bins, chunk_size)
    proc = ctx.Process(target=_child_render_main, args=(child_conn, params))
    proc.start()
    child_conn.close()

    try:
        if parent_conn.poll(timeout):
            data = parent_conn.recv()
        else:
            proc.terminate()
            proc.join()
            raise TimeoutError("Monte Carlo rendering timed out.")
    finally:
        parent_conn.close()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join()

    if isinstance(data, tuple) and data and data[0] == "__error__":
        raise RuntimeError(data[1])
    return data

