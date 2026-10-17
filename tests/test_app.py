import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_startet_ohne_fehler():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception


def test_app_zeigt_sechs_metriken_bei_erreichbarer_strecke():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.metric) == 6  # Energie (3) + Zeit (3)
    werte = [m.value for m in at.metric]
    assert all(w for w in werte)


def test_heizen_ausschalten_bleibt_fehlerfrei():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.toggle(key="heizen_toggle").set_value(False).run()
    assert not at.exception


def test_sehr_kalte_einstellung_bleibt_fehlerfrei():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.slider(key="temperatur_slider").set_value(-20).run()
    assert not at.exception


def test_app_hat_ueberschriften_fuer_ergebnis_heizeffekt_und_zusammenhaenge():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    header_texte = " ".join(h.value for h in at.header)
    assert "1. Ergebnis" in header_texte
    assert "2." in header_texte and "Heizens" in header_texte
    assert "Zusammenhänge" in header_texte


def test_anderes_preset_laedt_fehlerfrei_und_aendert_die_distanzen():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    distanzen_vorher = [n.value for n in at.sidebar.number_input]
    at.button[2].click().run()  # "Langstrecke, dünn besäult" - Presets stehen oben in der Mitte, nicht in der Sidebar
    assert not at.exception
    distanzen_nachher = [n.value for n in at.sidebar.number_input]
    assert distanzen_vorher != distanzen_nachher


def test_distanz_felder_entsprechen_der_saeulenzahl():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    anzahl = at.sidebar.slider(key="anzahl_saeulen_slider").value
    assert len(at.sidebar.number_input) == anzahl + 1


def test_mehr_saeulen_erzeugt_mehr_distanz_felder():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.slider(key="anzahl_saeulen_slider").set_value(5).run()
    assert not at.exception
    assert len(at.sidebar.number_input) == 6


def test_eigene_distanz_aenderung_wirkt_sich_auf_das_ergebnis_aus():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    vorher = [m.value for m in at.metric]
    at.sidebar.number_input(key="distanz_0").set_value(250.0).run()
    assert not at.exception
    nachher = [m.value for m in at.metric]
    assert vorher != nachher


def test_geschwindigkeit_und_heizleistung_regler_vorhanden_und_wirksam():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert at.sidebar.slider(key="geschwindigkeit_slider") is not None
    at.sidebar.slider(key="heizleistung_slider").set_value(3.0).run()
    assert not at.exception


def test_presets_stehen_oben_in_der_mitte_und_die_fahrzeugtypen_in_der_sidebar():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    from lade_constants import FAHRZEUGTYP_NAMEN, PRESET_NAMEN

    # drei Beispielstrecken im Hauptbereich, die vier Fahrzeugtypen in der Seitenleiste
    assert len(at.main.button) == len(PRESET_NAMEN)
    assert [b.key for b in at.sidebar.button] == [f"fahrzeugtyp_{n}" for n in FAHRZEUGTYP_NAMEN]


def test_mathematische_formulierung_expander_vorhanden():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    titel = [e.label for e in at.expander]
    assert any("Mathematische Formulierung" in t for t in titel)


def test_fahrzeugtyp_knoepfe_setzen_die_fahrzeugregler_und_bleiben_fehlerfrei():
    from lade_constants import FAHRZEUGTYPEN

    for name, werte in FAHRZEUGTYPEN.items():
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        at.sidebar.button(key=f"fahrzeugtyp_{name}").click().run()
        assert not at.exception, name
        assert at.session_state["fahrzeugtyp"] == name
        assert at.sidebar.slider(key="kapazitaet_slider").value == werte["kapazitaet"]
        assert at.sidebar.slider(key="verbrauch_slider").value == werte["verbrauch"]
        assert at.sidebar.slider(key="heizleistung_slider").value == werte["heizleistung"]
        assert at.sidebar.slider(key="geschwindigkeit_slider").value == werte["geschwindigkeit"]
        assert at.sidebar.slider(key="ladeleistung_slider").value == werte["ladeleistung"]
        assert len(at.metric) == 6  # Strecke bleibt erreichbar


def test_titel_und_einleitung_sind_fahrzeugunabhaengig():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert "Elektrofahrzeug" in at.title[0].value
    assert "Lieferfahrzeug" not in at.title[0].value


def test_neue_regler_fuer_laden_reserve_und_zeitwert_sind_vorhanden_mit_alten_standardwerten():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert at.sidebar.slider(key="ladeleistung_slider").value == 115.0
    assert at.sidebar.slider(key="pauschale_slider").value == 5
    assert at.sidebar.slider(key="reserve_slider").value == 0
    assert at.sidebar.select_slider(key="zeitwert_select").value == 0


def test_abschnitt_energie_gegen_zeit_ist_vorhanden():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert any("Energie gegen Zeit" in h.value for h in at.header)


def test_zeitmetriken_zeigen_gesamt_und_ladezeit():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    labels = [m.label for m in at.metric]
    assert any("Gesamtzeit" in l for l in labels)
    assert any("Laden" in l for l in labels)


def test_zeitwert_reserve_und_ladeleistung_aendern_das_ergebnis_fehlerfrei():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    vorher = [m.value for m in at.metric]
    at.sidebar.select_slider(key="zeitwert_select").set_value(100).run()
    assert not at.exception
    at.sidebar.slider(key="reserve_slider").set_value(10).run()
    assert not at.exception
    at.sidebar.slider(key="ladeleistung_slider").set_value(50.0).run()
    assert not at.exception
    assert [m.value for m in at.metric] != vorher


def test_zu_grosse_reserve_zeigt_fehlermeldung_statt_abzustuerzen():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.slider(key="reserve_slider").set_value(30).run()
    at.button[2].click().run()  # Langstrecke, dünn besäult: 150-km-Abschnitte lassen bei 30 % Reserve keinen Spielraum
    assert not at.exception
    assert len(at.error) >= 1


def _kopf_html(at) -> str:
    return " ".join(h.proto.body for h in at.get("html"))


def test_piktogramm_unter_der_ueberschrift_wechselt_mit_dem_fahrzeugtyp():
    from lade_constants import FAHRZEUGTYP_NAMEN, STANDARD_FAHRZEUGTYP

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert f'data-typ="{STANDARD_FAHRZEUGTYP}"' in _kopf_html(at)
    for name in FAHRZEUGTYP_NAMEN:
        at.sidebar.button(key=f"fahrzeugtyp_{name}").click().run()
        html = _kopf_html(at)
        assert f'data-typ="{name}"' in html
        assert html.count('class="lade-piktogramm"') == 1  # genau ein Piktogramm: das des gewählten Typs


def test_gewaehlter_fahrzeugtyp_ist_in_der_sidebar_hervorgehoben():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.button(key="fahrzeugtyp_Elektrobus").click().run()
    typen = {b.key: b.proto.type for b in at.sidebar.button}
    assert typen["fahrzeugtyp_Elektrobus"] == "primary"
    assert all(t == "secondary" for k, t in typen.items() if k != "fahrzeugtyp_Elektrobus")


def test_ueberschrift_und_piktogramm_stehen_in_einem_festen_kopf_container():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert "st-key-kopf" in _kopf_html(at)  # das Stylesheet setzt an der Klasse des Containers an
    assert at.title[0].value
