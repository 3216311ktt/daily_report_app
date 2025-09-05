import os
import jpholiday
from monthly_report_util import get_monthly_report
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from models import db, DailyReport, CompanyCalendar, User
from collections import defaultdict
from operator import attrgetter
from sqlalchemy import func
from datetime import datetime, timedelta, date as dt_date
from holiday_manager import HolidayManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

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
    for row in CompanyCalendar.query.all():
        # 年なしは仮に今年を付けておく
        date_str = row.date
        is_yearless = len(date_str) == 5

        # 色の設定
        if row.type == 'holiday':
            color = '#f00'
        elif row.type == 'workday':
            color = '#0a0'
        elif row.type == 'paidleave':
            color = '#00bfff'
        else:
            color = '#ccc'

        if is_yearless:
            # 年なしの場合だけ、対象の複数年に展開
            for year in years:
                full_date = f"{year}-{date_str}"
                try:
                    datetime.strptime(full_date, '%Y-%m-%d')
                except ValueError:
                    continue
                events.append({
                    "title": row.description,
                    "start": full_date,
                    "color": color,
                })
        else:
            # 年ありはそのまま
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                continue

            # 年指定があるときは、その年以外はスキップ
            if selected_year and dt.year != selected_year:
                continue


            events.append({
                    "title": row.description,
                    "start": date_str,
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

# 会社カレンダーの内容削除
@app.route('/api/delete',methods=['POST'])
def api_delete():
    data = request.json
    date = data.get('date').strip() # type: ignore

   # DBから検索
    record = CompanyCalendar.query.filter_by(date=date).first()

    if not record:
        return jsonify({'status': 'not_found'})

    # 削除
    db.session.delete(record)
    db.session.commit()

    return jsonify({'status': 'deleted'})


@app.route('/api/update', methods=['POST'])
def api_update():
    data = request.json
    date = data.get('date').strip() # type: ignore
    description = data.get('description').strip() # type: ignore
    day_type = data.get('type').strip() # type: ignore

     # DBから検索
    record = CompanyCalendar.query.filter_by(date=date).first()
    if record:
        record.description = description
        record.type = day_type
    else:
        record = CompanyCalendar(date=date, description=description, type=day_type) # type: ignore
        db.session.add(record)

    db.session.commit()
    return jsonify({'status': 'success'})
    

# 休日自動判定
@app.route('/api/check_holiday')
def api_check_holiday():
    """
    指定した日付が休日かどうかを判定するAPI。

    Args:
        date (str): 'YYYY-MM-DD'形式の日付をクエリパラメータで指定。

    Returns:
        JSONオブジェクト:
            {
                "date": 指定日付,
                "is_holiday": 休日ならTrue, そうでなければFalse,
                "is_forced_paidleave": 会社カレンダーで指定有給日ならTrue, そうでなければFalse
            }
    """
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'date is required'}), 400

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'invalid date format'}), 400
    
    # フロントから来た日付の MM-DD を抽出
    mmdd = date_obj.strftime('%m-%d')

    # DBで会社カレンダーを確認
    record = CompanyCalendar.query.filter(
        (CompanyCalendar.date==date_str) | (CompanyCalendar.date==mmdd)
    ).first()

    is_forced_paidleave = record and record.type.strip().lower() == 'paidleave'

    if record:
        rtype = record.type.strip().lower()
        if rtype == 'holiday':
            is_holiday = True
        elif rtype == 'workday':
            is_holiday = False
        elif rtype == 'paidleave':
            # 業務ロジック: 有給は休日扱いしない（必要ならTrueに変更）
            is_holiday = False
            is_forced_paidleave = True
        else:
            is_holiday = False
    else:
        # DB になければ土日・祝日で判定
        if date_obj.weekday() >= 5:  # 土日
            is_holiday = True
        elif jpholiday.is_holiday(date_obj):
            is_holiday = True
        else:
            is_holiday = False

    return jsonify({'date': date_str, 'is_holiday': is_holiday, 'is_forced_paidleave': is_forced_paidleave})


@app.route('/')
def index():
   # データベースから名前の一覧を取得
    name_list = db.session.query(User.name).filter_by(department='技術').all()
    name_list = [n[0] for n in name_list]

    # 今日の日付（初期値）
    today = datetime.now().strftime('%Y-%m-%d')
    today_obj = datetime.strptime(today, '%Y-%m-%d')

    # DB で会社カレンダーを検索
    record = CompanyCalendar.query.filter_by(date=today).first()
    is_forced_paidleave = record and record.type == 'paidleave'
    if record:
        if record.type == 'holiday':
            is_holiday = True
        elif record.type == 'workday':
            is_holiday = False
        elif record.type == 'paidleave':
            is_holiday = False  # 有給を休日扱いにする場合
            is_forced_paidleave = True
        else:
            is_holiday = False
    else:
        # DB にない場合は土日か祝日判定
        if today_obj.weekday() >= 5:  # 土日
            is_holiday = True
        elif jpholiday.is_holiday(today_obj):
            is_holiday = True
        else:
            is_holiday = False
       

    return render_template('index.html',
                           name_list=name_list,
                           today=today,
                           is_holiday=is_holiday,
                           is_forced_paidleave=is_forced_paidleave)

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    reports = data.get('reports', []) # type: ignore
    name = data.get('name', '未入力') # type: ignore
    date = data.get('date', datetime.now().strftime('%Y-%m-%d')) # type: ignore
    is_holiday_work = data.get('is_holiday_work', False) # type: ignore

    # この日が「指定有給日」かどうかを判定   
    calendar_entry = CompanyCalendar.query.filter_by(date=date).first()
    forced_paidleave = calendar_entry and calendar_entry.type == 'paidleave'

    for entry in reports:
        work_minutes = entry.get('work_minutes') or 0
        overtime_before = entry.get('overtime_before') or 0
        overtime_after = entry.get('overtime_after') or 0

        calc_total = work_minutes + overtime_before + overtime_after
        entry_total = entry.get('total_minutes') or 0
        if entry_total != calc_total:
            entry_total = calc_total

        # 既存レポートがある場合は削除して上書き
        existing = DailyReport.query.filter_by(name=name, date=date, title=entry.get('title')).first()
        if existing:
            db.session.delete(existing)

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
            holiday_work_minutes = entry.get('work_minutes') or 0
            overtime_before = entry.get('overtime_before') or 0
            overtime_after = entry.get('overtime_after') or 0
            holiday_total_minutes = (overtime_before + holiday_work_minutes + overtime_after)

            base_data.update(
                holiday_start_hour=entry.get('start_hour'),
                holiday_start_minute=entry.get('start_minute'),
                holiday_end_hour=entry.get('end_hour'),
                holiday_end_minute=entry.get('end_minute'),
                holiday_work_minutes=holiday_work_minutes,
                # holiday_total_minutes を計算して入れる
                holiday_total_minutes=holiday_total_minutes,
                paid_leave_minutes=0
            )
        else:
            # 指定有給日の場合は差分を自動計算
            if forced_paidleave:
                worked = work_minutes + overtime_before + overtime_after
                paid_leave = max(0, 480 - worked)
            else:
                paid_leave = entry.get('paid_leave_minutes', 0)

            base_data.update(
                start_hour=entry.get('start_hour'),
                start_minute=entry.get('start_minute'),
                end_hour=entry.get('end_hour'),
                end_minute=entry.get('end_minute'),
                work_minutes=entry.get('work_minutes', 0),
                total_minutes=entry_total,
                paid_leave_minutes=paid_leave
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
        report.paid_leave_minutes = int(float(request.form['paid_leave_minutes'] or 0) * 60) 

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
    total_minutes = 0  # 初期値を定義

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
        # 勤務時間の取得
        if report.is_holiday_work:
            work_time = report.holiday_total_minutes or 0
        else:
            work_time = report.total_minutes or 0

        key = f"{report.date}_{report.name}"
        daily_totals[key] += work_time
        monthly_total += work_time

        # 休日判定
        date_obj = datetime.strptime(report.date, '%Y-%m-%d')
        # DBの会社カレンダーを確認
        record = CompanyCalendar.query.filter_by(date=report.date).first()

        if report.is_holiday_work:
            # 休日出勤
            holiday_info[key] = 'holiday' # 休日出勤
        elif record and record.type == 'paidleave':
            # 指定有給日
            holiday_info[key] = 'paidleave' # 指定有給日
        elif record and record.type == 'holiday':
            # 会社休日
            holiday_info[key] = 'holiday' # 会社休日
        else:
            # DBにない場合は土日・祝日で判定
            if date_obj.weekday() >= 5 or jpholiday.is_holiday(date_obj):
                holiday_info[key] = 'holiday' # 土日祝
            else:
                holiday_info[key] = None # 平日
    
    # 月の合計を求める
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
                           total_minutes=total_minutes
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
    checked = True if data['checked'] in [True, 'true', 1, '1'] else False

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
    # クエリパラメータから名前と月を取得
    name = request.args.get('name')
    month_start = request.args.get('month')  # 'YYYY-MM' 形式

    if not name or not month_start:
        return "名前と月を指定してください", 400
    
    # 集計関数を呼び出す
    report_data = get_monthly_report(name, month_start)
    if not report_data:
        return "指定された条件のレポートが見つかりません", 404
      
    
    # 月報テンプレートに渡す
    context = {
        "name": name,
        "month": month_start,
        "basic_time": f"{report_data['basic_time_days']} 日",
        "overtime_a": report_data["overtime_a"],
        "overtime_b": report_data["overtime_b"],
        "holiday_work": report_data["holiday_work"],
        "total_hours": report_data["total_hours"],
        "paid_leave": report_data["paid_leave"],
        "time_diff": report_data["time_diff"],
        "late_early": report_data["late_early"],
        "target_amount": 0,
        "actual_amount": report_data["total_amount"],
        "performance_rate": 0,
        "main_tasks": report_data["main_tasks"],
        "main_total_hours": report_data["main_total_hours"],
        "main_total_amount": report_data["main_total_amount"],
        "other_tasks": report_data["other_tasks"],
        "other_total_hours": report_data["other_total_hours"],
        "other_total_amount": report_data["other_total_amount"],
        "previous_amount": 0,
    }

    return render_template('monthly_report.html', **context)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
    
