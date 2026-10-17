"""Ladekurve und Ladezeit: wie schnell lädt das Fahrzeug an einer Schnellladesäule - abhängig vom
Akkustand (Taper) und von der Batterietemperatur. Reine Funktionen, keine Optimierung (siehe
lade_planung.py).

Aufbau: Die Ladeleistung ist das Produkt aus drei Faktoren,

    P(Ladestand, T_Batt) = P_max · f(Ladestand) · g(T_Batt)

mit der maximalen Ladeleistung P_max (Fahrzeug an der Säule), der Leistungskurve f über den
Ladestand-Anteil (1 bis zum Taper-Beginn, danach linear fallend) und dem Temperaturfaktor g. Weil g nur
multiplikativ wirkt, ist die Ladezeit von s_von auf s_bis

    t = Q / P_max · (τ(s_bis / Q) − τ(s_von / Q)) / g(T_Batt),      τ(x) = ∫₀ˣ dx' / f(x')

mit einer geschlossenen Stammfunktion τ - ohne numerische Integration und vektorisierbar.

Kalibrierung - was belegt ist und was Annahme bleibt:

- Temperaturfaktor g: Idaho National Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500
  DC-Schnellladevorgänge) - bei 0 °C nach derselben Ladezeit 36 % weniger Ladestand als bei 25 °C,
  Schnellladen kann bis zu 3-mal länger dauern. Hier: g = 1 bei ≥ 20 °C und 1/3 bei -20 °C, linear
  dazwischen (g(0 °C) = 2/3). Das ist eine Näherung der Größenordnung, die Literatur belegt nicht genau diese
  Kurve; die 36 % gelten für einen Ladestand nach fester Zeit, nicht für die Momentanleistung.
- Leistungskurve f: Dass DC-Laden oberhalb von etwa 80 % Ladestand die Leistung reduziert, ist
  gut belegt (Messreihe an 62 Fahrzeugen, 10-90 % Ladestand: MDPI Batteries 2025, 11(11), 394). Wie
  stark, hängt vom Fahrzeug ab. Hier ANNAHME: Taper-Beginn bei 80 %, Leistung fällt linear auf 20 % bei
  100 % Ladestand. Keine Messkurve eines bestimmten Fahrzeugs.
- Maximale Ladeleistung der Fahrzeugtypen: Größenordnungen aus Herstellerangaben - eSprinter optional
  115 kW DC (10-80 % in etwa 42 min bei 113 kWh), eCitaro 150 kW per Stecker und 300 kW per Pantograph,
  eActros 600 bis 400 kW per CCS (Megawatt-Laden MCS bis 1000 kW ist als Option angekündigt). Der Pkw-Wert
  (150 kW) ist eine Annahme.
- Temperatur der Batterie beim Laden: vereinfachend konstant über den ganzen Ladehalt (die Zellen
  erwärmen sich beim Laden in der Realität etwas, das ist nicht modelliert).
"""

from __future__ import annotations

import numpy as np

LADELEISTUNG_KW_STANDARD = 115.0  # eSprinter, optionaler DC-Lader (Standardfahrzeug der Demo ist der Lieferwagen)
STOPP_PAUSCHALE_H_STANDARD = 5.0 / 60.0  # Anfahrt, Anstecken, Freigabe - ANNAHME, nur bei tatsächlichem Laden

TAPER_BEGINN_ANTEIL = 0.8  # ANNAHME: bis 80 % Ladestand volle Leistung
TAPER_ENDLEISTUNG_ANTEIL = 0.2  # ANNAHME: bei 100 % Ladestand noch 20 % der Maximalleistung

T_LADELEISTUNG_WARM_C = 20.0
T_LADELEISTUNG_KALT_C = -20.0
LADELEISTUNG_FAKTOR_KALT = 1.0 / 3.0  # INL: Schnellladen bis zu 3-mal länger bei Kälte

_TAPER_STEIGUNG = (1.0 - TAPER_ENDLEISTUNG_ANTEIL) / (1.0 - TAPER_BEGINN_ANTEIL)


def ladeleistung_temperaturfaktor(batterietemperatur_c):
    """Anteil der Normalleistung, den die Ladesteuerung bei dieser Batterietemperatur freigibt: 1 bei
    ≥ 20 °C, 1/3 bei ≤ -20 °C, linear dazwischen (Skalar oder numpy-Array)."""
    t = np.clip(batterietemperatur_c, T_LADELEISTUNG_KALT_C, T_LADELEISTUNG_WARM_C)
    anteil = (t - T_LADELEISTUNG_KALT_C) / (T_LADELEISTUNG_WARM_C - T_LADELEISTUNG_KALT_C)
    return LADELEISTUNG_FAKTOR_KALT + anteil * (1.0 - LADELEISTUNG_FAKTOR_KALT)


def ladeleistung_soc_faktor(soc_anteil):
    """Leistungskurve f(x) über den Ladestand-Anteil x ∈ [0, 1]: 1 bis zum Taper-Beginn, danach linear
    fallend auf TAPER_ENDLEISTUNG_ANTEIL bei x = 1."""
    x = np.clip(soc_anteil, 0.0, 1.0)
    return np.where(x <= TAPER_BEGINN_ANTEIL, 1.0, 1.0 - _TAPER_STEIGUNG * (x - TAPER_BEGINN_ANTEIL))


def ladezeit_integral(soc_anteil):
    """τ(x) = ∫₀ˣ dx' / f(x'): Ladezeit in Einheiten Q/P_max bis zum Ladestand-Anteil x bei
    Normalleistung. Geschlossen: linear bis zum Taper-Beginn, danach -ln(1 - a·(x - x₀)) / a."""
    x = np.clip(soc_anteil, 0.0, 1.0)
    linear = np.minimum(x, TAPER_BEGINN_ANTEIL)
    taper = np.maximum(x - TAPER_BEGINN_ANTEIL, 0.0)
    return linear - np.log(1.0 - _TAPER_STEIGUNG * taper) / _TAPER_STEIGUNG


def ladezeit_h(
    von_kwh,
    bis_kwh,
    kapazitaet_kwh: float,
    ladeleistung_kw: float,
    batterietemperatur_c,
    pauschale_h: float = 0.0,
):
    """Dauer in Stunden, um den Akku von `von_kwh` auf `bis_kwh` zu laden (Skalare oder numpy-Arrays,
    die zueinander broadcastbar sind). Ohne Ladebedarf (bis ≤ von) ist die Dauer 0 - die Stopp-Pauschale
    fällt nur an, wenn tatsächlich geladen wird."""
    von = np.asarray(von_kwh, dtype=float)
    bis = np.asarray(bis_kwh, dtype=float)
    reine_zeit = (
        (ladezeit_integral(bis / kapazitaet_kwh) - ladezeit_integral(von / kapazitaet_kwh))
        * kapazitaet_kwh
        / ladeleistung_kw
        / ladeleistung_temperaturfaktor(batterietemperatur_c)
    )
    ergebnis = np.where(bis - von > 1e-9, reine_zeit + pauschale_h, 0.0)
    return float(ergebnis) if ergebnis.ndim == 0 else ergebnis
