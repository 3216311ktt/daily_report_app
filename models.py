from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class DailyReport(db.Model):
    __tablename__ = 'daily_reports'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100),nullable=False)
    title = db.Column(db.String(200))
    task = db.Column(db.String(500))
    partner = db.Column(db.String(200))
    start_hour = db.Column(db.Integer)
    start_minute = db.Column(db.Integer)
    end_hour = db.Column(db.Integer)
    end_minute = db.Column(db.Integer)
    work_minutes = db.Column(db.Integer)       # 選択時間（分）
    overtime_before = db.Column(db.Integer)    # 前残業（分）
    overtime_after = db.Column(db.Integer)     # 後残業（分）
    total_minutes = db.Column(db.Integer)      # 合計時間（分）
    date = db.Column(db.String(10))            # 日付（例: "2025-06-16"）
    paid_leave_minutes = db.Column(db.Integer, default=0)   # 有休（分）

    # 休日出勤かどうか
    is_holiday_work = db.Column(db.Boolean, default=False)
    # 休日出勤時間帯
    holiday_start_hour = db.Column(db.Integer)
    holiday_start_minute = db.Column(db.Integer)
    holiday_end_hour = db.Column(db.Integer)
    holiday_end_minute = db.Column(db.Integer)
    # 休日出勤の選択時間や合計
    holiday_work_minutes = db.Column(db.Integer)
    holiday_total_minutes = db.Column(db.Integer)