# -*- coding: utf-8 -*-
"""导出服务：Excel(CSV) / Word(HTML) / 备份"""
import os
import csv
import io
import shutil
from database import (CompanyDao, RecordDao, AuditDao, STATUS_NAMES, RECORD_TYPES,
                      CONTENT_LABELS, fmt_dt, file_stamp, get_db_path, now_ms)


def _esc(s):
    return (s or "").replace(",", "，").replace("\n", " ").replace("\r", "")


def company_summary(company):
    """汇总企业备案流程信息"""
    info = {
        'apply_time': '', 'send_time': '',
        'reject_count': 0, 'last_reject_time': '', 'last_reject_content': '',
        'contact_count': 0, 'last_contact_time': '', 'last_contact_content': '',
        'fz_count': 0, 'last_fz_time': '', 'last_fz_content': '',
        'gacc_count': 0, 'last_gacc_time': '', 'last_gacc_content': '',
    }
    p = RecordDao.get_process(company['id'])
    if not p:
        return info
    info['apply_time'] = fmt_dt(p['apply_time'])
    info['send_time'] = fmt_dt(p['send_to_gacc_time'])
    for r in RecordDao.list(p['id']):
        t = fmt_dt(r['occur_time'])
        if r['type'] == 1:
            info['reject_count'] += 1
            info['last_reject_time'] = t
            info['last_reject_content'] = r['content']
        elif r['type'] == 2:
            info['contact_count'] += 1
            info['last_contact_time'] = t
            info['last_contact_content'] = r['content']
        elif r['type'] == 3:
            info['fz_count'] += 1
            info['last_fz_time'] = t
            info['last_fz_content'] = r['content']
        else:
            info['gacc_count'] += 1
            info['last_gacc_time'] = t
            info['last_gacc_content'] = r['content']
    return info


def export_all_csv(query=""):
    """导出全部企业为 CSV"""
    companies = CompanyDao.list(query, limit=100000, offset=0)
    out = io.StringIO()
    # 加 BOM 让 Excel 正确识别中文
    out.write('\ufeff')
    writer = csv.writer(out)
    writer.writerow(["序号", "企业名称", "统一社会信用代码", "企业类型", "联系人", "联系电话",
                     "申请时间", "发函总署时间", "总署打回次数", "最近打回时间", "最近打回要求",
                     "行邮联系福中次数", "最近联系时间", "最近联系内容",
                     "福中反馈次数", "最近反馈时间", "最近反馈情况",
                     "行邮反馈总署次数", "最近反馈时间", "最近反馈情况", "当前状态", "备注"])
    for i, c in enumerate(companies, 1):
        info = company_summary(c)
        writer.writerow([
            i, _esc(c['name']), _esc(c['credit_code']),
            "境内" if c['type'] == 0 else "境外",
            _esc(c['contact']), _esc(c['phone']),
            info['apply_time'], info['send_time'],
            info['reject_count'], info['last_reject_time'], _esc(info['last_reject_content']),
            info['contact_count'], info['last_contact_time'], _esc(info['last_contact_content']),
            info['fz_count'], info['last_fz_time'], _esc(info['last_fz_content']),
            info['gacc_count'], info['last_gacc_time'], _esc(info['last_gacc_content']),
            STATUS_NAMES[c['st']] if 'st' in c.keys() else STATUS_NAMES[0],
            _esc(c['remark'])
        ])
    name = "快件运营人备案台账_总表_%s.csv" % file_stamp()
    path = os.path.join(_export_dir(), name)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(out.getvalue())
    return path


def export_company_csv(company):
    """导出单个企业为 CSV"""
    info = company_summary(company)
    out = io.StringIO()
    out.write('\ufeff')
    writer = csv.writer(out)
    writer.writerow(["字段", "内容"])
    writer.writerow(["企业名称", _esc(company['name'])])
    writer.writerow(["档案编号", company['code']])
    writer.writerow(["统一社会信用代码", _esc(company['credit_code'])])
    writer.writerow(["企业类型", "境内" if company['type'] == 0 else "境外"])
    writer.writerow(["联系人", _esc(company['contact'])])
    writer.writerow(["联系电话", _esc(company['phone'])])
    writer.writerow(["地址", _esc(company['address'])])
    writer.writerow(["当前状态", STATUS_NAMES[company['st']] if 'st' in company.keys() else ""])
    writer.writerow(["备注", _esc(company['remark'])])
    writer.writerow([])
    writer.writerow(["备案流程记录"])
    writer.writerow(["节点", "时间", "内容", "备注"])
    p = RecordDao.get_process(company['id'])
    if p:
        writer.writerow(["企业申请备案", fmt_dt(p['apply_time']), "", ""])
        writer.writerow(["深圳海关发函总署", fmt_dt(p['send_to_gacc_time']), "", ""])
        for r in RecordDao.list(p['id']):
            writer.writerow([RECORD_TYPES.get(r['type'], "未知"),
                              fmt_dt(r['occur_time']), _esc(r['content']), _esc(r['remark'])])
    name = "%s_备案台账_%s.csv" % (_esc(company['name']), file_stamp())
    path = os.path.join(_export_dir(), name)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(out.getvalue())
    return path


def export_company_doc(company):
    """导出单个企业为 Word(HTML)"""
    info = company_summary(company)
    p = RecordDao.get_process(company['id'])
    rows = ""
    if p:
        rows += "<tr><td>企业申请备案</td><td>%s</td><td></td></tr>" % fmt_dt(p['apply_time'])
        rows += "<tr><td>深圳海关发函总署</td><td>%s</td><td></td></tr>" % fmt_dt(p['send_to_gacc_time'])
        for r in RecordDao.list(p['id']):
            rows += "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                RECORD_TYPES.get(r['type'], "未知"),
                fmt_dt(r['occur_time']), _esc(r['content']))
    status = STATUS_NAMES[company['st']] if 'st' in company.keys() else ""
    html = """<html><head><meta charset="utf-8"><style>
body{font-family:"Microsoft YaHei",SimSun,sans-serif;font-size:14px;}
h1{text-align:center;font-size:20px;}
table{border-collapse:collapse;width:100%%;margin:10px 0;}
td,th{border:1px solid #333;padding:6px 10px;}
th{background:#f0f0f0;}
</style></head><body>
<h1>快件运营人备案进度记录表</h1>
<table>
<tr><th>企业名称</th><td>%s</td><th>档案编号</th><td>%s</td></tr>
<tr><th>统一社会信用代码</th><td>%s</td><th>企业类型</th><td>%s</td></tr>
<tr><th>联系人</th><td>%s</td><th>联系电话</th><td>%s</td></tr>
<tr><th>地址</th><td colspan="3">%s</td></tr>
<tr><th>当前状态</th><td>%s</td><th>备注</th><td>%s</td></tr>
</table>
<h3>备案流程时间轴</h3>
<table>
<tr><th>节点</th><th>时间</th><th>内容/情况</th></tr>
%s
</table>
</body></html>""" % (
        _esc(company['name']), company['code'],
        _esc(company['credit_code']), "境内" if company['type'] == 0 else "境外",
        _esc(company['contact']), _esc(company['phone']),
        _esc(company['address']), status, _esc(company['remark']),
        rows)
    name = "%s_备案进度记录_%s.doc" % (_esc(company['name']), file_stamp())
    path = os.path.join(_export_dir(), name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def backup():
    """备份数据库"""
    src = get_db_path()
    name = "备案数据备份_%s.db" % file_stamp()
    dst = os.path.join(_export_dir(), name)
    shutil.copy2(src, dst)
    return dst


def restore(src_path):
    """从备份恢复"""
    dst = get_db_path()
    # 关闭当前连接
    from database import Database
    if Database._conn:
        Database._conn.close()
        Database._conn = None
    shutil.copy2(src_path, dst)
    return True


def clean_old():
    """清理超过1年的已完成/终止档案"""
    one_year = now_ms() - 365 * 86400 * 1000
    all_c = CompanyDao.list("", limit=100000, offset=0)
    count = 0
    for c in all_c:
        if (c['st'] == 7 or c['st'] == 8) and c['updated_at'] < one_year:
            CompanyDao.delete(c['id'])
            count += 1
    return count


def _export_dir():
    if os.name == 'nt':
        base = os.path.join(os.path.expanduser('~'), 'Documents', '快件备案台账')
    else:
        base = os.path.join(os.path.expanduser('~'), '快件备案台账')
    os.makedirs(base, exist_ok=True)
    return base
