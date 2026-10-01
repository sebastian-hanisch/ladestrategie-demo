"""Verbrauchsminimale Streckenplanung für ein E-Lieferfahrzeug - Streamlit-Demo.

Fall-Demo (Transport & Tourenplanung) der Website sebastianhanisch.net: eine feste Strecke mit
gegebenen Schnellladesäulen-Positionen, temperaturabhängigem Verbrauch und Ladewirkungsgrad, und der
Entscheidung, wie viel an jeder Säule geladen und wie viel vorher geheizt wird - gesucht ist die
Strategie, die insgesamt am wenigsten Netzenergie zieht.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from modell import ETA_KALT, ETA_WARM, Fahrzeug, Segment, Strecke, ladewirkungsgrad, verbrauch_kwh_km
from planung import Ergebnis, plane_route

st.set_page_config(page_title="Ladestrategie: E-Lieferfahrzeug im Winter", page_icon="🔋", layout="wide")

STANDARD_NAMEN = ["Depot (München)", "Schnelllader Ingolstadt", "Schnelllader Nürnberg", "Schnelllader Hof", "Ziel (Leipzig)"]
STANDARD_DISTANZEN = [80.0, 90.0, 100.0, 130.0]

st.title("🔋 Ladestrategie: E-Lieferfahrzeug im Winter")
st.caption("Fall-Demo (Transport & Tourenplanung) von sebastianhanisch.net - echte Studienwerte, keine frei erfundene Physik.")

st.markdown(
    "Ein E-Lieferfahrzeug fährt eine feste Strecke mit **gegebenen** Schnellladesäulen-Positionen "
    "(die Standorte sind keine Entscheidung - die gibt es, wo sie gebaut wurden). Entschieden wird an "
    "jeder Säule nur: **wie viel laden, und wie viel vorher heizen?** Kälte erhöht den Verbrauch beim "
    "Fahren UND senkt den Ladewirkungsgrad (kalte Zellen haben mehr Innenwiderstand) - Heizen kostet "
    "selbst Energie, kann sich aber lohnen, wenn es an der nächsten Säule genug Ladeverlust erspart. "
    "Gesucht ist die Strategie, die **insgesamt am wenigsten Energie aus dem Netz zieht**, nicht die "
    "schnellste."
)

with st.sidebar:
    st.header("Einstellungen")
    temperatur = st.slider("Außentemperatur (°C)", -20, 20, -5, help="Gilt einheitlich für die ganze Strecke.")
    kapazitaet = st.slider("Batteriekapazität (kWh)", 40, 120, 80, step=5)
    basisverbrauch = st.slider("Basisverbrauch bei 20 °C (kWh/km)", 0.20, 0.50, 0.32, step=0.01)
    start_soc_anteil = st.slider("Akkustand am Depot (%)", 50, 100, 100, step=5)
    heizen_erlaubt = st.toggle("Heizen vor dem Laden erlauben", value=True)

strecke = Strecke(namen=STANDARD_NAMEN, segmente=[Segment(d, float(temperatur)) for d in STANDARD_DISTANZEN])
fahrzeug = Fahrzeug(kapazitaet_kwh=float(kapazitaet), basisverbrauch_kwh_km=float(basisverbrauch), start_soc_kwh=kapazitaet * start_soc_anteil / 100)


@st.cache_data
def _route_planen(namen: tuple[str, ...], distanzen: tuple[float, ...], temp: float, kap: float, basis: float, start_soc: float, heizen: bool) -> Ergebnis:
    s = Strecke(namen=list(namen), segmente=[Segment(d, temp) for d in distanzen])
    f = Fahrzeug(kapazitaet_kwh=kap, basisverbrauch_kwh_km=basis, start_soc_kwh=start_soc)
    return plane_route(s, f, heizen_erlaubt=heizen)


ergebnis = _route_planen(tuple(STANDARD_NAMEN), tuple(STANDARD_DISTANZEN), float(temperatur), float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh, heizen_erlaubt)
ergebnis_ohne_heizen = _route_planen(tuple(STANDARD_NAMEN), tuple(STANDARD_DISTANZEN), float(temperatur), float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh, False)

st.header("1. Ergebnis bei dieser Einstellung")

if not ergebnis.erreichbar:
    st.error("Mit dieser Einstellung ist das Ziel nicht erreichbar - die Strecke überfordert die Reichweite selbst mit vollem Nachladen an jeder Säule.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Netzenergie gesamt", f"{ergebnis.netzenergie_gesamt_kwh:.1f} kWh")
    ersparnis = ergebnis_ohne_heizen.netzenergie_gesamt_kwh - ergebnis.netzenergie_gesamt_kwh if heizen_erlaubt and ergebnis_ohne_heizen.erreichbar else 0.0
    col2.metric("davon durch Heizen gespart", f"{ersparnis:.1f} kWh", delta=f"{-ersparnis:.1f} kWh" if ersparnis > 0 else None, delta_color="inverse")
    col3.metric("Verbrauch je km bei dieser Temperatur", f"{verbrauch_kwh_km(basisverbrauch, temperatur):.3f} kWh/km")

    # SOC-Verlauf über die Strecke
    x = [0.0]
    y = [fahrzeug.start_soc_kwh]
    kumulierte_distanz = 0.0
    for i, stopp in enumerate(ergebnis.stopps):
        kumulierte_distanz += strecke.segmente[i].distanz_km
        x += [kumulierte_distanz, kumulierte_distanz, kumulierte_distanz]
        y += [stopp.ankunft_soc_kwh, stopp.ankunft_soc_kwh - stopp.heiz_soc_kwh, stopp.abfahrt_soc_kwh]
    kumulierte_distanz += strecke.segmente[-1].distanz_km
    x.append(kumulierte_distanz)
    y.append(ergebnis.ankunft_ziel_soc_kwh)

    fig_soc = go.Figure()
    fig_soc.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#3E8E86", width=3), name="Akkustand"))
    fig_soc.add_hline(y=0, line_dash="dot", line_color="#D68A2E")
    kumuliert = 0.0
    for i, name in enumerate(strecke.namen):
        fig_soc.add_vline(x=kumuliert, line_dash="dot", line_color="#8A96A6")
        fig_soc.add_annotation(x=kumuliert, y=fahrzeug.kapazitaet_kwh, text=name, showarrow=False, textangle=-40, font=dict(size=10), xanchor="left")
        if i < len(strecke.segmente):
            kumuliert += strecke.segmente[i].distanz_km
    fig_soc.update_layout(title="Akkustand über die Strecke (Einbruch vor einem Ladestopp = Heizen)", xaxis_title="Strecke (km)", yaxis_title="Akkustand (kWh)", height=420, margin=dict(t=60, b=10))
    st.plotly_chart(fig_soc, width="stretch")

    if ergebnis.stopps:
        st.subheader("Entscheidungen an jeder Säule")
        for stopp in ergebnis.stopps:
            st.markdown(
                f"**{stopp.name}**: Ankunft {stopp.ankunft_soc_kwh:.2f} kWh"
                + (f", davon {stopp.heiz_soc_kwh:.2f} kWh fürs Heizen auf {stopp.batterietemperatur_beim_laden_c:.1f} °C Batterietemperatur" if stopp.heiz_soc_kwh > 0.01 else f" (Batterie bleibt bei {temperatur:.0f} °C, kein Heizen)")
                + f" → geladen {stopp.geladen_kwh:.2f} kWh ({stopp.netzenergie_kwh:.2f} kWh aus dem Netz, Wirkungsgrad {ladewirkungsgrad(stopp.batterietemperatur_beim_laden_c) * 100:.0f} %) → Abfahrt {stopp.abfahrt_soc_kwh:.2f} kWh"
            )

st.header("2. Effekt des Heizens über die Temperatur")
st.markdown(
    "Dieselbe Strecke, fest durchgerechnet für jede Temperatur von +20 °C bis -20 °C, einmal mit und "
    "einmal ohne Heizoption - zeigt, ab wann sich Heizen überhaupt lohnt."
)


@st.cache_data
def _temperatur_sweep(namen: tuple[str, ...], distanzen: tuple[float, ...], kap: float, basis: float, start_soc: float) -> list[dict]:
    zeilen = []
    for t in range(20, -21, -2):
        mit = _route_planen(namen, distanzen, float(t), kap, basis, start_soc, True)
        ohne = _route_planen(namen, distanzen, float(t), kap, basis, start_soc, False)
        if mit.erreichbar and ohne.erreichbar:
            zeilen.append({"temperatur": t, "mit_heizen": mit.netzenergie_gesamt_kwh, "ohne_heizen": ohne.netzenergie_gesamt_kwh})
    return zeilen


sweep = _temperatur_sweep(tuple(STANDARD_NAMEN), tuple(STANDARD_DISTANZEN), float(kapazitaet), float(basisverbrauch), fahrzeug.start_soc_kwh)
if sweep:
    fig_sweep = go.Figure()
    fig_sweep.add_trace(go.Scatter(x=[z["temperatur"] for z in sweep], y=[z["ohne_heizen"] for z in sweep], mode="lines+markers", name="ohne Heizen", line=dict(color="#8A96A6")))
    fig_sweep.add_trace(go.Scatter(x=[z["temperatur"] for z in sweep], y=[z["mit_heizen"] for z in sweep], mode="lines+markers", name="mit Heizen", line=dict(color="#3E8E86")))
    fig_sweep.update_layout(title="Netzenergie für die ganze Strecke, je nach Außentemperatur", xaxis_title="Außentemperatur (°C)", yaxis_title="Netzenergie gesamt (kWh)", height=420, xaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_sweep, width="stretch")
    ersparnis_bei_kaelte = next((z["ohne_heizen"] - z["mit_heizen"] for z in sweep if z["temperatur"] == -20), None)
    ersparnis_bei_mild = next((z["ohne_heizen"] - z["mit_heizen"] for z in sweep if z["temperatur"] == 10), None)
    if ersparnis_bei_kaelte is not None and ersparnis_bei_mild is not None:
        st.caption(
            f"Bei -20 °C spart Heizen {ersparnis_bei_kaelte:.1f} kWh auf dieser Strecke "
            f"({ersparnis_bei_kaelte / next(z['ohne_heizen'] for z in sweep if z['temperatur'] == -20) * 100:.1f} % weniger Netzenergie), "
            f"bei +10 °C nur noch {ersparnis_bei_mild:.1f} kWh - der Effekt wächst mit der Kälte, ist in milden Wintern aber gering."
        )

with st.expander("📐 Modellannahmen und Quellen"):
    st.markdown(
        f"""
- **Verbrauch bei Kälte**: AAA-Wintertest 2025 (Chevrolet Equinox EV, Tesla Model Y, Ford Mustang Mach-E) - bei -6,6 °C im Schnitt 35,6 % geringere Effizienz. Referenztemperatur 20 °C, linear zunehmender Mehrverbrauch darunter, kein Effekt oberhalb.
- **Ladewirkungsgrad bei Kälte**: Innenwiderstand von Li-Ion-Zellen bei -20 °C nachweislich etwa 3-mal so hoch wie bei Raumtemperatur (mehrere Studien zu Zellen bei tiefen Temperaturen) - mehr Widerstand heißt mehr ohmscher Verlust je geladener kWh. Kalibriert auf {ETA_WARM * 100:.0f} % bei ≥20 °C und {ETA_KALT * 100:.0f} % bei -20 °C, linear dazwischen - die Literatur belegt Richtung und Größenordnung, nicht exakt diese Kurve.
- **Ladeleistung/-zeit bei Kälte** (hier nicht Teil der Optimierung): Idaho National Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500 Schnellladevorgänge) - bei 0 °C nach gleicher Ladezeit 36 % weniger Ladestand als bei 25 °C, Schnellladen bis zu 3-mal langsamer. Das ist überwiegend ein Leistungseffekt (die Ladesteuerung drosselt den Strom zum Zellschutz), kein reiner Energie-Effizienz-Effekt - deshalb bewusst getrennt von der Wirkungsgrad-Kurve oben.
- **Vereinfachung**: die Batterie nimmt beim Fahren eines Abschnitts dessen Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte); heizen lässt sich nur unmittelbar vor einem Stopp, aus dem eigenen Akkustand, ohne Leistungsgrenze (nur die Energiebilanz zählt).
- **Strecke und Fahrzeug**: Positionen und Distanzen der Ladesäulen sind fest vorgegeben (keine Streckenwahl) - nur Lademenge und Heizdauer an jeder Säule sind die Entscheidung. Werte für Kapazität und Verbrauch orientieren sich an einem typischen E-Lieferfahrzeug (z. B. Mercedes eSprinter, VW ID. Buzz Cargo), frei einstellbar in der Seitenleiste.
- **Algorithmus**: dynamische Programmierung über (Haltepunkt, Akkustand), diskretisiert in {300} Stufen, mit einer feinen Rastersuche über die Heizmenge an jedem Stopp (siehe `planung.py`). Gegen eine deutlich feinere Auflösung geprüft (`tests/test_planung.py`): Abweichung unter 3 %.
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
    "- Modell und Algorithmus (ressourcenbeschränkter kürzester Weg: Akkustand als Ressource, "
    "dynamische Programmierung über diskretisierte Zustände) folgen demselben Muster wie die "
    "**[Kürzeste-Wege-Linie](https://sebastianhanisch.net/konzepte-kuerzeste-wege.html)** der Konzepte-Reihe."
)

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) - "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für Ihr "
    "Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
