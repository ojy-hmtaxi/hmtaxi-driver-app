"""연간 통계 중 Sheets 부담이 큰 필드(결근 합·가해사고 합)만 SQLite에 스냅샷.

연차(잔여/총액)는 매 요청 시 시트에서 갱신해 반영한다."""
import os
import sqlite3
import threading
import time

_lock = threading.Lock()


def _ensure_parent_dir(path):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def _init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS yearly_heavy (
            employee_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            annual_absent_days INTEGER NOT NULL,
            annual_accident_count INTEGER NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (employee_id, year)
        )
        """
    )
    conn.commit()


def get_heavy(employee_id, year, ttl_sec, db_path):
    """TTL 이내면 {'annual_absent_days', 'annual_accident_count'} 반환, 아니면 None."""
    if not db_path or ttl_sec <= 0:
        return None
    path = os.path.abspath(db_path)
    if not os.path.exists(path):
        return None
    with _lock:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            _init_db(conn)
            row = conn.execute(
                'SELECT annual_absent_days, annual_accident_count, updated_at FROM yearly_heavy WHERE employee_id=? AND year=?',
                (str(employee_id), int(year)),
            ).fetchone()
            if not row:
                return None
            absent, acc, ts = row
            if time.time() - float(ts) > ttl_sec:
                return None
            return {
                'annual_absent_days': int(absent),
                'annual_accident_count': int(acc),
            }
        finally:
            conn.close()


def peek_heavy(employee_id, year, ttl_sec, db_path):
    """스냅샷 행이 있으면 (데이터 dict, TTL 만료 여부). 없으면 None.

    SWR에서 만료 행이라도 먼저 보여 줄 때 사용. ttl_sec<=0 이면 stale=True 로만 본다."""
    if not db_path:
        return None
    path = os.path.abspath(db_path)
    if not os.path.exists(path):
        return None
    with _lock:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            _init_db(conn)
            row = conn.execute(
                'SELECT annual_absent_days, annual_accident_count, updated_at FROM yearly_heavy WHERE employee_id=? AND year=?',
                (str(employee_id), int(year)),
            ).fetchone()
            if not row:
                return None
            absent, acc, ts = row
            d = {'annual_absent_days': int(absent), 'annual_accident_count': int(acc)}
            if ttl_sec <= 0:
                return (d, True)
            stale = time.time() - float(ts) > ttl_sec
            return (d, stale)
        finally:
            conn.close()


def put_heavy(employee_id, year, annual_absent_days, annual_accident_count, db_path):
    if not db_path:
        return
    path = os.path.abspath(db_path)
    _ensure_parent_dir(path)
    with _lock:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            _init_db(conn)
            conn.execute(
                """INSERT OR REPLACE INTO yearly_heavy
                (employee_id, year, annual_absent_days, annual_accident_count, updated_at)
                VALUES (?,?,?,?,?)""",
                (
                    str(employee_id),
                    int(year),
                    int(annual_absent_days),
                    int(annual_accident_count),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def invalidate_employee(employee_id, db_path):
    """해당 사번 연도 스냅샷 전부 삭제."""
    if not db_path:
        return
    path = os.path.abspath(db_path)
    if not os.path.exists(path):
        return
    with _lock:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            _init_db(conn)
            conn.execute('DELETE FROM yearly_heavy WHERE employee_id=?', (str(employee_id),))
            conn.commit()
        finally:
            conn.close()
