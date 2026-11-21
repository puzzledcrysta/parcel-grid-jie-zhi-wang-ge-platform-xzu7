from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_shared_and_covered(cases):
    # TRAP-19
    actual, proof = evaluate(cases['shared_and_covered'])
    assert actual == Decimal('50')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['同级争议'])) == Decimal('35')


def test_same_owner_union(cases):
    actual, proof = evaluate(cases['same_owner_union'])
    assert actual == Decimal('13')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['覆盖并集'])) == Decimal('13')


def test_exact_touch(cases):
    # TRAP-23
    actual, proof = evaluate(cases['exact_touch'])
    assert actual == Decimal('4')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['同级争议'])) == Decimal('0')


def test_negative_coordinates(cases):
    actual, proof = evaluate(cases['negative_coordinates'])
    assert actual == Decimal('6.25')
    assert proof


def test_concentric(cases):
    actual, proof = evaluate(cases['concentric'])
    assert actual == Decimal('16')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['甲 可确认'])) == Decimal('16')


def test_contested_all(cases):
    actual, proof = evaluate(cases['contested_all'])
    assert actual == Decimal('0')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['同级争议'])) == Decimal('20')


def test_zero_rectangle(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['zero_rectangle'])
    assert error.value.code == 'GRID_SPAN'


def test_backward_bounds(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['backward_bounds'])
    assert error.value.code == 'GRID_SPAN'


def test_bad_rank(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['bad_rank'])
    assert error.value.code == 'RANGE'
