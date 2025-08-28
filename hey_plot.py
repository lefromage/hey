#!/usr/bin/env python3
import sys
import csv
import argparse
import threading
import time
from collections import deque
from queue import Queue, Empty

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


def parse_args():
    p = argparse.ArgumentParser(description="Live plot streaming CSV from hey (-o csv)")
    p.add_argument(
        "--file",
        "-f",
        help="CSV file to tail instead of reading stdin. If omitted, reads stdin.",
    )
    p.add_argument(
        "--x",
        default="offset",
        help="Column to use for X axis (default: offset)",
    )
    p.add_argument(
        "--y",
        default="response-time",
        help="Column to use for Y axis (default: response-time)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=200,
        help="Animation update interval in ms (default: 200)",
    )
    return p.parse_args()


def stream_lines_from_stdin(out_q: Queue):
    header = None
    reader = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        if header is None:
            # Initialize CSV reader header
            header = [h.strip() for h in line.split(",")]
            continue
        if reader is None:
            reader = csv.reader([line])
        else:
            reader = csv.reader([line])
        for row in reader:
            if len(row) != len(header):
                continue
            record = {h: v for h, v in zip(header, row)}
            out_q.put(record)


def tail_file(path: str, out_q: Queue):
    header = None
    with open(path, "r", buffering=1) as f:
        # Try to read existing lines from start
        while True:
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            if header is None:
                header = [h.strip() for h in line.split(",")]
                continue
            row = next(csv.reader([line]))
            if len(row) != len(header):
                continue
            out_q.put({h: v for h, v in zip(header, row)})
        # Now follow appends
        while True:
            where = f.tell()
            line = f.readline()
            if not line:
                time.sleep(0.1)
                f.seek(where)
                continue
            line = line.strip()
            if not line:
                continue
            if header is None:
                header = [h.strip() for h in line.split(",")]
                continue
            row = next(csv.reader([line]))
            if len(row) != len(header):
                continue
            out_q.put({h: v for h, v in zip(header, row)})


def main():
    args = parse_args()

    q: Queue = Queue()

    if args.file:
        t = threading.Thread(target=tail_file, args=(args.file, q), daemon=True)
    else:
        # If no stdin is piped and no file is given, prompt user
        if sys.stdin is None or sys.stdin in (sys.__stdin__,) and sys.stdin.isatty():
            print("No input detected. Pipe CSV into stdin or pass --file <path>.")
            print("Example: ./hey_test.sh | python hey_plot.py")
            return
        t = threading.Thread(target=stream_lines_from_stdin, args=(q,), daemon=True)
    t.start()

    xs = deque()
    ys = deque()
    status_codes = deque()

    fig, ax = plt.subplots()
    line, = ax.plot([], [], lw=1.8, color="#1f77b4")
    ax.set_xlabel(args.x)
    ax.set_ylabel(args.y)
    ax.grid(True, alpha=0.3)
    ax.set_title("hey live plot")

    def try_float(s):
        try:
            return float(s)
        except Exception:
            return None

    def update(_frame):
        updated = False
        while True:
            try:
                rec = q.get_nowait()
            except Empty:
                break
            x = rec.get(args.x)
            y = rec.get(args.y)
            sc = rec.get("status-code")
            xf = try_float(x)
            yf = try_float(y)
            if xf is None or yf is None:
                continue
            xs.append(xf)
            ys.append(yf)
            status_codes.append(sc)
            updated = True
        if updated:
            line.set_data(list(xs), list(ys))
            if xs and ys:
                ax.set_xlim(min(xs), max(xs) if len(xs) > 1 else max(xs) + 1e-6)
                ymin = min(ys)
                ymax = max(ys)
                if ymin == ymax:
                    ymin -= 0.1
                    ymax += 0.1
                ax.set_ylim(ymin, ymax)
            # Show last status in title
            if status_codes:
                ax.set_title(f"hey live plot — status {status_codes[-1]}")
        return line,

    ani = FuncAnimation(fig, update, interval=args.interval, blit=False)
    plt.show()


if __name__ == "__main__":
    main()
