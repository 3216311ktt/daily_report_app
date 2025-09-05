from models import db, DailyReport, CompanyCalendar
from collections import defaultdict
from datetime import date, timedelta
import jpholiday

def get_monthly_report(name: str, year_month: str, selected_main_titles=None):
    """
    指定社員・年月の月報集計を返す
    - 1か月は16日～翌月15日
    - selected_main_titles を渡すと、指定された案件を主要案件に分類
    """

    if selected_main_titles is None:
        selected_main_titles = []

    # --- 期間計算 ---
    year, month = map(int, year_month.split("-"))
    if month == 1:
        start_date = date(year-1, 12, 16)
        end_date = date(year, 1, 15)
    else:
        start_date = date(year, month-1, 16)
        end_date = date(year, month, 15)

    # --- 勤怠データ取得 ---
    reports = DailyReport.query.filter(
        DailyReport.name == name,
        DailyReport.date >= start_date.strftime("%Y-%m-%d"),
        DailyReport.date <= end_date.strftime("%Y-%m-%d")
    ).all()
    if not reports:
        return None

    # --- 件名ごとにまとめる ---
    task_groups = defaultdict(list)
    for r in reports:
        task_groups[r.title].append(r)

    main_tasks = []
    other_tasks = []

    # --- 主要案件 / その他案件に分類 ---
    for title, items in task_groups.items():
        tasks_list = [r.task for r in items if r.task]
        tasks_text = "/".join(tasks_list[:3])

        partners = [r.partner for r in items if r.partner]
        unique_partners = list(dict.fromkeys(partners))
        partners_text = ""
        if len(unique_partners) > 1:
            partners_text = f"{unique_partners[0]} 他"
        elif unique_partners:
            partners_text = unique_partners[0]

        task_data = {
            "project_name": title,
            "description": tasks_text + (" / " + partners_text if partners_text else ""),
            "hours": round(sum(r.total_minutes or 0 for r in items)/60, 2),
            "amount": 0  # 金額計算ロジックは別途
        }

        if title in selected_main_titles:
            main_tasks.append(task_data)
        else:
            other_tasks.append(task_data)

    MAX_OTHER_LENGTH = 50 # 文字数目安

    other_texts = []
    total_other_hours = 0
    total_other_amount = 0

    for t in other_tasks:
        text = f"{t['project_name']}: {t['hours']}H"
        other_texts.append(text)
        total_other_hours += t["hours"]
        total_other_amount += t["amount"]

    combined_other = " / ".join(other_texts)
    if len (combined_other) > MAX_OTHER_LENGTH:
        combined_other = combined_other[:MAX_OTHER_LENGTH] + "…他"

    # 他案件を1行にまとめる
    other_tasks_summary = [{
        "project_name": combined_other,
        "hours": round(total_other_hours, 2),
        "amount": total_other_amount
    }]


    # --- 合計時間・金額計算 ---
    main_total_hours = round(sum(t["hours"] for t in main_tasks), 2)
    main_total_amount = sum(t["amount"] for t in main_tasks)
    other_total_hours = round(sum(t["hours"] for t in other_tasks), 2)
    other_total_amount = sum(t["amount"] for t in other_tasks)

    total_hours = main_total_hours + other_total_hours
    total_amount = main_total_amount + other_total_amount

    # --- 出勤日数の計算 ---
    all_days = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    company_calendar = CompanyCalendar.query.filter(
        CompanyCalendar.date >= start_date.strftime("%Y-%m-%d"),
        CompanyCalendar.date <= end_date.strftime("%Y-%m-%d")
    ).all()
    special_days = {date.fromisoformat(r.date): r.type for r in company_calendar}

    workdays = []
    for d in all_days:
        if d.weekday() >= 5 and special_days.get(d) != "workday":
            continue
        if special_days.get(d) in ("holiday", "paidleave"):
            continue
        if jpholiday.is_holiday(d) and special_days.get(d) != "workday":
            continue
        workdays.append(d)
    basic_time_days = len(workdays)

    # 残業・休日・有給・欠勤の計算
    overtime_a = 0
    overtime_b = 0
    holiday_work = 0
    late_early = 0

    daily_hours_required = 8 
    scheduled_start = 8 * 60 + 30
    scheduled_end   = 17 * 60 + 30

    for r in reports:
        # 前・後残業
        overtime_a += (r.overtime_before + r.overtime_after or 0) / 60

        # B残業
        overtime_b += (r.b_overtime_minutes or 0) /60
        

        # 休日出勤
        if r.is_holiday_work:
            holiday_work += (r.holiday_total_minutes or 0) / 60


        # 遅刻・早退
        if r.start_hour is not None and r.start_minute is not None:
            start_minutes = r.start_hour * 60 + r.start_minute
            if start_minutes > scheduled_start:
                late_early += (start_minutes - scheduled_start) /60

        if r.end_hour is not None and r.end_minute is not None:
            end_minutes = r.end_hour * 60 + r.end_minute
            if end_minutes < scheduled_end:
                late_early += (scheduled_end - end_minutes) / 60

    # 有給
    paid_leave_minutes = sum(r.paid_leave_minutes or 0 for r in reports)
    # 時間に直す
    paid_leave_hours = round(paid_leave_minutes / 60, 1)

    # 所定労働時間との差
    expected_hours = basic_time_days * daily_hours_required
    time_diff = total_hours - expected_hours

    return {
        "period_start": f"{start_date} ~ {end_date}",
        "basic_time_days": basic_time_days,
        "main_tasks": main_tasks,
        "other_tasks": other_tasks_summary,
        "main_total_hours": main_total_hours,
        "main_total_amount": main_total_amount,
        "other_total_hours": other_total_hours,
        "other_total_amount": other_total_amount,
        "total_hours": total_hours,
        "total_amount": total_amount,
        "overtime_a": round(overtime_a, 2),
        "overtime_b": round(overtime_b, 2),
        "holiday_work": round(holiday_work, 2),
        "paid_leave": paid_leave_hours,
        "time_diff": round(time_diff, 2),
        "late_early": round(late_early, 2)
    }
