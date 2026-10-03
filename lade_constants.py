"""Regler-Wertebereiche, Standardwerte und Beispielstrecken (Presets) - eine Wahrheitsquelle, wie im
übrigen Demo-Portfolio (siehe z. B. dj_constants.py der Dijkstra-Demo)."""

TEMPERATUR_MIN, TEMPERATUR_MAX, TEMPERATUR_STANDARD = -20, 20, -5
KAPAZITAET_MIN, KAPAZITAET_MAX, KAPAZITAET_STANDARD = 20, 700, 80  # kWh - Pkw bis Elektro-Lkw/-Gelenkbus
VERBRAUCH_MIN, VERBRAUCH_MAX, VERBRAUCH_STANDARD = 0.10, 2.00, 0.32  # kWh/km
START_SOC_PROZENT_MIN, START_SOC_PROZENT_MAX, START_SOC_PROZENT_STANDARD = 50, 100, 100
GESCHWINDIGKEIT_MIN, GESCHWINDIGKEIT_MAX, GESCHWINDIGKEIT_STANDARD = 30, 130, 80
# kW; 3-8 kW sind für Pkw-Pakete belegt (siehe lade_modell.py), größere Pakete (Bus, Lkw) sind darüber
# hinaus mit proportional größerer Heizleistung angenommen - das sind Annahmen, keine Herstellerwerte.
HEIZLEISTUNG_MIN, HEIZLEISTUNG_MAX, HEIZLEISTUNG_STANDARD = 1.0, 60.0, 6.0
ANZAHL_SAEULEN_MIN, ANZAHL_SAEULEN_MAX, ANZAHL_SAEULEN_STANDARD = 1, 6, 3
DISTANZ_MIN, DISTANZ_MAX = 20.0, 300.0  # km, je Abschnitt

# Fahrzeugtypen: setzen Kapazität, Basisverbrauch, Heizleistung und Geschwindigkeit auf typische Größenordnungen.
# Kapazität/Verbrauch sind Richtwerte aus Herstellerangaben (Größenordnung, keine Messung der Demo):
# Mercedes eSprinter 113 kWh (auch 56/81 kWh), Mercedes eActros 600 621 kWh bei rund 1,2 kWh/km,
# Mercedes eCitaro bis 588 kWh. Der Busverbrauch (1,3 kWh/km) und die Heizleistungen für Bus und Lkw
# (Packgröße x etwa 0,07 kW/kWh wie beim Standardfahrzeug) sind Annahmen, keine Herstellerwerte.
# Das Standardfahrzeug (Lieferwagen) ist unverändert der bisherige Standard der Demo.
FAHRZEUGTYPEN = {
    "Pkw": dict(kapazitaet=60, verbrauch=0.17, heizleistung=6.0, geschwindigkeit=100),
    "Lieferwagen": dict(kapazitaet=KAPAZITAET_STANDARD, verbrauch=VERBRAUCH_STANDARD, heizleistung=HEIZLEISTUNG_STANDARD, geschwindigkeit=GESCHWINDIGKEIT_STANDARD),
    "Elektrobus": dict(kapazitaet=350, verbrauch=1.3, heizleistung=25.0, geschwindigkeit=60),
    "Elektro-Lkw": dict(kapazitaet=620, verbrauch=1.2, heizleistung=45.0, geschwindigkeit=80),
}
FAHRZEUGTYP_NAMEN = tuple(FAHRZEUGTYPEN)
STANDARD_FAHRZEUGTYP = "Lieferwagen"

# Jedes Preset: Startname, dann Etappen (Name, Distanz in km) - die letzte Etappe ist das Ziel, alle
# davor sind Ladesäulen. Generische Namen (kein realer Ort) - die Distanzen sind das, was zählt, nicht
# eine behauptete Geografie. Alle drei über den vollen Temperaturbereich (-20 °C bis +20 °C) mit dem
# Standardfahrzeug auf Erreichbarkeit geprüft.
PRESETS = {
    "Standardstrecke": {
        "start": "Start",
        "etappen": [("Ladesäule 1", 80.0), ("Ladesäule 2", 90.0), ("Ladesäule 3", 100.0), ("Ziel", 130.0)],
    },
    "Kurzstrecke, dicht besäult": {
        "start": "Start",
        "etappen": [("Ladesäule 1", 40.0), ("Ladesäule 2", 35.0), ("Ladesäule 3", 30.0), ("Ziel", 90.0)],
    },
    "Langstrecke, dünn besäult": {
        "start": "Start",
        "etappen": [("Ladesäule 1", 150.0), ("Ladesäule 2", 150.0), ("Ladesäule 3", 150.0), ("Ziel", 150.0)],
    },
}
PRESET_NAMEN = tuple(PRESETS)
