import json
from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup


def save_comparison(comparison_id, base_run_id, target_run_id, report):
    created = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO comparisons VALUES (?,?,?,?,?)',
                   (comparison_id, base_run_id, target_run_id,
                    json.dumps(report, ensure_ascii=False), created))
        row = db.execute('SELECT * FROM comparisons WHERE id=?', (comparison_id,)).fetchone()
        return row


def get_comparison(db, comparison_id):
    row = db.execute('SELECT * FROM comparisons WHERE id=?', (comparison_id,)).fetchone()
    if row is None:
        raise DataError('COMPARE_UNKNOWN', '没有此对账批次', 404)
    return row


def list_comparisons():
    with connection() as db:
        rows = db.execute('SELECT id,base_run_id,target_run_id,created FROM comparisons '
                          'ORDER BY created DESC,id DESC LIMIT 50').fetchall()
        return [dict(row) for row in rows]


def load(comparison_id):
    with connection() as db:
        row = get_comparison(db, comparison_id)
        report = json.loads(row['report'])
        notes = db.execute('SELECT parcel_key,note FROM comparison_notes WHERE comparison_id=?',
                           (comparison_id,)).fetchall()
    by_key = {item['parcel_key']: item['note'] for item in notes}
    for item in report['rows']:
        item['note'] = by_key.get(item['key'], '')
    report['unexplained_count'] = sum(
        1 for item in report['rows']
        if item['status'] != 'unchanged' and not item['auto_explained'] and not item['note'])
    return report


def set_note(comparison_id, parcel_key, note):
    note = note.strip()
    changed = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        get_comparison(db, comparison_id)
        report = json.loads(db.execute('SELECT report FROM comparisons WHERE id=?',
                                       (comparison_id,)).fetchone()['report'])
        if not any(row['key'] == parcel_key for row in report['rows']):
            raise DataError('REQUIRED', '对账批次没有此地块')
        if not note:
            db.execute('DELETE FROM comparison_notes WHERE comparison_id=? AND parcel_key=?',
                       (comparison_id, parcel_key))
        else:
            db.execute('INSERT INTO comparison_notes VALUES (?,?,?,?) '
                       'ON CONFLICT(comparison_id,parcel_key) DO UPDATE SET note=excluded.note, changed=excluded.changed',
                       (comparison_id, parcel_key, note, changed))
    return load(comparison_id)


def unexplained_for_run(db, run_id):
    """返回以 run_id 为新批的所有对账中仍解释不清的地块键。"""
    rows = db.execute('SELECT id, report FROM comparisons WHERE target_run_id=?', (run_id,)).fetchall()
    blocked = []
    for row in rows:
        report = json.loads(row['report'])
        notes = {item['parcel_key']: item['note']
                 for item in db.execute('SELECT parcel_key,note FROM comparison_notes WHERE comparison_id=?',
                                        (row['id'],)).fetchall()}
        for item in report['rows']:
            if item['status'] != 'unchanged' and not item['auto_explained'] and not notes.get(item['key']):
                blocked.append(item['key'])
    return sorted(set(blocked))
