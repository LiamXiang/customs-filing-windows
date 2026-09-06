# -*- coding: utf-8 -*-
"""快件运营人备案管理 - Windows 桌面版 (Tkinter)"""
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
import calendar

from database import (Database, CompanyDao, RecordDao, AuditDao,
                      STATUS_NAMES, RECORD_TYPES, CONTENT_LABELS,
                      fmt_dt, now_ms, get_db_path)
import export as export_svc

APP_TITLE = "快件运营人备案管理"
APP_VERSION = "1.0.0"
PAGE_SIZE = 20

# 颜色
COLOR_PRIMARY = "#1976D2"
COLOR_PRIMARY_DARK = "#1565C0"
COLOR_BG = "#F5F5F5"
COLOR_WHITE = "#FFFFFF"
COLOR_TEXT = "#333333"
COLOR_GRAY = "#999999"


def status_color(s):
    if s == 7:
        return "#2E7D32"  # 绿
    if s == 8:
        return "#757575"  # 灰
    if s == 3:
        return "#E65100"  # 橙
    return COLOR_PRIMARY


class PinLockDialog(tk.Toplevel):
    """应用锁验证"""
    def __init__(self, master, correct_pin):
        super().__init__(master)
        self.title("应用锁")
        self.resizable(False, False)
        self.correct_pin = correct_pin
        self.unlocked = False
        self._build_ui()
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        frm = ttk.Frame(self, padding=30)
        frm.pack()
        ttk.Label(frm, text="请输入应用锁PIN码", font=("Microsoft YaHei", 12)).pack(pady=(0, 15))
        self.entry = ttk.Entry(frm, show="*", width=20, font=("Microsoft YaHei", 12), justify="center")
        self.entry.pack(pady=5)
        self.entry.focus()
        self.entry.bind("<Return>", lambda e: self._check())
        btn_frm = ttk.Frame(frm)
        btn_frm.pack(pady=15)
        ttk.Button(btn_frm, text="解锁", command=self._check).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="退出", command=self._on_close).pack(side="left", padx=5)

    def _check(self):
        if self.entry.get() == self.correct_pin:
            self.unlocked = True
            self.destroy()
        else:
            messagebox.showerror("错误", "PIN码错误", parent=self)
            self.entry.delete(0, tk.END)

    def _on_close(self):
        self.destroy()
        self.master.destroy()


class RecordEditDialog(tk.Toplevel):
    """添加/编辑备案记录"""
    def __init__(self, master, record_type, existing=None, on_save=None):
        super().__init__(master)
        self.title("编辑记录" if existing else "添加记录")
        self.resizable(False, False)
        self.record_type = record_type
        self.existing = existing
        self.on_save = on_save
        self._build_ui()
        self.transient(master)
        self.grab_set()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="发生时间", font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky="w", pady=5)
        self.time_var = tk.StringVar()
        time_frm = ttk.Frame(frm)
        time_frm.grid(row=0, column=1, sticky="w", pady=5, padx=5)
        self.time_entry = ttk.Entry(time_frm, textvariable=self.time_var, width=20)
        self.time_entry.pack(side="left")
        ttk.Button(time_frm, text="选择", command=self._pick_time, width=6).pack(side="left", padx=5)

        label = CONTENT_LABELS.get(self.record_type, "内容")
        ttk.Label(frm, text=label, font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky="nw", pady=5)
        self.content_text = tk.Text(frm, width=40, height=5, font=("Microsoft YaHei", 10))
        self.content_text.grid(row=1, column=1, sticky="w", pady=5, padx=5)

        ttk.Label(frm, text="备注", font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky="nw", pady=5)
        self.remark_text = tk.Text(frm, width=40, height=2, font=("Microsoft YaHei", 10))
        self.remark_text.grid(row=2, column=1, sticky="w", pady=5, padx=5)

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frm, text="保存", command=self._save).pack(side="left", padx=5)
        if self.existing:
            ttk.Button(btn_frm, text="删除", command=self._delete).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="取消", command=self.destroy).pack(side="left", padx=5)

        if self.existing:
            self.time_var.set(fmt_dt(self.existing['occur_time']))
            self.content_text.insert("1.0", self.existing['content'])
            self.remark_text.insert("1.0", self.existing['remark'] or "")
        else:
            self.time_var.set(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def _pick_time(self):
        dlg = TimePickDialog(self, self.time_var.get())
        self.wait_window(dlg)
        if dlg.result:
            self.time_var.set(dlg.result)

    def _save(self):
        time_str = self.time_var.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        remark = self.remark_text.get("1.0", "end").strip()
        if not time_str:
            messagebox.showerror("提示", "请选择发生时间", parent=self)
            return
        if not content:
            messagebox.showerror("提示", "请填写%s" % CONTENT_LABELS.get(self.record_type, "内容"), parent=self)
            return
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            occur_ms = int(dt.timestamp() * 1000)
        except ValueError:
            messagebox.showerror("提示", "时间格式错误，请用 年-月-日 时:分", parent=self)
            return
        if self.existing:
            RecordDao.update(self.existing['id'], {'occur_time': occur_ms, 'content': content, 'remark': remark})
            AuditDao.log(0, "record", self.existing['id'], "编辑记录", "",
                          fmt_dt(occur_ms) + " " + content)
        else:
            if self.on_save:
                self.on_save({'type': self.record_type, 'occur_time': occur_ms, 'content': content, 'remark': remark})
        self.destroy()

    def _delete(self):
        if messagebox.askyesno("确认", "确定删除此记录？", parent=self):
            RecordDao.delete(self.existing['id'])
            AuditDao.log(0, "record", self.existing['id'], "删除记录",
                          fmt_dt(self.existing['occur_time']), "")
            self.destroy()


class TimePickDialog(tk.Toplevel):
    """时间选择器"""
    def __init__(self, master, current=""):
        super().__init__(master)
        self.title("选择时间")
        self.resizable(False, False)
        self.result = None
        now = datetime.now()
        if current:
            try:
                now = datetime.strptime(current, "%Y-%m-%d %H:%M")
            except ValueError:
                pass
        self.year_var = tk.StringVar(value=str(now.year))
        self.month_var = tk.StringVar(value=str(now.month))
        self.day_var = tk.StringVar(value=str(now.day))
        self.hour_var = tk.StringVar(value=str(now.hour))
        self.minute_var = tk.StringVar(value=str(now.minute))
        self._build_ui()
        self.transient(master)
        self.grab_set()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=15)
        frm.pack()
        years = [str(y) for y in range(2020, 2036)]
        months = [str(m) for m in range(1, 13)]
        days = [str(d) for d in range(1, 32)]
        hours = [str(h) for h in range(0, 24)]
        minutes = [str(m) for m in range(0, 60)]
        ttk.Label(frm, text="年").grid(row=0, column=0)
        ttk.Combobox(frm, textvariable=self.year_var, values=years, width=6).grid(row=0, column=1, padx=2)
        ttk.Label(frm, text="月").grid(row=0, column=2)
        ttk.Combobox(frm, textvariable=self.month_var, values=months, width=4).grid(row=0, column=3, padx=2)
        ttk.Label(frm, text="日").grid(row=0, column=4)
        ttk.Combobox(frm, textvariable=self.day_var, values=days, width=4).grid(row=0, column=5, padx=2)
        ttk.Label(frm, text="时").grid(row=1, column=0, pady=5)
        ttk.Combobox(frm, textvariable=self.hour_var, values=hours, width=6).grid(row=1, column=1, padx=2)
        ttk.Label(frm, text="分").grid(row=1, column=2)
        ttk.Combobox(frm, textvariable=self.minute_var, values=minutes, width=4).grid(row=1, column=3, padx=2)
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=2, column=0, columnspan=6, pady=10)
        ttk.Button(btn_frm, text="确定", command=self._ok).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="取消", command=self.destroy).pack(side="left", padx=5)

    def _ok(self):
        try:
            y, m, d = int(self.year_var.get()), int(self.month_var.get()), int(self.day_var.get())
            h, mi = int(self.hour_var.get()), int(self.minute_var.get())
            # 校验日期
            calendar.monthrange(y, m)
            if d < 1 or d > calendar.monthrange(y, m)[1]:
                raise ValueError
            self.result = "%04d-%02d-%02d %02d:%02d" % (y, m, d, h, mi)
            self.destroy()
        except ValueError:
            messagebox.showerror("提示", "日期无效", parent=self)


class StatusPickDialog(tk.Toplevel):
    """状态选择"""
    def __init__(self, master, current, on_select):
        super().__init__(master)
        self.title("选择备案状态")
        self.resizable(False, False)
        self.on_select = on_select
        self._build_ui(current)
        self.transient(master)
        self.grab_set()

    def _build_ui(self, current):
        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(frm, width=30, height=10, font=("Microsoft YaHei", 10),
                                   activestyle="none", selectmode="single")
        for i, name in enumerate(STATUS_NAMES):
            self.listbox.insert("end", name)
            if i == current:
                self.listbox.selection_set(i)
        self.listbox.pack(pady=5)
        self.listbox.bind("<Double-Button-1>", lambda e: self._ok())
        btn_frm = ttk.Frame(frm)
        btn_frm.pack(pady=5)
        ttk.Button(btn_frm, text="确定", command=self._ok).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="取消", command=self.destroy).pack(side="left", padx=5)

    def _ok(self):
        sel = self.listbox.curselection()
        if sel:
            self.on_select(sel[0])
        self.destroy()


class CompanyEditDialog(tk.Toplevel):
    """新增/编辑企业"""
    def __init__(self, master, company_id=None, on_saved=None):
        super().__init__(master)
        self.title("编辑企业" if company_id else "新增企业")
        self.resizable(False, False)
        self.company_id = company_id
        self.on_saved = on_saved
        self._build_ui()
        self.transient(master)
        self.grab_set()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)
        self.name_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.type_var = tk.StringVar(value="境内")
        self.addr_var = tk.StringVar()
        self.contact_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.remark_text = tk.Text(frm, width=40, height=3, font=("Microsoft YaHei", 10))

        row = 0
        ttk.Label(frm, text="企业名称 *", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.name_var, width=40).grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="统一社会信用代码 *", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.code_var, width=40).grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="企业类型", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(frm, textvariable=self.type_var, values=["境内", "境外"], width=38, state="readonly").grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="企业地址", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.addr_var, width=40).grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="联系人", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.contact_var, width=40).grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="联系电话", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.phone_var, width=40).grid(row=row, column=1, pady=4, padx=5)
        row += 1
        ttk.Label(frm, text="备注", font=("Microsoft YaHei", 10)).grid(row=row, column=0, sticky="nw", pady=4)
        self.remark_text.grid(row=row, column=1, pady=4, padx=5)

        row += 1
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frm, text="保存", command=self._save).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="取消", command=self.destroy).pack(side="left", padx=5)

        if self.company_id:
            c = CompanyDao.get_by_id(self.company_id)
            if c:
                self.name_var.set(c['name'])
                self.code_var.set(c['credit_code'])
                self.type_var.set("境内" if c['type'] == 0 else "境外")
                self.addr_var.set(c['address'] or "")
                self.contact_var.set(c['contact'] or "")
                self.phone_var.set(c['phone'] or "")
                self.remark_text.insert("1.0", c['remark'] or "")

    def _save(self):
        name = self.name_var.get().strip()
        code = self.code_var.get().strip()
        if not name:
            messagebox.showerror("提示", "请输入企业名称", parent=self)
            return
        if len(code) != 18:
            messagebox.showerror("提示", "统一社会信用代码应为18位", parent=self)
            return
        data = {
            'name': name, 'credit_code': code,
            'type': 0 if self.type_var.get() == "境内" else 1,
            'address': self.addr_var.get().strip(),
            'contact': self.contact_var.get().strip(),
            'phone': self.phone_var.get().strip(),
            'remark': self.remark_text.get("1.0", "end").strip(),
        }
        if self.company_id:
            CompanyDao.update(self.company_id, data)
            AuditDao.log(self.company_id, "company", self.company_id, "编辑企业", "", name)
        else:
            cid = CompanyDao.insert(data)
            AuditDao.log(cid, "company", cid, "新增企业", "", name)
        if self.on_saved:
            self.on_saved()
        self.destroy()


class CompanyDetailWindow(tk.Toplevel):
    """企业详情窗口"""
    def __init__(self, master, company_id, on_changed=None):
        super().__init__(master)
        self.company_id = company_id
        self.on_changed = on_changed
        self.company = CompanyDao.get_by_id(company_id)
        if not self.company:
            self.destroy()
            return
        self.title("%s - 企业详情" % self.company['name'])
        self.geometry("900x650")
        self.minsize(800, 550)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self, bg=COLOR_PRIMARY, height=50)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(toolbar, text=self.company['name'], fg="white", bg=COLOR_PRIMARY,
                 font=("Microsoft YaHei", 13, "bold")).pack(side="left", padx=15)
        tk.Label(toolbar, text=self.company['code'], fg="#BBDEFB", bg=COLOR_PRIMARY,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=5)
        for text, cmd in [("导出Excel", self._export_excel), ("导出Word", self._export_word),
                          ("编辑企业", self._edit_company), ("删除企业", self._delete_company)]:
            btn = tk.Button(toolbar, text=text, fg="white", bg=COLOR_PRIMARY_DARK,
                            activebackground="#0D47A1", activeforeground="white",
                            relief="flat", font=("Microsoft YaHei", 9), padx=10, pady=2, command=cmd)
            btn.pack(side="right", padx=3, pady=10)

        # Tab
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        self._build_process_tab()
        self._build_info_tab()
        self._build_audit_tab()

    def _build_process_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="备案流程")
        canvas = tk.Canvas(frame, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.process_inner = ttk.Frame(canvas)
        self.process_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.process_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._refresh_process()

    def _refresh_process(self):
        for w in self.process_inner.winfo_children():
            w.destroy()
        p = RecordDao.get_process(self.company_id)
        if not p:
            return
        # 状态行
        status_frm = tk.Frame(self.process_inner, bg=COLOR_WHITE, pady=10, padx=15)
        status_frm.pack(fill="x", padx=10, pady=8)
        tk.Label(status_frm, text="当前状态：", bg=COLOR_WHITE, font=("Microsoft YaHei", 10)).pack(side="left")
        sc = status_color(p['status'])
        tk.Label(status_frm, text=STATUS_NAMES[p['status']], bg=sc, fg="white",
                 font=("Microsoft YaHei", 9), padx=10, pady=2).pack(side="left", padx=8)
        tk.Button(status_frm, text="更新状态", command=lambda: self._change_status(p),
                  fg=COLOR_PRIMARY, bg=COLOR_WHITE, relief="flat", font=("Microsoft YaHei", 10),
                  activebackground=COLOR_WHITE, cursor="hand2").pack(side="right")

        # 固定节点
        self._add_node("企业申请备案时间", p['apply_time'],
                        lambda: self._pick_fixed_time(p, 'apply_time'))
        self._add_node("深圳海关发函给总署时间", p['send_to_gacc_time'],
                        lambda: self._pick_fixed_time(p, 'send_to_gacc_time'))

        # 四类记录
        records = RecordDao.list(p['id'])
        for rtype, title in [(1, "总署打回修改"), (2, "行邮处联系福中海关修改"),
                              (3, "福中海关修改反馈行邮处"), (4, "行邮处反馈总署")]:
            self._add_record_group(p['id'], rtype, title, [r for r in records if r['type'] == rtype])

    def _add_node(self, title, time_ms, on_click):
        frm = tk.Frame(self.process_inner, bg=COLOR_WHITE, pady=12, padx=15)
        frm.pack(fill="x", padx=10, pady=4)
        # 时间轴圆点
        dot = tk.Canvas(frm, width=16, height=16, bg=COLOR_WHITE, highlightthickness=0)
        dot.pack(side="left", padx=(0, 10))
        dot.create_oval(2, 2, 14, 14, fill=COLOR_PRIMARY, outline=COLOR_PRIMARY)
        info = tk.Frame(frm, bg=COLOR_WHITE)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=title, bg=COLOR_WHITE, font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        time_text = fmt_dt(time_ms) if time_ms else "待填写"
        tc = COLOR_TEXT if time_ms else COLOR_GRAY
        tk.Label(info, text=time_text, bg=COLOR_WHITE, fg=tc, font=("Microsoft YaHei", 10)).pack(anchor="w", pady=(2, 0))
        tk.Button(frm, text="编辑", command=on_click, fg=COLOR_PRIMARY, bg=COLOR_WHITE,
                  relief="flat", font=("Microsoft YaHei", 9), cursor="hand2").pack(side="right")

    def _add_record_group(self, process_id, rtype, title, records):
        header = tk.Frame(self.process_inner, bg=COLOR_BG, pady=8, padx=15)
        header.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(header, text="%s（%d次）" % (title, len(records)), bg=COLOR_BG,
                 font=("Microsoft YaHei", 11, "bold")).pack(side="left")
        tk.Button(header, text="+ 添加", command=lambda: self._add_record(process_id, rtype),
                  fg=COLOR_PRIMARY, bg=COLOR_BG, relief="flat", font=("Microsoft YaHei", 10),
                  cursor="hand2").pack(side="right")
        for r in records:
            frm = tk.Frame(self.process_inner, bg=COLOR_WHITE, pady=10, padx=15)
            frm.pack(fill="x", padx=20, pady=2)
            info = tk.Frame(frm, bg=COLOR_WHITE)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=fmt_dt(r['occur_time']), bg=COLOR_WHITE, fg=COLOR_GRAY,
                     font=("Microsoft YaHei", 9)).pack(anchor="w")
            tk.Label(info, text=r['content'], bg=COLOR_WHITE, font=("Microsoft YaHei", 10),
                     wraplength=600, justify="left").pack(anchor="w", pady=(2, 0))
            if r['remark']:
                tk.Label(info, text="备注：%s" % r['remark'], bg=COLOR_WHITE, fg=COLOR_GRAY,
                         font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(2, 0))
            tk.Button(frm, text="编辑", command=lambda rec=r: self._edit_record(rec),
                      fg=COLOR_PRIMARY, bg=COLOR_WHITE, relief="flat", font=("Microsoft YaHei", 9),
                      cursor="hand2").pack(side="right")

    def _pick_fixed_time(self, process, field):
        current = fmt_dt(process[field]) if process[field] else ""
        dlg = TimePickDialog(self, current)
        self.wait_window(dlg)
        if dlg.result:
            try:
                dt = datetime.strptime(dlg.result, "%Y-%m-%d %H:%M")
                ms = int(dt.timestamp() * 1000)
                if field == 'apply_time':
                    RecordDao.update_process(process['id'], apply_time=ms)
                else:
                    RecordDao.update_process(process['id'], send_time=ms)
                self._refresh_process()
                if self.on_changed:
                    self.on_changed()
            except ValueError:
                pass

    def _add_record(self, process_id, rtype):
        def on_save(data):
            data['process_id'] = process_id
            rid = RecordDao.insert(data)
            AuditDao.log(self.company_id, "record", rid, "新增记录", "",
                          fmt_dt(data['occur_time']) + " " + data['content'])
            self._refresh_process()
            if self.on_changed:
                self.on_changed()
        RecordEditDialog(self, rtype, on_save=on_save)

    def _edit_record(self, record):
        dlg = RecordEditDialog(self, record['type'], existing=record)
        self.wait_window(dlg)
        self._refresh_process()
        if self.on_changed:
            self.on_changed()

    def _change_status(self, process):
        def on_select(new_status):
            old = STATUS_NAMES[process['status']]
            RecordDao.update_process(process['id'], status=new_status)
            AuditDao.log(self.company_id, "process", process['id'], "更新备案状态", old, STATUS_NAMES[new_status])
            self._refresh_process()
            if self.on_changed:
                self.on_changed()
        StatusPickDialog(self, process['status'], on_select)

    def _build_info_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="企业信息")
        info = self.company
        rows = [
            ("档案编号", info['code']),
            ("企业名称", info['name']),
            ("统一社会信用代码", info['credit_code']),
            ("企业类型", "境内" if info['type'] == 0 else "境外"),
            ("联系人", info['contact'] or ""),
            ("联系电话", info['phone'] or ""),
            ("企业地址", info['address'] or ""),
            ("创建时间", fmt_dt(info['created_at'])),
            ("更新时间", fmt_dt(info['updated_at'])),
            ("备注", info['remark'] or ""),
        ]
        for i, (k, v) in enumerate(rows):
            row_frm = tk.Frame(frame, bg=COLOR_WHITE if i % 2 == 0 else COLOR_BG, pady=8, padx=15)
            row_frm.pack(fill="x", padx=10, pady=1)
            tk.Label(row_frm, text=k, bg=row_frm.cget("bg"), fg=COLOR_GRAY,
                     font=("Microsoft YaHei", 10), width=18, anchor="w").pack(side="left")
            tk.Label(row_frm, text=v, bg=row_frm.cget("bg"), font=("Microsoft YaHei", 10),
                     wraplength=550, justify="left").pack(side="left", fill="x", expand=True)

    def _build_audit_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="修改历史")
        tree = ttk.Treeview(frame, columns=("action", "old", "new", "operator", "time"), show="headings", height=20)
        tree.heading("action", text="操作")
        tree.heading("old", text="原值")
        tree.heading("new", text="新值")
        tree.heading("operator", text="操作人")
        tree.heading("time", text="时间")
        tree.column("action", width=120)
        tree.column("old", width=200)
        tree.column("new", width=200)
        tree.column("operator", width=80)
        tree.column("time", width=140)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        sb.pack(side="right", fill="y")
        logs = AuditDao.list(self.company_id)
        for log in logs:
            tree.insert("", "end", values=(log['action'], log['old_data'] or "",
                                            log['new_data'] or "", log['operator'], fmt_dt(log['created_at'])))

    def _export_excel(self):
        try:
            path = export_svc.export_company_csv(self.company)
            messagebox.showinfo("导出成功", "已导出到：\n%s" % path, parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self)

    def _export_word(self):
        try:
            path = export_svc.export_company_doc(self.company)
            messagebox.showinfo("导出成功", "已导出到：\n%s" % path, parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self)

    def _edit_company(self):
        CompanyEditDialog(self, company_id=self.company_id, on_saved=self._on_company_changed)

    def _on_company_changed(self):
        self.company = CompanyDao.get_by_id(self.company_id)
        self.title("%s - 企业详情" % self.company['name'])
        self._build_info_tab_refresh()
        if self.on_changed:
            self.on_changed()

    def _build_info_tab_refresh(self):
        # 重建 info tab
        tab_id = self.notebook.tabs()[1]
        self.notebook.forget(tab_id)
        frame = ttk.Frame(self.notebook)
        self.notebook.insert(1, frame, text="企业信息")
        info = self.company
        rows = [
            ("档案编号", info['code']),
            ("企业名称", info['name']),
            ("统一社会信用代码", info['credit_code']),
            ("企业类型", "境内" if info['type'] == 0 else "境外"),
            ("联系人", info['contact'] or ""),
            ("联系电话", info['phone'] or ""),
            ("企业地址", info['address'] or ""),
            ("创建时间", fmt_dt(info['created_at'])),
            ("更新时间", fmt_dt(info['updated_at'])),
            ("备注", info['remark'] or ""),
        ]
        for i, (k, v) in enumerate(rows):
            row_frm = tk.Frame(frame, bg=COLOR_WHITE if i % 2 == 0 else COLOR_BG, pady=8, padx=15)
            row_frm.pack(fill="x", padx=10, pady=1)
            tk.Label(row_frm, text=k, bg=row_frm.cget("bg"), fg=COLOR_GRAY,
                     font=("Microsoft YaHei", 10), width=18, anchor="w").pack(side="left")
            tk.Label(row_frm, text=v, bg=row_frm.cget("bg"), font=("Microsoft YaHei", 10),
                     wraplength=550, justify="left").pack(side="left", fill="x", expand=True)

    def _delete_company(self):
        if messagebox.askyesno("确认删除", "确定删除该企业及其全部备案记录？此操作不可恢复。", parent=self):
            CompanyDao.delete(self.company_id)
            if self.on_changed:
                self.on_changed()
            self.destroy()

    def _on_close(self):
        self.destroy()


class StatisticsWindow(tk.Toplevel):
    """统计窗口"""
    def __init__(self, master):
        super().__init__(master)
        self.title("数据统计")
        self.geometry("800x600")
        self.minsize(700, 500)
        self._build_ui()

    def _build_ui(self):
        companies = CompanyDao.list("", limit=100000, offset=0)
        total = len(companies)
        in_progress = sum(1 for c in companies if c['st'] < 7)
        completed = sum(1 for c in companies if c['st'] == 7)
        terminated = sum(1 for c in companies if c['st'] == 8)

        # 指标卡片
        card_frm = tk.Frame(self, bg=COLOR_BG)
        card_frm.pack(fill="x", padx=10, pady=10)
        cards = [("企业总数", total, COLOR_PRIMARY),
                 ("进行中", in_progress, "#E65100"),
                 ("已完成", completed, "#2E7D32"),
                 ("已终止", terminated, "#757575")]
        for i, (title, val, color) in enumerate(cards):
            card = tk.Frame(card_frm, bg=COLOR_WHITE, pady=15, padx=10)
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            card_frm.grid_columnconfigure(i, weight=1)
            tk.Label(card, text=str(val), fg=color, bg=COLOR_WHITE,
                     font=("Microsoft YaHei", 20, "bold")).pack()
            tk.Label(card, text=title, fg=COLOR_GRAY, bg=COLOR_WHITE,
                     font=("Microsoft YaHei", 10)).pack()

        # 状态分布（用 Canvas 画柱状图）
        chart_frm = tk.LabelFrame(self, text="备案状态分布", bg=COLOR_WHITE, font=("Microsoft YaHei", 10, "bold"))
        chart_frm.pack(fill="both", expand=True, padx=10, pady=5)
        canvas = tk.Canvas(chart_frm, bg=COLOR_WHITE, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self._draw_bar_chart(canvas, companies)

        # 月度趋势
        trend_frm = tk.LabelFrame(self, text="近12个月新增企业", bg=COLOR_WHITE, font=("Microsoft YaHei", 10, "bold"))
        trend_frm.pack(fill="both", expand=True, padx=10, pady=5)
        canvas2 = tk.Canvas(trend_frm, bg=COLOR_WHITE, highlightthickness=0)
        canvas2.pack(fill="both", expand=True, padx=10, pady=10)
        self._draw_line_chart(canvas2, companies)

    def _draw_bar_chart(self, canvas, companies):
        counts = [0] * 9
        for c in companies:
            if 0 <= c['st'] < 9:
                counts[c['st']] += 1
        max_val = max(counts) if max(counts) > 0 else 1
        canvas.update()
        w = max(canvas.winfo_width(), 600)
        h = max(canvas.winfo_height(), 200)
        bar_w = min(50, (w - 60) // 9)
        x_start = 40
        for i, cnt in enumerate(counts):
            x = x_start + i * (bar_w + 8)
            bar_h = int((cnt / max_val) * (h - 50))
            y = h - 30 - bar_h
            color = status_color(i)
            canvas.create_rectangle(x, y, x + bar_w, h - 30, fill=color, outline="")
            canvas.create_text(x + bar_w // 2, y - 10, text=str(cnt), font=("Microsoft YaHei", 9))
            canvas.create_text(x + bar_w // 2, h - 15, text=STATUS_NAMES[i][:4],
                               font=("Microsoft YaHei", 8), fill=COLOR_GRAY)

    def _draw_line_chart(self, canvas, companies):
        now = datetime.now()
        months = []
        for i in range(11, -1, -1):
            y = now.year - (1 if now.month - i <= 0 else 0)
            m = ((now.month - i - 1) % 12) + 1
            months.append((y, m))
        counts = [0] * 12
        for c in companies:
            dt = datetime.fromtimestamp(c['created_at'] / 1000)
            for i, (y, m) in enumerate(months):
                if dt.year == y and dt.month == m:
                    counts[i] += 1
                    break
        max_val = max(counts) if max(counts) > 0 else 1
        canvas.update()
        w = max(canvas.winfo_width(), 600)
        h = max(canvas.winfo_height(), 180)
        x_start = 40
        x_end = w - 20
        y_top = 20
        y_bottom = h - 30
        points = []
        for i, cnt in enumerate(counts):
            x = x_start + int((x_end - x_start) * i / 11)
            y = y_bottom - int((cnt / max_val) * (y_bottom - y_top))
            points.append((x, y))
        # 画线
        for i in range(len(points) - 1):
            canvas.create_line(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1],
                               fill=COLOR_PRIMARY, width=2)
        for i, (x, y) in enumerate(points):
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=COLOR_PRIMARY, outline="")
            canvas.create_text(x, y_bottom + 12, text="%d月" % months[i][1], font=("Microsoft YaHei", 8), fill=COLOR_GRAY)
            canvas.create_text(x, y - 12, text=str(counts[i]), font=("Microsoft YaHei", 8), fill=COLOR_TEXT)


class SettingsWindow(tk.Toplevel):
    """设置窗口"""
    def __init__(self, master):
        super().__init__(master)
        self.title("设置")
        self.geometry("500x450")
        self.resizable(False, False)
        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="数据管理", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Button(frm, text="数据备份", command=self._backup, width=30).pack(anchor="w", pady=3)
        ttk.Button(frm, text="数据恢复", command=self._restore, width=30).pack(anchor="w", pady=3)
        ttk.Button(frm, text="清理过期数据（完成/终止超1年）", command=self._clean, width=30).pack(anchor="w", pady=3)

        ttk.Separator(frm).pack(fill="x", pady=10)
        ttk.Label(frm, text="安全", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Button(frm, text="设置/修改应用锁PIN", command=self._set_pin, width=30).pack(anchor="w", pady=3)
        ttk.Button(frm, text="关闭应用锁", command=self._clear_pin, width=30).pack(anchor="w", pady=3)

        ttk.Separator(frm).pack(fill="x", pady=10)
        ttk.Label(frm, text="关于", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Label(frm, text="快件运营人备案管理 v%s" % APP_VERSION, font=("Microsoft YaHei", 10)).pack(anchor="w")
        ttk.Label(frm, text="数据库位置：%s" % get_db_path(), font=("Microsoft YaHei", 9),
                  foreground=COLOR_GRAY, wraplength=440, justify="left").pack(anchor="w", pady=5)

    def _backup(self):
        try:
            path = export_svc.backup()
            messagebox.showinfo("备份成功", "已备份到：\n%s" % path, parent=self)
        except Exception as e:
            messagebox.showerror("备份失败", str(e), parent=self)

    def _restore(self):
        path = filedialog.askopenfilename(title="选择备份文件", filetypes=[("数据库文件", "*.db"), ("所有文件", "*.*")])
        if path:
            if messagebox.askyesno("确认恢复", "恢复将覆盖当前数据，确定继续？", parent=self):
                try:
                    export_svc.restore(path)
                    messagebox.showinfo("恢复成功", "数据已恢复，请重启应用", parent=self)
                except Exception as e:
                    messagebox.showerror("恢复失败", str(e), parent=self)

    def _clean(self):
        if messagebox.askyesno("确认清理", "将删除已完成或终止且超过1年的企业档案，确定继续？", parent=self):
            count = export_svc.clean_old()
            messagebox.showinfo("清理完成", "已清理 %d 条档案" % count, parent=self)

    def _set_pin(self):
        pin = simpledialog.askstring("设置PIN", "请输入4-6位PIN码：", show="*", parent=self)
        if pin and 4 <= len(pin) <= 6:
            pin2 = simpledialog.askstring("确认PIN", "请再次输入PIN码：", show="*", parent=self)
            if pin == pin2:
                import json
                cfg = self._load_cfg()
                cfg['pin'] = pin
                cfg['lock_enabled'] = True
                self._save_cfg(cfg)
                messagebox.showinfo("成功", "应用锁已设置", parent=self)
            else:
                messagebox.showerror("错误", "两次输入不一致", parent=self)

    def _clear_pin(self):
        cfg = self._load_cfg()
        if cfg.get('pin'):
            if messagebox.askyesno("确认", "确定关闭应用锁？", parent=self):
                cfg['lock_enabled'] = False
                cfg.pop('pin', None)
                self._save_cfg(cfg)
                messagebox.showinfo("成功", "应用锁已关闭", parent=self)
        else:
            messagebox.showinfo("提示", "当前未设置应用锁", parent=self)

    def _cfg_path(self):
        if os.name == 'nt':
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'FilingApp')
        else:
            base = os.path.join(os.path.expanduser('~'), '.filingapp')
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'config.json')

    def _load_cfg(self):
        try:
            with open(self._cfg_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cfg(self, cfg):
        with open(self._cfg_path(), 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


class MainWindow:
    """主窗口"""
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x600")
        self.root.minsize(800, 500)
        self.root.configure(bg=COLOR_BG)
        self.query = ""
        self.page = 0
        self.total = 0
        self._build_ui()
        self._check_lock()

    def _check_lock(self):
        cfg_path = self._cfg_path()
        try:
            import json
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if cfg.get('lock_enabled') and cfg.get('pin'):
                dlg = PinLockDialog(self.root, cfg['pin'])
                self.root.wait_window(dlg)
                if not dlg.unlocked:
                    self.root.destroy()
        except Exception:
            pass

    def _cfg_path(self):
        if os.name == 'nt':
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'FilingApp')
        else:
            base = os.path.join(os.path.expanduser('~'), '.filingapp')
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'config.json')

    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self.root, bg=COLOR_PRIMARY, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=APP_TITLE, fg="white", bg=COLOR_PRIMARY,
                 font=("Microsoft YaHei", 14, "bold")).pack(side="left", padx=20)

        # 搜索栏
        search_frm = tk.Frame(self.root, bg=COLOR_WHITE, pady=8, padx=15)
        search_frm.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(search_frm, text="搜索：", bg=COLOR_WHITE, font=("Microsoft YaHei", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())
        search_entry = ttk.Entry(search_frm, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", padx=5)
        tk.Label(search_frm, text="（企业名称/信用代码/联系人/电话）", bg=COLOR_WHITE,
                 fg=COLOR_GRAY, font=("Microsoft YaHei", 9)).pack(side="left", padx=5)

        # 列表
        list_frm = tk.Frame(self.root, bg=COLOR_BG)
        list_frm.pack(fill="both", expand=True, padx=10, pady=8)
        self.tree = ttk.Treeview(list_frm, columns=("name", "code", "status", "time"),
                                  show="headings", selectmode="browse")
        self.tree.heading("name", text="企业名称")
        self.tree.heading("code", text="统一社会信用代码")
        self.tree.heading("status", text="当前状态")
        self.tree.heading("time", text="最近更新")
        self.tree.column("name", width=250)
        self.tree.column("code", width=200)
        self.tree.column("status", width=120)
        self.tree.column("time", width=150)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", lambda e: self._open_detail())
        sb = ttk.Scrollbar(list_frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        # 分页栏
        page_frm = tk.Frame(self.root, bg=COLOR_WHITE, pady=8, padx=15)
        page_frm.pack(fill="x", padx=10, pady=(0, 8))
        self.page_label = tk.Label(page_frm, text="", bg=COLOR_WHITE, font=("Microsoft YaHei", 10))
        self.page_label.pack(side="left")
        ttk.Button(page_frm, text="上一页", command=self._prev_page, width=8).pack(side="right", padx=5)
        ttk.Button(page_frm, text="下一页", command=self._next_page, width=8).pack(side="right", padx=5)

        # 底部操作栏
        bottom = tk.Frame(self.root, bg=COLOR_PRIMARY, height=48)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        for text, cmd, icon in [("新增企业", self._add_company, "＋"),
                                 ("统计", self._show_stats, "📊"),
                                 ("设置", self._show_settings, "⚙"),
                                 ("导出全部Excel", self._export_all, "📤")]:
            btn = tk.Button(bottom, text="%s %s" % (icon, text), fg="white", bg=COLOR_PRIMARY,
                            activebackground=COLOR_PRIMARY_DARK, activeforeground="white",
                            relief="flat", font=("Microsoft YaHei", 10), padx=15, pady=5, command=cmd)
            btn.pack(side="left", padx=5, pady=6)

        self._refresh()

    def _on_search(self):
        self.query = self.search_var.get().strip()
        self.page = 0
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        companies = CompanyDao.list(self.query, limit=PAGE_SIZE, offset=self.page * PAGE_SIZE)
        self.total = CompanyDao.count(self.query)
        for c in companies:
            status = c['st'] if 'st' in c.keys() else 0
            self.tree.insert("", "end", iid=str(c['id']),
                             values=(c['name'], c['credit_code'], STATUS_NAMES[status], fmt_dt(c['updated_at'])))
        total_pages = max(1, (self.total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page_label.config(text="第 %d/%d 页，共 %d 条" % (self.page + 1, total_pages, self.total))

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._refresh()

    def _next_page(self):
        total_pages = max(1, (self.total + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.page < total_pages - 1:
            self.page += 1
            self._refresh()

    def _open_detail(self):
        sel = self.tree.selection()
        if sel:
            cid = int(sel[0])
            CompanyDetailWindow(self.root, cid, on_changed=self._refresh)

    def _add_company(self):
        CompanyEditDialog(self.root, on_saved=self._refresh)

    def _show_stats(self):
        StatisticsWindow(self.root)

    def _show_settings(self):
        SettingsWindow(self.root)

    def _export_all(self):
        try:
            path = export_svc.export_all_csv(self.query)
            messagebox.showinfo("导出成功", "已导出到：\n%s" % path, parent=self.root)
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self.root)


def main():
    Database.get_conn()
    root = tk.Tk()
    # 设置主题
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    # 自定义样式
    style.configure("TButton", font=("Microsoft YaHei", 10), padding=6)
    style.configure("TEntry", font=("Microsoft YaHei", 10))
    style.configure("TCombobox", font=("Microsoft YaHei", 10))
    style.configure("Treeview", font=("Microsoft YaHei", 10), rowheight=28)
    style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))
    style.configure("TNotebook", font=("Microsoft YaHei", 10))
    style.configure("TNotebook.Tab", padding=[15, 8], font=("Microsoft YaHei", 10))

    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
