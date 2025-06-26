import jpholiday
import csv
from datetime import datetime

class HolidayManager:
    def __init__(self, csv_path='company_holidays.csv'):
        self.company_holidays = set()
        self._load_company_holidays(csv_path)

    def _load_company_holidays(self, csv_path):
            try:
                 with open(csv_path, encoding='utf-8') as f:
                      reader = csv.DictReader(f)
                      for row in reader:
                           date_str = row['date'].strip()
                           self.company_holidays.add(date_str)
            except FileNotFoundError:
                 print(f"⚠ 会社休日CSVファイルが見つかりません: {csv_path}")
            except Exception as e:
                 print(f"⚠ CSV読み込みエラー: {e}")
           
        

    def is_holiday(self, date_str):
        """
        日付が土日・祝日・会社休日のいずれかなら True を返す
        """
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
             return False
        
        return (
            jpholiday.is_holiday(date_obj) or
            date_obj.weekday() >= 5 or
            date_str in self.company_holidays
            )

    def is_company_holiday(self, date_str):
        """
        会社独自の休日のみ判定したい場合
        """
        return date_str in self.company_holidays
    