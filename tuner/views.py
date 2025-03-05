import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from .models import PIDLoop, BumpTest, TrendChart
from .forms import TrendChartUploadForm
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from django.core.files.base import ContentFile
import os
from django.utils.timezone import get_current_timezone, get_fixed_timezone
from django.db.models import Q
from django.utils.timezone import localtime, is_aware
from django.core.files.storage import default_storage
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
    """Handles trend chart uploads with dynamic header detection and null filling."""

    charts = TrendChart.objects.all()

    if request.method == "POST":
        form = TrendChartUploadForm(request.POST, request.FILES)

        if form.is_valid():
            trend_chart = form.save(commit=False)  # Don't save yet

            file = request.FILES.get("csv_file")
            if not file:
                return JsonResponse({"error": "No file uploaded."}, status=400)

            # ✅ Ensure media directory exists
            media_dir = os.path.join(settings.MEDIA_ROOT, "trend_charts")
            os.makedirs(media_dir, exist_ok=True)

            # ✅ Determine file extension and delimiter
            file_ext = os.path.splitext(file.name)[-1].lower()
            delimiter = "," if file_ext == ".csv" else "\t"

            # ✅ Read CSV file as string (to avoid dtype inference issues)
            df = pd.read_csv(file, delimiter=delimiter, dtype=str)

            # ✅ Ensure 'Time' column exists
            if "Time" not in df.columns:
                return JsonResponse({"error": "Time column missing in file."}, status=400)

            # ✅ Convert and fix Time column
            df["Time"] = pd.to_datetime(df["Time"], errors="coerce", format="%m/%d/%Y %I:%M:%S.%f %p")
            df["Time"] = df["Time"].ffill()  # Forward fill missing timestamps

            # ✅ Detect PV and CV dynamically
            pv_candidates = ["PV", "MEAS", "Process Variable", "IN"]
            cv_candidates = ["CV", "OUT", "Control Variable"]

            pv_col = next((col for col in df.columns if any(keyword in col.upper() for keyword in pv_candidates)), None)
            cv_col = next((col for col in df.columns if any(keyword in col.upper() for keyword in cv_candidates)), None)

            if not pv_col or not cv_col:
                return JsonResponse({"error": "Could not detect PV or CV columns."}, status=400)

            # ✅ Rename detected columns
            df.rename(columns={pv_col: "PV", cv_col: "CV"}, inplace=True)

            # ✅ Fill missing values with last known value
            df["PV"] = df["PV"].astype(float).ffill()
            df["CV"] = df["CV"].astype(float).ffill()

            # ✅ Save processed file
            output_filename = f"processed_{file.name}"
            output_path = os.path.join(media_dir, output_filename)
            df.to_csv(output_path, index=False)

            # ✅ Associate file with TrendChart model
            with open(output_path, "rb") as f:
                trend_chart.csv_file.save(output_filename, f)

            trend_chart.save()  # Now save to DB

            return redirect("upload_trend_chart")

    else:
        form = TrendChartUploadForm()

    return render(request, "upload_trend_chart.html", {"form": form, "charts": charts})


def trend_chart_list(request):
    charts = TrendChart.objects.all()
    print("Charts Found:", charts)  # Debugging line
    return render(request, "trend_chart_list.html", {"charts": charts})


def view_trend_chart(request, chart_id):
    utc = get_fixed_timezone(0)  # 0 offset means UTC
    trend_chart = get_object_or_404(TrendChart, id=chart_id)

    bump_tests = BumpTest.objects.filter(trend_chart=trend_chart)

    if not trend_chart.csv_file:
        return JsonResponse({"error": "File not found."})

    # Read CSV and ensure Time is parsed correctly
    df = pd.read_csv(trend_chart.csv_file.path)

    # Ensure 'Time' column is correctly parsed and converted to UTC
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce').dt.tz_localize(utc)

    # Drop NaT (Invalid dates)
    df = df.dropna(subset=['Time'])

    # Convert timestamps to UTC ISO format for frontend compatibility
    df['Time'] = df['Time'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')  # Convert to ISO format

    chart_data = df.to_dict(orient="records")

    # Ensure correct format for bump test times (convert to UTC before sending)
    bump_test_list = []
    for bump in bump_tests:
        if bump.start_time and bump.end_time:
            bump_test_list.append({
                "id": bump.id,
                "start_time": localtime(bump.start_time).strftime('%Y-%m-%d %H:%M:%S'),  # ✅ Convert to local
                "end_time": localtime(bump.end_time).strftime('%Y-%m-%d %H:%M:%S'),
            })

    context = {
        "trend_chart": trend_chart,
        "trend_chart_id": chart_id,
        "pid_name": trend_chart.pid_loop.name,
        "chart_data": json.dumps(chart_data, ensure_ascii=False),
        "bump_tests": bump_test_list,  # ✅ Now sending bump tests as UTC
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
                return JsonResponse({"success": False, "error": "Missing data"})

            # Get Django's current timezone
            local_tz = get_current_timezone()

            # Parse timestamps as timezone-aware in local time
            bump_start_dt = datetime.strptime(bump_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=local_tz)
            bump_end_dt = datetime.strptime(bump_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=local_tz)

            trend_chart = TrendChart.objects.get(id=trend_chart_id)
            BumpTest.objects.create(trend_chart=trend_chart, start_time=bump_start_dt, end_time=bump_end_dt)

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request"})


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

            if not bump_test_id:
                return JsonResponse({"success": False, "error": "Missing bump_test_id"}, status=400)

            bump_test = BumpTest.objects.get(id=bump_test_id)

            def parse_datetime_flexible(dt_str):
                if not dt_str:
                    return None
                try:
                    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return None

            bump_test.T1 = parse_datetime_flexible(T1)
            bump_test.T2 = parse_datetime_flexible(T2)
            bump_test.T3 = parse_datetime_flexible(T3)
            bump_test.T4 = parse_datetime_flexible(T4)

            bump_test.save()
            return JsonResponse({"success": True})

        except Exception as e:
            print(f"❌ Error in update_t1_t2: {e}")
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




































