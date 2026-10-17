"""Tests der Ladekurve und der Ladezeit (lade_ladekurve.py): Form der Kurve, Temperaturfaktor, geschlossene
Stammfunktion gegen numerische Integration, Additivität, Pauschale."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lade_ladekurve import (  # noqa: E402
    LADELEISTUNG_FAKTOR_KALT,
    TAPER_BEGINN_ANTEIL,
    TAPER_ENDLEISTUNG_ANTEIL,
    ladeleistung_soc_faktor,
    ladeleistung_temperaturfaktor,
    ladezeit_h,
    ladezeit_integral,
)


def test_leistungskurve_ist_bis_zum_taper_beginn_voll_und_faellt_danach_auf_den_endwert():
    assert ladeleistung_soc_faktor(0.0) == 1.0
    assert ladeleistung_soc_faktor(TAPER_BEGINN_ANTEIL) == 1.0
    assert ladeleistung_soc_faktor(1.0) == pytest.approx(TAPER_ENDLEISTUNG_ANTEIL)
    assert ladeleistung_soc_faktor(0.9) == pytest.approx((1.0 + TAPER_ENDLEISTUNG_ANTEIL) / 2)


def test_leistungskurve_faellt_monoton():
    x = np.linspace(0.0, 1.0, 201)
    f = ladeleistung_soc_faktor(x)
    assert np.all(np.diff(f) <= 1e-12)
    assert np.all(f >= TAPER_ENDLEISTUNG_ANTEIL - 1e-12)


def test_temperaturfaktor_an_den_eckwerten_und_monoton():
    assert ladeleistung_temperaturfaktor(20.0) == pytest.approx(1.0)
    assert ladeleistung_temperaturfaktor(35.0) == pytest.approx(1.0)  # oberhalb der Referenz keine Beschleunigung
    assert ladeleistung_temperaturfaktor(-20.0) == pytest.approx(LADELEISTUNG_FAKTOR_KALT)
    assert ladeleistung_temperaturfaktor(-40.0) == pytest.approx(LADELEISTUNG_FAKTOR_KALT)
    assert ladeleistung_temperaturfaktor(0.0) == pytest.approx(2.0 / 3.0)
    t = np.linspace(-30.0, 30.0, 121)
    assert np.all(np.diff(ladeleistung_temperaturfaktor(t)) >= -1e-12)


def test_stammfunktion_ist_bis_zum_taper_beginn_linear():
    assert ladezeit_integral(0.0) == 0.0
    assert ladezeit_integral(0.5) == pytest.approx(0.5)
    assert ladezeit_integral(TAPER_BEGINN_ANTEIL) == pytest.approx(TAPER_BEGINN_ANTEIL)


def test_stammfunktion_stimmt_mit_numerischer_integration_von_eins_durch_leistung_ueberein():
    """Unabhängiger Gegencheck: Mittelpunktsregel über 1/f(x) statt der geschlossenen Formel."""
    for ziel in (0.3, 0.8, 0.9, 1.0):
        n = 20000
        mitten = (np.arange(n) + 0.5) * ziel / n
        numerisch = float(np.sum(1.0 / ladeleistung_soc_faktor(mitten)) * ziel / n)
        assert ladezeit_integral(ziel) == pytest.approx(numerisch, rel=1e-6)


def test_ladezeit_ist_additiv_ueber_teilintervalle():
    kwargs = dict(kapazitaet_kwh=80.0, ladeleistung_kw=100.0, batterietemperatur_c=5.0)
    ganz = ladezeit_h(10.0, 78.0, **kwargs)
    geteilt = ladezeit_h(10.0, 40.0, **kwargs) + ladezeit_h(40.0, 65.0, **kwargs) + ladezeit_h(65.0, 78.0, **kwargs)
    assert ganz == pytest.approx(geteilt, rel=1e-12)


def test_ladezeit_im_vollen_leistungsbereich_ist_energie_durch_leistung():
    # 10 -> 60 kWh bei 80 kWh Kapazität und 20 °C: bleibt unter 80 %, also volle Leistung
    assert ladezeit_h(10.0, 60.0, 80.0, 100.0, 20.0) == pytest.approx(50.0 / 100.0)


def test_ladezeit_ueber_den_taper_hinaus_dauert_laenger_als_bei_voller_leistung():
    assert ladezeit_h(60.0, 80.0, 80.0, 100.0, 20.0) > 20.0 / 100.0


def test_kaelte_verlaengert_die_ladezeit_auf_das_dreifache():
    warm = ladezeit_h(10.0, 60.0, 80.0, 100.0, 20.0)
    kalt = ladezeit_h(10.0, 60.0, 80.0, 100.0, -20.0)
    assert kalt == pytest.approx(3.0 * warm)


def test_doppelte_ladeleistung_halbiert_die_ladezeit():
    langsam = ladezeit_h(10.0, 70.0, 80.0, 60.0, 0.0)
    schnell = ladezeit_h(10.0, 70.0, 80.0, 120.0, 0.0)
    assert schnell == pytest.approx(langsam / 2.0)


def test_pauschale_faellt_nur_bei_tatsaechlichem_laden_an():
    assert ladezeit_h(30.0, 30.0, 80.0, 100.0, 0.0, pauschale_h=0.1) == 0.0
    assert ladezeit_h(30.0, 25.0, 80.0, 100.0, 0.0, pauschale_h=0.1) == 0.0
    mit = ladezeit_h(30.0, 31.0, 80.0, 100.0, 0.0, pauschale_h=0.1)
    ohne = ladezeit_h(30.0, 31.0, 80.0, 100.0, 0.0)
    assert mit == pytest.approx(ohne + 0.1)


def test_arrays_werden_gebroadcastet_und_stimmen_mit_den_einzelwerten_ueberein():
    von = np.array([[5.0], [20.0], [40.0]])  # (3, 1)
    bis = np.array([[30.0, 60.0, 78.0, 80.0]])  # (1, 4)
    temp = np.array([[-10.0], [0.0], [15.0]])  # (3, 1)
    matrix = ladezeit_h(von, bis, 80.0, 90.0, temp, pauschale_h=0.05)
    assert matrix.shape == (3, 4)
    for i in range(3):
        for j in range(4):
            einzeln = ladezeit_h(float(von[i, 0]), float(bis[0, j]), 80.0, 90.0, float(temp[i, 0]), pauschale_h=0.05)
            assert matrix[i, j] == pytest.approx(einzeln)
