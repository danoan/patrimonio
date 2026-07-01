import pytest
from app.money import fmt_eur, fmt_pct, fmt_usd

NBSP = "\xa0"  # non-breaking space (before € and %)
NNBSP = " "  # narrow no-break space (thousands separator)


@pytest.mark.unit
def test_fmt_eur_zero() -> None:
    assert fmt_eur(0) == f"0,00{NBSP}€"


@pytest.mark.unit
def test_fmt_eur_positive() -> None:
    assert fmt_eur(100) == f"1,00{NBSP}€"


@pytest.mark.unit
def test_fmt_eur_thousands() -> None:
    result = fmt_eur(1_234_56)
    assert f"1{NNBSP}234,56{NBSP}€" == result


@pytest.mark.unit
def test_fmt_eur_negative() -> None:
    result = fmt_eur(-100)
    assert result == f"-1,00{NBSP}€"


@pytest.mark.unit
def test_fmt_usd_zero() -> None:
    assert fmt_usd(0) == "$0.00"


@pytest.mark.unit
def test_fmt_usd_positive() -> None:
    assert fmt_usd(100) == "$1.00"


@pytest.mark.unit
def test_fmt_usd_thousands() -> None:
    result = fmt_usd(1_234_56)
    assert result == "$1,234.56"


@pytest.mark.unit
def test_fmt_usd_negative() -> None:
    result = fmt_usd(-100)
    assert result.startswith("-")
    assert "$1.00" in result


@pytest.mark.unit
def test_fmt_pct_default() -> None:
    result = fmt_pct(0.1234)
    assert f"12,3{NBSP}%" == result


@pytest.mark.unit
def test_fmt_pct_zero() -> None:
    result = fmt_pct(0.0)
    assert f"0,0{NBSP}%" == result


@pytest.mark.unit
def test_fmt_pct_one() -> None:
    result = fmt_pct(1.0)
    assert f"100,0{NBSP}%" == result
