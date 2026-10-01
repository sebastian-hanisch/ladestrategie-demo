import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modell import (
    ETA_KALT,
    ETA_WARM,
    Fahrzeug,
    Segment,
    Strecke,
    ladewirkungsgrad,
    temperaturanstieg_durch_heizen,
    verbrauch_kwh_km,
)


def test_verbrauch_bei_referenztemperatur_ist_basisverbrauch():
    assert verbrauch_kwh_km(0.32, 20.0) == 0.32


def test_verbrauch_steigt_bei_kaelte():
    basis = 0.32
    assert verbrauch_kwh_km(basis, 0.0) > verbrauch_kwh_km(basis, 10.0) > verbrauch_kwh_km(basis, 20.0)


def test_verbrauch_waermer_als_referenz_aendert_sich_nicht():
    """Kein Kuehlbonus oberhalb der Referenztemperatur - das Modell deckt nur den Kaelteeffekt ab."""
    assert verbrauch_kwh_km(0.32, 30.0) == verbrauch_kwh_km(0.32, 20.0)


def test_verbrauch_bei_aaa_kalibrierungspunkt():
    """AAA-Wintertest 2025: bei -6,6 °C im Schnitt 35,6 % Mehrverbrauch."""
    basis = 0.32
    erwartet = basis * 1.356
    assert abs(verbrauch_kwh_km(basis, -6.6) - erwartet) < 1e-9


def test_ladewirkungsgrad_monoton_in_der_temperatur():
    temps = [-20, -10, 0, 10, 20]
    werte = [ladewirkungsgrad(t) for t in temps]
    assert werte == sorted(werte)


def test_ladewirkungsgrad_an_den_eckwerten():
    assert ladewirkungsgrad(20.0) == ETA_WARM
    assert ladewirkungsgrad(-20.0) == ETA_KALT
    assert ladewirkungsgrad(30.0) == ETA_WARM, "oberhalb des warmen Eckwerts wird geklemmt"
    assert ladewirkungsgrad(-30.0) == ETA_KALT, "unterhalb des kalten Eckwerts wird geklemmt"


def test_heizen_erhoeht_temperatur_und_ist_monoton():
    assert temperaturanstieg_durch_heizen(0.0) == 0.0
    assert temperaturanstieg_durch_heizen(1.0) > temperaturanstieg_durch_heizen(0.5) > 0.0


def test_strecke_prueft_laenge_von_namen_und_segmenten():
    try:
        Strecke(namen=["Start", "Ziel"], segmente=[])
        assert False, "sollte ValueError werfen"
    except ValueError:
        pass


def test_strecke_distanz_und_ladestationen():
    s = Strecke(
        namen=["Start", "A", "B", "Ziel"],
        segmente=[Segment(100, 5.0), Segment(120, 5.0), Segment(80, 5.0)],
    )
    assert s.distanz_gesamt_km == 300
    assert s.ladestationen == ["A", "B"]


def test_fahrzeug_ist_ein_einfaches_datenobjekt():
    f = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80)
    assert f.reserve_kwh == 0.0
