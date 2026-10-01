import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modell import Fahrzeug, Segment, Strecke, ladewirkungsgrad
from planung import _kosten_batch, kosten_bei_stopp, plane_route


def _einfache_strecke(distanzen_temps: list[tuple[float, float]], namen: list[str] | None = None) -> Strecke:
    n = namen or (["Start"] + [f"Halt {i + 1}" for i in range(len(distanzen_temps) - 1)] + ["Ziel"])
    return Strecke(namen=n, segmente=[Segment(d, t) for d, t in distanzen_temps])


def test_kein_ladestopp_noetig_wenn_akku_reicht():
    strecke = _einfache_strecke([(100, 20.0)])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80)
    ergebnis = plane_route(strecke, fahrzeug)
    assert ergebnis.erreichbar
    assert ergebnis.netzenergie_gesamt_kwh == 0.0
    assert ergebnis.stopps == []
    assert ergebnis.ankunft_ziel_soc_kwh > 0


def test_unerreichbar_ohne_ladestationen():
    strecke = _einfache_strecke([(500, 20.0)])
    fahrzeug = Fahrzeug(kapazitaet_kwh=60, basisverbrauch_kwh_km=0.32, start_soc_kwh=60)
    ergebnis = plane_route(strecke, fahrzeug)
    assert not ergebnis.erreichbar
    assert ergebnis.netzenergie_gesamt_kwh == float("inf")


def test_reserve_wird_am_ziel_eingehalten():
    strecke = _einfache_strecke([(100, 20.0), (50, 20.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80, reserve_kwh=10)
    ergebnis = plane_route(strecke, fahrzeug, soc_aufloesung=400)
    assert ergebnis.erreichbar
    assert ergebnis.ankunft_ziel_soc_kwh >= fahrzeug.reserve_kwh - 1e-6


def test_heizen_erlaubt_ist_nie_schlechter_als_verboten():
    """heiz_soc=0 ist immer eine zulaessige Wahl innerhalb der Heizsuche - Heizen kann also nur
    helfen oder neutral sein, nie zu einer schlechteren Loesung zwingen."""
    strecke = _einfache_strecke([(120, -15.0), (120, -15.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80)
    mit_heizen = plane_route(strecke, fahrzeug, heizen_erlaubt=True, soc_aufloesung=300)
    ohne_heizen = plane_route(strecke, fahrzeug, heizen_erlaubt=False, soc_aufloesung=300)
    assert mit_heizen.erreichbar and ohne_heizen.erreichbar
    assert mit_heizen.netzenergie_gesamt_kwh <= ohne_heizen.netzenergie_gesamt_kwh + 1e-6


def test_heizen_lohnt_sich_bei_starker_kaelte_und_grossem_ladebedarf():
    """Bei sehr kalten Temperaturen und einem Stopp, der viel nachladen muss, sollte die Suche
    tatsaechlich heizen (nicht nur theoretisch duerfen) - sonst waere die Heizoption in der Praxis nie
    sichtbar."""
    strecke = _einfache_strecke([(140, -18.0), (140, -18.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=100, basisverbrauch_kwh_km=0.4, start_soc_kwh=100)
    ergebnis = plane_route(strecke, fahrzeug, heizen_erlaubt=True, soc_aufloesung=300)
    assert ergebnis.erreichbar
    assert any(s.heiz_soc_kwh > 0.01 for s in ergebnis.stopps)


def test_waermere_strecke_braucht_nicht_mehr_netzenergie_als_kaeltere():
    kalt = _einfache_strecke([(130, -10.0), (130, -10.0)], namen=["Start", "Säule", "Ziel"])
    warm = _einfache_strecke([(130, 15.0), (130, 15.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=90, basisverbrauch_kwh_km=0.35, start_soc_kwh=90)
    e_kalt = plane_route(kalt, fahrzeug, soc_aufloesung=300)
    e_warm = plane_route(warm, fahrzeug, soc_aufloesung=300)
    assert e_kalt.erreichbar and e_warm.erreichbar
    assert e_warm.netzenergie_gesamt_kwh <= e_kalt.netzenergie_gesamt_kwh + 1e-6


def test_energiebilanz_an_jedem_stopp_ist_konsistent():
    strecke = _einfache_strecke([(100, -12.0), (100, -12.0), (100, -12.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.35, start_soc_kwh=80)
    ergebnis = plane_route(strecke, fahrzeug, soc_aufloesung=300)
    assert ergebnis.erreichbar
    for s in ergebnis.stopps:
        soc_nach_heizen = s.ankunft_soc_kwh - s.heiz_soc_kwh
        assert soc_nach_heizen >= -1e-6
        assert abs(soc_nach_heizen + s.geladen_kwh - s.abfahrt_soc_kwh) < 1e-6
        eta_erwartet = ladewirkungsgrad(s.batterietemperatur_beim_laden_c)
        if s.geladen_kwh > 1e-9:
            assert abs(s.netzenergie_kwh - s.geladen_kwh / eta_erwartet) < 1e-6


def test_feinere_diskretisierung_aendert_ergebnis_kaum():
    """Konvergenzpruefung: 200 vs. 1000 SOC-Stufen duerfen sich nur im Diskretisierungsrauschen
    unterscheiden, nicht grundsaetzlich."""
    strecke = _einfache_strecke([(130, -8.0), (110, -8.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=90, basisverbrauch_kwh_km=0.33, start_soc_kwh=90)
    grob = plane_route(strecke, fahrzeug, soc_aufloesung=300)
    fein = plane_route(strecke, fahrzeug, soc_aufloesung=2000)
    assert grob.erreichbar and fein.erreichbar
    abweichung = abs(grob.netzenergie_gesamt_kwh - fein.netzenergie_gesamt_kwh)
    referenz = max(fein.netzenergie_gesamt_kwh, 1.0)
    assert abweichung / referenz < 0.03, f"{abweichung=} {referenz=}"


def test_kosten_bei_stopp_ohne_ladebedarf_ist_null():
    ergebnis = kosten_bei_stopp(ankunft_soc_kwh=50, abfahrt_soc_kwh=40, aussentemperatur_c=0.0, heizen_erlaubt=True)
    assert ergebnis == (0.0, 0.0)


def test_kosten_bei_stopp_ohne_heizerlaubnis_entspricht_direkter_formel():
    eta = ladewirkungsgrad(-10.0)
    ergebnis = kosten_bei_stopp(ankunft_soc_kwh=10, abfahrt_soc_kwh=40, aussentemperatur_c=-10.0, heizen_erlaubt=False)
    assert ergebnis is not None
    netzenergie, heiz_soc = ergebnis
    assert heiz_soc == 0.0
    assert abs(netzenergie - 30 / eta) < 1e-9


def test_kosten_batch_stimmt_mit_der_einzelnen_suche_ueberein():
    """Die vektorisierte Batch-Suche (Performance) muss dasselbe liefern wie die einzelne Suche je
    Abfahrt-Kandidat - nur eben alle auf einmal."""
    abfahrt_kandidaten = np.array([10.0, 25.0, 40.0, 55.5, 70.0])
    for heizen_erlaubt in (True, False):
        kosten_arr, heiz_arr = _kosten_batch(18.0, abfahrt_kandidaten, -12.0, heizen_erlaubt)
        for i, abfahrt in enumerate(abfahrt_kandidaten):
            einzeln = kosten_bei_stopp(18.0, float(abfahrt), -12.0, heizen_erlaubt)
            assert einzeln is not None
            netzenergie_einzeln, heiz_einzeln = einzeln
            assert abs(kosten_arr[i] - netzenergie_einzeln) < 1e-6, (heizen_erlaubt, abfahrt)
            assert abs(heiz_arr[i] - heiz_einzeln) < 1e-6, (heizen_erlaubt, abfahrt)
