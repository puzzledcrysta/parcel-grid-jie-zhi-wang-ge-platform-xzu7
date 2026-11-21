from collections import defaultdict
from decimal import Decimal as D
from app.errors import DataError
from .values import whole, number, parts


def evaluate(row):
    rights = []
    entries = parts(row['权属矩形'])
    if not 1 <= len(entries) <= 60:
        raise DataError('GRID_LIMIT','要求 1 至 60 个矩形权证')
    for item in entries:
        segments = item.split(':')
        if len(segments) != 6 or not segments[0]:
            raise DataError('GRID_FORMAT','矩形须含业主、等级和四个坐标')
        owner,rank,*coordinates = segments
        x0,y0,x1,y1 = [number(piece,-100000,100000) for piece in coordinates]
        if x0 >= x1 or y0 >= y1:
            raise DataError('GRID_SPAN', f'{owner} 权证边界无正面积')
        rights.append((x0,y0,x1,y1,whole(rank,1,10),owner))
    x_steps = sorted({x for a,_,b,_,_,_ in rights for x in (a,b)})
    areas = defaultdict(D)
    disputed = D(0)
    for lower, upper in zip(x_steps,x_steps[1:]):
        active = [r for r in rights if r[0]<=lower and upper<=r[2]]
        y_steps = sorted({y for _,a,_,b,_,_ in active for y in (a,b)})
        for floor, ceiling in zip(y_steps,y_steps[1:]):
            contenders = [(rank,owner) for _,a,_,b,rank,owner in active if a<=floor and ceiling<=b]
            if not contenders:
                continue
            area = (upper-lower)*(ceiling-floor)
            priority = max(rank for rank,_ in contenders)
            owners = {owner for rank,owner in contenders if rank==priority}
            if len(owners) == 1:
                areas[owners.pop()] += area
            else:
                disputed += area
    proof = [(f'{owner} 可确认',area,'平方米') for owner,area in sorted(areas.items())]
    proof += [('同级争议',disputed,'平方米'),('覆盖并集',sum(areas.values())+disputed,'平方米')]
    return areas[row['目标业主']], proof
