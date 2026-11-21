from decimal import Decimal, InvalidOperation
from hashlib import sha256
from app.settings import RULE_VERSION, UNIT
from app.errors import DataError

DISPUTED_METRIC = '同级争议'
QUARANTINE_REASONS = {
    'GRID_LIMIT': '权证矩形数量超限', 'GRID_FORMAT': '权证矩形无效',
    'GRID_SPAN': '权证边界无正面积', 'RANGE': '数字越界',
    'NUMBER': '数字无法归一', 'BUSINESS': '业务规则无法判定',
    'REQUIRED': '主键或业务字段缺失', 'REV_CONFLICT': '最高版本证据有冲突',
    'REV_BLOCKED': '较新来源尚未采信',
}
SUPPRESSED_REASONS = {
    'SUPERSEDED': '已被更新版本代替', 'EXACT_DUP': '同版本重复传输',
}


def side(run):
    """提取一个批次按业务键排列的快照，供并排对账使用。"""
    accepted = {row['key']: row for row in run['accepted']}
    quarantined, suppressed = {}, {}
    for row in run['quarantine']:
        if not row.get('key'):
            continue  # 主键都无法解析的坏行不属于任何地块，留在隔离清单中即可。
        quarantined.setdefault(row['key'], []).append(row)
    for row in run['suppressed']:
        if not row.get('key'):
            continue
        suppressed.setdefault(row['key'], []).append(row)
    book = {row['key']: row for row in run['book']['rows'] if row['key']}
    return {'accepted': accepted, 'quarantined': quarantined,
            'suppressed': suppressed, 'book': book}


def proof_value(row, metric):
    for item in row['proof']:
        if item['metric'] == metric:
            return item['value']
    return None


def as_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def delta_dimension(base_book, target_book):
    old_delta = base_book['delta'] if base_book else None
    new_delta = target_book['delta'] if target_book else None
    changed = as_decimal(old_delta) != as_decimal(new_delta)
    return {'label': '外账差异', 'base': old_delta, 'target': new_delta,
            'changed': changed, 'unit': UNIT}


def dim(label, base_value, target_value, unit, changed=None):
    if changed is None:
        changed = (base_value != target_value)
    return {'label': label, 'base': base_value, 'target': target_value,
            'changed': changed, 'unit': unit}


def explain(key, base_side, target_side, dimensions, status):
    """自动解释：只采信批次内可追溯的痕迹——
    1) 隔离原因码；2) 地块在某一侧完全退出测面（重传/替代痕迹）；
    3) 几何未变时的外部账单边更新。
    已采信地块在本批次内部的重传/替代标记属于流水线簿记，
    不能解释跨批次变化；纯几何或无痕迹修订变化留给复核员补注。"""
    if status == 'unchanged':
        return True, []
    reasons = []
    for snapshot in (base_side, target_side):
        for row in snapshot['quarantined'].get(key, []):
            label = QUARANTINE_REASONS.get(row['code'])
            if label:
                reasons.append(f'{label}（{row["code"]}）')
    # 地块在一侧未被采信且没有隔离记录时，重传/替代痕迹才能解释其进退场。
    if key not in base_side['accepted'] or key not in target_side['accepted']:
        for snapshot in (base_side, target_side):
            for row in snapshot['suppressed'].get(key, []):
                label = SUPPRESSED_REASONS.get(row['code'])
                if label:
                    reasons.append(f'{label}（{row["code"]}）')
    area_dim = next(item for item in dimensions if item['label'] == '可确认面积')
    dispute_dim = next(item for item in dimensions if item['label'] == '争议冻结')
    book_dim = next(item for item in dimensions if item['label'] == '外部账记录值')
    delta_dim = next(item for item in dimensions if item['label'] == '外账差异')
    geometry_changed = area_dim['changed'] or dispute_dim['changed']
    # 地块仍在测面范围内、来源几何未动，差异完全来自外部账调整时，才能按外账更新解释。
    if status == 'changed' and not geometry_changed and (book_dim['changed'] or delta_dim['changed']):
        reasons.append('外部账更新')
    reasons = list(dict.fromkeys(reasons))
    return bool(reasons), reasons


def compare_runs(base_run, target_run):
    base_side, target_side = side(base_run), side(target_run)
    keys = sorted(set(base_side['accepted']) | set(target_side['accepted'])
                  | set(base_side['quarantined']) | set(target_side['quarantined'])
                  | set(base_side['suppressed']) | set(target_side['suppressed'])
                  | set(base_side['book']) | set(target_side['book']))
    rows = []
    for key in keys:
        old = base_side['accepted'].get(key)
        new = target_side['accepted'].get(key)
        old_book, new_book = base_side['book'].get(key), target_side['book'].get(key)
        dimensions = [
            dim('采信修订', old['revision'] if old else None,
                new['revision'] if new else None, '版'),
            dim('可确认面积', old['amount'] if old else None,
                new['amount'] if new else None, UNIT),
            dim('争议冻结', proof_value(old, DISPUTED_METRIC) if old else None,
                proof_value(new, DISPUTED_METRIC) if new else None, UNIT),
            dim('外部账记录值', old_book['reference'] if old_book else None,
                new_book['reference'] if new_book else None, UNIT),
            delta_dimension(old_book, new_book),
        ]
        base_status = 'accepted' if old else _absent_status(base_side, key)
        target_status = 'accepted' if new else _absent_status(target_side, key)
        if base_status != target_status:
            # 新增、退出测面、被隔离或降级为重传：状态本身就是变化，不能落入无变化。
            if base_status == 'absent':
                status = 'added'
            elif target_status == 'absent':
                status = 'removed'
            else:
                status = 'changed'
        elif any(item['changed'] for item in dimensions):
            # 即使可确认面积碰巧相同，争议冻结或外账变化也不能写成无变化。
            status = 'changed'
        else:
            status = 'unchanged'
        auto_explained, reasons = explain(key, base_side, target_side, dimensions, status)
        rows.append({'key': key, 'status': status, 'dimensions': dimensions,
                     'auto_explained': auto_explained, 'reasons': reasons,
                     'base_status': base_status, 'target_status': target_status,
                     'note': ''})
    counts = {name: sum(1 for row in rows if row['status'] == name)
              for name in ('added', 'removed', 'changed', 'unchanged')}
    unexplained = sum(1 for row in rows
                      if row['status'] != 'unchanged' and not row['auto_explained'] and not row['note'])
    return {
        'base': run_header(base_run), 'target': run_header(target_run),
        'rows': rows, 'counts': counts, 'unexplained_count': unexplained,
        'book_summary': {'base': base_run['book']['delta'], 'target': target_run['book']['delta']},
    }


def _absent_status(snapshot, key):
    if key in snapshot['quarantined']:
        return 'quarantined'
    if key in snapshot['suppressed']:
        return 'suppressed'
    return 'absent'


def run_header(run):
    manifest = run['manifest']
    return {'run_id': manifest['run_id'], 'created': manifest['created'],
            'source_sha256': manifest['source_sha256'], 'book_sha256': manifest['book_sha256']}


def comparison_id(base_run_id, target_run_id):
    if base_run_id == target_run_id:
        raise DataError('COMPARE_SAME', '新旧批次不能相同')
    return sha256(f'{RULE_VERSION}:{base_run_id}:{target_run_id}'.encode()).hexdigest()
