# -*- coding: utf-8 -*-
"""数据库层：SQLite 封装 + DAO"""
import sqlite3
import os
import time
from datetime import datetime


def get_db_path():
    if os.name == 'nt':
        base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'FilingApp')
    else:
        base = os.path.join(os.path.expanduser('~'), '.filingapp')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, 'filing.db')


class Database:
    _conn = None

    @classmethod
    def get_conn(cls):
        if cls._conn is None:
            cls._conn = sqlite3.connect(get_db_path())
            cls._conn.row_factory = sqlite3.Row
            cls._conn.execute("PRAGMA foreign_keys = ON")
            cls._create_tables()
        return cls._conn

    @classmethod
    def _create_tables(cls):
        c = cls._conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE, name TEXT, credit_code TEXT, type INTEGER,
            address TEXT, contact TEXT, phone TEXT, remark TEXT,
            created_at INTEGER, updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS filing_process (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER, status INTEGER,
            apply_time INTEGER, send_to_gacc_time INTEGER,
            created_at INTEGER, updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS modification_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process_id INTEGER, type INTEGER, occur_time INTEGER,
            content TEXT, remark TEXT, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id INTEGER, action TEXT,
            old_data TEXT, new_data TEXT, operator TEXT, created_at INTEGER
        );
        """)
        c.commit()


def now_ms():
    return int(time.time() * 1000)


def fmt_dt(ms):
    if not ms:
        return "待填写"
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def fmt_date(ms):
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def file_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


STATUS_NAMES = ["待申请", "已申请待发函", "已发函待总署回复", "总署打回修改中",
                "行邮处处理中", "福中海关修改中", "已反馈总署", "备案完成", "备案终止"]

RECORD_TYPES = {
    1: "总署打回修改",
    2: "行邮处联系福中海关修改",
    3: "福中海关修改反馈行邮处",
    4: "行邮处反馈总署",
}

CONTENT_LABELS = {1: "修改要求", 2: "修改内容", 3: "反馈情况", 4: "反馈情况"}


class CompanyDao:
    @staticmethod
    def generate_code():
        year = str(datetime.now().year)
        c = Database.get_conn()
        row = c.execute("SELECT code FROM company WHERE code LIKE ? ORDER BY code DESC LIMIT 1",
                        (year + "%",)).fetchone()
        seq = 0
        if row:
            try:
                seq = int(row['code'][len(year):])
            except (ValueError, IndexError):
                pass
        return year + "%04d" % (seq + 1)

    @staticmethod
    def insert(data):
        c = Database.get_conn()
        now = now_ms()
        code = CompanyDao.generate_code()
        cur = c.execute("""INSERT INTO company
            (code,name,credit_code,type,address,contact,phone,remark,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (code, data['name'], data['credit_code'], data.get('type', 0),
             data.get('address', ''), data.get('contact', ''), data.get('phone', ''),
             data.get('remark', ''), now, now))
        cid = cur.lastrowid
        c.execute("INSERT INTO filing_process (company_id,status,created_at,updated_at) VALUES (?,?,?,?)",
                  (cid, 0, now, now))
        c.commit()
        return cid

    @staticmethod
    def update(cid, data):
        c = Database.get_conn()
        c.execute("""UPDATE company SET name=?,credit_code=?,type=?,address=?,contact=?,phone=?,remark=?,updated_at=? WHERE id=?""",
                  (data['name'], data['credit_code'], data.get('type', 0),
                   data.get('address', ''), data.get('contact', ''), data.get('phone', ''),
                   data.get('remark', ''), now_ms(), cid))
        c.commit()

    @staticmethod
    def delete(cid):
        c = Database.get_conn()
        row = c.execute("SELECT id FROM filing_process WHERE company_id=?", (cid,)).fetchone()
        if row:
            c.execute("DELETE FROM modification_record WHERE process_id=?", (row['id'],))
            c.execute("DELETE FROM filing_process WHERE id=?", (row['id'],))
        c.execute("DELETE FROM company WHERE id=?", (cid,))
        c.execute("DELETE FROM audit_log WHERE entity_id=?", (cid,))
        c.commit()

    @staticmethod
    def get_by_id(cid):
        c = Database.get_conn()
        return c.execute("SELECT * FROM company WHERE id=?", (cid,)).fetchone()

    @staticmethod
    def list(query="", limit=20, offset=0):
        c = Database.get_conn()
        if query:
            like = "%" + query.strip() + "%"
            sql = """SELECT c.*, IFNULL(fp.status,0) AS st FROM company c
                LEFT JOIN filing_process fp ON fp.company_id=c.id
                WHERE c.name LIKE ? OR c.credit_code LIKE ? OR c.contact LIKE ? OR c.phone LIKE ?
                ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"""
            return c.execute(sql, (like, like, like, like, limit, offset)).fetchall()
        else:
            sql = """SELECT c.*, IFNULL(fp.status,0) AS st FROM company c
                LEFT JOIN filing_process fp ON fp.company_id=c.id
                ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"""
            return c.execute(sql, (limit, offset)).fetchall()

    @staticmethod
    def count(query=""):
        c = Database.get_conn()
        if query:
            like = "%" + query.strip() + "%"
            row = c.execute("""SELECT COUNT(*) AS n FROM company
                WHERE name LIKE ? OR credit_code LIKE ? OR contact LIKE ? OR phone LIKE ?""",
                (like, like, like, like)).fetchone()
        else:
            row = c.execute("SELECT COUNT(*) AS n FROM company").fetchone()
        return row['n'] if row else 0


class RecordDao:
    @staticmethod
    def get_process(company_id):
        c = Database.get_conn()
        return c.execute("SELECT * FROM filing_process WHERE company_id=?", (company_id,)).fetchone()

    @staticmethod
    def update_process(pid, status=None, apply_time=None, send_time=None):
        c = Database.get_conn()
        sets, args = [], []
        if status is not None:
            sets.append("status=?"); args.append(status)
        if apply_time is not None:
            sets.append("apply_time=?"); args.append(apply_time)
        if send_time is not None:
            sets.append("send_to_gacc_time=?"); args.append(send_time)
        sets.append("updated_at=?"); args.append(now_ms())
        args.append(pid)
        c.execute("UPDATE filing_process SET " + ",".join(sets) + " WHERE id=?", args)
        c.commit()

    @staticmethod
    def list(process_id):
        c = Database.get_conn()
        return c.execute("SELECT * FROM modification_record WHERE process_id=? ORDER BY occur_time ASC, id ASC",
                         (process_id,)).fetchall()

    @staticmethod
    def insert(data):
        c = Database.get_conn()
        cur = c.execute("""INSERT INTO modification_record
            (process_id,type,occur_time,content,remark,created_at) VALUES (?,?,?,?,?,?)""",
            (data['process_id'], data['type'], data['occur_time'],
             data['content'], data.get('remark', ''), now_ms()))
        c.commit()
        return cur.lastrowid

    @staticmethod
    def update(rid, data):
        c = Database.get_conn()
        c.execute("UPDATE modification_record SET occur_time=?,content=?,remark=? WHERE id=?",
                  (data['occur_time'], data['content'], data.get('remark', ''), rid))
        c.commit()

    @staticmethod
    def delete(rid):
        c = Database.get_conn()
        c.execute("DELETE FROM modification_record WHERE id=?", (rid,))
        c.commit()


class AuditDao:
    @staticmethod
    def log(company_id, entity_type, entity_id, action, old="", new=""):
        c = Database.get_conn()
        c.execute("""INSERT INTO audit_log
            (entity_type,entity_id,action,old_data,new_data,operator,created_at) VALUES (?,?,?,?,?,?,?)""",
            (entity_type, entity_id, action, old, new, "本机用户", now_ms()))
        c.commit()

    @staticmethod
    def list(company_id):
        c = Database.get_conn()
        return c.execute("SELECT * FROM audit_log WHERE entity_id=? ORDER BY created_at DESC",
                         (company_id,)).fetchall()
