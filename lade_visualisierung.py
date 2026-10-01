"""Plotly-Diagramme der App - getrennt von der Streamlit-Oberfläche (siehe z. B. dj_visualization.py
der Dijkstra-Demo), damit app.py reine Oberflächen-Orchestrierung bleibt."""

from __future__ import annotations

import plotly.graph_objects as go

from lade_modell import Fahrzeug, Strecke
from lade_planung import Ergebnis

FARBE_AKKU = "#3E8E86"
FARBE_GRENZE = "#D68A2E"
FARBE_HALTEPUNKT = "#8A96A6"
FARBE_OHNE_HEIZEN = "#8A96A6"
FARBE_MIT_HEIZEN = "#3E8E86"


def soc_verlauf_figur(strecke: Strecke, fahrzeug: Fahrzeug, ergebnis: Ergebnis) -> go.Figure:
    """Akkustand über die Strecke: fällt beim Fahren, bricht vor einem Stopp zusätzlich ein, wenn dort
    geheizt wurde, springt beim Laden wieder hoch."""
    x = [0.0]
    y = [fahrzeug.start_soc_kwh]
    kumulierte_distanz = 0.0
    for i, stopp in enumerate(ergebnis.stopps):
        kumulierte_distanz += strecke.segmente[i].distanz_km
        x += [kumulierte_distanz, kumulierte_distanz, kumulierte_distanz]
        y += [stopp.ankunft_soc_kwh, stopp.ankunft_soc_kwh - stopp.heiz_energie_kwh, stopp.abfahrt_soc_kwh]
    kumulierte_distanz += strecke.segmente[-1].distanz_km
    x.append(kumulierte_distanz)
    y.append(ergebnis.ankunft_ziel_soc_kwh)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=FARBE_AKKU, width=3), name="Akkustand"))
    fig.add_hline(y=0, line_dash="dot", line_color=FARBE_GRENZE)
    kumuliert = 0.0
    for i, name in enumerate(strecke.namen):
        fig.add_vline(x=kumuliert, line_dash="dot", line_color=FARBE_HALTEPUNKT)
        fig.add_annotation(x=kumuliert, y=fahrzeug.kapazitaet_kwh, text=name, showarrow=False, textangle=-40, font=dict(size=10), xanchor="left")
        if i < len(strecke.segmente):
            kumuliert += strecke.segmente[i].distanz_km
    fig.update_layout(
        title="Akkustand über die Strecke (Einbruch vor einem Ladestopp = Heizen während der Fahrt)",
        xaxis_title="Strecke (km)", yaxis_title="Akkustand (kWh)", height=420, margin=dict(t=60, b=10),
    )
    return fig


def temperatur_sweep_figur(sweep: list[dict]) -> go.Figure:
    """Netzenergie der ganzen Strecke über die Außentemperatur, mit und ohne Heizoption."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[z["temperatur"] for z in sweep], y=[z["ohne_heizen"] for z in sweep], mode="lines+markers", name="ohne Heizen", line=dict(color=FARBE_OHNE_HEIZEN)))
    fig.add_trace(go.Scatter(x=[z["temperatur"] for z in sweep], y=[z["mit_heizen"] for z in sweep], mode="lines+markers", name="mit Heizen", line=dict(color=FARBE_MIT_HEIZEN)))
    fig.update_layout(
        title="Netzenergie für die ganze Strecke, je nach Außentemperatur",
        xaxis_title="Außentemperatur (°C)", yaxis_title="Netzenergie gesamt (kWh)", height=420, xaxis=dict(autorange="reversed"),
    )
    return fig
