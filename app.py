import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, DailyReport
from datetime import datetime, timedelta
from collections import defaultdict
from operator import attrgetter
from sqlalchemy import func

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
    # データベースから名前の一覧を取得
    name_list = db.session.query(DailyReport.name).distinct().order_by(DailyReport.name).all()
    name_list = [n[0] for n in name_list]
    return render_template('index.html', name_list=name_list)

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
    for report in reports:
        key = f"{report.date}_{report.name}"
        daily_totals[key] += report.total_minutes or 0
        monthly_total += report.total_minutes or 0
    
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
    
    return render_template('report_chart.html',
                           reports=reports,
                           name=name,
                           date=date,
                           daily_totals=daily_totals,
                           monthly_total=monthly_total,
                           name_list=name_list
                           )
    

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
    
