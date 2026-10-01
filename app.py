"""Verbrauchsminimale Streckenplanung für ein E-Lieferfahrzeug - Streamlit-Demo.

Fall-Demo (Transport & Tourenplanung) der Website sebastianhanisch.net: eine feste Strecke mit
konfigurierbaren Schnellladesäulen-Positionen, temperaturabhängigem Verbrauch und Ladewirkungsgrad,
und der Entscheidung, wie viel an jeder Säule geladen und wie lange während der Fahrt vorher geheizt
wird - gesucht ist die Strategie, die insgesamt am wenigsten Netzenergie zieht.
"""

from __future__ import annotations

import streamlit as st

from lade_constants import (
    ANZAHL_SAEULEN_MAX,
    ANZAHL_SAEULEN_MIN,
    DISTANZ_MAX,
    DISTANZ_MIN,
    GESCHWINDIGKEIT_MAX,
    GESCHWINDIGKEIT_MIN,
    GESCHWINDIGKEIT_STANDARD,
    HEIZLEISTUNG_MAX,
    HEIZLEISTUNG_MIN,
    HEIZLEISTUNG_STANDARD,
    KAPAZITAET_MAX,
    KAPAZITAET_MIN,
    KAPAZITAET_STANDARD,
    PRESET_NAMEN,
    START_SOC_PROZENT_MAX,
    START_SOC_PROZENT_MIN,
    START_SOC_PROZENT_STANDARD,
    TEMPERATUR_MAX,
    TEMPERATUR_MIN,
    TEMPERATUR_STANDARD,
    VERBRAUCH_MAX,
    VERBRAUCH_MIN,
    VERBRAUCH_STANDARD,
)
from lade_modell import (
    ETA_KALT,
    ETA_WARM,
    WAERMEVERLUST_ZEITKONSTANTE_H,
    Fahrzeug,
    ladewirkungsgrad,
    verbrauch_kwh_km,
)
from lade_planung import Ergebnis, plane_route
from lade_szenario import (
    anwenden_preset,
    baue_strecke,
    etappen_namen_fuer,
    init_session_state_defaults,
)
from lade_visualisierung import soc_verlauf_figur, temperatur_sweep_figur

st.set_page_config(page_title="Ladestrategie: E-Lieferfahrzeug im Winter", page_icon="🔋", layout="wide")

init_session_state_defaults()

st.title("🔋 Ladestrategie: E-Lieferfahrzeug im Winter")
st.caption("Fall-Demo (Transport & Tourenplanung) von sebastianhanisch.net - echte Studienwerte, keine frei erfundene Physik.")

st.markdown(
    "Diese Demo gehört zur **Graphen-und-Netzwerke-Linie** der Konzepte-Reihe von "
    "[sebastianhanisch.net](https://sebastianhanisch.net) - anders als die dortigen Verfahrens-Demos "
    "(ein Algorithmus an einem wachsenden, meist künstlichen Beispiel) ist das hier eine "
    "**Analyse-Karte**: eine Kennzahl an einem einzigen, aber echten Fall berechnen und interpretieren, "
    "kein Verfahrensvergleich. Ein E-Lieferfahrzeug fährt eine feste Strecke mit **frei einstellbaren** "
    "Schnellladesäulen-Positionen. Entschieden wird an jeder Säule nur: **wie viel laden, und wie lange "
    "vorher heizen?** Kälte erhöht den Verbrauch beim Fahren UND senkt den Ladewirkungsgrad (kalte "
    "Zellen haben mehr Innenwiderstand) - Heizen kostet selbst Energie, kann sich aber lohnen, wenn es "
    "an der nächsten Säule genug Ladeverlust erspart. Gesucht ist die Strategie, die **insgesamt am "
    "wenigsten Energie aus dem Netz zieht**, nicht die schnellste."
)

with st.sidebar:
    st.header("Strecke")
    st.caption("Beispiele")
    for name in PRESET_NAMEN:
        st.button(name, on_click=anwenden_preset, args=(name,), width="stretch")

    st.caption("Eigene Strecke")
    anzahl_saeulen = st.slider("Anzahl Ladesäulen", ANZAHL_SAEULEN_MIN, ANZAHL_SAEULEN_MAX, key="anzahl_saeulen_slider")
    etappen_namen = etappen_namen_fuer(anzahl_saeulen)
    start_name = st.text_input("Start", key="start_name")
    distanzen = [st.number_input(f"Strecke zu {name} (km)", DISTANZ_MIN, DISTANZ_MAX, key=f"distanz_{i}", step=5.0) for i, name in enumerate(etappen_namen)]

    st.header("Fahrzeug & Wetter")
    temperatur = st.slider("Außentemperatur (°C)", TEMPERATUR_MIN, TEMPERATUR_MAX, TEMPERATUR_STANDARD, key="temperatur_slider", help="Gilt einheitlich für die ganze Strecke.")
    kapazitaet = st.slider("Batteriekapazität (kWh)", KAPAZITAET_MIN, KAPAZITAET_MAX, KAPAZITAET_STANDARD, step=5, key="kapazitaet_slider")
    basisverbrauch = st.slider("Basisverbrauch bei 20 °C (kWh/km)", VERBRAUCH_MIN, VERBRAUCH_MAX, VERBRAUCH_STANDARD, step=0.01, key="verbrauch_slider")
    start_soc_anteil = st.slider("Akkustand am Start (%)", START_SOC_PROZENT_MIN, START_SOC_PROZENT_MAX, START_SOC_PROZENT_STANDARD, step=5, key="start_soc_slider")
    geschwindigkeit = st.slider("Geschwindigkeit (km/h)", GESCHWINDIGKEIT_MIN, GESCHWINDIGKEIT_MAX, GESCHWINDIGKEIT_STANDARD, key="geschwindigkeit_slider", help="Bestimmt, wie viel Zeit während eines Abschnitts fürs Heizen bleibt.")
    heizleistung = st.slider("Heizleistung (kW)", HEIZLEISTUNG_MIN, HEIZLEISTUNG_MAX, HEIZLEISTUNG_STANDARD, step=0.5, key="heizleistung_slider", help="Typisch 3-8 kW für große Batteriepakete (z. B. Tesla Model 3: 6 kW).")
    heizen_erlaubt = st.toggle("Heizen während der Fahrt erlauben", value=True, key="heizen_toggle")

alle_namen = tuple([start_name] + etappen_namen)
alle_distanzen = tuple(float(d) for d in distanzen)
strecke = baue_strecke(start_name, list(zip(etappen_namen, distanzen)), float(temperatur))
fahrzeug = Fahrzeug(
    kapazitaet_kwh=float(kapazitaet),
    basisverbrauch_kwh_km=float(basisverbrauch),
    start_soc_kwh=kapazitaet * start_soc_anteil / 100,
    geschwindigkeit_kmh=float(geschwindigkeit),
    heizleistung_kw=float(heizleistung),
)


@st.cache_data
def _route_planen(namen: tuple[str, ...], distanzen: tuple[float, ...], temp: float, kap: float, basis: float, start_soc: float, geschwindigkeit: float, heizleistung: float, heizen: bool) -> Ergebnis:
    s = baue_strecke(namen[0], list(zip(namen[1:], distanzen)), temp)
    f = Fahrzeug(kapazitaet_kwh=kap, basisverbrauch_kwh_km=basis, start_soc_kwh=start_soc, geschwindigkeit_kmh=geschwindigkeit, heizleistung_kw=heizleistung)
    return plane_route(s, f, heizen_erlaubt=heizen)


ergebnis = _route_planen(alle_namen, alle_distanzen, float(temperatur), float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh, float(geschwindigkeit), float(heizleistung), heizen_erlaubt)
ergebnis_ohne_heizen = _route_planen(alle_namen, alle_distanzen, float(temperatur), float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh, float(geschwindigkeit), float(heizleistung), False)

st.header("1. Ergebnis bei dieser Einstellung")

if not ergebnis.erreichbar:
    st.error("Mit dieser Einstellung ist das Ziel nicht erreichbar - die Strecke überfordert die Reichweite selbst mit vollem Nachladen an jeder Säule.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Netzenergie gesamt", f"{ergebnis.netzenergie_gesamt_kwh:.1f} kWh")
    ersparnis = ergebnis_ohne_heizen.netzenergie_gesamt_kwh - ergebnis.netzenergie_gesamt_kwh if heizen_erlaubt and ergebnis_ohne_heizen.erreichbar else 0.0
    col2.metric("davon durch Heizen gespart", f"{ersparnis:.1f} kWh", delta=f"{-ersparnis:.1f} kWh" if ersparnis > 0 else None, delta_color="inverse")
    col3.metric("Verbrauch je km bei dieser Temperatur", f"{verbrauch_kwh_km(basisverbrauch, temperatur):.3f} kWh/km")

    st.plotly_chart(soc_verlauf_figur(strecke, fahrzeug, ergebnis), width="stretch")

    if ergebnis.stopps:
        st.subheader("Entscheidungen an jeder Säule")
        for stopp in ergebnis.stopps:
            heiz_text = (
                f", davon {stopp.heiz_dauer_h * 60:.0f} min geheizt ({stopp.heiz_energie_kwh:.2f} kWh) auf {stopp.batterietemperatur_beim_laden_c:.1f} °C Batterietemperatur"
                if stopp.heiz_dauer_h > 0.001
                else f" (Batterie bleibt bei {temperatur:.0f} °C, kein Heizen)"
            )
            st.markdown(
                f"**{stopp.name}**: Ankunft {stopp.ankunft_soc_kwh:.2f} kWh"
                + heiz_text
                + f" → geladen {stopp.geladen_kwh:.2f} kWh ({stopp.netzenergie_kwh:.2f} kWh aus dem Netz, Wirkungsgrad {ladewirkungsgrad(stopp.batterietemperatur_beim_laden_c) * 100:.0f} %) → Abfahrt {stopp.abfahrt_soc_kwh:.2f} kWh"
            )

st.header("2. Effekt des Heizens über die Temperatur")
st.markdown(
    "Dieselbe Strecke, fest durchgerechnet für jede Temperatur von +20 °C bis -20 °C, einmal mit und "
    "einmal ohne Heizoption - zeigt, ab wann sich Heizen überhaupt lohnt."
)


@st.cache_data
def _temperatur_sweep(namen: tuple[str, ...], distanzen: tuple[float, ...], kap: float, basis: float, start_soc: float, geschwindigkeit: float, heizleistung: float) -> list[dict]:
    zeilen = []
    for t in range(20, -21, -2):
        mit = _route_planen(namen, distanzen, float(t), kap, basis, start_soc, geschwindigkeit, heizleistung, True)
        ohne = _route_planen(namen, distanzen, float(t), kap, basis, start_soc, geschwindigkeit, heizleistung, False)
        if mit.erreichbar and ohne.erreichbar:
            zeilen.append({"temperatur": t, "mit_heizen": mit.netzenergie_gesamt_kwh, "ohne_heizen": ohne.netzenergie_gesamt_kwh})
    return zeilen


sweep = _temperatur_sweep(alle_namen, alle_distanzen, float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh, float(geschwindigkeit), float(heizleistung))
if sweep:
    st.plotly_chart(temperatur_sweep_figur(sweep), width="stretch")
    ersparnis_bei_kaelte = next((z["ohne_heizen"] - z["mit_heizen"] for z in sweep if z["temperatur"] == -20), None)
    ersparnis_bei_mild = next((z["ohne_heizen"] - z["mit_heizen"] for z in sweep if z["temperatur"] == 10), None)
    if ersparnis_bei_kaelte is not None and ersparnis_bei_mild is not None:
        st.caption(
            f"Bei -20 °C spart Heizen {ersparnis_bei_kaelte:.1f} kWh auf dieser Strecke "
            f"({ersparnis_bei_kaelte / next(z['ohne_heizen'] for z in sweep if z['temperatur'] == -20) * 100:.1f} % weniger Netzenergie), "
            f"bei +10 °C nur noch {ersparnis_bei_mild:.1f} kWh - der Effekt wächst mit der Kälte, ist in milden Wintern aber gering."
        )
else:
    st.info("Für diese Strecke/dieses Fahrzeug ist nicht jede Temperatur im Bereich erreichbar - der Vergleich wird übersprungen.")

with st.expander("📐 Modellannahmen und Quellen"):
    st.markdown(
        f"""
- **Verbrauch bei Kälte**: AAA-Wintertest 2025 (Chevrolet Equinox EV, Tesla Model Y, Ford Mustang Mach-E) - bei -6,6 °C im Schnitt 35,6 % geringere Effizienz. Referenztemperatur 20 °C, linear zunehmender Mehrverbrauch darunter, kein Effekt oberhalb.
- **Ladewirkungsgrad bei Kälte**: Innenwiderstand von Li-Ion-Zellen bei -20 °C nachweislich etwa 3-mal so hoch wie bei Raumtemperatur (mehrere Studien zu Zellen bei tiefen Temperaturen) - mehr Widerstand heißt mehr ohmscher Verlust je geladener kWh. Kalibriert auf {ETA_WARM * 100:.0f} % bei ≥20 °C und {ETA_KALT * 100:.0f} % bei -20 °C, linear dazwischen - die Literatur belegt Richtung und Größenordnung, nicht exakt diese Kurve.
- **Ladeleistung/-zeit bei Kälte** (hier nicht Teil der Optimierung): Idaho National Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500 Schnellladevorgänge) - bei 0 °C nach gleicher Ladezeit 36 % weniger Ladestand als bei 25 °C, Schnellladen bis zu 3-mal langsamer. Das ist überwiegend ein Leistungseffekt (die Ladesteuerung drosselt den Strom zum Zellschutz), kein reiner Energie-Effizienz-Effekt - deshalb bewusst getrennt von der Wirkungsgrad-Kurve oben.
- **Heizen während der Fahrt**: begrenzt durch die Heizleistung (3-8 kW typisch für große Batteriepakete, z. B. Tesla Model 3 mit 6 kW - Standardwert hier) UND durch Wärmeverlust an die kalte Außenluft während des Heizens (exponentielle Annäherung an eine Gleichgewichtstemperatur, keine beliebig schnelle Erwärmung). Die thermische Zeitkonstante ({WAERMEVERLUST_ZEITKONSTANTE_H:.0f} Stunden) ist ein Erfahrungswert aus einer realen Abkühlkurve (Nissan-LEAF-Fallstudie), kein Laborwert - deutlich länger als eine einzelne Fahrstrecke, aber nicht vernachlässigbar bei langem Heizen.
- **Vereinfachung**: die Batterie nimmt beim Fahren eines Abschnitts dessen Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte hinweg) - Heizen wirkt nur im unmittelbar vorangehenden Abschnitt.
- **Strecke und Fahrzeug**: Anzahl und Distanzen der Ladesäulen sind frei einstellbar (links), aber während der Optimierung fest - keine Streckenwahl, nur Lademenge und Heizdauer an jeder Säule sind die Entscheidung. Werte für Kapazität und Verbrauch orientieren sich an einem typischen E-Lieferfahrzeug (z. B. Mercedes eSprinter, VW ID. Buzz Cargo).
- **Algorithmus**: dynamische Programmierung über (Haltepunkt, Akkustand), mit einer feinen Rastersuche über die Heizdauer an jedem Stopp (siehe `lade_planung.py`). Gegen eine deutlich feinere Auflösung geprüft (`tests/test_lade_planung.py`): Abweichung unter 3 %.
        """
    )

st.header("Zusammenhänge zu anderen Stücken des Portfolios")
st.markdown(
    "- **[Fernverkehr: Lenkzeiten und Elektro-Lkw](https://sebastianhanisch-fernverkehr-demo.streamlit.app/)** "
    "hat bereits feste Ladesäulen, Reichweite und Ladestopps für Elektro-Lkw - dort geht es aber um die "
    "**Tourkosten mehrerer Fahrzeuge** unter Fahrerregeln, mit Laden proportional zur Energie und ohne "
    "Temperatureffekt. Diese Demo hier ergänzt genau das Fehlende: **eine einzelne Strecke, "
    "energieminimal**, mit Temperaturphysik bei Verbrauch und Ladewirkungsgrad - kein Duplikat, sondern "
    "die thermische Tiefe, die dort bewusst außen vor blieb.\n"
    "- **[Zentralität](https://sebastianhanisch-centrality-demo.streamlit.app/)** und "
    "**[Strukturkennzahlen und Nullmodelle](https://sebastianhanisch-strukturkennzahlen-demo.streamlit.app/)** "
    "sind die anderen Analyse-Karten der Graphen-und-Netzwerke-Linie - dieselbe Grundidee (eine "
    "Kennzahl berechnen und interpretieren, kein Verfahrensvergleich), andere Kennzahlen.\n"
    "- Modell und Algorithmus (ressourcenbeschränkter kürzester Weg: Akkustand als Ressource, "
    "dynamische Programmierung über diskretisierte Zustände) folgen demselben Muster wie die "
    "**[Kürzeste-Wege-Linie](https://sebastianhanisch.net/konzepte-kuerzeste-wege.html)** der Konzepte-Reihe."
)

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) - "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für Ihr "
    "Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
