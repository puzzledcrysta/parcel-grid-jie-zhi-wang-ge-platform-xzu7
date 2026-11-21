import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '界址网格台'
SLUG = 'parcel-grid'
KEY = '地块复核单'
FIELDS = ('权属矩形', '目标业主')
ROLE = '自然资源所界址复核员'
UNIT = '平方米'
RULE_VERSION = 'parcel-grid-1.0'
SIGNATURE = '面积归属'
TABS = {'intake': '权证采信', 'contract': '测绘字段', 'quality': '异常权证', 'domain': '冲突测面', 'reconcile': '地籍清单', 'runs': '测面批次', 'review': '界址复核'}
