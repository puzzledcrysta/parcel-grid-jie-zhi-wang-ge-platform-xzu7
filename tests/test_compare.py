import csv
from io import StringIO
import pytest

HEADER = '地块复核单,修订号,提交时间,权属矩形,目标业主,原始备注'
STAMP = '2026-11-18T09:30:00+08:00'


def source_csv(rows):
    out = StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(HEADER.split(','))
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode()


def book_csv(entries):
    out = StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['地块复核单', '外部记录值(平方米)'])
    for key, value in entries:
        writer.writerow([key, value])
    return out.getvalue().encode()


def make_run(client, rows, entries):
    response = client.post('/api/runs', json={'data': source_csv(rows).decode(),
                                              'book': book_csv(entries).decode()})
    assert response.status_code == 200, response.text
    return response.json()['manifest']['run_id']


def dim_map(report):
    return {row['key']: {dim['label']: dim for dim in row['dimensions']}
            for row in report['rows']}


def compare(client, base, target):
    response = client.post('/api/compare', json={'base_run_id': base, 'target_run_id': target})
    assert response.status_code == 200, response.text
    return response.json()


def test_same_inputs_do_not_create_new_comparison_batch(client):
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    target = make_run(client, [['P02', '1', STAMP, '甲:1:0:0:3:3', '甲', '']], [('P02', '9')])
    first = compare(client, base, target)
    second = compare(client, base, target)
    assert first['comparison_id'] == second['comparison_id']
    assert len(client.get('/api/compare').json()) == 1


def test_side_by_side_shows_revision_area_and_book_changes(client):
    base = make_run(client, [
        ['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', ''],
        ['P02', '1', STAMP, '甲:1:0:0:5:5', '甲', ''],
    ], [('P01', '16'), ('P02', '25')])
    target = make_run(client, [
        ['P01', '2', STAMP, '甲:1:0:0:5:5', '甲', ''],
        ['P02', '1', STAMP, '甲:1:0:0:5:5', '甲', ''],
        ['P03', '1', STAMP, '甲:1:0:0:2:2', '甲', ''],
    ], [('P01', '25'), ('P02', '25'), ('P03', '4')])
    report = compare(client, base, target)
    rows = {row['key']: row for row in report['rows']}
    assert report['counts'] == {'added': 1, 'removed': 0, 'changed': 1, 'unchanged': 1}
    p01 = dim_map(report)['P01']
    assert (p01['采信修订']['base'], p01['采信修订']['target'], p01['采信修订']['changed']) == (1, 2, True)
    assert (p01['可确认面积']['base'], p01['可确认面积']['target']) == ('16', '25')
    assert (p01['外部账记录值']['base'], p01['外部账记录值']['target']) == ('16', '25')
    assert (p01['外账差异']['base'], p01['外账差异']['target']) == ('0', '0')
    assert rows['P03']['status'] == 'added'
    assert rows['P02']['status'] == 'unchanged'


def test_equal_final_area_still_flagged_when_dispute_or_book_changes(client):
    # TRAP: 新版本争议冻结、外账都改了值，但可确认面积碰巧相同，不能只写无变化。
    base = make_run(client, [
        # 完整 4x4 矩形：可确认 16，无冻结。
        ['P02', '1', STAMP, '甲:1:0:0:4:4', '甲', ''],
    ], [('P02', '16')])
    target = make_run(client, [
        # 5x5 中与同级异主重叠 9 平方米：业主可确认面积碰巧仍为 16，但冻结 9。
        ['P02', '1', STAMP, '甲:1:0:0:5:5;乙:1:0:0:3:3', '甲', ''],
    ], [('P02', '7')])
    row = compare(client, base, target)['rows'][0]
    dimensions = {dim['label']: dim for dim in row['dimensions']}
    assert row['status'] == 'changed'
    assert dimensions['可确认面积']['changed'] is False
    assert dimensions['争议冻结']['base'] == '0' and dimensions['争议冻结']['target'] == '9'
    assert dimensions['争议冻结']['changed'] is True
    assert dimensions['外部账记录值']['base'] == '16' and dimensions['外部账记录值']['target'] == '7'
    assert dimensions['外部账记录值']['changed'] is True
    assert dimensions['外账差异']['base'] == '0' and dimensions['外账差异']['target'] == '9'
    assert dimensions['外账差异']['changed'] is True


def test_same_run_and_unknown_run_are_rejected(client):
    run_id = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    same = client.post('/api/compare', json={'base_run_id': run_id, 'target_run_id': run_id})
    assert (same.status_code, same.json()['code']) == (422, 'COMPARE_SAME')
    missing = client.post('/api/compare', json={'base_run_id': run_id, 'target_run_id': 'nope'})
    assert (missing.status_code, missing.json()['code']) == (404, 'RUN_UNKNOWN')
    assert client.get('/api/compare').json() == []
    assert client.get('/api/compare/nope').status_code == 404


def test_keyless_bad_rows_are_not_parcels(client):
    # 列数不足的坏行没有可解析主键：它属于隔离清单，不应出现在地块对账里。
    first = client.post('/api/runs', json={}).json()['manifest']['run_id']
    second = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    report = compare(client, first, second)
    assert all(row['key'] for row in report['rows'])
