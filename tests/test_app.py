import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_startet_ohne_fehler():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception


def test_app_zeigt_drei_metriken_bei_erreichbarer_strecke():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.metric) == 3
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


def test_presets_stehen_oben_in_der_mitte_nicht_in_der_sidebar():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.button) == 3
    assert len(at.sidebar.button) == 0


def test_mathematische_formulierung_expander_vorhanden():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    titel = [e.label for e in at.expander]
    assert any("Mathematische Formulierung" in t for t in titel)
