import pandas as pd
from .models import PIDLoop, BumpTest, TrendChart
from .forms import TrendChartUploadForm
import json, os, pytz
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.utils.timezone import localtime, is_aware, get_fixed_timezone
from django.utils.dateparse import parse_datetime
from django.conf import settings  # ✅ Import settings for MEDIA path


def home(request):
    return render(request, "home.html")


def pid_loop_list(request):
    loops = PIDLoop.objects.all()
    return render(request, "pid_loop_list.html", {"loops": loops})


def pid_loop_detail(request, loop_id):
    pid_loop = get_object_or_404(PIDLoop, id=loop_id)
    trend_charts = TrendChart.objects.filter(pid_loop=pid_loop)

    return render(request, "pid_loop_detail.html", {
        "pid_loop": pid_loop,
        "trend_charts": trend_charts
    })


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
                df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
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

            return redirect("upload_trend_chart")

    else:
        form = TrendChartUploadForm()

    return render(request, "upload_trend_chart.html", {"form": form})


def trend_chart_list(request):
    charts = TrendChart.objects.all()
    print("Charts Found:", charts)  # Debugging line
    return render(request, "trend_chart_list.html", {"charts": charts})


def view_trend_chart(request, chart_id):
    """View a trend chart ensuring no unintended row filtering."""

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

    # ✅ Convert Time column to datetime format (debug before dropping anything)
    df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")

    # 🚨 Debug: Check how many NaT (invalid times) were generated
    invalid_times = df["Time"].isna().sum()
    print(f"⚠️ Invalid Time Entries After Parsing: {invalid_times}")

    # ✅ Drop NaT (invalid timestamps) only if they exist
    before_drop = len(df)
    df.dropna(subset=["Time"], inplace=True)
    after_drop = len(df)

    print(f"✅ Rows before dropna: {before_drop}, after dropna: {after_drop}")

    # ✅ Ensure "PV" and "CV" exist
    if "PV" not in df.columns or "CV" not in df.columns:
        return JsonResponse({"error": "Missing PV/CV columns!"})

    # ✅ Convert PV and CV to float
    df["PV"] = df["PV"].astype(float)
    df["CV"] = df["CV"].astype(float)

    # ✅ Debug Final Processed DataFrame
    print(f"✅ Final Processed DataFrame ({len(df)} rows):\n", df.head(10))

    # ✅ Convert timestamps for frontend compatibility
    df["Time"] = df["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ✅ Convert to JSON format for rendering
    chart_data = df.to_dict(orient="records")

    print(f"📌 Final Data Sent to Frontend ({len(chart_data)} points):", chart_data[:10])

    context = {
        "trend_chart": trend_chart,
        "trend_chart_id": chart_id,
        "pid_name": trend_chart.pid_loop.name,
        "chart_data": json.dumps(chart_data, ensure_ascii=False),
    }

    return render(request, "view_trend_chart.html", context)


@csrf_exempt
def save_bump(request, chart_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            trend_chart_id = data.get("trend_chart_id")
            bump_start = data.get("bump_start")
            bump_end = data.get("bump_end")

            if not trend_chart_id or not bump_start or not bump_end:
                return JsonResponse({"success": False, "error": "Missing required data."}, status=400)

            # ✅ Parse ISO 8601 timestamps correctly
            bump_start_dt = parse_datetime(bump_start)
            bump_end_dt = parse_datetime(bump_end)

            if not bump_start_dt or not bump_end_dt:
                return JsonResponse({"success": False, "error": "Invalid timestamp format."}, status=400)

            # ✅ Ensure timestamps are explicitly stored in UTC
            if bump_start_dt.tzinfo is None:
                bump_start_dt = bump_start_dt.replace(tzinfo=pytz.UTC)
            else:
                bump_start_dt = bump_start_dt.astimezone(pytz.UTC)

            if bump_end_dt.tzinfo is None:
                bump_end_dt = bump_end_dt.replace(tzinfo=pytz.UTC)
            else:
                bump_end_dt = bump_end_dt.astimezone(pytz.UTC)

            trend_chart = TrendChart.objects.get(id=trend_chart_id)
            BumpTest.objects.create(trend_chart=trend_chart, start_time=bump_start_dt, end_time=bump_end_dt)

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


@csrf_exempt
def delete_bump(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            bump_id = data.get("bump_id")  # Get the ID from the request

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
    # Retrieve all PID Loops
    pid_loops = PIDLoop.objects.all()

    pid_loop_data = []

    # Iterate through all PID loops to gather trend charts and bump tests
    for pid_loop in pid_loops:
        trend_charts = TrendChart.objects.filter(pid_loop=pid_loop)
        bump_tests_data = []

        # Collect bump tests for each trend chart
        for trend_chart in trend_charts:
            bump_tests = BumpTest.objects.filter(trend_chart=trend_chart).filter(
                Q(start_time__isnull=False) | Q(end_time__isnull=False))

            bump_tests_data.extend([
                {"bump_id": bump.id, "start_time": bump.start_time, "end_time": bump.end_time,
                 "trend_chart_id": trend_chart.id}
                for bump in bump_tests
            ])

        pid_loop_data.append({
            "pid_loop": pid_loop,
            "trend_charts": trend_charts,
            "bump_tests": bump_tests_data,
        })

    context = {
        "pid_loop_data": pid_loop_data
    }

    return render(request, "identity_trend_list.html", context)


def identity_trend_detail(request, chart_id, bump_test_id):
    trend_chart = get_object_or_404(TrendChart, id=chart_id)
    bump_test = get_object_or_404(BumpTest, id=bump_test_id)

    if not trend_chart.csv_file:
        return JsonResponse({"error": "File not found."})

    df = pd.read_csv(trend_chart.csv_file.path)

    if "Time" not in df.columns or "PV" not in df.columns:
        return JsonResponse({"error": "CSV file is missing required columns ('Time', 'PV')."})

    # ✅ Ensure CSV times are timezone-naive
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce').dt.tz_localize(None)
    df.dropna(subset=['Time'], inplace=True)

    # Convert T1-T4 times to timezone-naive format
    def make_naive(dt):
        if dt and is_aware(dt):
            return localtime(dt).replace(tzinfo=None)  # Convert to naive
        return dt

    t_times = {
        "T1": make_naive(bump_test.T1),
        "T2": make_naive(bump_test.T2),
        "T3": make_naive(bump_test.T3),
        "T4": make_naive(bump_test.T4),
    }

    # ✅ Find the closest PV values for each T1-T4
    t_markers = {}
    for key, t_time in t_times.items():
        if t_time:
            t_time_dt = pd.to_datetime(t_time)
            closest_idx = (df['Time'] - t_time_dt).abs().idxmin()
            closest_pv = df.iloc[closest_idx]["PV"]
            t_markers[key] = {
                "time": t_time.strftime('%Y-%m-%d %H:%M:%S'),  # ✅ Convert to string
                "pv": float(closest_pv)  # ✅ Ensure PV is a standard float
            }

    # ✅ Convert chart data timestamps to strings for JSON compatibility
    df['Time'] = df['Time'].dt.strftime('%Y-%m-%d %H:%M:%S')

    chart_data = df.to_dict(orient="records")  # Convert to JSON serializable format

    context = {
        "trend_chart": trend_chart,
        "bump_test": bump_test,
        "chart_data": json.dumps(chart_data, ensure_ascii=False),  # ✅ Fully serializable
        "start_time": t_times["T1"].strftime('%Y-%m-%d %H:%M:%S') if t_times["T1"] else None,
        "end_time": t_times["T4"].strftime('%Y-%m-%d %H:%M:%S') if t_times["T4"] else None,
        "t_markers": json.dumps(t_markers),  # ✅ Fully serializable
    }

    return render(request, "identity_trend_detail.html", context)


@csrf_exempt
def update_t1_t2(request, bump_test_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            T1 = data.get("T1")
            T2 = data.get("T2")
            T3 = data.get("T3")
            T4 = data.get("T4")

            bump_test = BumpTest.objects.get(id=bump_test_id)

            def parse_datetime_flexible(dt_str):
                if not dt_str:
                    return None
                try:
                    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=get_fixed_timezone(0))
                except ValueError:
                    return None

            bump_test.T1 = parse_datetime_flexible(T1)
            bump_test.T2 = parse_datetime_flexible(T2)
            bump_test.T3 = parse_datetime_flexible(T3)
            bump_test.T4 = parse_datetime_flexible(T4)

            bump_test.save()
            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


def pid_calculation_list(request):
    """Display a list of PID loops with links to their calculation details."""
    pid_loops = PIDLoop.objects.all()
    return render(request, "pid_calculation_list.html", {"pid_loops": pid_loops})


def pid_calculation_detail(request, loop_id):
    """Display PID tuning parameters for a specific PID loop."""
    pid_loop = get_object_or_404(PIDLoop, id=loop_id)
    pid_calculation = getattr(pid_loop, "pid_calculation", None)  # Get related PIDCalculation

    return render(request, "pid_calculation_detail.html", {
        "pid_loop": pid_loop,
        "pid_calculation": pid_calculation
    })




































