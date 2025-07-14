import os
import jpholiday
from flask import Flask, render_template, request, redirect, url_for, jsonify
from models import db, DailyReport
from datetime import datetime, timedelta
from collections import defaultdict
from operator import attrgetter
from sqlalchemy import func
from datetime import datetime
from holiday_manager import HolidayManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

holiday_checker = HolidayManager('static/company_calendar.csv')

# なければ作成
if not os.path.exists('db'):
    os.makedirs('db')

# 安定するpath
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db', 'daily_report.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] =False
db.init_app(app)

migrate = Migrate(app, db)

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
    reports = request.json.get('reports', [])
    name = request.json.get('name', '未入力')
    date = datetime.now().strftime('%Y-%m-%d')
    is_holiday_work = request.json.get('is_holiday_work', False)

    print('POSTされたデータ:', reports)
    print('名前:', name, '日付:', date, '休日出勤:', is_holiday_work
          )

    for entry in reports:
            # 共通部分
            base_data = dict(
                name=name,
                title=entry.get('title'),
                task= entry.get('task'),
                partner=entry.get('partner'),
                is_holiday_work=is_holiday_work,
                overtime_before=entry.get('overtime_before'),
                overtime_after=entry.get('overtime_after'),
                total_minutes=entry.get('total_minutes'),
                paid_leave_minutes=entry.get('paid_leave_minutes', 8),
                date=date
            )

            if is_holiday_work:
                base_data.update(
                    holiday_start_hour=entry.get('start_hour'),
                    holiday_start_minute=entry.get('start_minute'),
                    holiday_end_hour=entry.get('end_hour'),
                    holiday_end_minute=entry.get('end_minute'),
                    holiday_work_minutes=entry.get('work_minutes'),
                )
            else:
                base_data.update(
                    start_hour=entry.get('start_hour'),
                    start_minute=entry.get('start_minute'),
                    end_hour=entry.get('end_hour'),
                    end_minute=entry.get('end_minute'),
                    work_minutes=entry.get('work_minutes'),
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
                           date=date,
                           daily_totals=daily_totals,
                           monthly_total=monthly_total,
                           name_list=name_list,
                           holiday_info=holiday_info,
                           monthly_paid_leave=monthly_paid_leave,
                           )
    

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
    
