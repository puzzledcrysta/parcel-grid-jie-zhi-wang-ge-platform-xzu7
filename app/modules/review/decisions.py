import json
from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup
from app.modules.compare.repository import unexplained_for_run


def timeline(run_id):
    with connection() as db:
        lookup(db,run_id)
        return list(map(dict,db.execute('SELECT version,decision,note,changed FROM reviews WHERE run_id=? ORDER BY version DESC',(run_id,))))


def decide(run_id,version,decision,note):
    note = note.strip()
    if decision not in {'确认','退回'}:
        raise DataError('REVIEW_DECISION','复核结论无效')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = json.loads(lookup(db,run_id)['result'])
        current = db.execute('SELECT COALESCE(MAX(version),0) FROM reviews WHERE run_id=?',(run_id,)).fetchone()[0]
        if current != version:
            raise DataError('STALE','复核版本已过期，请刷新',409)
        if (run['book']['mismatched'] or run['quarantine'] or decision=='退回') and not note:
            raise DataError('REVIEW_NOTE','有差异时须填写复核意见')
        if decision == '确认':
            blocked = [key for key in unexplained_for_run(db, run_id) if key]
            if blocked:
                preview = ', '.join(blocked[:8])
                suffix = ' 等' if len(blocked) > 8 else ''
                raise DataError('REVIEW_UNEXPLAINED',
                                f'存在解释不清的地块，不能确认新批：{preview}{suffix}')
        record = {'version':current+1,'decision':decision,'note':note,'changed':datetime.now(timezone.utc).isoformat()}
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(run_id,*record.values()))
        return record
