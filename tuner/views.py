import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from .models import PIDLoop, BumpTest, TrendChart, BumpTest
from .forms import TrendChartUploadForm
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta
from django.core.files.base import ContentFile
import os


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
            file = request.FILES["file"]

            # Determine delimiter based on file extension
            ext = os.path.splitext(file.name)[1].lower()
            delimiter = "\t" if ext in [".tsv", ".txt"] else ","

            # Load the file with the detected delimiter
            df = pd.read_csv(file, delimiter=delimiter).dropna(axis=1, how="all")

            # Standardize column names
            rename_map = {}
            for col in df.columns:
                col_lower = col.lower().replace(" ", "").replace("_", "")
                if col_lower in ["meas", "input", "pv", "pnt", "processvariable", "processvariable"]:
                    rename_map[col] = "PV"
                elif col_lower in ["out", "output", "cv"]:
                    rename_map[col] = "CV"

            # Apply renaming
            df.rename(columns=rename_map, inplace=True)
            df.rename(columns={df.columns[0]: "Time"}, inplace=True)

            # If PV or CV are missing, assume the 2nd column is PV and 3rd is CV
            if "PV" not in df.columns and len(df.columns) > 1:
                df.rename(columns={df.columns[1]: "PV"}, inplace=True)
            if "CV" not in df.columns and len(df.columns) > 2:
                df.rename(columns={df.columns[2]: "CV"}, inplace=True)

            # Handle time rollover (midnight issue)
            if "Time" in df.columns:
                today = datetime.today().strftime("%Y-%m-%d")

                # Append today's date and convert to datetime
                df["Time"] = today + " " + df["Time"]
                df["Time"] = pd.to_datetime(df["Time"], errors="coerce")

                # Fix midnight rollovers
                previous_time = df["Time"].iloc[0]
                for i in range(1, len(df)):
                    if df["Time"].iloc[i] < previous_time:  # Time went backwards (next day)
                        df.loc[i:, "Time"] += timedelta(days=1)  # Increment date
                    previous_time = df["Time"].iloc[i]

                # Ensure millisecond precision
                df["Time"] = df["Time"].dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]

            # Fill missing values in 'CV' with last known value
            if "CV" in df.columns:
                df["CV"].fillna(method="ffill", inplace=True)

            # Ensure final column order: Time, PV, CV
            expected_columns = ["Time", "PV", "CV"]
            df = df[[col for col in expected_columns if col in df.columns]]

            # Save the cleaned file as CSV (regardless of input format)
            modified_csv = df.to_csv(index=False)
            trend_chart.file.save(file.name.replace(ext, ".csv"), ContentFile(modified_csv.encode()))

            trend_chart.save()
            return redirect("trend_chart_list")

    else:
        form = TrendChartUploadForm()

    return render(request, "upload_trend_chart.html", {"form": form})


def trend_chart_list(request):
    charts = TrendChart.objects.all()
    print("Charts Found:", charts)  # Debugging line
    return render(request, "trend_chart_list.html", {"charts": charts})


def view_trend_chart(request, chart_id):
    trend_chart = get_object_or_404(TrendChart, id=chart_id)
    bump_tests = BumpTest.objects.filter(trend_chart=trend_chart)

    if not trend_chart.file:
        return JsonResponse({"error": "File not found."})

    # Read CSV and ensure Time is parsed correctly
    df = pd.read_csv(trend_chart.file.path)

    # Rename columns dynamically for Process Variable and Control Variable
    column_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in ["meas", "pv", "in", "input", "process variable"]):
            column_mapping[col] = "PV"
        elif any(keyword in col_lower for keyword in ["out", "cv", "output", "control variable"]):
            column_mapping[col] = "CV"

    df.rename(columns=column_mapping, inplace=True)

    # Ensure 'Time' column is correctly parsed
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')  # Auto-detects full timestamp

    # Drop NaT (Invalid dates)
    df = df.dropna(subset=['Time'])

    # Convert to string format for JSON serialization
    df['Time'] = df['Time'].dt.strftime('%Y-%m-%dT%H:%M:%S')  # Ensure correct formatting

    # Fill NaN values forward
    df.ffill(inplace=True)

    chart_data = df.to_dict(orient="records")

    # Ensure correct format for bump test times
    bump_test_list = []
    for bump in bump_tests:
        if bump.start_time and bump.end_time:
            parsed_start = parse_datetime(str(bump.start_time))
            parsed_end = parse_datetime(str(bump.end_time))
            if parsed_start and parsed_end:
                bump_test_list.append({
                    "id": bump.id,  # Include the ID
                    "start_time": bump.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "end_time": bump.end_time.strftime('%Y-%m-%d %H:%M:%S'),
                })

    context = {
        "trend_chart": trend_chart,
        "trend_chart_id": chart_id,
        "pid_name": trend_chart.pid_loop.name,
        "chart_data": json.dumps(chart_data, ensure_ascii=False),  # ✅ Fix JSON encoding
        "bump_tests": json.dumps(bump_test_list, ensure_ascii=False) if bump_test_list else "[]",
    }
    return render(request, "view_trend_chart.html", context)


@csrf_exempt  # Remove this after debugging
def save_bump(request, chart_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            trend_chart_id = data.get("trend_chart_id")
            bump_start = data.get("bump_start")
            bump_end = data.get("bump_end")

            if not trend_chart_id or not bump_start or not bump_end:
                return JsonResponse({"success": False, "error": "Missing data"})

            trend_chart = TrendChart.objects.get(id=trend_chart_id)
            BumpTest.objects.create(trend_chart=trend_chart, start_time=bump_start, end_time=bump_end)

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






