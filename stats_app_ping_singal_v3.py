import csv
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates
from pathlib import Path
import sys
import argparse


def check_int(s):
    if len(s) == 0:
        return False

    if s[0] in ("-", "+"):
        return s[1:].isdigit()
    return s.isdigit()


## GLOBAL DEFAULTS (edit these as needed)
DEFAULT_MODE = "hybrid"
DEFAULT_GAP_SECONDS = 5
DEFAULT_INTERP_LIMIT = 2
MIN_POINTS = 5
MAX_INTERP_GAP = 3
NOISE_STD = 1.0
DEFAULT_FILENAME = "week10_26"

## PARSING ARGUMENTS
parser = argparse.ArgumentParser(description="Signal analysis with gap handling")

parser.add_argument(
    "--mode",
    choices=["cut", "interpolate", "hybrid"],
    default=DEFAULT_MODE,
    help="Handling missing data: cut gaps, interpolate, or hybrid"
)

parser.add_argument(
    "--gap",
    type=int,
    default=DEFAULT_GAP_SECONDS,
    help="Gap threshold in seconds (used for cut/hybrid)"
)

parser.add_argument(
    "--interp_limit",
    type=int,
    default=DEFAULT_INTERP_LIMIT,
    help="Max consecutive missing points to interpolate (hybrid mode)"
)

parser.add_argument(
    "--filename",
    type=str,
    default=DEFAULT_FILENAME,
    help="Input CSV base filename (without .csv extension)"
)

args = parser.parse_args()

# Global config
MODE = args.mode
GAP_SECONDS = args.gap
INTERP_LIMIT = args.interp_limit
filename = args.filename




# Step 1: Read the CSV and identify column positions
data = []
rsrp_pos = rsrq_pos = rssnr_pos = ssRsrp_pos = ssRsrq_pos = ssSinr_pos = 0
time_pos = ping_pos = lpn_pos = roaming_pos = trip_time_pos = 0
radiotype_pos = 0

devices_id = set(())
curr_device = 0

csv_candidates = [
    Path(f"{filename}.csv"),
    Path("5G-Seagul_data") / f"{filename}.csv",
]
input_csv = next((path for path in csv_candidates if path.exists()), None)
charts_folder = Path("graphs") / filename
charts_folder.mkdir(parents=True, exist_ok=True)

if input_csv is None:
    candidate_list = ", ".join(str(path) for path in csv_candidates)
    raise FileNotFoundError(f"CSV file not found. Checked: {candidate_list}")

with input_csv.open(newline="") as csvfile:
    spamreader = csv.reader(csvfile, delimiter=",", quotechar='"')
    for row in spamreader:
        data.append(row)

# Identify column positions
for j in range(len(data[0])):
    if data[0][j] == "rsrp":
        rsrp_pos = j
    elif data[0][j] == "rsrq":
        rsrq_pos = j
    elif data[0][j] == "rssnr":
        rssnr_pos = j
    elif data[0][j] == "ssRsrp":
        ssRsrp_pos = j
    elif data[0][j] == "ssRsrq":
        ssRsrq_pos = j
    elif data[0][j] == "ssSinr":
        ssSinr_pos = j
    elif data[0][j] == "Time":
        time_pos = j
    elif data[0][j] == "ping":
        ping_pos = j
    elif data[0][j] == "lpn":
        lpn_pos = j
    elif data[0][j] == "roaming":
        roaming_pos = j
    elif data[0][j] == "trip_time":
        trip_time_pos = j
    elif data[0][j] == "radiotype":
        radiotype_pos = j


for i in range(1, len(data)):
    devices_id.add(data[i][lpn_pos])

# print(devices_id)
devices_id = list(devices_id)
devices_id.sort()
print(devices_id);

# Combine ssRsrp, ssRsrq into rsrp, rsrq if they are empty
for i in range(1, len(data)):
    if data[i][rsrp_pos] == "":
        data[i][rsrp_pos] = data[i][ssRsrp_pos]
    if data[i][rsrq_pos] == "":
        data[i][rsrq_pos] = data[i][ssRsrq_pos]
    if data[i][rssnr_pos] == "":
        data[i][rssnr_pos] = data[i][ssSinr_pos]


offset = 500

for curr_device in range(len(devices_id)):
    print(f"\nProcessing device: {devices_id[curr_device]}")
    car_data = []

    # Data per car
    for elem in data:
        if elem[lpn_pos] == devices_id[curr_device]:
            car_data.append(elem)

    # Step 2: Identify both types of sessions in a single loop
    sessions_off_to_on = []  # roaming false -> true
    sessions_on_to_off = []  # roaming true -> false

    for i in range(1, len(car_data)):
        if car_data[i-1][roaming_pos] == "false" and car_data[i][roaming_pos] == "true":
            sessions_off_to_on.append({"start": i})
        elif car_data[i-1][roaming_pos] == "true" and car_data[i][roaming_pos] == "false":
            sessions_on_to_off.append({"start": i})

    # Function to process and plot sessions
    def plot_session_data(sessions, transition_type, line_color):
        session_data = []
        for session in sessions:
            start_idx = max(1, session["start"] - offset)
            end_idx = min(len(car_data) - 1, session["start"] + offset)
            session_data.append(car_data[start_idx:end_idx])

        for idx, session_entries in enumerate(session_data):
            fila_date = datetime.strptime(
                car_data[sessions[idx]["start"]][time_pos], "%Y-%m-%d %H:%M:%S"
            ).strftime("%d_%m_%Y_%H_%M_%S")
            start_transition = datetime.strptime(
                car_data[sessions[idx]["start"]][time_pos], "%Y-%m-%d %H:%M:%S"
            )

            prev_network = None
            segment_start = None
            dt = None
            network_changes = []  # Store (start_time, end_time, network_type)

            # Build DataFrame with datetime index and numeric metrics
            records = []
            for entry in session_entries:
                if entry[lpn_pos] != devices_id[curr_device]:
                    continue
                records.append(
                    {
                        "time": entry[time_pos],
                        "rsrp": entry[rsrp_pos],
                        "rsrq": entry[rsrq_pos],
                        "rssnr": entry[rssnr_pos],
                        "ping": entry[ping_pos],
                        "radiotype": entry[radiotype_pos].strip().upper(),
                    }
                )

            if not records:
                print(f"Skipping session {idx + 1} ({transition_type}): no valid data in window")
                plt.close()
                continue

            df = pd.DataFrame(records)
            df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
            df = df.dropna(subset=["time"]).sort_values("time").set_index("time")
            for metric in ["rsrp", "rsrq", "rssnr", "ping"]:
                df[metric] = pd.to_numeric(df[metric], errors="coerce")

            if df.empty or df["ping"].dropna().empty:
                print(f"Skipping session {idx + 1} ({transition_type}): no valid data in window")
                plt.close()
                continue

            def prepare_segments(metric):
                series = df[metric]
                if series.empty:
                    return [], np.array([])

                # Reindex/interpolation requires unique datetime labels.
                if not series.index.is_unique:
                    series = series.groupby(level=0).mean()

                time_diff = series.index.to_series().diff().dt.total_seconds().fillna(0)
                segment_id = (time_diff > GAP_SECONDS).cumsum()
                segments = []
                combined_values = []
                mode = MODE.lower()

                if mode == "interpolate":
                    raw_valid = series.dropna()
                    if len(raw_valid) < MIN_POINTS:
                        return [], np.array([])
                    full_idx = pd.date_range(series.index.min(), series.index.max(), freq="1s")
                    seg_full = series.reindex(full_idx)
                    seg_processed = seg_full.interpolate(method="time")
                    seg_valid = seg_processed.dropna()
                    if len(seg_valid) >= MIN_POINTS:
                        segments.append((seg_valid.index.to_pydatetime(), seg_valid.values))
                        combined_values.append(seg_valid.values)
                else:
                    for _, seg in series.groupby(segment_id):
                        if seg.empty:
                            continue
                        raw_valid = seg.dropna()
                        if len(raw_valid) < MIN_POINTS:
                            continue

                        if mode == "hybrid":
                            internal_gaps = (
                                raw_valid.index.to_series().diff().dt.total_seconds().dropna()
                            )
                            can_interpolate = (
                                len(raw_valid) >= MIN_POINTS
                                and (
                                    internal_gaps.le(MAX_INTERP_GAP).all()
                                    if not internal_gaps.empty
                                    else True
                                )
                            )

                            if can_interpolate:
                                full_idx = pd.date_range(
                                    raw_valid.index.min(), raw_valid.index.max(), freq="1s"
                                )
                                seg_full = raw_valid.reindex(full_idx)
                                seg_interp = seg_full.interpolate(method="time")

                                # Add controlled jitter to avoid unnaturally straight interpolated traces.
                                if metric in ("rsrp", "rsrq") and NOISE_STD > 0:
                                    noise = np.random.normal(0, NOISE_STD, size=len(seg_interp))
                                    seg_noisy = seg_interp + noise
                                else:
                                    seg_noisy = seg_interp

                                seg_processed = seg_noisy.rolling(window=3, min_periods=1).mean()
                            else:
                                # Sparse segments stay raw to avoid interpolation artifacts.
                                seg_processed = raw_valid

                            seg_valid = seg_processed.dropna()
                            if len(seg_valid) < MIN_POINTS:
                                continue

                            segments.append((seg_valid.index.to_pydatetime(), seg_valid.values))
                            combined_values.append(seg_valid.values)
                            continue
                        else:
                            seg_processed = raw_valid

                        seg_valid = seg_processed.dropna()
                        if len(seg_valid) < MIN_POINTS:
                            continue

                        segments.append((seg_valid.index.to_pydatetime(), seg_valid.values))
                        combined_values.append(seg_valid.values)

                if not combined_values:
                    return [], np.array([])
                return segments, np.concatenate(combined_values)

            rsrp_segments, y_rsrp = prepare_segments("rsrp")
            rsrq_segments, y_rsrq = prepare_segments("rsrq")
            rssnr_segments, y_rssnr = prepare_segments("rssnr")
            ping_segments, y_ping = prepare_segments("ping")

            # Detect network type transitions on valid, sorted timestamps
            network_df = df[["radiotype"]].dropna()
            for ts, row in network_df.iterrows():
                dt = ts.to_pydatetime()
                network_type = row["radiotype"]
                if prev_network is None:
                    prev_network = network_type
                    segment_start = dt
                elif network_type != prev_network:
                    network_changes.append((segment_start, dt, prev_network))
                    segment_start = dt
                    prev_network = network_type

            # Add last segment
            if segment_start is not None and prev_network is not None and not df.empty:
                network_changes.append((segment_start, df.index[-1].to_pydatetime(), prev_network))

            # Create subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), sharex=True)
            below_50_percentage = (
                (np.sum(np.array(y_ping) < 100) / len(y_ping)) * 100 if len(y_ping) > 0 else None
            )

            ax1.grid(True, linestyle="--", alpha=0.5)
            ax2.grid(True, linestyle="--", alpha=0.5)

            ax1.yaxis.set_major_locator(MaxNLocator(nbins=12))
            ax2.yaxis.set_major_locator(MaxNLocator(nbins=12))

            ax1.xaxis.set_major_locator(MaxNLocator(nbins=15))
            ax2.xaxis.set_major_locator(MaxNLocator(nbins=15))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

            # Plot stats and metrics
            def safe_stats(arr, name):
                if len(arr) == 0:
                    return f"{name}: No data"
                return f"{name} Min: {np.min(arr)}, Max: {np.max(arr)}, Mean: {np.mean(arr):.2f}"

            stats_text = {
                "rsrp": safe_stats(y_rsrp, "RSRP"),
                "rsrq": safe_stats(y_rsrq, "RSRQ"),
                "rssnr": safe_stats(y_rssnr, "RSSNR"),
                "ping": safe_stats(y_ping, "Ping")
                + (f", <100ms:{below_50_percentage:.2f}%" if below_50_percentage is not None else ""),
            }

            ax1.text(0.01, 1 + (0.05 * 1), stats_text['rsrp'], transform=ax1.transAxes, fontsize=10, color='blue', verticalalignment="bottom")
            ax1.text(0.01, 1 + (0.05 * 2), stats_text['rsrq'], transform=ax1.transAxes, fontsize=10, color='red', verticalalignment="bottom")
            ax1.text(0.01, 1 + (0.05 * 3), stats_text['rssnr'], transform=ax1.transAxes, fontsize=10, color='black', verticalalignment="bottom")

            # Plot RSRP, RSRQ, RSSNR
            for i_seg, (x_seg, y_seg) in enumerate(rsrp_segments):
                ax1.plot(x_seg, y_seg, label="RSRP" if i_seg == 0 else "_nolegend_", color="blue")
            for i_seg, (x_seg, y_seg) in enumerate(rsrq_segments):
                ax1.plot(x_seg, y_seg, label="RSRQ" if i_seg == 0 else "_nolegend_", color="red")
            for i_seg, (x_seg, y_seg) in enumerate(rssnr_segments):
                ax1.plot(x_seg, y_seg, label="RSSNR" if i_seg == 0 else "_nolegend_", color="black")
            ax1.axvline(x=start_transition, color=line_color, linestyle="--",
                       label=f"Roaming: {transition_type}", alpha=0.7)
            ax1.set_title("RSRP, RSRQ, RSSNR Metrics")
            handles, labels = ax1.get_legend_handles_labels()
            unique_labels = dict(zip(labels, handles))  # Remove duplicates
            ax1.legend(unique_labels.values(), unique_labels.keys(), loc="upper right")
            ax1.set_ylabel("Signal Metrics")

            # Add ping stats
            ax2.text(0.01, 1, stats_text['ping'], transform=ax2.transAxes, fontsize=10, color="green", verticalalignment="bottom")

            # Plot Ping
            for i_seg, (x_seg, y_seg) in enumerate(ping_segments):
                ax2.plot(x_seg, y_seg, label="Ping" if i_seg == 0 else "_nolegend_", color="green")
            ax2.axvline(x=start_transition, color=line_color, linestyle="--",
                       label=transition_type.replace("Roaming: ", ""), alpha=0.7)
            ax2.set_title("Ping Metric")
            ax2.legend(handles=ax2.get_legend_handles_labels()[0], loc="upper right")
            ax2.set_xlabel("Time")
            ax2.set_ylabel("Ping (ms)")

            plt.suptitle(f"Session")
            suffix = "1" if transition_type == "Off → On" else "2"
            output_file = charts_folder / f"{fila_date}_singal_{devices_id[curr_device]}_{suffix}.png"
            plt.savefig(output_file, dpi=300, bbox_inches="tight")
            print(f"Figure saved as {output_file}")
            plt.close()

    # Plot both types of sessions
    plot_session_data(sessions_off_to_on, "Off → On", "red")
    plot_session_data(sessions_on_to_off, "On → Off", "blue")


