"""
Export v26 dataset into clean public CSVs for the awesome-ros repo.
Run once, then delete this script.
"""
import csv
import os
import json

SRC = r"c:\Users\asmbatati\Desktop\ros_survey_revision\data\ROS2 Related Works_v26.csv"
FRAMEWORKS_SRC = r"c:\Users\asmbatati\Desktop\ros_survey_revision\data\ros2pkgs.csv"
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT_DIR, exist_ok=True)

# --- Papers ---
PAPER_COLS = [
    "Paper Title", "DOI", "Authors", "Abstract", "Year",
    "Date of Publication", "Venue of Publication", "Publisher",
    "Type of Manuscript", "ROS Version",
    "Contribution_Type", "Core_type", "Eco_type",
    "App_field", "App_platform",
    "Research_Domain", "Research_Subdomain", "Keyword_Labels",
    "Github Repo", "URL",
]

# Also collect all Label_* columns dynamically
with open(SRC, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    all_headers = reader.fieldnames
    label_cols = [h for h in all_headers if h.startswith("Label_")]

export_cols = PAPER_COLS + label_cols

with open(SRC, "r", encoding="utf-8") as f_in:
    reader = csv.DictReader(f_in)
    out_path = os.path.join(OUT_DIR, "papers.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=export_cols, extrasaction="ignore")
        writer.writeheader()
        count = 0
        for row in reader:
            out_row = {col: row.get(col, "") for col in export_cols}
            writer.writerow(out_row)
            count += 1
    print(f"Exported {count} papers to {out_path}")

# --- Frameworks ---
if os.path.exists(FRAMEWORKS_SRC):
    with open(FRAMEWORKS_SRC, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fw_headers = reader.fieldnames
        out_path = os.path.join(OUT_DIR, "frameworks.csv")
        with open(out_path, "w", encoding="utf-8", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fw_headers)
            writer.writeheader()
            fw_count = 0
            for row in reader:
                writer.writerow(row)
                fw_count += 1
        print(f"Exported {fw_count} frameworks to {out_path}")
else:
    print(f"WARNING: Frameworks source not found at {FRAMEWORKS_SRC}")

# --- Stats summary ---
with open(SRC, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total = len(rows)
ros2 = sum(1 for r in rows if r.get("ROS Version", "").strip().upper() in ("ROS2", "ROS 2", "BOTH"))
ros1 = sum(1 for r in rows if r.get("ROS Version", "").strip().upper() in ("ROS1", "ROS 1"))
years = sorted(set(r.get("Year", "") for r in rows if r.get("Year", "").strip()))
year_range = f"{years[0]}-{years[-1]}" if years else "N/A"

stats = {
    "total_papers": total,
    "ros2_papers": ros2,
    "ros1_papers": ros1,
    "years_covered": year_range,
}
stats_path = os.path.join(OUT_DIR, "stats.json")
with open(stats_path, "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2)
print(f"Stats: {stats}")
print("Done.")
