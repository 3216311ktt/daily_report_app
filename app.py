import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, DailyReport
from datetime import datetime
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

    for entry in reports:
        report = DailyReport(
            name=name,
            title=entry.get('title'),
            task= entry.get('task'),
            partner=entry.get('partner'),
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
    reports = DailyReport.query.order_by(DailyReport.date, DailyReport.name, DailyReport.id).all()

    grouped = defaultdict(list)
    for r in reports:
        key = (r.date, r.name)
        grouped[key].append(r)

    return render_template('report_chart.html', grouped=grouped)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)

