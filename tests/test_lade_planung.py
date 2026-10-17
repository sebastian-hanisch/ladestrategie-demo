import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lade_constants import FAHRZEUGTYPEN, PRESETS
from lade_ladekurve import ladezeit_h
from lade_modell import Fahrzeug, Segment, Strecke, ladewirkungsgrad
from lade_szenario import baue_strecke
from lade_planung import _kosten_batch, kosten_bei_stopp, plane_route


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
    """heiz_dauer=0 ist immer eine zulaessige Wahl innerhalb der Heizsuche - Heizen kann also nur
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
    sichtbar. Niedrige Geschwindigkeit gibt der Heizung genug Zeit im Abschnitt vor der Saeule."""
    strecke = _einfache_strecke([(140, -18.0), (140, -18.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=100, basisverbrauch_kwh_km=0.4, start_soc_kwh=100, geschwindigkeit_kmh=70)
    ergebnis = plane_route(strecke, fahrzeug, heizen_erlaubt=True, soc_aufloesung=300)
    assert ergebnis.erreichbar
    assert any(s.heiz_dauer_h > 0.01 for s in ergebnis.stopps)


def test_mehr_heizzeit_durch_niedrigere_geschwindigkeit_erlaubt_mehr_heizen():
    """Weniger Geschwindigkeit heisst mehr Fahrzeit im Abschnitt, also mehr moegliche Heizdauer. Bei
    40 km/h ist die Heizdauer nicht durch die Zeit begrenzt (0,92 h von 3,5 h verfuegbaren) - der
    Vergleich braucht also eine Geschwindigkeit, bei der die Zeit tatsaechlich bindet (600 km/h ->
    nur 0,23 h verfuegbar, deutlich weniger als die bei viel Zeit gewaehlten 0,92 h), sonst sind beide
    Faelle praktisch gleich und der Vergleich zeigt nur Diskretisierungsrauschen."""
    strecke = _einfache_strecke([(140, -18.0), (140, -18.0)], namen=["Start", "Säule", "Ziel"])
    langsam = Fahrzeug(kapazitaet_kwh=100, basisverbrauch_kwh_km=0.4, start_soc_kwh=100, geschwindigkeit_kmh=40)
    schnell = Fahrzeug(kapazitaet_kwh=100, basisverbrauch_kwh_km=0.4, start_soc_kwh=100, geschwindigkeit_kmh=600)
    e_langsam = plane_route(strecke, langsam, soc_aufloesung=300)
    e_schnell = plane_route(strecke, schnell, soc_aufloesung=300)
    assert e_langsam.erreichbar and e_schnell.erreichbar
    assert e_langsam.netzenergie_gesamt_kwh < e_schnell.netzenergie_gesamt_kwh


def test_keine_heizleistung_heisst_kein_heizen_moeglich():
    strecke = _einfache_strecke([(140, -18.0), (140, -18.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=100, basisverbrauch_kwh_km=0.4, start_soc_kwh=100, heizleistung_kw=0.0)
    ergebnis = plane_route(strecke, fahrzeug, heizen_erlaubt=True, soc_aufloesung=300)
    assert ergebnis.erreichbar
    assert all(s.heiz_dauer_h == 0.0 for s in ergebnis.stopps)


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
        assert abs(s.heiz_energie_kwh - fahrzeug.heizleistung_kw * s.heiz_dauer_h) < 1e-6
        soc_nach_heizen = s.ankunft_soc_kwh - s.heiz_energie_kwh
        assert soc_nach_heizen >= -1e-6
        assert abs(soc_nach_heizen + s.geladen_kwh - s.abfahrt_soc_kwh) < 1e-6
        eta_erwartet = ladewirkungsgrad(s.batterietemperatur_beim_laden_c)
        if s.geladen_kwh > 1e-9:
            assert abs(s.netzenergie_kwh - s.geladen_kwh / eta_erwartet) < 1e-6


def test_feinere_diskretisierung_aendert_ergebnis_kaum():
    """Konvergenzpruefung: 300 vs. 2000 SOC-Stufen duerfen sich nur im Diskretisierungsrauschen
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
    ergebnis = kosten_bei_stopp(ankunft_soc_kwh=50, abfahrt_soc_kwh=40, aussentemperatur_c=0.0, segment_zeit_h=1.0, heizleistung_kw=6.0, heizen_erlaubt=True)
    assert ergebnis == (0.0, 0.0, 0.0)


def test_kosten_bei_stopp_ohne_heizerlaubnis_entspricht_direkter_formel():
    eta = ladewirkungsgrad(-10.0)
    ergebnis = kosten_bei_stopp(ankunft_soc_kwh=10, abfahrt_soc_kwh=40, aussentemperatur_c=-10.0, segment_zeit_h=1.0, heizleistung_kw=6.0, heizen_erlaubt=False)
    assert ergebnis is not None
    netzenergie, heiz_dauer, _ladezeit = ergebnis
    assert heiz_dauer == 0.0
    assert abs(netzenergie - 30 / eta) < 1e-9


def test_kosten_bei_stopp_begrenzt_heizdauer_auf_verfuegbare_zeit():
    """Bei sehr kurzer Fahrzeit vor dem Stopp kann nicht beliebig lange geheizt werden - die
    erreichte Temperatur bleibt entsprechend niedriger als bei viel Zeit."""
    kurz = kosten_bei_stopp(ankunft_soc_kwh=50, abfahrt_soc_kwh=90, aussentemperatur_c=-15.0, segment_zeit_h=0.02, heizleistung_kw=6.0, heizen_erlaubt=True)
    lang = kosten_bei_stopp(ankunft_soc_kwh=50, abfahrt_soc_kwh=90, aussentemperatur_c=-15.0, segment_zeit_h=2.0, heizleistung_kw=6.0, heizen_erlaubt=True)
    assert kurz is not None and lang is not None
    assert kurz[1] <= 0.02 + 1e-9
    assert lang[0] <= kurz[0] + 1e-6, "mehr verfuegbare Heizzeit darf die Kosten nur senken, nie erhoehen"


def test_kosten_batch_stimmt_mit_der_einzelnen_suche_ueberein():
    """Die vektorisierte Batch-Suche (Performance) muss dasselbe liefern wie die einzelne Suche je
    Abfahrt-Kandidat - nur eben alle auf einmal."""
    abfahrt_kandidaten = np.array([10.0, 25.0, 40.0, 55.5, 70.0])
    for heizen_erlaubt in (True, False):
        kosten_arr, heiz_arr, _zeit_arr = _kosten_batch(18.0, abfahrt_kandidaten, -12.0, 1.0, 6.0, heizen_erlaubt)
        for i, abfahrt in enumerate(abfahrt_kandidaten):
            einzeln = kosten_bei_stopp(18.0, float(abfahrt), -12.0, 1.0, 6.0, heizen_erlaubt)
            assert einzeln is not None
            netzenergie_einzeln, heiz_einzeln, _zeit_einzeln = einzeln
            assert abs(kosten_arr[i] - netzenergie_einzeln) < 1e-6, (heizen_erlaubt, abfahrt)
            assert abs(heiz_arr[i] - heiz_einzeln) < 1e-6, (heizen_erlaubt, abfahrt)


@pytest.mark.parametrize("typ", list(FAHRZEUGTYPEN))
@pytest.mark.parametrize("preset", list(PRESETS))
@pytest.mark.parametrize("temperatur", [-20.0, -5.0, 10.0])
def test_alle_fahrzeugtypen_erreichen_alle_beispielstrecken_und_heizen_ist_nie_schlechter(typ, preset, temperatur):
    """Pkw, Lieferwagen, Elektrobus und Elektro-Lkw: jede Beispielstrecke ist über den vollen
    Temperaturbereich erreichbar, und die Heizoption verschlechtert das Ergebnis nie."""
    v = FAHRZEUGTYPEN[typ]
    strecke = baue_strecke(PRESETS[preset]["start"], PRESETS[preset]["etappen"], temperatur)
    fahrzeug = Fahrzeug(
        kapazitaet_kwh=v["kapazitaet"], basisverbrauch_kwh_km=v["verbrauch"], start_soc_kwh=v["kapazitaet"],
        geschwindigkeit_kmh=v["geschwindigkeit"], heizleistung_kw=v["heizleistung"],
    )
    mit = plane_route(strecke, fahrzeug, heizen_erlaubt=True, soc_aufloesung=100)
    ohne = plane_route(strecke, fahrzeug, heizen_erlaubt=False, soc_aufloesung=100)
    assert mit.erreichbar and ohne.erreichbar
    assert mit.netzenergie_gesamt_kwh <= ohne.netzenergie_gesamt_kwh + 1e-6


def test_batch_und_einzelsuche_stimmen_auch_bei_grossem_paket_ueberein():
    from lade_modell import waermekapazitaet_kwh_pro_grad

    c = waermekapazitaet_kwh_pro_grad(620.0)
    abfahrt = np.array([300.0, 450.0, 600.0])
    kosten_arr, heiz_arr, _zeit_arr = _kosten_batch(250.0, abfahrt, -12.0, 1.0, 45.0, True, waermekapazitaet_kwh_pro_grad=c)
    for k, ab in enumerate(abfahrt):
        einzeln = kosten_bei_stopp(250.0, float(ab), -12.0, 1.0, 45.0, True, waermekapazitaet_kwh_pro_grad=c)
        assert einzeln is not None
        assert abs(einzeln[0] - kosten_arr[k]) < 1e-6
        assert abs(einzeln[1] - heiz_arr[k]) < 1e-9


# ---------- Zeit als zweites Kriterium, Reserve bei jeder Ankunft ----------


def _fahrzeug_typ(typ: str, **extra) -> Fahrzeug:
    v = FAHRZEUGTYPEN[typ]
    return Fahrzeug(
        kapazitaet_kwh=v["kapazitaet"], basisverbrauch_kwh_km=v["verbrauch"], start_soc_kwh=v["kapazitaet"],
        geschwindigkeit_kmh=v["geschwindigkeit"], heizleistung_kw=v["heizleistung"], ladeleistung_kw=v["ladeleistung"], **extra,
    )


@pytest.mark.parametrize(
    "typ, preset, temperatur, heizen, erwartet",
    [
        # Referenzwerte des Stands VOR dem Zeitkriterium (Standardauflösung 300 / 400): bei Zeitwert 0 darf sich
        # die Netzenergie durch die Erweiterung nicht ändern.
        ("Lieferwagen", "Standardstrecke", -15.0, True, 124.89954908967353),
        ("Lieferwagen", "Standardstrecke", -15.0, False, 132.15867148867),
        ("Elektrobus", "Langstrecke, dünn besäult", -8.0, True, 816.4718907523057),
        ("Elektro-Lkw", "Standardstrecke", -5.0, True, 24.68829006784705),
    ],
)
def test_zeitwert_null_aendert_die_netzenergie_gegenueber_dem_stand_vor_dem_zeitkriterium_nicht(typ, preset, temperatur, heizen, erwartet):
    strecke = baue_strecke(PRESETS[preset]["start"], PRESETS[preset]["etappen"], temperatur)
    ergebnis = plane_route(strecke, _fahrzeug_typ(typ), heizen_erlaubt=heizen)
    assert ergebnis.netzenergie_gesamt_kwh == pytest.approx(erwartet, abs=1e-6)


def test_gesamtzeit_ist_fahrzeit_plus_summe_der_ladezeiten():
    strecke = _einfache_strecke([(120, -12.0), (100, -12.0), (110, -12.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.35, start_soc_kwh=80, geschwindigkeit_kmh=90)
    e = plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=3.0)
    assert e.erreichbar
    assert e.fahrzeit_h == pytest.approx(330 / 90)
    assert e.ladezeit_gesamt_h == pytest.approx(sum(s.ladezeit_h for s in e.stopps))
    assert e.gesamtzeit_h == pytest.approx(e.fahrzeit_h + e.ladezeit_gesamt_h)
    assert e.ladezeit_gesamt_h > 0


def test_ladezeit_je_stopp_entspricht_der_ladekurve_plus_pauschale():
    """Unabhängige Neuberechnung aus den ausgegebenen Stopp-Daten (Heizen kostet keine Zeit, Laden von
    'Ankunft minus Heizenergie' auf 'Abfahrt' bei der Batterietemperatur beim Laden)."""
    strecke = _einfache_strecke([(130, -15.0), (130, -15.0), (130, -15.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.35, start_soc_kwh=80, ladeleistung_kw=100.0, stopp_pauschale_h=0.1)
    e = plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=2.0)
    assert e.erreichbar and any(s.geladen_kwh > 0 for s in e.stopps)
    for s in e.stopps:
        if s.geladen_kwh > 1e-9:
            erwartet = ladezeit_h(s.ankunft_soc_kwh - s.heiz_energie_kwh, s.abfahrt_soc_kwh, 80.0, 100.0, s.batterietemperatur_beim_laden_c, 0.1)
            assert s.ladezeit_h == pytest.approx(erwartet, abs=1e-9)
        else:
            assert s.ladezeit_h == 0.0


def test_ohne_ladebedarf_gibt_es_keine_ladezeit():
    strecke = _einfache_strecke([(100, 20.0)])
    e = plane_route(strecke, Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80))
    assert e.ladezeit_gesamt_h == 0.0
    assert e.gesamtzeit_h == pytest.approx(e.fahrzeit_h)


def test_jeder_ladehalt_kostet_mindestens_die_pauschale():
    strecke = _einfache_strecke([(130, -5.0), (130, -5.0), (130, -5.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.35, start_soc_kwh=80, stopp_pauschale_h=0.25)
    e = plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=5.0)
    geladen = [s for s in e.stopps if s.geladen_kwh > 1e-9]
    assert geladen
    assert e.ladezeit_gesamt_h >= 0.25 * len(geladen) - 1e-9


def test_hoeherer_zeitwert_verschiebt_nie_zugunsten_von_energie():
    """Mit wachsendem Zeitwert darf die Ladezeit nur sinken und die Netzenergie nur steigen (bis auf
    Diskretisierungsrauschen von höchstens einer SOC-Stufe je Ladestopp)."""
    strecke = baue_strecke("Start", PRESETS["Standardstrecke"]["etappen"], -15.0)
    fahrzeug = _fahrzeug_typ("Lieferwagen")
    toleranz_kwh = 3 * fahrzeug.kapazitaet_kwh / 300 / 0.80
    plaene = [plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=z, heiz_aufloesung=100) for z in (0.0, 1.0, 3.0, 10.0, 100.0, 1e5)]
    assert all(p.erreichbar for p in plaene)
    for kleiner, groesser in zip(plaene, plaene[1:]):
        assert groesser.ladezeit_gesamt_h <= kleiner.ladezeit_gesamt_h + 1e-9
        assert groesser.netzenergie_gesamt_kwh >= kleiner.netzenergie_gesamt_kwh - toleranz_kwh


def test_der_plan_je_zeitwert_ist_fuer_diesen_zeitwert_nicht_schlechter_als_die_plaene_der_anderen():
    strecke = baue_strecke("Start", PRESETS["Standardstrecke"]["etappen"], -15.0)
    fahrzeug = _fahrzeug_typ("Lieferwagen")
    zeitwerte = (0.0, 2.0, 20.0, 1e3)
    plaene = {z: plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=z, heiz_aufloesung=100) for z in zeitwerte}
    for z in zeitwerte:
        eigener = plaene[z].netzenergie_gesamt_kwh + z * plaene[z].ladezeit_gesamt_h
        for z2 in zeitwerte:
            fremder = plaene[z2].netzenergie_gesamt_kwh + z * plaene[z2].ladezeit_gesamt_h
            assert eigener <= fremder + 1e-6, (z, z2)


def test_kleiner_zeitwert_aendert_die_netzenergie_nicht_und_verlaengert_die_ladezeit_nicht():
    """Ein verschwindend kleiner Zeitwert wirkt nur als Tiebreak: gleiche Energie, nie mehr Ladezeit."""
    strecke = _einfache_strecke([(150, 15.0), (150, 15.0), (150, 15.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.3, start_soc_kwh=80, ladeleistung_kw=100.0)
    energie = plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=0.0, heizen_erlaubt=False)
    sehr_klein = plane_route(strecke, fahrzeug, zeitwert_kwh_pro_h=1e-6, heizen_erlaubt=False)
    assert energie.netzenergie_gesamt_kwh == pytest.approx(sehr_klein.netzenergie_gesamt_kwh, abs=1e-4)
    assert energie.ladezeit_gesamt_h <= sehr_klein.ladezeit_gesamt_h + 1e-9


def test_kaelte_und_geringe_ladeleistung_verlaengern_die_ladezeit():
    fahrzeug = _fahrzeug_typ("Lieferwagen")
    langsam = Fahrzeug(**{**fahrzeug.__dict__, "ladeleistung_kw": fahrzeug.ladeleistung_kw / 2})
    strecke_kalt = baue_strecke("Start", PRESETS["Standardstrecke"]["etappen"], -18.0)
    strecke_mild = baue_strecke("Start", PRESETS["Standardstrecke"]["etappen"], 8.0)
    z = 5.0
    kalt = plane_route(strecke_kalt, fahrzeug, zeitwert_kwh_pro_h=z, heiz_aufloesung=100)
    mild = plane_route(strecke_mild, fahrzeug, zeitwert_kwh_pro_h=z, heiz_aufloesung=100)
    halbe_leistung = plane_route(strecke_kalt, langsam, zeitwert_kwh_pro_h=z, heiz_aufloesung=100)
    assert kalt.ladezeit_gesamt_h > mild.ladezeit_gesamt_h
    assert halbe_leistung.ladezeit_gesamt_h > kalt.ladezeit_gesamt_h


def test_reserve_gilt_bei_jeder_ankunft_nicht_nur_am_ziel():
    strecke = _einfache_strecke([(150, -5.0), (150, -5.0), (150, -5.0)], namen=["Start", "A", "B", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.3, start_soc_kwh=80, reserve_kwh=12.0)
    e = plane_route(strecke, fahrzeug, soc_aufloesung=300)
    assert e.erreichbar
    for s in e.stopps:
        assert s.ankunft_soc_kwh >= 12.0 - 1e-6
        assert s.ankunft_soc_kwh - s.heiz_energie_kwh >= 12.0 - 1e-6  # Vorheizen unterschreitet die Reserve nicht
    assert e.ankunft_ziel_soc_kwh >= 12.0 - 1e-6


def test_reserve_null_ist_der_bisherige_plan_und_mehr_reserve_wird_nie_billiger():
    strecke = baue_strecke("Start", PRESETS["Standardstrecke"]["etappen"], -10.0)
    ohne = plane_route(strecke, _fahrzeug_typ("Lieferwagen"))
    mit_null = plane_route(strecke, _fahrzeug_typ("Lieferwagen", reserve_kwh=0.0))
    assert ohne.netzenergie_gesamt_kwh == mit_null.netzenergie_gesamt_kwh
    letzte = ohne.netzenergie_gesamt_kwh
    for reserve in (4.0, 8.0, 16.0):
        e = plane_route(strecke, _fahrzeug_typ("Lieferwagen", reserve_kwh=reserve))
        assert e.erreichbar
        assert e.netzenergie_gesamt_kwh >= letzte - 1e-6
        letzte = e.netzenergie_gesamt_kwh


def test_zu_grosse_reserve_macht_die_strecke_unerreichbar():
    """Der erste Abschnitt von 200 km braucht bei 0,32 kWh/km 64 kWh: mit vollem 80-kWh-Akku kommt man
    ohne Reserve an, mit 20 kWh Reserve bei Ankunft nicht."""
    strecke = _einfache_strecke([(200, 20.0), (50, 20.0)], namen=["Start", "Säule", "Ziel"])
    fahrzeug = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80)
    assert plane_route(strecke, fahrzeug).erreichbar
    streng = Fahrzeug(kapazitaet_kwh=80, basisverbrauch_kwh_km=0.32, start_soc_kwh=80, reserve_kwh=20.0)
    assert not plane_route(strecke, streng).erreichbar


@pytest.mark.parametrize("zeitwert", [0.0, 3.0, 40.0])
def test_batch_und_einzelsuche_stimmen_mit_zeitwert_reserve_und_pauschale_ueberein(zeitwert):
    kandidaten = np.array([20.0, 35.0, 50.0, 64.0, 79.0])
    extras = dict(zeitwert_kwh_pro_h=zeitwert, kapazitaet_kwh=80.0, ladeleistung_kw=90.0, pauschale_h=0.08, reserve_kwh=6.0)
    for heizen in (True, False):
        e_arr, h_arr, z_arr = _kosten_batch(18.0, kandidaten, -12.0, 1.0, 6.0, heizen, **extras)
        for i, ab in enumerate(kandidaten):
            einzeln = kosten_bei_stopp(18.0, float(ab), -12.0, 1.0, 6.0, heizen, **extras)
            assert einzeln is not None
            assert abs(e_arr[i] - einzeln[0]) < 1e-6, (heizen, ab)
            assert abs(h_arr[i] - einzeln[1]) < 1e-6, (heizen, ab)
            assert abs(z_arr[i] - einzeln[2]) < 1e-6, (heizen, ab)


def test_kosten_bei_stopp_beachtet_die_reserve_beim_heizen():
    mit_reserve = kosten_bei_stopp(20.0, 70.0, -15.0, 3.0, 6.0, True, reserve_kwh=14.0)
    assert mit_reserve is not None
    assert mit_reserve[1] <= (20.0 - 14.0) / 6.0 + 1e-9  # höchstens 1 h Heizen, sonst rutscht der Akku unter die Reserve
