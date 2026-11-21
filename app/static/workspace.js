import {query, readInput, encodeInput} from './api.js';
import {el, evidence, table} from './table.js';

const byId = id => document.getElementById(id);
const settings = JSON.parse(byId('settings').textContent);
const links = [...document.querySelectorAll('[data-module]')];
const body = byId('grid-data');
const alert = byId('notice');
const live = byId('state');
const action = document.querySelector('#source button[type=submit]');
const topExport = byId('export');
let selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
let result = null;
let inputs = {};
let reviewVersion = 0;
let renderEpoch = 0;
let activeView = null;
let activeCompare = null;
const filter = byId('filter');
const differences = byId('differences');

function filterTable() {
  if (!activeView) return;
  const {columns, rows, stage} = activeView;
  const query = filter.value.trim().toLocaleLowerCase();
  const selected = rows.filter(row => {
    if (stage === 'reconcile' && differences.checked && row.code === 'MATCH') return false;
    return !query || [row.key,row.id,row.line,row.code,settings.reasons[row.code],row.detail,row.note,row.kind]
      .some(value => String(value ?? '').toLocaleLowerCase().includes(query));
  });
  byId('shown').textContent = `${selected.length} / ${rows.length}`;
  table(body, columns, selected);
}
filter.addEventListener('input', filterTable);
differences.addEventListener('change', filterTable);
const uploaded = new Map();

function notice(message, error = false) {
  alert.value = message;
  alert.classList.toggle('problem', error);
}

function tag(code) {
  return el('span', settings.reasons[code] || code, code === 'MATCH' ? 'state' : 'state problem');
}


function showEvidence(row) {
  const panel = byId('evidence-panel');
  const record = byId('evidence-key');
  const details = byId('signal');
  if (!row) {
    record.textContent = '';
    details.replaceChildren(el('p', '本批没有可采信记录', 'empty'));
    return;
  }
  record.textContent = row.key;
  const content = el('ol', undefined, panel.dataset.instrument);
  for (const item of row.proof) {
    const line = el('li');
    line.append(el('span', item.metric));
    line.append(el('strong', item.unit ? `${item.value} ${item.unit}` : item.value, 'measure'));
    content.append(line);
  }
  details.replaceChildren(content);
}

function inspect(row) {
  const button = el('button', '查看依据', 'btn');
  button.type = 'button';
  button.addEventListener('click', () => showEvidence(row));
  const raw = evidence('原始字段', row.raw);
  const cell = el('div');
  cell.append(button, raw);
  return cell;
}

function setRun(report) {
  result = report;
  byId('created').textContent = `${report.manifest.created.slice(0, 19).replace('T', ' ')} UTC`;
  showEvidence(report.accepted[0]);
  const id = result.manifest.run_id;
  byId('run-id').textContent = id.slice(0, 9);
  byId('run-id').title = id;
  topExport.hidden = false;
  topExport.href = `/api/export/${id}`;
  const values = {...result.counts, delta: result.book.delta, mismatched: result.book.mismatched};
  for (const cell of document.querySelectorAll('[data-count]')) cell.textContent = values[cell.dataset.count];
  live.textContent = `批次 ${id.slice(0, 9)} · ${result.balanced ? '记录已对齐' : '记录数不符'}`;
}

async function render() {
  const ticket = ++renderEpoch;
  const stage = selected;
  byId('phase').textContent = settings.tabs[stage];
  byId('review').hidden = true;
  for (const link of links) {
    if (link.dataset.module === stage) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  byId('compare-panel').hidden = stage !== 'compare';
  if (!result && stage !== 'compare') return;
  const id = result?.manifest.run_id;
  const raw = row => evidence('来源字段', row.raw);
  const key = [settings.key, 'key'];
  const line = ['行号', 'line', 'num'];
  try {
    let view, rows;
    if (stage === 'domain') {
      view = [key, [`可确认面积 · ${settings.unit}`, 'amount', 'num'], line, ['明细依据', inspect]];
      rows = result.accepted;
    } else if (stage === 'quality') {
      view = [key, line, ['判定', row => tag(row.code)], ['说明', 'detail'], ['字段', raw]];
      rows = [...result.quarantine, ...result.suppressed].sort((a,b) => a.line-b.line);
    } else if (stage === 'reconcile') {
      view = [key, ['实际', 'amount', 'num'], ['外部账', 'reference', 'num'], ['差值', 'delta', 'num'], ['外部行', 'book_line', 'num'], ['结论', row => tag(row.code)]];
      rows = [...result.book.rows].sort((a,b) => Number(a.code === 'MATCH') - Number(b.code === 'MATCH'));
    } else if (stage === 'intake') {
      const intake = await query('/api/intake', inputs);
      view = [line, ['分类', 'kind'], ['字段', raw]];
      rows = [...intake.rows.map(row => ({...row,kind:'完整记录'})), ...intake.rejected.map(row => ({...row,kind:'坏行'})),
              ...intake.blank_lines.map(line => ({line,kind:'空白行',raw:[]})),
              ...intake.header_lines.map(line => ({line,kind:'重复表头',raw:[]}))].sort((a,b) => a.line-b.line);
    } else if (stage === 'contract') {
      const contract = await query('/api/contract', inputs);
      view = [key, line, ['修订', 'revision', 'num'], ['来源时刻 UTC', 'time'], ['字段', row => evidence('归一值', Object.entries(row.fields).map(([k,v]) => `${k} · ${v}`))]];
      rows = contract.accepted;
    } else if (stage === 'runs') {
      const runs = await query('/api/runs');
      view = [['指纹','id'], ['创建 UTC','created'], ['操作', row => {
        const current = row.id === id;
        const button = el('button',current ? '复算当前批' : '打开此批','btn');
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            if (current) {
              setRun(await query(`/api/runs/${id}/replay`, {}));
              notice('复算已核对');
            } else {
              const [past, original] = await Promise.all([
                query(`/api/runs/${row.id}`), query(`/api/runs/${row.id}/source`),
              ]);
              inputs = original;
              setRun(past);
              notice('已打开历史批次');
              await render();
            }
          }
          catch (error) { notice(error.message, true); }
          finally { button.disabled = false; }
        });
        return button;
      }]];
      rows = runs;
    } else if (stage === 'compare') {
      const compare = await compareView(ticket);
      view = compare.columns;
      rows = compare.rows;
    } else {
      const timeline = await query(`/api/review/${id}`);
      view = [['版本','version','num'], ['结论','decision'], ['复核意见','note'], ['登记 UTC','changed']];
      rows = timeline;
      if (ticket === renderEpoch) {
        reviewVersion = timeline[0]?.version || 0;
        byId('review').hidden = false;
      }
    }
    if (ticket === renderEpoch) {
      if (activeView?.stage !== stage) filter.value = '';
      activeView = {stage, columns: view, rows};
      byId('tools').hidden = false;
      byId('only-differences').hidden = stage !== 'reconcile';
      filterTable();
    }
  } catch (error) {
    if (ticket === renderEpoch) notice(error.message, true);
  }
}

const COMPARE_STATUS = {added: '新批新增', removed: '新批退出', changed: '有变化', unchanged: '无变化'};
const SIDE_STATUS = {accepted: '可采信', quarantined: '已隔离', suppressed: '重传/替代', absent: '无此键'};

function shortId(id) {
  return id ? id.slice(0, 9) : '';
}

function pairCell(dim) {
  const cell = el('div');
  cell.append(el('span', `${dim.base ?? '—'} → ${dim.target ?? '—'}`, dim.changed ? 'pair pair--changed' : 'pair'));
  return cell;
}

function explainCell(row) {
  const cell = el('div');
  const unexplained = row.status !== 'unchanged' && !row.auto_explained && !row.note;
  cell.append(el('span', unexplained ? '解释不清' : (row.note || row.auto_explained ? '已解释' : '—'),
    unexplained ? 'state problem' : 'state'));
  const reasons = el('details');
  reasons.append(el('summary', '解释依据'));
  const list = el('ul');
  for (const text of row.reasons) list.append(el('li', text));
  if (row.note) list.append(el('li', `复核员补注：${row.note}`));
  if (!row.reasons.length && !row.note) list.append(el('li', '批次内无采信/隔离痕迹，需复核员补注'));
  reasons.append(list);
  cell.append(reasons);
  return cell;
}

function noteCell(row) {
  const cell = el('div');
  const editor = el('details');
  editor.append(el('summary', row.note ? '查看/修改补注' : '填写补注'));
  const area = el('textarea');
  area.rows = 2;
  area.maxLength = 500;
  area.value = row.note;
  const save = el('button', '保存补注', 'btn');
  save.type = 'button';
  save.addEventListener('click', async () => {
    save.disabled = true;
    try {
      await query(`/api/compare/${activeCompare.comparison_id}/notes/${encodeURIComponent(row.key)}`, {note: area.value});
      notice(`地块 ${row.key} 的补注已保存`);
      await render();
    } catch (error) { notice(error.message, true); save.disabled = false; }
  });
  editor.append(area, save);
  cell.append(editor);
  return cell;
}

async function compareView(ticket) {
  const runs = await query('/api/runs');
  const panel = byId('compare-panel');
  panel.hidden = false;
  const baseSelect = byId('compare-base');
  const targetSelect = byId('compare-target');
  const previous = [baseSelect.value, targetSelect.value];
  for (const [index, select] of [baseSelect, targetSelect].entries()) {
    select.replaceChildren(el('option', '选择批次…', ''));
    for (const item of runs) {
      select.append(new Option(`${shortId(item.id)} · ${item.created.slice(0, 19).replace('T', ' ')} UTC`, item.id));
    }
    if (runs.some(item => item.id === previous[index])) select.value = previous[index];
  }
  if (!baseSelect.dataset.filled) {
    if (result) {
      targetSelect.value = result.manifest.run_id;
      const older = runs.find(item => item.id !== result.manifest.run_id);
      if (older) baseSelect.value = older.id;
    }
    baseSelect.dataset.filled = '1';
  }
  byId('compare-form').onsubmit = async event => {
    event.preventDefault();
    if (!baseSelect.value || !targetSelect.value) return notice('请先选择新旧两个批次', true);
    try {
      const report = await query('/api/compare', {base_run_id: baseSelect.value, target_run_id: targetSelect.value});
      activeCompare = report;
      notice('对账批次已生成（重跑同一对批次不会新增记录）');
      await render();
    } catch (error) { notice(error.message, true); }
  };
  const history = await query('/api/compare');
  const historyList = byId('compare-history');
  historyList.replaceChildren();
  for (const item of history) {
    const link = el('button', `${shortId(item.base_run_id)} → ${shortId(item.target_run_id)}`, 'btn');
    link.type = 'button';
    link.addEventListener('click', async () => {
      activeCompare = await query(`/api/compare/${item.id}`);
      notice('已打开历史对账批次');
      await render();
    });
    historyList.append(link);
  }
  if (!activeCompare || ticket !== renderEpoch) {
    return {rows: [], columns: []};
  }
  const report = activeCompare;
  byId('compare-meta').textContent =
    `旧批 ${shortId(report.base.run_id)} → 新批 ${shortId(report.target.run_id)} · ` +
    `新增 ${report.counts.added} · 退出 ${report.counts.removed} · 变化 ${report.counts.changed} · ` +
    `无变化 ${report.counts.unchanged} · 解释不清 ${report.unexplained_count} · ` +
    `外账总差 ${report.book_summary.base} → ${report.book_summary.target}`;
  const statusCell = row => {
    const cell = el('div');
    cell.append(el('span', COMPARE_STATUS[row.status], row.status === 'unchanged' ? 'state' : 'state problem'));
    cell.append(el('small', `${SIDE_STATUS[row.base_status]} → ${SIDE_STATUS[row.target_status]}`));
    return cell;
  };
  return {
    rows: report.rows,
    columns: [
      [settings.key, 'key'],
      ['地块状态', statusCell],
      ['采信修订（旧 → 新）', row => pairCell(row.dimensions[0])],
      [`可确认面积 · ${settings.unit}`, row => pairCell(row.dimensions[1])],
      ['争议冻结（旧 → 新）', row => pairCell(row.dimensions[2])],
      ['外部账记录值（旧 → 新）', row => pairCell(row.dimensions[3])],
      ['外账差异（旧 → 新）', row => pairCell(row.dimensions[4])],
      ['解释', explainCell],
      ['复核补注', noteCell],
    ],
  };
}

window.addEventListener('hashchange', () => {
  selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
  render();
});
byId('sample').addEventListener('click', async () => {
  const paths = ['shift', 'external'];
  try {
    const responses = await Promise.all(paths.map(name => fetch(`/api/samples/${name}`)));
    if (responses.some(item => !item.ok)) throw Error('样例暂时不可用');
    const files = await Promise.all(responses.map(item => item.arrayBuffer()));
    for (const [index,name] of ['source','book'].entries()) {
      const decoded = new TextDecoder('utf-8').decode(files[index]);
      byId(`${name}-csv`).value = decoded;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes:files[index]});
    }
    byId('source-file').value = '';
    byId('book-file').value = '';
    document.querySelector('#source details').open = true;
    notice('样例已载入');
  } catch (error) { notice(error.message, true); }
});
for (const name of ['source','book']) {
  byId(`${name}-file`).addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    action.disabled = true;
    try {
      const [text,bytes] = await readInput(file);
      byId(`${name}-csv`).value = text;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes});
      notice(`已读取 ${file.name}`);
    } catch (error) {
      event.target.value = '';
      notice(error.message, true);
    } finally { action.disabled = false; }
  });
}
byId('source').addEventListener('submit', async event => {
  event.preventDefault();
  const candidate = {};
  for (const [control,name] of [['source','data'],['book','book']]) {
    const text = byId(`${control}-csv`).value;
    const original = uploaded.get(control);
    if (original && text === original.text) candidate[`${name}_base64`] = encodeInput(original.bytes);
    else if (text.length || original) candidate[name] = text;
  }
  action.disabled = true;
  ++renderEpoch;
  notice('计算中');
  try {
    const report = await query('/api/runs', candidate);
    inputs = candidate;
    setRun(report);
    notice('批次已计算');
    await render();
  } catch (error) { notice(error.message, true); }
  finally { action.disabled = false; }
});
byId('review').addEventListener('submit', async event => {
  event.preventDefault();
  const id = result.manifest.run_id;
  const note = byId('review-note');
  try {
    await query(`/api/review/${id}`, {version: reviewVersion, decision: byId('decision').value, note: note.value});
    notice('复核已登记');
    note.value = '';
    await render();
  } catch (error) {
    notice(error.message, true);
    if (error.status === 409) await render();
  }
});
render();
