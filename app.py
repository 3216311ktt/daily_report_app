import os
import jpholiday
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from models import db, DailyReport
from datetime import datetime, timedelta
from collections import defaultdict
from operator import attrgetter
from sqlalchemy import func
from datetime import datetime, date as dt_date
from holiday_manager import HolidayManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

holiday_checker = HolidayManager('static/company_calendar.csv')

# 安定するpath
# このファイルがあるディレクトリ（app.py）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 親ディレクトリの絶対パス
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))

# 上の階層の db ディレクトリを使う
DB_DIR = os.path.join(PARENT_DIR, 'db')

# ディレクトリがなければ作る
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

# 共通DBファイルのパス
DB_PATH = os.path.join(DB_DIR, 'unified.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] =False
app.secret_key ='super_secret_key'
app.permanent_session_lifetime = timedelta(minutes=5) # セッションの有効期限を10分に設定
db.init_app(app)

migrate = Migrate(app, db)

@app.template_filter('comma')
def comma_filter(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

# 土曜出勤、祝日、会社休日の情報を取得
@app.route('/calendar')
def calendar():
    return render_template('calendar.html')

@app.route('/api/calendar')
def api_calendar():
    events = []

    # クエリで年を受け取る
    selected_year = request.args.get('year', type=int)


    if selected_year:
         # 📋 一覧表示 → 単年
        years = [selected_year]
    else:
         # 📅 カレンダー表示 → 今年を中心に前後1年
         current_year = datetime.now().year
         years = range(current_year - 1, current_year + 2)
    
        
    # 会社独自カレンダー
    for row in holiday_checker.company_calendar:
        # 年なしは仮に今年を付けておく
        date_str = row['date']
        is_yearless = len(date_str) == 5

        for year in years:
            if is_yearless:
                full_date = f"{year}-{date_str}"
            else:
                if int(date_str[:4]) != year:
                    continue
                full_date = date_str

            # 無効な日付はスキップ
            try:
                datetime.strptime(full_date, '%Y-%m-%d')
            except ValueError:
                continue
            
            color = '#f00' if row['type'] == 'holiday' else '#0a0'

            events.append({
                "title": row['description'],
                "start": full_date,
                "color": color
            })

    # jpholidayの祝日
    for year in years:

        for date_obj, name in jpholiday.year_holidays(year):
            date_str = date_obj.strftime('%Y-%m-%d')

            # すでに会社休日として登録されていればスキップ
            if any(e['start'] == date_str for e in events):
                continue

            events.append({
                "title": name,
                "start": date_str,
                "color": "#ff9999"
            })

    return jsonify(events)

@app.route('/api/update', methods=['POST'])
def api_update():
    data = request.json
    date = data.get('date').strip()
    description = data.get('description').strip()
    day_type = data.get('type').strip()

    # 既存データ更新 or 新規追加
    found = False
    for row in holiday_checker.company_calendar:
        if row['date'] == date:
            row['description'] = description
            row['type'] = day_type
            found = True
            break
    if not found:
        holiday_checker.company_calendar.append({
            'date': date,
            'description': description,
            'type': day_type
        })

    holiday_checker.save_calendar()
    return jsonify({'status': 'success'})

# 休日自動判定
@app.route('/api/check_holiday')
def api_check_holiday():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'date is required'}), 400

    is_holiday = holiday_checker.is_holiday(date_str)
    return jsonify({'date': date_str, 'is_holiday': is_holiday})


@app.route('/')
def index():
    # データベースから名前の一覧を取得
    name_list = db.session.query(DailyReport.name).distinct().order_by(DailyReport.name).all()
    name_list = [n[0] for n in name_list]

    # 今日の日付（初期値）
    today = datetime.now().strftime('%Y-%m-%d')

    # 会社カレンダー＋祝日＋土曜で判定
    is_holiday = holiday_checker.is_holiday(today)

    return render_template('index.html',
                           name_list=name_list,
                           today=today,
                           is_holiday=is_holiday)

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    reports = data.get('reports', [])
    name = data.get('name', '未入力')
    date = date.get('date', datetime.now().strftime('%Y-%m-%d'))
    is_holiday_work = data.get('is_holiday_work', False)

    for entry in reports:
            # total_minutesを再計算して安全性確保
            calc_total = (
                entry.get('work_minutes', 0) +
                entry.get('overtime_before', 0) +
                entry.get('overtime_after', 0)
            )
            entry_total = entry.get('total_minutes', 0)
            if entry_total != calc_total:
                entry_total = calc_total

            # 共通部分
            base_data = dict(
                name=name,
                title=entry.get('title'),
                task= entry.get('task'),
                partner=entry.get('partner'),
                date=date,
                is_holiday_work=is_holiday_work,
                overtime_before=entry.get('overtime_before', 0),
                overtime_after=entry.get('overtime_after', 0),
            )

            if is_holiday_work:
                base_data.update(
                    holiday_start_hour=entry.get('start_hour'),
                    holiday_start_minute=entry.get('start_minute'),
                    holiday_end_hour=entry.get('end_hour'),
                    holiday_end_minute=entry.get('end_minute'),
                    holiday_work_minutes=entry.get('work_minutes'),
                    # holliday_total_minutes を計算して入れる
                    holiday_totoal_minutes=entry_total,
                    paid_leave_minutes=0
                )
            else:
                base_data.update(
                    start_hour=entry.get('start_hour'),
                    start_minute=entry.get('start_minute'),
                    end_hour=entry.get('end_hour'),
                    end_minute=entry.get('end_minute'),
                    work_minutes=entry.get('work_minutes', 0),
                    total_minutes=entry_total,
                    paid_leave_minutes=entry.get('paid_leave_minutes', 0)
            )
            
            report = DailyReport(**base_data)   
            db.session.add(report)

    db.session.commit()
    return {'status': 'success'}

# 確認用一覧画面
@app.route('/view_reports')
def view_reports():
    name = request.args.get('name')
    date = request.args.get('date')

    query = DailyReport.query

    if name:
        query = query.filter(DailyReport.name.contains(name))
    if date:
        query = query.filter(DailyReport.date == date)

    reports = query.order_by(DailyReport.date.desc(), DailyReport.name).all()

    # Noneの値を0に変換
    for r in reports:
        if r.work_minutes is None:
            r.work_minutes = 0
        if r.total_minutes is None:
            r.total_minutes = 0
        if r.paid_leave_minutes is None:
            r.paid_leave_minutes = 0
    return render_template('view_reports.html', reports=reports)
    
# 編集ルート
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_report(id):
    report = DailyReport.query.get_or_404(id)

    if request.method == 'POST':
        report.date = request.form['date']
        report.name = request.form['name']
        report.title = request.form['title']
        report.task = request.form['task']
        report.partner = request.form['partner']
        report.overtime_before = int(float(request.form['overtime_before']) * 60)
        report.overtime_after = int(float(request.form['overtime_after']) *60)

        if report.is_holiday_work:
            # 休日出勤の場合
            report.holiday_work_minutes = int(float(request.form['work_minutes']) * 60)
            report.holiday_total_minutes = report.overtime_before + report.holiday_work_minutes + report.overtime_after
        else:
            # 通常勤務の場合
            report.work_minutes = int(float(request.form['work_minutes']) * 60)
            report.total_minutes = report.overtime_before + report.work_minutes + report.overtime_after

        db.session.commit()
        return redirect(request.referrer or url_for('view_reports'))
    
    return render_template('edit_report.html', report=report)

# 削除ルート
@app.route('/delete/<int:id>')
def delete_report(id):
    report = DailyReport.query.get_or_404(id)
    db.session.delete(report)
    db.session.commit()
    return redirect(url_for('view_reports'))

# 一人１日をカード表示
@app.route('/chart')
def report_chart():
    name = request.args.get('name', '')
    date = request.args.get('date', '')
    today = dt_date.today().isoformat()
    
    
    query =DailyReport.query

    if name:
        query = query.filter(DailyReport.name.contains(name))
    if date:
        query = query.filter(DailyReport.date == date)

    reports = query.order_by(DailyReport.date.desc(), DailyReport.name).all()

    # 日別合計
    daily_totals = defaultdict(int)
    monthly_total = 0
    holiday_info = {}

    for report in reports:
        if report.is_holiday_work:
            work_time = report.holiday_total_minutes or 0
        else:
            work_time = report.total_minutes or 0

        key = f"{report.date}_{report.name}"
        daily_totals[key] += work_time
        monthly_total += work_time

        holiday_info[key] = report.is_holiday_work or holiday_checker.is_holiday(report.date)
    
    # 月の合計を求める
    total_minutes = None
    if name and date:
        month_str = date[:7]
        total_minutes = db.session.query(func.sum(DailyReport.total_minutes))\
            .filter(DailyReport.name == name)\
            .filter(DailyReport.date.like(f'{month_str}-%'))\
            .scalar() or 0
        
    # 社員名一覧
    all_names = db.session.query(DailyReport.name).distinct().order_by(DailyReport.name).all()
    name_list = [n[0] for n in all_names]

    # 有給休暇の合計
    monthly_paid_leave = sum(r.paid_leave_minutes or 0 for r in reports)
    
    return render_template('report_chart.html',
                           reports=reports,
                           name=name,
                           date=today,
                           daily_totals=daily_totals,
                           monthly_total=monthly_total,
                           name_list=name_list,
                           holiday_info=holiday_info,
                           monthly_paid_leave=monthly_paid_leave,
                           )

# 役職ログインAPI
@app.route('/login_role', methods=['POST'])
def login_role():
    data = request.get_json()
    role = data['role']
    password = data['password']

    ROLE_PASSWORDS = {
        'manager': 'managerpass',
        'director': 'directorpass',
        'president': 'presidentpass'
    }

    if ROLE_PASSWORDS.get(role) == password:
        session.permanent = True
        session[f'{role}_logged_in'] = True
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})
    
# ログイン状態確認ＡＰＩ
@app.route('/check_login', methods=['POST'])
def check_login():
    data = request.get_json()
    print('受け取ったデータ:', data)

    if not data:
        return jsonify({'error': 'No JSON received'}), 400
    
    role = data['role']
    is_logged_in = session.get(f'{role}_logged_in', False)
    return jsonify({'logged_in': is_logged_in})

# チェック状態保存ＡＰＩ
@app.route('/check_approval', methods=['POST'])
def check_approval():
    data = request.get_json()
    report_id = data['report_id']
    role = data['role']
    checked = data['checked']

    if not session.get(f'{role}_logged_in'):
        return jsonify({'seccess': False, 'message': 'ログインしてください'})
    
    report = DailyReport.query.get(report_id)
    if report:
        setattr(report, f'{role}_checked', checked)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'レポートが見つかりません'})
    
# 月報用ルート
@app.route('/monthly_report')
def monthly_report():
    # name = request.args.get('name')
    # # month = request.args.get('month')
    # reports = DailyReport.query.filter(
    #     DailyReport.name == name,
    #     # DailyReport.date.startswith(month)
    # ).all()

    # # 集計ロジック
    # grouped = ...

    # return render_template('monthly_report.html',
    #                        name=name,
    #                     #    month=month,
    #                        reports=reports,
    #                        grouped=grouped)
    performance_rate = round((258850 / 1091200) * 100, 2)
    context = {
        "name": "田中 郁二",
        "month": "2025-07",
        "basic_time": "22 日",
        "overtime_a": "2.5 H",
        "overtime_b": "0 H",
        "holiday_work": "8.5 H",
        "total_hours": 179,  # 総合計時間
        "paid_leave": "0 日",
        "time_diff": "-8 H",
        "late_early": "0 H",
        "target_amount": 1091200,
        "actual_amount": 258850,  # 総合計金額
        "performance_rate": performance_rate,
        "main_tasks": [
            {"project_name": "東山中高", "description": "弱電迂回工事 / 水野", "hours": 23, "amount": 0},
        ],
        "main_total_hours": 72,
        "main_total_amount": 0,
        "other_tasks": [
            {"category": "社内", "description": "プログラミング学習 他", "hours": 56, "amount": 0},
            {"category": "電設", "description": "枚方長尾谷NKビル 他", "hours": 17, "amount": 18600},
        ],
        "other_total_hours": 73,
        "other_total_amount": 104850,
        "previous_amount": 155000,
    }
    return render_template("monthly_report.html", **context)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
    
