"""Manual benchmark: CPU/memory of PyAV decoding the RTP stream of stream.sdp for 60 s (needs psutil)."""

from pathlib import Path
import os
import time

import av
import psutil

SDP_PATH = Path(__file__).resolve().parents[2] / "stream.sdp"  # repository root
DURATION_SECONDS = 60
REPORT_SECONDS = 10


def main():
    process = psutil.Process(os.getpid())
    process.cpu_percent(interval=None)

    options = {
        "protocol_whitelist": "file,crypto,data,udp,rtp,tcp",
    }

    print("=== SAFEFLIGHT VIDEO PERFORMANCE TEST ===")
    print(f"SDP: {SDP_PATH}")
    print(f"PID: {os.getpid()}")
    print(f"Duracion: {DURATION_SECONDS} segundos")
    print("Esperando fotogramas RTP...", flush=True)

    frames = 0
    window_frames = 0
    start = None
    window_start = None
    last_frame_time = None
    intervals_ms = []

    try:
        with av.open(
            str(SDP_PATH),
            mode="r",
            format="sdp",
            options=options,
            timeout=(10.0, 10.0),
        ) as container:

            for frame in container.decode(video=0):
                now = time.perf_counter()

                if start is None:
                    start = now
                    window_start = now
                    print(
                        f"Primer frame: {frame.width}x{frame.height}",
                        flush=True,
                    )

                if last_frame_time is not None:
                    intervals_ms.append(
                        (now - last_frame_time) * 1000
                    )

                last_frame_time = now
                frames += 1
                window_frames += 1

                elapsed_window = now - window_start

                if elapsed_window >= REPORT_SECONDS:
                    fps = window_frames / elapsed_window
                    cpu = process.cpu_percent(interval=None)
                    ram = (
                        process.memory_info().rss / (1024 ** 2)
                    )

                    print(
                        f"[{now - start:.1f}s] "
                        f"FPS={fps:.2f} | "
                        f"CPU={cpu:.1f}% | "
                        f"RAM={ram:.1f} MB",
                        flush=True,
                    )

                    window_start = now
                    window_frames = 0

                if now - start >= DURATION_SECONDS:
                    break

        if start is not None and frames:
            duration = time.perf_counter() - start
            average_fps = frames / duration

            print("\n=== RESULTADOS ===")
            print(f"Frames recibidos: {frames}")
            print(f"FPS promedio: {average_fps:.2f}")

            if intervals_ms:
                ordered = sorted(intervals_ms)
                p95_index = int(0.95 * (len(ordered) - 1))

                print(
                    f"Intervalo mediano: "
                    f"{ordered[len(ordered) // 2]:.1f} ms"
                )
                print(
                    f"Intervalo P95: "
                    f"{ordered[p95_index]:.1f} ms"
                )
                print(
                    f"Intervalo maximo: "
                    f"{ordered[-1]:.1f} ms"
                )

            print("PRUEBA FINALIZADA")

        else:
            print("No se recibieron fotogramas.")

    except Exception as exc:
        print(
            f"ERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )


if __name__ == "__main__":
    main()
