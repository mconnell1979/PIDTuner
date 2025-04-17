from dateutil import parser  # Ensure this is imported at the top
import pandas as pd, uuid
from .models import PIDLoop, PIDCalculation, LambdaVariable, BumpTest, TrendChart
from .forms import TrendChartUploadForm, PIDLoopForm
import json, os, pytz
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import is_aware, make_aware
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.urls import reverse_lazy
from django.views.generic import CreateView
import numpy as np

def pid_loop_list(request):
    loops = PIDLoop.objects.all()

    if request.method == "POST":
        # Handle Delete Action
        for loop in loops:
            if f"delete_{loop.id}" in request.POST:
                loop.delete()
                return redirect("tuner:pid_loop_list")  # Redirect to refresh the list after deletion

        # Handle Save (Edit) Action
        for loop in loops:
            if f"save_{loop.id}" in request.POST:
                loop.name = request.POST.get(f"name_{loop.id}", loop.name)
                loop.pid_type = request.POST.get(f"pid_type_{loop.id}", loop.pid_type)
                loop.description = request.POST.get(f"description_{loop.id}", loop.description)
                loop.save()
                break  # Process only the edited row to prevent unintended saves

        return redirect("tuner:pid_loop_list")  # Redirect to refresh the page

    return render(request, "tuner/pid_loop_list.html", {"loops": loops})


def pid_loop_detail(request, loop_id):
    pid_loop = get_object_or_404(PIDLoop, id=loop_id)
    trend_charts = TrendChart.objects.filter(pid_loop=pid_loop)

    return render(request, "tuner/pid_loop_detail.html", {
        "pid_loop": pid_loop,
        "trend_charts": trend_charts
    })


def pid_loop_create(request):
    if request.method == "POST":
        form = PIDLoopForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tuner:pid_loop_list")  # Redirect to the list after saving
    else:
        form = PIDLoopForm()

    return render(request, "tuner/pid_loop_form.html", {"form": form})


class PIDLoopCreateView(CreateView):
    model = PIDLoop
    form_class = PIDLoopForm
    template_name = "tuner/pid_loop_form.html"  # Still needs a template
    success_url = reverse_lazy("tuner:pid_loop_list")


def upload_trend_chart(request):
    preview_data = None
    user_timezone = request.POST.get("user_timezone", "UTC")

    if request.method == "POST":
        form = TrendChartUploadForm(request.POST, request.FILES)

        if not form.is_valid():
            return JsonResponse({"error": "Invalid form submission."}, status=400)

        file = request.FILES.get("csv_file")
        if not file:
            return JsonResponse({"error": "No file uploaded."}, status=400)

        # ✅ Generate unique filename
        unique_filename = f"{uuid.uuid4()}_{file.name}"
        file_path = os.path.join(settings.MEDIA_ROOT, "trend_charts", unique_filename)

        with open(file_path, "wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        # ✅ Detect delimiter
        file_ext = os.path.splitext(file.name)[-1].lower()
        delimiter = "," if file_ext == ".csv" else "\t"

        # ✅ Read CSV file
        try:
            df = pd.read_csv(file_path, delimiter=delimiter, dtype=str)
            print(f"📂 Raw DataFrame Columns: {df.columns.tolist()}")
            print(f"📂 Raw DataFrame Head:\n{df.head()}")
        except Exception as e:
            return JsonResponse({"error": f"Error reading file: {str(e)}"}, status=400)

        # ✅ Ensure "Time" column exists
        time_col = next((col for col in df.columns if "time" in col.lower()), None)
        if not time_col:
            return JsonResponse({"error": "Missing 'Time' column in CSV."}, status=400)

        # ✅ Detect PV and CV columns dynamically
        pv_col = next((col for col in df.columns if "pv" in col.lower()), None)
        cv_col = next((col for col in df.columns if "cv" in col.lower()), None)
        if not pv_col or not cv_col:
            return JsonResponse({"error": "Missing PV/CV columns in CSV."}, status=400)

        # ✅ Rename columns for consistency
        df.rename(columns={time_col: "Time", pv_col: "PV", cv_col: "CV"}, inplace=True)

        # ✅ Use dateutil.parser for flexible datetime parsing
        df["Time"] = df["Time"].apply(lambda x: parser.parse(x) if pd.notna(x) else pd.NaT)

        # 🚨 Check if no valid timestamps were found
        if df["Time"].isna().all():
            print("🚨 ERROR: No valid timestamps found after trying all formats!")
            return JsonResponse({"error": "Processed CSV has no valid timestamps."}, status=400)

        # ✅ Drop NaT timestamps
        df.dropna(subset=["Time"], inplace=True)

        # ✅ Convert Time to UTC
        try:
            user_tz = pytz.timezone(user_timezone)
            df["Time"] = df["Time"].dt.tz_localize(user_tz).dt.tz_convert(pytz.utc)
        except Exception as e:
            return JsonResponse({"error": f"Invalid timezone conversion: {str(e)}"}, status=400)

        # ✅ Convert PV and CV to numeric
        df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
        df["CV"] = pd.to_numeric(df["CV"], errors="coerce")

        # ✅ Forward-fill missing PV and CV values
        df["PV"] = df["PV"].ffill()
        df["CV"] = df["CV"].ffill()

        # ✅ Print debugging info to confirm forward-fill
        print(f"✅ Final Processed Data (First 5 Rows After Fill-Forward):\n{df.head()}")

        # ✅ Save cleaned file before storing in the database
        df.to_csv(file_path, index=False, encoding="utf-8")

        # ✅ Save TrendChart instance
        trend_chart = form.save(commit=False)
        trend_chart.csv_file = os.path.join("trend_charts", unique_filename)  # 🛠️ Fix path issue
        trend_chart.save()

        # ✅ Extract preview data (first 20 rows)
        preview_data = df.head(20).to_dict(orient="records")

        print(f"✅ Processed file saved: {file.name}")
        print(f"📊 Preview Data Sent to Template:\n {preview_data}")

        return render(request, "tuner/upload_trend_chart.html", {
            "form": form,
            "preview_data": preview_data,
        })

    else:
        form = TrendChartUploadForm()  # ✅ Ensures form is passed when loading the page initially

    return render(request, "tuner/upload_trend_chart.html", {"form": form})


def trend_chart_list(request):
    charts = TrendChart.objects.all()
    print("Charts Found:", charts)  # Debugging line
    return render(request, "tuner/trend_chart_list.html", {"charts": charts})


def view_trend_chart(request, chart_id):
    """View a trend chart ensuring all timestamps are correctly parsed and display saved bump tests."""

    from django.http import JsonResponse
    import pandas as pd

    trend_chart = get_object_or_404(TrendChart, id=chart_id)

    if not trend_chart.csv_file:
        return JsonResponse({"error": "File not found."})

    # ✅ Read CSV file
    df = pd.read_csv(trend_chart.csv_file.path)

    print(f"🔍 Raw Data from CSV ({len(df)} rows):\n", df.head(10))

    if "Time" not in df.columns:
        return JsonResponse({"error": "Missing 'Time' column in trend file!"}, status=400)

    # ✅ Known timestamp formats to check
    known_formats = [
        "%Y-%m-%d %H:%M:%S.%f%z",  # Format with microseconds and timezone
        "%Y-%m-%d %H:%M:%S%z",  # Format without microseconds
        "%Y-%m-%d %H:%M:%S",  # Standard format without timezone
        "%m/%d/%Y %I:%M:%S %p",  # MM/DD/YYYY hh:mm:ss AM/PM
    ]

    def try_parsing_time(time_str):
        """Attempts parsing using predefined formats."""
        if pd.isna(time_str) or not isinstance(time_str, str):
            return None

        for fmt in known_formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        return pd.NaT  # Return NaT if parsing fails

    # ✅ Apply explicit parsing instead of relying on Pandas auto-inference
    df["Time"] = df["Time"].apply(try_parsing_time)

    # 🚨 Debug: Count invalid timestamps (NaT)
    invalid_times = df["Time"].isna().sum()
    print(f"⚠️ Invalid Time Entries After Parsing: {invalid_times}")

    # ✅ Drop NaT (invalid timestamps)
    before_drop = len(df)
    df.dropna(subset=["Time"], inplace=True)
    after_drop = len(df)
    print(f"✅ Rows before dropna: {before_drop}, after dropna: {after_drop}")

    # ✅ Ensure "PV" and "CV" exist
    if "PV" not in df.columns or "CV" not in df.columns:
        return JsonResponse({"error": "Missing PV/CV columns!"})

    # ✅ Convert PV and CV to float
    df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
    df["CV"] = pd.to_numeric(df["CV"], errors="coerce")

    # ✅ Forward fill missing values
    df["PV"] = df["PV"].ffill()
    df["CV"] = df["CV"].ffill()

    # ✅ Ensure chronological order
    df = df.sort_values(by="Time")

    print(f"✅ After Processing: {len(df)} rows remaining.")

    # ✅ Convert timestamps for frontend compatibility
    # Ensure "Time" is a proper datetime column before using .dt
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")

    # Drop rows where Time could not be converted (if needed)
    df.dropna(subset=["Time"], inplace=True)

    # Now safely format the datetime column
    df["Time"] = df["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ✅ Convert to JSON format for rendering
    # Convert DataFrame to JSON safely (replace NaN with None)
    chart_data = df.where(pd.notna(df), None).to_dict(orient="records")

    # ✅ Fetch associated bump tests
    bump_tests = BumpTest.objects.filter(trend_chart=trend_chart)
    print(f"🔍 Found {len(bump_tests)} bump tests for trend chart {trend_chart.id}")

    # 🚀 Final Debugging
    print(f"📌 Final Data Sent to Frontend ({len(chart_data)} points):", chart_data[:10])

    context = {
        "trend_chart": trend_chart,
        "trend_chart_id": chart_id,
        "pid_name": trend_chart.pid_loop.name,
        "chart_data": json.dumps(chart_data, ensure_ascii=False, allow_nan=False),
        "bump_tests": bump_tests,  # ✅ Pass bump tests to template
    }

    return render(request, "tuner/view_trend_chart.html", context)


@csrf_exempt
def save_bump(request, chart_id):
    """Saves a bump test while ensuring correct UTC handling."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    try:
        data = json.loads(request.body)
        bump_start = data.get("bump_start")
        bump_end = data.get("bump_end")

        if not bump_start or not bump_end:
            return JsonResponse({"error": "Missing bump start or end time"}, status=400)

        trend_chart = get_object_or_404(TrendChart, id=chart_id)

        # ✅ Parse ISO timestamps (they are already in UTC from JavaScript)
        bump_start_dt = parse_datetime(bump_start)
        bump_end_dt = parse_datetime(bump_end)

        # ✅ Ensure timestamps are stored as UTC (just in case)
        if not is_aware(bump_start_dt):
            bump_start_dt = make_aware(bump_start_dt)
        if not is_aware(bump_end_dt):
            bump_end_dt = make_aware(bump_end_dt)

        new_bump = BumpTest.objects.create(
            trend_chart=trend_chart,
            start_time=bump_start_dt,
            end_time=bump_end_dt
        )

        print(f"✅ Saved Bump {new_bump.id}: {bump_start_dt} → {bump_end_dt} (UTC)")
        return JsonResponse({"success": True, "bump_id": new_bump.id})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def update_bump_tests(request, pid_calculation_id):
    """Handles individual bump test selections for a given PID Calculation."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            bump_id = data.get("bump_id")
            assigned = data.get("assigned", False)

            if bump_id is None:
                return JsonResponse({"success": False, "error": "No bump_id provided"}, status=400)

            pid_calculation = get_object_or_404(PIDCalculation, id=pid_calculation_id)
            bump_test = get_object_or_404(BumpTest, id=bump_id)

            if assigned:
                pid_calculation.bump_tests.add(bump_test)  # ✅ Add bump test
            else:
                pid_calculation.bump_tests.remove(bump_test)  # ✅ Remove bump test

            pid_calculation.save()
            pid_calculation.recalculate_tuning()  # ✅ Trigger recalculation
            pid_calculation.save()  # ✅ Save changes

            return JsonResponse({
                "success": True,
                "assigned_bumps": list(pid_calculation.bump_tests.values_list('id', flat=True))
            })

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Invalid request method"}, status=400)


@csrf_exempt
def delete_bump(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            bump_id = data.get("bump_id")  # ✅ Get the ID from the request

            if not bump_id:
                return JsonResponse({"success": False, "error": "Missing bump ID"})

            deleted, _ = BumpTest.objects.filter(id=bump_id).delete()

            if deleted:
                return JsonResponse({"success": True})
            else:
                return JsonResponse({"success": False, "error": "Bump test not found"})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request method"})


def identity_trend(request):
    pid_loops = PIDLoop.objects.all()
    pid_loop_data = []

    for loop in pid_loops:
        trend_charts = TrendChart.objects.filter(pid_loop=loop)
        trend_charts_data = []

        for chart in trend_charts:
            bumps = BumpTest.objects.filter(
                trend_chart=chart,
                start_time__isnull=False,
                end_time__isnull=False
            )

            trend_charts_data.append({
                "trend_chart": chart,
                "bump_tests": bumps,
            })

        pid_loop_data.append({
            "pid_loop": loop,
            "trend_charts_data": trend_charts_data,
        })

    context = {"pid_loop_data": pid_loop_data}
    return render(request, "tuner/identity_trend_list.html", context)


def format_marker_with_offset(time_value, offset_hours):
    """Convert a timestamp to a string and adjust for the user's local timezone offset."""
    if time_value:
        adjusted_time = time_value + timedelta(hours=offset_hours)
        return adjusted_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return ""


def format_marker(time_value):
    """Convert a timestamp to a string in UTC format."""
    if time_value:
        return time_value.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return ""


def identity_trend_detail(request, chart_id, bump_test_id):
    trend_chart = get_object_or_404(TrendChart, id=chart_id)
    bump_test = get_object_or_404(BumpTest, id=bump_test_id, trend_chart=trend_chart)
    pid_loop = trend_chart.pid_loop  # Get the associated PIDLoop

    # ✅ Get timezone offset (in hours) from frontend request
    timezone_offset = request.GET.get("timezone_offset", 0)
    try:
        timezone_offset = int(timezone_offset)
    except ValueError:
        timezone_offset = 0  # Default to 0 if invalid

    # ✅ Function to convert UTC to local time using the offset
    def convert_to_local(utc_time):
        if utc_time:
            return (utc_time.astimezone(pytz.UTC) + timedelta(hours=timezone_offset)).isoformat()
        return None

    if not trend_chart.csv_file:
        return JsonResponse({"error": "File not found."}, status=400)

    df = pd.read_csv(trend_chart.csv_file.path)

    print("📌 All Available Timestamps in Dataset Whe df just set:")
    print(df["Time"].head(20))  # Print first 20 timestamps
    print(df["Time"].tail(20))  # Print last 20 timestamps

    if "Time" not in df.columns:
        return JsonResponse({"error": "Missing 'Time' column in trend file!"}, status=400)

    df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
    df.dropna(subset=["Time"], inplace=True)
    df = df.sort_values(by="Time")

    print("📌 All Available Timestamps in Dataset after pd.to_dtattiem, dropna, and sort:")
    print(df["Time"].head(20))  # Print first 20 timestamps
    print(df["Time"].tail(20))  # Print last 20 timestamps

    if "PV" not in df.columns or "CV" not in df.columns:
        return JsonResponse({"error": "Missing PV/CV columns!"}, status=400)

    df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
    df["CV"] = pd.to_numeric(df["CV"], errors="coerce")
    df.ffill(inplace=True)

    bump_start = bump_test.start_time.astimezone(pytz.UTC).replace(microsecond=0)
    bump_end = bump_test.end_time.astimezone(pytz.UTC).replace(microsecond=0)

    print("📌 Bump Start Time (UTC):", bump_start)
    print("📌 Bump End Time (UTC):", bump_end)

    print("📌 All Available Timestamps in Dataset:")
    print(df["Time"].head(20))  # Print first 20 timestamps
    print(df["Time"].tail(20))  # Print last 20 timestamps

    # ✅ New Fix: If filtering results in an empty DataFrame, use full dataset
    if bump_start and bump_end:
        df_filtered = df[(df["Time"] >= bump_start) & (df["Time"] <= bump_end)]
        if df_filtered.empty:
            print("⚠️ No data found within bump range! Sending full dataset instead.")
            df_filtered = df  # ✅ Fallback: Send entire dataset
    else:
        df_filtered = df  # ✅ Fallback: Send entire dataset if bump times are missing

    df_filtered = df_filtered.copy()
    df_filtered["Time"] = df_filtered["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # ✅ Keep UTC format

    print("📌 First 5 Rows of CSV Data (Before Processing):")
    print(df.head(5))  # Logs original data

    print("📌 First 5 Rows of Filtered Data (After Processing):")
    print(df_filtered.head(5))  # Logs filtered data

    # Calculate delta_cv (change in CV)
    if not df_filtered.empty:
        start_cv = df_filtered.iloc[0]["CV"]
        end_cv = df_filtered.iloc[-1]["CV"]
        bump_test.delta_cv = end_cv - start_cv

        # Calculate delta_pv only if loop_type is "1st Order"
        if pid_loop.pid_type == "1st Order":
            start_pv = df_filtered.iloc[0]["PV"]
            end_pv = df_filtered.iloc[-1]["PV"]
            bump_test.delta_pv = end_pv - start_pv
        else:
            bump_test.delta_pv = None  # Reset if not 1st Order

        bump_test.save()

    chart_data = df_filtered.to_dict(orient="records")
    chart_data_json = json.dumps(chart_data, ensure_ascii=False) if chart_data else "[]"

    # ✅ Convert markers to UTC (Do NOT adjust for local time before sending)
    t_markers = {
        "T1": {"time": bump_test.T1.isoformat() if bump_test.T1 else None, "pv": None},
        "T2": {"time": bump_test.T2.isoformat() if bump_test.T2 else None, "pv": None},
        "T3": {"time": bump_test.T3.isoformat() if bump_test.T3 else None, "pv": None},
        "T4": {"time": bump_test.T4.isoformat() if bump_test.T4 else None, "pv": None},
        "TCV": {"time": bump_test.TCV.isoformat() if bump_test.TCV else None, "pv": None},
    }

    t_marker_notes = {
        "T1": bump_test.T1_note or "No Note",
        "T2": bump_test.T2_note or "No Note",
        "T3": bump_test.T3_note or "No Note",
        "T4": bump_test.T4_note or "No Note"
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        return JsonResponse({
            "t_markers": t_markers,
            "t_marker_notes": t_marker_notes,
            "delta_cv": bump_test.delta_cv,
            "delta_pv": bump_test.delta_pv if pid_loop.pid_type == "1st Order" else None,
        })

    print("📌 Final Chart Data Sent to Frontend (First 5 Rows):")
    print(chart_data[:5])  # Logs first 5 rows

    return render(request, "tuner/identity_trend_detail.html", {
        "trend_chart": trend_chart,
        "bump_test": bump_test,
        "pid_loop": pid_loop,
        "t_markers": json.dumps(t_markers, ensure_ascii=False),
        "t_marker_notes": t_marker_notes,
        "chart_data": chart_data_json.replace("</", "<\\/"),
        "delta_cv": bump_test.delta_cv,
        "delta_pv": bump_test.delta_pv if pid_loop.pid_type == "1st Order" else None,
    })


@csrf_exempt
def update_t1_t2(request, bump_test_id):
    """Update only modified T markers for a bump test and return updated values."""

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method"}, status=400)

    try:
        data = json.loads(request.body)

        print(f"📌 Received data for Bump Test {bump_test_id}: {data}")

        bump_test = get_object_or_404(BumpTest, id=bump_test_id)
        trend_chart = bump_test.trend_chart
        pid_loop = trend_chart.pid_loop

        if not trend_chart.csv_file:
            return JsonResponse({"error": "File not found."}, status=400)

        # ✅ Get the timezone offset from frontend (should be in hours)
        browser_timezone_offset = float(data.get("timezone_offset", 0))  # Convert to float in case it's a string

        print(f"📌 Received Timezone Offset from Browser: {browser_timezone_offset} hours")

        # ✅ Helper function to convert local timestamps to UTC
        def convert_local_to_utc(dt_str):
            if not dt_str:
                return None
            try:
                local_dt = datetime.fromisoformat(dt_str.replace("Z", ""))  # Convert string to datetime
                timezone_offset_seconds = browser_timezone_offset * 3600  # Convert hours to seconds
                utc_dt = local_dt - timedelta(seconds=timezone_offset_seconds)  # Adjust to UTC
                print(f"📌 MCC TimeZone Offset {browser_timezone_offset} hours")
                print(f"📌 Adjusting {dt_str} (Local) → {utc_dt} (UTC), Offset Applied: {browser_timezone_offset} hours")
                return utc_dt.replace(tzinfo=pytz.UTC)
            except ValueError as e:
                print(f"❌ Error parsing datetime: {dt_str} -> {e}")
                return None

        # ✅ Only update the fields that exist in the request payload
        updated_fields = {}

        print(f"📌 Received update for {bump_test_id}: {data}")

        # ✅ Always update T1, T2, T4, and TCV regardless of pid_type
        for key in ["T1", "T2", "T4", "TCV"]:
            if key in data and isinstance(data[key], str) and data[key]:
                try:
                    print(f"📌 Parsing {key}: {data[key]}")  # ✅ Debugging
                    # ✅ Use dateutil.parser.parse() to handle ISO format correctly
                    parsed_time = parser.parse(data[key])
                    print(f"📌 Parsing Finished!!!")  # ✅ Debugging

                    # ✅ Ensure parsed_time is timezone-aware
                    if parsed_time.tzinfo is None:
                        parsed_time = parsed_time.replace(tzinfo=pytz.UTC)

                    parsed_time = parsed_time.astimezone(pytz.UTC)  # Ensure final timezone is UTC
                    print(f"✅ Successfully parsed {key}: {parsed_time} (Type: {type(parsed_time)})")  # Debugging output
                    setattr(bump_test, key, parsed_time)
                    print(f"📌 setattr Finished!!!")  # ✅ Debugging
                    updated_fields[key] = parsed_time
                    print(f"📌 updated fields key finished!!!")  # ✅ Debugging
                except Exception as e:
                    print(f"❌ Error parsing {key}: {data[key]} -> {e}")  # ✅ Log exact failure
                    return JsonResponse({"success": False, "error": f"Invalid datetime format for {key}: {e}"},
                                        status=400)

        # ✅ Read the trend chart data
        file_path = trend_chart.csv_file.path
        if not os.path.exists(file_path):
            return JsonResponse({"error": "Trend chart file not found."}, status=400)

        df = pd.read_csv(file_path)
        df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
        df.dropna(subset=["Time"], inplace=True)
        df = df.sort_values(by="Time")

        bump_start = bump_test.start_time.astimezone(pytz.UTC).replace(microsecond=0)
        bump_end = bump_test.end_time.astimezone(pytz.UTC).replace(microsecond=0)
        df_filtered = df[(df["Time"] >= bump_start) & (df["Time"] <= bump_end)]

        # ✅ Update TCV: Find the first time the final CV value appears
        if not df_filtered.empty:
            final_cv_value = df_filtered.iloc[-1]["CV"]
            matching_rows = df_filtered[df_filtered["CV"] == final_cv_value]
            if not matching_rows.empty:
                bump_test.TCV = matching_rows.iloc[0]["Time"]
                updated_fields["TCV"] = bump_test.TCV

        # New Code
        if pid_loop.pid_type == "1st Order":
            # ✅ Use only data within bump start & end times
            if not df_filtered.empty:
                start_pv = df_filtered.iloc[0]["PV"]  # ✅ Use bump start PV
                end_pv = df_filtered.iloc[-1]["PV"]  # ✅ Use bump end PV
                delta_pv = end_pv - start_pv
                target_pv = start_pv + 0.632 * delta_pv  # ✅ Find 63.2% response within bump window

                # Find the closest timestamp where PV reaches `target_pv` inside bump range
                closest_row = df_filtered.iloc[(df_filtered["PV"] - target_pv).abs().argsort()[:1]]

                if not closest_row.empty:
                    closest_time = closest_row["Time"].values[0]
                    bump_test.T3 = closest_time  # ✅ Assign calculated T3
                    updated_fields["T3"] = closest_time
        elif pid_loop.pid_type in ["Integrating", "Integrating with Lag"]:
            # ✅ Allow manual updates for T3
            if "T3" in data and isinstance(data["T3"], str) and data["T3"]:
                try:
                    parsed_time = parse_datetime(data["T3"])
                    if parsed_time:
                        parsed_time = parsed_time.astimezone(pytz.UTC)
                        bump_test.T3 = parsed_time
                        updated_fields["T3"] = parsed_time
                except Exception as e:
                    return JsonResponse({"success": False, "error": f"Invalid datetime format for T3: {e}"},
                                        status=400)

        # Ensure all updated fields are stored in proper datetime format
        for key in updated_fields:
            if isinstance(updated_fields[key], pd.Timestamp):
                updated_fields[key] = updated_fields[key].to_pydatetime()
            elif isinstance(updated_fields[key], np.datetime64):
                updated_fields[key] = pd.to_datetime(updated_fields[key]).to_pydatetime()
            elif isinstance(updated_fields[key], str):
                try:
                    updated_fields[key] = parser.parse(updated_fields[key])
                except Exception as e:
                    print(f"❌ Error parsing {key}: {updated_fields[key]} -> {e}")

        # Convert pandas.Timestamp and numpy.datetime64 to Python datetime before saving
        for key in updated_fields:
            if isinstance(updated_fields[key], pd.Timestamp):
                updated_fields[key] = updated_fields[key].to_pydatetime()
            elif isinstance(updated_fields[key], np.datetime64):
                updated_fields[key] = pd.to_datetime(updated_fields[key]).to_pydatetime()
            elif isinstance(updated_fields[key], str):
                try:
                    updated_fields[key] = parser.parse(updated_fields[key])  # ✅ Convert to datetime, NOT string
                except Exception as e:
                    print(f"❌ Error parsing {key}: {updated_fields[key]} -> {e}")

        # 🚨 DO NOT CONVERT TO STRING BEFORE SAVING!
        print(f"📌 Final Updated Fields Before Save (Fixed): {updated_fields}")

        try:
            # ✅ Ensure `bump_test` gets datetime objects, NOT strings
            for key, value in updated_fields.items():
                setattr(bump_test, key, value)

            bump_test.save()
            print(f"✅ Bump Test {bump_test_id} Saved Successfully!")

        except Exception as e:
            print(f"❌ Error during bump_test.save(): {e}")
            return JsonResponse({"success": False, "error": f"Failed to save bump test: {e}"}, status=500)

        # ✅ Now, convert to strings ONLY for the JSON response
        return JsonResponse({
            "success": True,
            **{key: updated_fields[key].isoformat() if isinstance(updated_fields[key], datetime) else None for key in
               updated_fields}
        })


    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def pid_calculation_list(request):
    """Display a list of PID loops with links to their calculation details."""
    pid_loops = PIDLoop.objects.all()
    return render(request, "tuner/pid_calculation_list.html", {"pid_loops": pid_loops})


def pid_calculation_detail(request, loop_id):
    """Display PID tuning parameters for a specific PID loop."""
    pid_loop = get_object_or_404(PIDLoop, id=loop_id)

    # ✅ Ensure PIDCalculation exists
    pid_calculation, created = PIDCalculation.objects.get_or_create(
        pid_loop=pid_loop,
        defaults={"proportional_gain": 1.0, "integral_time": 10.0, "derivative_time": 0.0, "acceptable_filter_time": 0.5}
    )

    # ✅ Ensure LambdaVariable exists
    lambda_variable, created = LambdaVariable.objects.get_or_create(
        pid_loop=pid_loop,
        defaults={"lambda_value": 10.0, "min_lambda": 1.0, "max_lambda": 100.0}
    )

    # ✅ Retrieve all BumpTests associated with this PID Loop
    available_bump_tests = BumpTest.objects.filter(trend_chart__pid_loop=pid_loop)

    # ✅ Retrieve all BumpTests currently assigned to this PID Calculation
    assigned_bump_tests = pid_calculation.bump_tests.all()

    # ✅ Debugging: Print available bump tests
    print(f"PIDCalculation {pid_calculation.id} has {assigned_bump_tests.count()} assigned bump tests.")

    for bump in assigned_bump_tests:
        print(f" - Bump Test {bump.id} (T1: {bump.T1}, T2: {bump.T2})")

    return render(request, "tuner/pid_calculation_detail.html", {
        "pid_loop": pid_loop,
        "pid_calculation": pid_calculation,
        "available_bump_tests": available_bump_tests,
        "assigned_bump_tests": assigned_bump_tests,
    })


@csrf_exempt
def recalculate_pid(request, loop_id):
    """Handles recalculating PID tuning when lambda is updated."""

    print(f"🔍 Received request to recalculate PID for loop ID: {loop_id}")

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            new_lambda = float(data.get("lambda_value"))

            # Fetch PIDLoop using loop_id
            pid_loop = get_object_or_404(PIDLoop, id=loop_id)

            # Fetch the PIDCalculation associated with this PIDLoop
            pid_calculation = get_object_or_404(PIDCalculation, pid_loop=pid_loop)

            print(f"✅ Found PIDCalculation: {pid_calculation}")

            # ✅ Update Lambda Value and Recalculate
            pid_calculation.lambda_value = new_lambda
            pid_calculation.recalculate_tuning()
            pid_calculation.save()

            # ✅ Get Updated BumpTest Data
            bump_tests_data = [
                {
                    "id": bump.id,
                    "p": round(bump.p, 3) if bump.p is not None else "-",
                    "i": round(bump.i, 1) if bump.i is not None else "-",
                    "d": round(bump.d, 1) if bump.d is not None else "-",
                }
                for bump in pid_calculation.bump_tests.all()
            ]

            return JsonResponse(
                {
                    "success": True,
                    "kp": round(pid_calculation.proportional_gain, 3),
                    "ti": round(pid_calculation.integral_time, 1),
                    "td": round(pid_calculation.derivative_time, 1),
                    "bump_tests": bump_tests_data,  # ✅ Send updated bump test values
                }
            )

        except Exception as e:
            print(f"❌ Error during recalculation: {e}")
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Invalid request method"}, status=400)































