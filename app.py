import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, DailyReport
from datetime import datetime

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

