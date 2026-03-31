import csv
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates
from pathlib import Path
import sys


def check_int(s):
    if len(s) == 0:
        return False

    if s[0] in ("-", "+"):
        return s[1:].isdigit()
    return s.isdigit()


# Step 1: Read the CSV and identify column positions
data = []
rsrp_pos = rsrq_pos = rssnr_pos = ssRsrp_pos = ssRsrq_pos = ssSinr_pos = 0
time_pos = ping_pos = lpn_pos = roaming_pos = trip_time_pos = 0
radiotype_pos = 0

devices_id = set(())
curr_device = 0

filename = "week10_26"
if len(sys.argv) > 1:
    filename = sys.argv[1]

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
            x_time, x_time1 = [], []
            y_rsrp, y_rsrq, y_rssnr, y_ping = [], [], [], []

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

            for entry in session_entries:
                if (
                    check_int(entry[rsrp_pos])
                    and check_int(entry[rsrq_pos])
                    and check_int(entry[rssnr_pos])
                    and check_int(entry[ping_pos])
                    and entry[lpn_pos] == devices_id[curr_device]):
                    dt = datetime.strptime(entry[time_pos], "%Y-%m-%d %H:%M:%S")
                    x_time.append(dt)
                    y_rsrp.append(int(entry[rsrp_pos]))
                    y_rsrq.append(int(entry[rsrq_pos]))
                    y_rssnr.append(int(entry[rssnr_pos]))

                if (check_int(entry[ping_pos])
                    and entry[lpn_pos] == devices_id[curr_device]):
                    dt = datetime.strptime(entry[time_pos], "%Y-%m-%d %H:%M:%S")
                    x_time1.append(dt)
                    y_ping.append(int(entry[ping_pos]))

                # Get network type from CSV
                network_type = entry[radiotype_pos].strip().upper()  # e.g., "NR", "LTE"

                # Detect changes in network type (only after dt has been set)
                if dt is None:
                    continue
                if prev_network is None:
                    prev_network = network_type
                    segment_start = dt
                elif network_type != prev_network:
                    network_changes.append((segment_start, dt, prev_network))
                    segment_start = dt
                    prev_network = network_type

            if not y_ping:
                print(f"Skipping session {idx + 1} ({transition_type}): no valid data in window")
                plt.close()
                continue

            # Add last segment
            if segment_start is not None and prev_network is not None:
                network_changes.append((segment_start, x_time[-1], prev_network))

            # Create subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), sharex=True)
            below_50_percentage = (np.sum(np.array(y_ping) < 100) / len(y_ping)) * 100

            ax1.grid(True, linestyle="--", alpha=0.5)
            ax2.grid(True, linestyle="--", alpha=0.5)

            ax1.yaxis.set_major_locator(MaxNLocator(nbins=12))
            ax2.yaxis.set_major_locator(MaxNLocator(nbins=12))

            ax1.xaxis.set_major_locator(MaxNLocator(nbins=15))
            ax2.xaxis.set_major_locator(MaxNLocator(nbins=15))
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

            # Plot stats and metrics
            stats_text = {
                'rsrp': f"RSRP Min: {min(y_rsrp)}, Max: {max(y_rsrp)}, Mean: {np.mean(y_rsrp):.2f}",
                'rsrq': f"RSRQ Min: {min(y_rsrq)}, Max: {max(y_rsrq)}, Mean: {np.mean(y_rsrq):.2f}",
                'rssnr': f"RSSNR Min: {min(y_rssnr)}, Max: {max(y_rssnr)}, Mean: {np.mean(y_rssnr):.2f}",
                'ping': f"Ping Min: {min(y_ping)}, Max: {max(y_ping)}, Mean: {np.mean(y_ping):.2f}, <100ms:{below_50_percentage:.2f}%"
            }

            ax1.text(0.01, 1 + (0.05 * 1), stats_text['rsrp'], transform=ax1.transAxes, fontsize=10, color='blue', verticalalignment="bottom")
            ax1.text(0.01, 1 + (0.05 * 2), stats_text['rsrq'], transform=ax1.transAxes, fontsize=10, color='red', verticalalignment="bottom")
            ax1.text(0.01, 1 + (0.05 * 3), stats_text['rssnr'], transform=ax1.transAxes, fontsize=10, color='black', verticalalignment="bottom")

            # Plot RSRP, RSRQ, RSSNR
            ax1.plot(x_time, y_rsrp, label="RSRP", color="blue")
            ax1.plot(x_time, y_rsrq, label="RSRQ", color="red")
            ax1.plot(x_time, y_rssnr, label="RSSNR", color="black")
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
            ax2.plot(x_time1, y_ping, label="Ping", color="green")
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


