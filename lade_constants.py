"""Regler-Wertebereiche, Standardwerte und Beispielstrecken (Presets) - eine Wahrheitsquelle, wie im
übrigen Demo-Portfolio (siehe z. B. dj_constants.py der Dijkstra-Demo)."""

TEMPERATUR_MIN, TEMPERATUR_MAX, TEMPERATUR_STANDARD = -20, 20, -5
KAPAZITAET_MIN, KAPAZITAET_MAX, KAPAZITAET_STANDARD = 40, 120, 80
VERBRAUCH_MIN, VERBRAUCH_MAX, VERBRAUCH_STANDARD = 0.20, 0.50, 0.32
START_SOC_PROZENT_MIN, START_SOC_PROZENT_MAX, START_SOC_PROZENT_STANDARD = 50, 100, 100
GESCHWINDIGKEIT_MIN, GESCHWINDIGKEIT_MAX, GESCHWINDIGKEIT_STANDARD = 40, 130, 80
HEIZLEISTUNG_MIN, HEIZLEISTUNG_MAX, HEIZLEISTUNG_STANDARD = 3.0, 8.0, 6.0  # kW, 3-8 kW typisch (AAA/Fallstudien, siehe lade_modell.py)
ANZAHL_SAEULEN_MIN, ANZAHL_SAEULEN_MAX, ANZAHL_SAEULEN_STANDARD = 1, 6, 3
DISTANZ_MIN, DISTANZ_MAX = 20.0, 300.0  # km, je Abschnitt

# Jedes Preset: Startname, dann Etappen (Name, Distanz in km) - die letzte Etappe ist das Ziel, alle
# davor sind Ladesäulen. Generische Namen (kein realer Ort) - die Distanzen sind das, was zählt, nicht
# eine behauptete Geografie. Alle drei über den vollen Temperaturbereich (-20 °C bis +20 °C) mit dem
# Standardfahrzeug auf Erreichbarkeit geprüft.
PRESETS = {
    "Standardstrecke": {
        "start": "Depot",
        "etappen": [("Ladesäule 1", 80.0), ("Ladesäule 2", 90.0), ("Ladesäule 3", 100.0), ("Ziel", 130.0)],
    },
    "Kurzstrecke, dicht besäult": {
        "start": "Depot",
        "etappen": [("Ladesäule 1", 40.0), ("Ladesäule 2", 35.0), ("Ladesäule 3", 30.0), ("Ziel", 90.0)],
    },
    "Langstrecke, dünn besäult": {
        "start": "Depot",
        "etappen": [("Ladesäule 1", 150.0), ("Ladesäule 2", 150.0), ("Ladesäule 3", 150.0), ("Ziel", 150.0)],
    },
}
PRESET_NAMEN = tuple(PRESETS)
