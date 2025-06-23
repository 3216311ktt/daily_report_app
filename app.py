import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, DailyReport
from datetime import datetime, timedelta
from collections import defaultdict
from operator import attrgetter

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    reports = request.json.get('reports', [])
    name = request.json.get('name', '未入力')
    date = datetime.now().strftime('%Y-%m-%d')

    print('POSTされたデータ:', reports)
    print('名前:', name, '日付:', date)

    for entry in reports:
        print('レポート1件:', entry)
        report = DailyReport(
            name=name,
            title=entry.get('title'),
            task= entry.get('task'),
            partner=entry.get('partner'),
            start_hour=entry.get('start_hour'),
            start_minute=entry.get('start_minute'),
            end_hour=entry.get('end_hour'),
            end_minute=entry.get('end_minute'),
            work_minutes=entry.get('work_minutes'),
            overtime_before=entry.get('overtime_before'),
            overtime_after=entry.get('overtime_after'),
            total_minutes=entry.get('total_minutes'),
            date=date
        )
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
        report.work_minutes = int(float(request.form['work_minutes']) * 60)
        report.overtime_after = int(float(request.form['overtime_after']) *60)
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
    date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')

    reports = DailyReport.query.filter_by(date=date).order_by(DailyReport.name, DailyReport.id).all()

    # データ整形（1人1日単位でまとめる）
    grouped = defaultdict(list)
    for r in reports:
        grouped[r.date, r.name].append(r)

    result = []
    for name, items in grouped.items():
        entry_list = []
        current = datetime.strptime("08:30", "%H:%M")

        for item in items:
            work_start = current
            work_end = work_start + timedelta(minutes=item.work_minutes)

            # 昼休憩(12:00~13:00)をスッキプ
            if work_start < datetime.strptime("12:00", "%H:%M") < work_end:
                work_end += timedelta(hours=1)

            # 前残業
            before = None
            if item.overtime_before:
                before = {
                    'start': (work_start - timedelta(minutes=item.overtime_before)).strftime('%H:%M'),
                    'end': work_start.strftime('%H:%M'),
                    'color': '#f88'
                }

            # 通常作業
            main = {
                'start': work_start.strftime('%H:%M'),
                'end': work_end.strftime('%H:%M'),
                'title': item.title,
                'color': '#9f9'
            }

            # 後残業
            after = None
            if item.overtime_after:
                after_start = work_end
                after_end = after_start + timedelta(minutes=item.overtime_after)
                after = {
                    'start': after_start.strftime('%H:%M'),
                    'end': after_end.strftime('%H:%M'),
                    'color': '#f88'
                }

            entry_list.append({
                'before': before,
                'main': main,
                'after': after
            })

            current = work_end
            if item.overtime_after:
                current += timedelta(minutes=item.overtime_after)

        result.append({
            'name': name,
            'date': date,
            'entries': entry_list
        })

    return render_template('report_chart.html', grouped=grouped)

def time_to_percent(t):
    t = datetime.strptime(t, "%H:%M")
    minutes = t.hour * 60 + t.minute

    # 作業時間枠　8:30(510)~17:30(1050) - 昼休憩(12:00~13:00, 60分除外)
    if minutes >= 780: # 13:00以降
        minutes -= 60
    percent = (minutes - 510) / 480 * 100
    return max(0, min(percent, 100))

def time_range_percent(start, end):
    s = datetime.strptime(start, "%H:%M")
    e = datetime.strptime(end, "%H:%M")
    s_min = s.hour * 60 + s.minute
    e_min = e.hour * 60 + e.minute

    # 昼休憩またぐ場合は60分除外
    overlap_start = max(s_min, 720)
    overlap_end = min(e_min, 780)
    lunch_overlap = max(0, overlap_end - overlap_start)

    duration = e_min - s_min - lunch_overlap
    return duration / 480 * 100

app.jinja_env.globals.update(time_to_percent=time_to_percent)
app.jinja_env.globals.update(time_range_percent=time_range_percent)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
    
