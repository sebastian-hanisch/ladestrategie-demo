"""Verbrauchsminimale Streckenplanung für ein Elektrofahrzeug (Pkw, Lieferwagen, Bus, Lkw) - Streamlit-Demo.

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
    HEIZLEISTUNG_MAX,
    HEIZLEISTUNG_MIN,
    KAPAZITAET_MAX,
    KAPAZITAET_MIN,
    FAHRZEUGTYP_NAMEN,
    PRESET_NAMEN,
    START_SOC_PROZENT_MAX,
    START_SOC_PROZENT_MIN,
    START_SOC_PROZENT_STANDARD,
    TEMPERATUR_MAX,
    TEMPERATUR_MIN,
    TEMPERATUR_STANDARD,
    VERBRAUCH_MAX,
    VERBRAUCH_MIN,
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
    anwenden_fahrzeugtyp,
    anwenden_preset,
    baue_strecke,
    etappen_namen_fuer,
    init_session_state_defaults,
)
from lade_visualisierung import soc_verlauf_figur, temperatur_sweep_figur

st.set_page_config(page_title="Ladestrategie: Elektrofahrzeug im Winter", page_icon="🔋", layout="wide")

init_session_state_defaults()

st.title("🔋 Ladestrategie: Elektrofahrzeug im Winter")
st.caption("Fall-Demo (Transport & Tourenplanung) von sebastianhanisch.net - echte Studienwerte, keine frei erfundene Physik.")

st.markdown(
    "Ein Elektrofahrzeug - Pkw, Lieferwagen, Bus oder Lkw - fährt eine Strecke mit **frei einstellbaren** Schnellladesäulen-Positionen. "
    "Entschieden wird an jeder Säule nur: **wie viel laden, und wie lange vorher heizen?** Kälte erhöht "
    "den Verbrauch beim Fahren UND senkt den Ladewirkungsgrad (kalte Zellen haben mehr Innenwiderstand) "
    "- Heizen kostet selbst Energie, kann sich aber lohnen, wenn es an der nächsten Säule genug "
    "Ladeverlust erspart. Gesucht ist die Strategie, die **insgesamt am wenigsten Energie aus dem Netz "
    "zieht**, nicht die schnellste."
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
preset_col1, preset_col2, preset_col3 = st.columns(3)
for preset_col, name in zip((preset_col1, preset_col2, preset_col3), PRESET_NAMEN):
    with preset_col:
        st.button(name, on_click=anwenden_preset, args=(name,), width="stretch")

st.caption("🚗 Fahrzeugtyp wählen (setzt Kapazität, Verbrauch, Heizleistung und Geschwindigkeit):")
fahrzeug_cols = st.columns(len(FAHRZEUGTYP_NAMEN))
for fahrzeug_col, name in zip(fahrzeug_cols, FAHRZEUGTYP_NAMEN):
    with fahrzeug_col:
        st.button(name, on_click=anwenden_fahrzeugtyp, args=(name,), width="stretch", key=f"fahrzeugtyp_{name}")

with st.sidebar:
    st.header("Strecke")
    st.caption("Eigene Strecke")
    anzahl_saeulen = st.slider("Anzahl Ladesäulen", ANZAHL_SAEULEN_MIN, ANZAHL_SAEULEN_MAX, key="anzahl_saeulen_slider")
    etappen_namen = etappen_namen_fuer(anzahl_saeulen)
    start_name = st.text_input("Start", key="start_name")
    distanzen = [st.number_input(f"Strecke zu {name} (km)", DISTANZ_MIN, DISTANZ_MAX, key=f"distanz_{i}", step=5.0) for i, name in enumerate(etappen_namen)]

    st.header("Fahrzeug & Wetter")
    temperatur = st.slider("Außentemperatur (°C)", TEMPERATUR_MIN, TEMPERATUR_MAX, TEMPERATUR_STANDARD, key="temperatur_slider", help="Gilt einheitlich für die ganze Strecke.")
    kapazitaet = st.slider("Batteriekapazität (kWh)", KAPAZITAET_MIN, KAPAZITAET_MAX, step=5, key="kapazitaet_slider", help="Pkw ca. 50-100 kWh, Lieferwagen ca. 55-115 kWh, Elektrobus bis ca. 600 kWh, Elektro-Lkw ca. 400-620 kWh. Die Wärmekapazität des Zellpakets wächst proportional mit.")
    basisverbrauch = st.slider("Basisverbrauch bei 20 °C (kWh/km)", VERBRAUCH_MIN, VERBRAUCH_MAX, step=0.01, key="verbrauch_slider")
    start_soc_anteil = st.slider("Akkustand am Start (%)", START_SOC_PROZENT_MIN, START_SOC_PROZENT_MAX, START_SOC_PROZENT_STANDARD, step=5, key="start_soc_slider")
    geschwindigkeit = st.slider("Geschwindigkeit (km/h)", GESCHWINDIGKEIT_MIN, GESCHWINDIGKEIT_MAX, key="geschwindigkeit_slider", help="Bestimmt, wie viel Zeit während eines Abschnitts fürs Heizen bleibt.")
    heizleistung = st.slider("Heizleistung (kW)", HEIZLEISTUNG_MIN, HEIZLEISTUNG_MAX, step=0.5, key="heizleistung_slider", help="Typisch 3-8 kW für Pkw-Pakete (z. B. Tesla Model 3: 6 kW). Bei Bus und Lkw ist eine proportional größere Heizleistung angenommen (kein Herstellerwert).")
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
    "Dieselbe Strecke, fest durchgerechnet für jede Temperatur von -20 °C bis +20 °C, einmal mit und "
    "einmal ohne Heizoption - zeigt, ab wann sich Heizen überhaupt lohnt."
)


@st.cache_data
def _temperatur_sweep(namen: tuple[str, ...], distanzen: tuple[float, ...], kap: float, basis: float, start_soc: float, geschwindigkeit: float, heizleistung: float) -> list[dict]:
    zeilen = []
    for t in range(-20, 21, 2):
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
            f"bei +10 °C nur noch {ersparnis_bei_mild:.1f} kWh - der Effekt nimmt mit steigender Temperatur ab und ist in milden Wintern gering."
        )
else:
    st.info("Für diese Strecke/dieses Fahrzeug ist nicht jede Temperatur im Bereich erreichbar - der Vergleich wird übersprungen.")

with st.expander("📐 Modellannahmen und Quellen"):
    st.markdown(
        f"""
- **Verbrauch bei Kälte**: AAA-Wintertest 2025 (Chevrolet Equinox EV, Tesla Model Y, Ford Mustang Mach-E) - bei -6,6 °C im Schnitt 35,6 % geringere Effizienz. Referenztemperatur 20 °C, linear zunehmender Mehrverbrauch darunter, kein Effekt oberhalb.
- **Ladewirkungsgrad bei Kälte**: Innenwiderstand von Li-Ion-Zellen bei -20 °C nachweislich etwa 3-mal so hoch wie bei Raumtemperatur (mehrere Studien zu Zellen bei tiefen Temperaturen) - mehr Widerstand heißt mehr ohmscher Verlust je geladener kWh. Kalibriert auf {ETA_WARM * 100:.0f} % bei ≥20 °C und {ETA_KALT * 100:.0f} % bei -20 °C, linear dazwischen - die Literatur belegt Richtung und Größenordnung, nicht exakt diese Kurve.
- **Ladeleistung/-zeit bei Kälte** (hier nicht Teil der Optimierung): Idaho National Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500 Schnellladevorgänge) - bei 0 °C nach gleicher Ladezeit 36 % weniger Ladestand als bei 25 °C, Schnellladen bis zu 3-mal langsamer. Das ist überwiegend ein Leistungseffekt (die Ladesteuerung drosselt den Strom zum Zellschutz), kein reiner Energie-Effizienz-Effekt - deshalb bewusst getrennt von der Wirkungsgrad-Kurve oben.
- **Heizen während der Fahrt**: begrenzt durch die Heizleistung (3-8 kW bei Pkw-Paketen, z. B. Tesla Model 3 mit 6 kW - Standardwert hier; bei Bus und Lkw ist eine proportional größere Heizleistung angenommen, kein Herstellerwert) UND durch Wärmeverlust an die kalte Außenluft während des Heizens (exponentielle Annäherung an eine Gleichgewichtstemperatur, keine beliebig schnelle Erwärmung). Die thermische Zeitkonstante ({WAERMEVERLUST_ZEITKONSTANTE_H:.0f} Stunden) ist ein Erfahrungswert aus einer realen Abkühlkurve (Nissan-LEAF-Fallstudie), kein Laborwert - deutlich länger als eine einzelne Fahrstrecke, aber nicht vernachlässigbar bei langem Heizen.
- **Vereinfachung**: die Batterie nimmt beim Fahren eines Abschnitts dessen Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte hinweg) - Heizen wirkt nur im unmittelbar vorangehenden Abschnitt.
- **Strecke und Fahrzeug**: Anzahl und Distanzen der Ladesäulen sind frei einstellbar (links), aber während der Optimierung fest - keine Streckenwahl, nur Lademenge und Heizdauer an jeder Säule sind die Entscheidung. Die Fahrzeugtyp-Knöpfe oben setzen typische Größenordnungen: Pkw (60 kWh, 0,17 kWh/km), Lieferwagen (80 kWh, 0,32 kWh/km - Standardwert, orientiert an Mercedes eSprinter und VW ID. Buzz Cargo), Elektrobus (350 kWh, 1,3 kWh/km; der eCitaro hat bis zu 588 kWh) und Elektro-Lkw (620 kWh, 1,2 kWh/km, orientiert am Mercedes eActros 600). Der Busverbrauch ist eine Annahme.
- **Übertragbarkeit auf Nutzfahrzeuge**: Die Kalibrierungsquellen sind Pkw-Studien. Die Richtung der Effekte (Kälte erhöht den Verbrauch und senkt den Ladewirkungsgrad) hängt an der Li-Ion-Chemie und gilt für jedes Elektrofahrzeug, die Zahlenwerte übertragen sich nur näherungsweise: Der relative Kälte-Mehrverbrauch dürfte bei Bus und Lkw anders ausfallen (hier ungeprüft), und größere Pakete kühlen langsamer aus als die 9 Stunden der Pkw-Fallstudie (kleineres Oberfläche-zu-Volumen-Verhältnis) - die Zeitkonstante ist für sie eher konservativ. Die Wärmekapazität des Zellpakets wächst im Modell proportional zur Batteriekapazität (80 kWh ≙ 450 kg ≙ 0,125 kWh/K); bei gleicher Heizleistung erwärmt sich ein größeres Paket entsprechend langsamer.
- **Algorithmus**: dynamische Programmierung über (Haltepunkt, Akkustand), mit einer feinen Rastersuche über die Heizdauer an jedem Stopp (siehe `lade_planung.py`). Gegen eine deutlich feinere Auflösung geprüft (`tests/test_lade_planung.py`): Abweichung unter 3 %.
        """
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Gegeben:**

- Haltepunkte $0,\dots,n$ ($0$ = Start, $1,\dots,n-1$ = Ladesäulen, $n$ = Ziel), Segmente
  $j=1,\dots,n$ mit Distanz $d_j$ und einheitlicher Außentemperatur $T$
- Fahrzeug: Kapazität $Q$, Basisverbrauch $b$ (kWh/km bei 20 °C), Geschwindigkeit $v$,
  Heizleistung $P$, Segmentzeit $t_j = d_j / v$
- Verbrauch je km (`verbrauch_kwh_km`): $c(T) = b \cdot \big(1 + \alpha \max(0,\,20-T)\big)$,
  $\alpha$ AAA-kalibriert
- Ladewirkungsgrad (`ladewirkungsgrad`): linear zwischen $\eta_{kalt}=0{,}80$ bei $-20\,°C$ und
  $\eta_{warm}=0{,}95$ bei $\geq 20\,°C$
- Batterietemperatur nach Heizdauer $h$ bei Leistung $P$ (`batterietemperatur_nach_heizen`),
  geschlossene Lösung der Wärme-ODE $\tfrac{dT_{batt}}{dt} = r - k(T_{batt}-T)$:
"""
    )
    st.latex(
        r"T_{batt}(h) = T + \frac{r}{k}\big(1 - e^{-kh}\big), "
        r"\qquad r = \frac{P \cdot \eta_{heiz}}{C}, \qquad k = \frac{1}{\tau}"
    )
    st.markdown(
        r"""
mit Heiz-Wirkungsgrad $\eta_{heiz}=0{,}9$, Wärmekapazität $C = c_Q \cdot Q$ (proportional zur
Batteriekapazität, $c_Q = 0{,}125/80\;\mathrm{kWh/(K \cdot kWh)}$, `waermekapazitaet_kwh_pro_grad`) und thermischer Zeitkonstante
$\tau = 9\,$h (Quellen siehe oben) - $T_{batt}(h)$ nähert sich für $h\to\infty$ der
Gleichgewichtstemperatur $T + r/k$ an, statt unbegrenzt zu steigen.

**Zustand:** Akkustand $s \in [0,Q]$, diskretisiert in $K+1$ gleich breite Stufen (`soc_aufloesung`,
Standard $K=300$) - ein Schichten-DAG mit einer Schicht je Haltepunkt, exakt bis auf diese
Diskretisierung.

**Entscheidung an Ladesäule $j$:** Heizdauer $h_j \in [0,\bar h_j]$ mit
$\bar h_j = \min\!\big(t_j,\; s_j^{ank}/P\big)$ (begrenzt durch Zeit UND verfügbare Akkuenergie),
sowie die Abfahrt-SOC-Stufe $s_j^{ab} \geq s_j^{ank}-P h_j$.

**Kostenfunktion an einem Stopp** (`kosten_bei_stopp` / `_kosten_batch`): die minimale aus dem Netz
gezogene Energie, um von Ankunft $s^{ank}$ auf Abfahrt $s^{ab}$ zu kommen, optimal über $h$ gesucht:
"""
    )
    st.latex(
        r"\mathrm{kosten}(s^{ank}, s^{ab}, T, t, P) = \min_{h \,\in\, [0,\bar h]} "
        r"\frac{\max\!\big(0,\; s^{ab} - (s^{ank} - Ph)\big)}{\eta\big(T_{batt}(h)\big)}"
    )
    st.markdown(
        r"""
Keine geschlossene Lösung für das optimale $h$: $\eta(T_{batt}(h))$ sättigt (Wärmeverlust), während
die benötigte Lademenge $s^{ab}-(s^{ank}-Ph)$ mit $h$ linear sinkt und bei $Ph=s^{ab}-s^{ank}$ auf
0 fällt - das Produkt ist nicht garantiert konvex in $h$, deshalb eine endliche Rastersuche
(`heiz_aufloesung`, Standard 400 Schritte) statt einer Ableitung.

**Bellman-Rekursion** (`plane_route`): $f_j(s)$ = minimale Netzenergie, um Haltepunkt $j$ mit
Akkustand $s$ zu erreichen, $f_0(s_0^{start})=0$ sonst $\infty$:
"""
    )
    st.latex(
        r"f_j(s^{ab}) = \min_{s \,:\, s^{ank}(s) \,\leq\, s^{ab}} \; "
        r"f_{j-1}(s) + \mathrm{kosten}\big(s^{ank}(s),\, s^{ab},\, T_j,\, t_j,\, P\big), "
        r"\qquad s^{ank}(s) = s - c(T_j)\, d_j"
    )
    st.markdown(
        r"""
am Ziel ($j=n$) entfällt die Ladeentscheidung (`ist_ziel`-Fall): $f_n(s^{ank}(s)) = \min\big(f_n(s^{ank}(s)),\, f_{n-1}(s)\big)$,
nur die Sicherheitsreserve muss erreicht werden. Gesucht ist die Gesamtlösung
"""
    )
    st.latex(r"\mathrm{netzenergie\_gesamt} = \min_{s} f_n(s)")
    st.markdown(
        r"""
**Modellzuordnung:** ressourcenbeschränkter kürzester Weg (resource-constrained shortest path) - der
Akkustand ist die Ressource, der Haltepunkt-Index die Schicht. Rückverfolgung über `herkunft[j][b]`
liefert den optimalen Pfad (Lade-/Heizentscheidung an jedem Stopp), analog zur Pfadrekonstruktion
bei einer gewöhnlichen Kürzeste-Wege-DP. Komplexität: $O(n \cdot K^2 \cdot H)$ (Haltepunkte ×
SOC-Stufen² × Heizauflösung) vor der numpy-Vektorisierung über $H$ in `_kosten_batch`.
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
