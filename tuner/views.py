import pandas as pd
from .models import PIDLoop, BumpTest, TrendChart
from .forms import TrendChartUploadForm, PIDLoopForm
import json, os, pytz
from datetime import datetime, timedelta, timedelta, timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import localtime, is_aware, get_fixed_timezone, make_aware
from django.utils.dateparse import parse_datetime
from django.conf import settings


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


def upload_trend_chart(request):
    if request.method == "POST":
        form = TrendChartUploadForm(request.POST, request.FILES)

        if form.is_valid():
            trend_chart = form.save(commit=False)
            file = request.FILES.get("csv_file")

            if not file:
                return JsonResponse({"error": "No file uploaded."}, status=400)

            # ✅ Save model to retain file
            trend_chart.save()
            file_path = os.path.join(settings.MEDIA_ROOT, str(trend_chart.csv_file))

            if not os.path.exists(file_path):
                return JsonResponse({"error": f"File not found: {file_path}"}, status=400)

            # ✅ Detect delimiter based on file extension
            file_ext = os.path.splitext(file.name)[-1].lower()
            delimiter = "," if file_ext == ".csv" else "\t"

            try:
                df = pd.read_csv(file_path, delimiter=delimiter, dtype=str)
            except Exception as e:
                return JsonResponse({"error": f"Error reading file: {str(e)}"}, status=400)

            # ✅ Clean Timestamps (Handles mixed formats)
            try:
                df = TrendChart.clean_timestamps(df)
                missing_timestamps = df["Time"].isna().sum()
                if missing_timestamps > 0:
                    print(f"⚠️ {missing_timestamps} rows had invalid timestamps and were dropped.")

                df.dropna(subset=["Time"], inplace=True)  # Only drop rows where timestamps failed
            except Exception as e:
                return JsonResponse({"error": f"Error processing timestamps: {str(e)}"}, status=400)

            # ✅ Detect PV and CV columns correctly
            try:
                pv_col, cv_col = TrendChart().detect_pv_cv_columns(df)
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)

            # ✅ Convert PV and CV to numeric safely
            df.rename(columns={pv_col: "PV", cv_col: "CV"}, inplace=True)
            df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
            df["CV"] = pd.to_numeric(df["CV"], errors="coerce")

            # ✅ Forward-fill missing values (only within valid ranges)
            df["PV"] = df["PV"].ffill()
            df["CV"] = df["CV"].ffill()

            # ✅ Save cleaned file
            df.to_csv(file_path, index=False, encoding="utf-8")

            print(f"✅ Processed file saved: {trend_chart.csv_file.name}")

            return redirect("tuner:upload_trend_chart")

    else:
        form = TrendChartUploadForm()

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
    df["Time"] = df["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ✅ Convert to JSON format for rendering
    chart_data = df.to_dict(orient="records")

    # ✅ Fetch associated bump tests
    bump_tests = BumpTest.objects.filter(trend_chart=trend_chart)
    print(f"🔍 Found {len(bump_tests)} bump tests for trend chart {trend_chart.id}")

    # 🚀 Final Debugging
    print(f"📌 Final Data Sent to Frontend ({len(chart_data)} points):", chart_data[:10])

    context = {
        "trend_chart": trend_chart,
        "trend_chart_id": chart_id,
        "pid_name": trend_chart.pid_loop.name,
        "chart_data": json.dumps(chart_data, ensure_ascii=False),
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


@csrf_exempt  # ❌ Remove this if using CSRF protection
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

    if not trend_chart.csv_file:
        return JsonResponse({"error": "File not found."}, status=400)

    df = pd.read_csv(trend_chart.csv_file.path)

    if "Time" not in df.columns:
        return JsonResponse({"error": "Missing 'Time' column in trend file!"}, status=400)

    df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
    df.dropna(subset=["Time"], inplace=True)
    df = df.sort_values(by="Time")

    if "PV" not in df.columns or "CV" not in df.columns:
        return JsonResponse({"error": "Missing PV/CV columns!"}, status=400)

    df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
    df["CV"] = pd.to_numeric(df["CV"], errors="coerce")
    df.ffill(inplace=True)

    bump_start = bump_test.start_time.astimezone(pytz.UTC).replace(microsecond=0)
    bump_end = bump_test.end_time.astimezone(pytz.UTC).replace(microsecond=0)
    df_filtered = df[(df["Time"] >= bump_start) & (df["Time"] <= bump_end)]

    df_filtered = df_filtered.copy()
    df_filtered["Time"] = df_filtered["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    chart_data = df_filtered.to_dict(orient="records")
    chart_data_json = json.dumps(chart_data, ensure_ascii=False) if chart_data else "[]"

    t_markers = {
        "T1": {"time": bump_test.T1.astimezone(pytz.UTC).isoformat() if bump_test.T1 else None, "pv": None},
        "T2": {"time": bump_test.T2.astimezone(pytz.UTC).isoformat() if bump_test.T2 else None, "pv": None},
        "T3": {"time": bump_test.T3.astimezone(pytz.UTC).isoformat() if bump_test.T3 else None, "pv": None},
        "T4": {"time": bump_test.T4.astimezone(pytz.UTC).isoformat() if bump_test.T4 else None, "pv": None},
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
            "t_marker_notes": t_marker_notes
        })

    return render(request, "tuner/identity_trend_detail.html", {
        "trend_chart": trend_chart,
        "bump_test": bump_test,
        "t_markers": json.dumps(t_markers, ensure_ascii=False),
        "t_marker_notes": t_marker_notes,
        "chart_data": chart_data_json.replace("</", "<\\/"),
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

                print(f"📌 Adjusting {dt_str} (Local) → {utc_dt} (UTC), Offset Applied: {browser_timezone_offset} hours")
                return utc_dt.replace(tzinfo=pytz.UTC)
            except ValueError as e:
                print(f"❌ Error parsing datetime: {dt_str} -> {e}")
                return None

        # ✅ Only update the fields that exist in the request payload
        updated_fields = {}

        for key in ["T1", "T2", "T3", "T4"]:
            if key in data and data[key]:  # Only update if key exists and is not None/empty
                setattr(bump_test, key, convert_local_to_utc(data[key]))
                updated_fields[key] = getattr(bump_test, key)  # Store updated values

        if updated_fields:
            bump_test.save()  # ✅ Save only if there are updates

            print(f"✅ Updated Bump Test {bump_test.id}: {updated_fields}")

            return JsonResponse({
                "success": True,
                **{key: updated_fields[key].isoformat() if updated_fields[key] else None for key in updated_fields}
            })
        else:
            print("⚠️ No valid updates received. No changes made.")
            return JsonResponse({"success": False, "error": "No valid updates received"}, status=400)

    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON received")
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    except Exception as e:
        print(f"❌ Error saving bump test: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def pid_calculation_list(request):
    """Display a list of PID loops with links to their calculation details."""
    pid_loops = PIDLoop.objects.all()
    return render(request, "tuner/pid_calculation_list.html", {"pid_loops": pid_loops})


def pid_calculation_detail(request, loop_id):
    """Display PID tuning parameters for a specific PID loop."""
    pid_loop = get_object_or_404(PIDLoop, id=loop_id)
    pid_calculation = getattr(pid_loop, "pid_calculation", None)  # Get related PIDCalculation

    return render(request, "tuner/pid_calculation_detail.html", {
        "pid_loop": pid_loop,
        "pid_calculation": pid_calculation
    })




































