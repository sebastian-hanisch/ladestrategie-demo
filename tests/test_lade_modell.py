import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lade_modell import (
    ETA_KALT,
    ETA_WARM,
    REFERENZ_KAPAZITAET_KWH,
    WAERMEKAPAZITAET_KWH_PRO_GRAD,
    WAERMEVERLUST_ZEITKONSTANTE_H,
    Fahrzeug,
    Segment,
    Strecke,
    batterietemperatur_nach_heizen,
    ladewirkungsgrad,
    verbrauch_kwh_km,
    waermekapazitaet_kwh_pro_grad,
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


def test_heizen_ohne_dauer_aendert_die_temperatur_nicht():
    assert batterietemperatur_nach_heizen(-10.0, 0.0, heizleistung_kw=6.0) == -10.0


def test_heizen_erhoeht_temperatur_und_ist_monoton_in_der_dauer():
    t_kurz = batterietemperatur_nach_heizen(-10.0, 0.1, heizleistung_kw=6.0)
    t_mittel = batterietemperatur_nach_heizen(-10.0, 0.5, heizleistung_kw=6.0)
    t_lang = batterietemperatur_nach_heizen(-10.0, 2.0, heizleistung_kw=6.0)
    assert -10.0 < t_kurz < t_mittel < t_lang


def test_heizen_naehert_sich_einer_gleichgewichtstemperatur_an_statt_unbegrenzt_zu_steigen():
    """Wärmeverlust an die Umgebung bremst den Anstieg - die Temperatur überschreitet nie
    Außentemperatur + Heizrate/Verlustkonstante, auch nicht bei sehr langer Heizdauer."""
    heizrate_pro_h = 6.0 * 0.9 / 0.125
    grenze = -10.0 + heizrate_pro_h * WAERMEVERLUST_ZEITKONSTANTE_H
    t_sehr_lang = batterietemperatur_nach_heizen(-10.0, 100.0, heizleistung_kw=6.0)
    assert t_sehr_lang < grenze
    assert t_sehr_lang > grenze - 1.0, "sollte sich der Grenze nach so langer Zeit praktisch annaehern"


def test_mehr_heizleistung_erreicht_dieselbe_temperatur_schneller():
    dauer = 0.3
    t_schwach = batterietemperatur_nach_heizen(-10.0, dauer, heizleistung_kw=3.0)
    t_stark = batterietemperatur_nach_heizen(-10.0, dauer, heizleistung_kw=8.0)
    assert t_stark > t_schwach


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


# ---------- Wärmekapazität wächst mit der Batteriekapazität (Fahrzeugtypen) ----------


def test_waermekapazitaet_des_referenzpakets_entspricht_der_konstante():
    assert waermekapazitaet_kwh_pro_grad(REFERENZ_KAPAZITAET_KWH) == WAERMEKAPAZITAET_KWH_PRO_GRAD


def test_waermekapazitaet_ist_proportional_zur_kapazitaet():
    assert waermekapazitaet_kwh_pro_grad(160.0) == 2 * waermekapazitaet_kwh_pro_grad(80.0)
    assert Fahrzeug(kapazitaet_kwh=620, basisverbrauch_kwh_km=1.2, start_soc_kwh=620).waermekapazitaet_kwh_pro_grad == waermekapazitaet_kwh_pro_grad(620.0)


def test_standardaufruf_bleibt_das_80_kwh_referenzpaket():
    """Abwärtskompatibel: ohne Wärmekapazitäts-Argument rechnet die Funktion wie vor der Fahrzeugtypen."""
    assert batterietemperatur_nach_heizen(-10.0, 0.5, 6.0) == batterietemperatur_nach_heizen(
        -10.0, 0.5, 6.0, waermekapazitaet_kwh_pro_grad(80.0)
    )


def test_groesseres_paket_erwaermt_sich_bei_gleicher_heizleistung_langsamer():
    klein = batterietemperatur_nach_heizen(-10.0, 0.5, 6.0, waermekapazitaet_kwh_pro_grad(80.0))
    gross = batterietemperatur_nach_heizen(-10.0, 0.5, 6.0, waermekapazitaet_kwh_pro_grad(620.0))
    assert klein > gross > -10.0
