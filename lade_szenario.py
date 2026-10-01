"""Baut eine Strecke aus Start, Etappen (Ladesäule oder Ziel, mit Distanz) und einer einheitlichen
Außentemperatur - sowohl für die frei einstellbare Route als auch für die Presets aus
lade_constants.py. Die Session-State-Funktionen unten folgen demselben Muster wie im übrigen
Demo-Portfolio (siehe z. B. dj_presets.py der Dijkstra-Demo): Widgets lesen/schreiben nur über ihren
`key` in st.session_state, nie über ein zusätzliches `value=` - sonst der bekannte Streamlit-Warnhinweis
bei gleichzeitig gesetztem `value` und belegtem Session-State-Key."""

from __future__ import annotations

import streamlit as st

from lade_constants import DISTANZ_MIN, PRESET_NAMEN, PRESETS
from lade_modell import Segment, Strecke


def baue_strecke(start_name: str, etappen: list[tuple[str, float]], temperatur_c: float) -> Strecke:
    """`etappen`: Liste aus (Name, Distanz_km), in Fahrtrichtung - der letzte Eintrag ist das Ziel,
    alle davor sind Ladesäulen. Dieselbe Außentemperatur gilt für die ganze Strecke (ein Regler)."""
    namen = [start_name] + [name for name, _ in etappen]
    segmente = [Segment(distanz_km=distanz, temperatur_c=temperatur_c) for _, distanz in etappen]
    return Strecke(namen=namen, segmente=segmente)


def _distanz_key(i: int) -> str:
    return f"distanz_{i}"


def init_session_state_defaults() -> None:
    """Einmalig beim ersten Laden: Start-Preset in den Session State."""
    if "anzahl_saeulen_slider" in st.session_state:
        return
    anwenden_preset(PRESET_NAMEN[0])


def anwenden_preset(name: str) -> None:
    """on_click-Callback der Preset-Knöpfe: überschreibt Start, Namen und Distanzen direkt im
    Session State - die Widgets übernehmen das beim nächsten Zeichnen über ihren `key`."""
    preset = PRESETS[name]
    st.session_state["start_name"] = preset["start"]
    st.session_state["anzahl_saeulen_slider"] = len(preset["etappen"]) - 1
    for i, (etappen_name, distanz) in enumerate(preset["etappen"]):
        st.session_state[_distanz_key(i)] = distanz
    st.session_state["etappen_namen"] = [n for n, _ in preset["etappen"]]


def etappen_namen_fuer(anzahl_saeulen: int) -> list[str]:
    """Passt die gemerkten Etappen-Namen an eine (ggf. von Hand geänderte) Säulenzahl an: behält
    vorhandene Namen, ergänzt generische ('Ladesäule n') für neue, das letzte Element ist immer
    'Ziel'. Wird aufgerufen, NACHDEM der Anzahl-Regler gezeichnet wurde, aber BEVOR die
    Distanz-Widgets gezeichnet werden."""
    bisherige = [n for n in st.session_state.get("etappen_namen", []) if n != "Ziel"]
    namen = (bisherige + [f"Ladesäule {i + 1}" for i in range(len(bisherige), anzahl_saeulen)])[:anzahl_saeulen]
    namen.append("Ziel")
    st.session_state["etappen_namen"] = namen
    for i in range(anzahl_saeulen + 1):
        key = _distanz_key(i)
        if key not in st.session_state:
            st.session_state[key] = float(DISTANZ_MIN) * 3  # ein unauffaelliger, sicher zulaessiger Startwert
    return namen
