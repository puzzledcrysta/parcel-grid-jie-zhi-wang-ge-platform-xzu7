from tests.test_compare import make_run, compare, STAMP


def review(client, run_id, decision='确认', note=''):
    timeline = client.get(f'/api/review/{run_id}').json()
    version = timeline[0]['version'] if timeline else 0
    return client.post(f'/api/review/{run_id}',
                       json={'version': version, 'decision': decision, 'note': note})


def test_unexplained_parcel_blocks_confirmation_until_note(client):
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    target = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:5:5', '甲', '']], [('P01', '16')])
    report = compare(client, base, target)
    row = report['rows'][0]
    assert row['auto_explained'] is False and report['unexplained_count'] == 1
    blocked = review(client, target, '确认', '已核对来源行')
    assert (blocked.status_code, blocked.json()['code']) == (422, 'REVIEW_UNEXPLAINED')
    # 退回不受拦截。
    returned = review(client, target, '退回', '请补充来源旁证')
    assert returned.status_code == 200
    # 复核员补注后即可确认新批。
    noted = client.post(f"/api/compare/{report['comparison_id']}/notes/P01",
                        json={'note': '现场指界确认扩边至 5 米'})
    assert noted.status_code == 200 and noted.json()['unexplained_count'] == 0
    assert review(client, target, '确认', '已逐条核对').status_code == 200


def test_version_and_quarantine_traces_are_explained_automatically(client):
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    # 新批中 P02 最高修订冲突被隔离，旧版无法接替；P01 修订升级后面积变化。
    rows = [
        ['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '前版'],
        ['P01', '2', STAMP, '甲:1:0:0:5:5', '甲', '补正'],
        ['P02', '2', STAMP, '甲:1:0:0:4:4', '甲', ''],
        ['P02', '2', STAMP, '甲:1:0:0:3:3', '甲', ''],
    ]
    target = make_run(client, rows, [('P01', '25')])
    report = compare(client, base, target)
    by_key = {row['key']: row for row in report['rows']}
    assert by_key['P02']['auto_explained'] is True
    assert [reason for reason in by_key['P02']['reasons'] if 'REV_CONFLICT' in reason] == ['最高版本证据有冲突（REV_CONFLICT）']
    # P01 几何随修订变化且无痕迹，仍需复核员补注后才能确认。
    assert by_key['P01']['auto_explained'] is False
    client.post(f"/api/compare/{report['comparison_id']}/notes/P01", json={'note': '补正扩边已现场指界'})
    assert review(client, target, '确认', '已逐条核对').status_code == 200


def test_quarantined_parcel_recovering_is_explained(client):
    base = make_run(client, [
        ['P09', '2', STAMP, '甲:1:0:0:4:4', '甲', ''],
        ['P09', '2', STAMP, '甲:1:0:0:3:3', '甲', ''],
    ], [])
    target = make_run(client, [['P09', '2', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P09', '16')])
    row = compare(client, base, target)['rows'][0]
    assert (row['base_status'], row['target_status'], row['status']) == ('quarantined', 'accepted', 'changed')
    assert row['auto_explained'] is True
    assert review(client, target, '确认', '隔离恢复已核').status_code == 200


def test_book_only_change_is_explained_but_geometry_change_is_not(client):
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    target = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '20')])
    report = compare(client, base, target)
    row = report['rows'][0]
    assert row['auto_explained'] is True
    assert row['reasons'] == ['外部账更新']
    assert review(client, target, '确认', '外部账调整已核').status_code == 200


def test_revision_change_without_trace_still_needs_note(client):
    # 修订号升级但两版几何完全相同：重传痕迹不能替代变化解释，必须补注。
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    target = make_run(client, [
        ['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '前版'],
        ['P01', '2', STAMP, '甲:1:0:0:4:4', '甲', '补正'],
    ], [('P01', '16')])
    report = compare(client, base, target)
    row = report['rows'][0]
    assert row['status'] == 'changed' and row['auto_explained'] is False
    assert report['unexplained_count'] == 1
    blocked = review(client, target, '确认', '尝试确认')
    assert blocked.json()['code'] == 'REVIEW_UNEXPLAINED'
    client.post(f"/api/compare/{report['comparison_id']}/notes/P01", json={'note': '修订仅调整登记信息'})
    assert review(client, target, '确认', '已核').status_code == 200


def test_switch_failure_keeps_old_batch_and_review_evidence(client):
    base = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    target = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:5:5', '甲', '']], [('P01', '25')])
    assert review(client, base, '确认', '旧批依据完整').status_code == 200
    compare(client, base, target)
    # 对账是只读操作：旧批结果、原输入与复核时间线都不能被覆盖。
    old = client.get(f'/api/runs/{base}').json()
    assert old['accepted'][0]['amount'] == '16'
    source = client.get(f'/api/runs/{base}/source').json()
    import base64
    decoded = base64.b64decode(source['data_base64']).decode()
    assert '甲:1:0:0:4:4' in decoded
    timeline = client.get(f'/api/review/{base}').json()
    assert [item['decision'] for item in timeline] == ['确认']
    # 新批被拦截，旧批复核版本号不因失败而推进。
    blocked = review(client, target, '确认', '尝试确认新批')
    assert blocked.status_code == 422
    assert client.get(f'/api/review/{base}').json()[0]['version'] == 1
    assert client.get(f'/api/review/{target}').json() == []
    # 旧批仍可再次打开并复算，结果不变。
    assert client.post(f'/api/runs/{base}/replay').json() == old
    assert len(client.get('/api/runs').json()) == 2


def test_replay_same_pair_does_not_add_batch(client):
    run_id = make_run(client, [['P01', '1', STAMP, '甲:1:0:0:4:4', '甲', '']], [('P01', '16')])
    client.post(f'/api/runs/{run_id}/replay')
    client.post(f'/api/runs/{run_id}/replay')
    assert len(client.get('/api/runs').json()) == 1
