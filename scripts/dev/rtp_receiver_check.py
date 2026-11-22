"""Manual check: decode the RTP/H.264 stream described by stream.sdp (PyAV). Run from any directory."""

from pathlib import Path

import av

SDP_PATH = Path(__file__).resolve().parents[2] / "stream.sdp"  # repository root

def main():
    print(f"[VIDEO] SDP: {SDP_PATH}", flush=True)

    options = {
        "protocol_whitelist": "file,crypto,data,udp,rtp,tcp",
    }

    try:
        with av.open(
            str(SDP_PATH),
            mode="r",
            format="sdp",
            options=options,
            timeout=(10.0, 10.0),
        ) as container:

            print("[VIDEO] Receptor RTP abierto", flush=True)

            count = 0

            for frame in container.decode(video=0):
                image = frame.to_ndarray(format="bgr24")
                count += 1

                if count == 1 or count % 10 == 0:
                    print(
                        f"[VIDEO] Frame {count}: "
                        f"{image.shape[1]}x{image.shape[0]}",
                        flush=True,
                    )

                if count >= 50:
                    print("[VIDEO] PRUEBA SUPERADA: 50 frames")
                    break

    except Exception as exc:
        print(f"[VIDEO] ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
