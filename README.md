# Ladestrategie: E-Lieferfahrzeug im Winter – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-ladestrategie-demo.streamlit.app/)**

Fall-Demo (Transport & Tourenplanung) für die Website "Sebastian Hanisch – Operations Research und
Machine Learning": ein E-Lieferfahrzeug fährt eine Strecke mit **frei einstellbaren**
Schnellladesäulen-Positionen (Anzahl, Abstände und Start frei wählbar, drei Beispielstrecken als
Schnellstart). Entschieden wird an jeder Säule, wie viel geladen und wie lange während der Fahrt
vorher geheizt wird. Kälte erhöht den Verbrauch beim Fahren und senkt den Ladewirkungsgrad; Heizen
kostet selbst Energie, kann sich aber lohnen. Gesucht ist die Strategie mit dem geringsten
Netzenergieverbrauch über die ganze Strecke.

## Warum dieses Problem

Reichweite und Ladestopps für Elektrofahrzeuge sind im Portfolio nicht neu (`fernverkehr-demo`), aber
bisher ohne Temperatureffekt gerechnet. Zwei reale, in unabhängigen Studien belegte Effekte fehlten:
Kälte erhöht den Verbrauch beim Fahren **und** verschlechtert den Ladewirkungsgrad (kalte Zellen haben
mehr Innenwiderstand, mehr Ladeenergie geht als Wärme verloren). Das öffnet eine echte Entscheidung,
die es ohne Temperatureffekt nicht gäbe: lohnt es sich, während der Fahrt Akkuenergie in die
Vorwärmung der Batterie zu stecken, damit an der nächsten Säule weniger verloren geht? Die Antwort ist
nicht immer Ja – bei milder Kälte, wenig Ladebedarf oder zu wenig Zeit/Heizleistung kostet das Heizen
mehr, als es einspart, oder reicht schlicht nicht aus.

## Modell

- **Strecke**: Abfolge aus Start, Schnellladesäulen und Ziel – Anzahl der Säulen (1–6), Name des Starts
  und Distanz jedes Abschnitts sind frei einstellbar, ebenso drei Beispielstrecken zum Schnellstart.
  Während der Optimierung selbst liegt die Strecke fest – keine Streckenwahl, nur Lade-/Heizentscheidungen
  an jeder Säule.
- **Verbrauch bei Kälte**: AAA-Wintertest 2025 (Chevrolet Equinox EV, Tesla Model Y, Ford Mustang
  Mach-E) – bei -6,6 °C im Schnitt 35,6 % geringere Effizienz. Referenztemperatur 20 °C, linear
  zunehmender Mehrverbrauch darunter.
- **Ladewirkungsgrad bei Kälte**: Innenwiderstand von Li-Ion-Zellen bei -20 °C nachweislich etwa 3-mal
  so hoch wie bei Raumtemperatur (mehrere Studien zu Zellen bei tiefen Temperaturen) – kalibriert auf
  95 % bei ≥20 °C und 80 % bei -20 °C, linear dazwischen. Die Literatur belegt Richtung und
  Größenordnung des Effekts, nicht exakt diese Kurve.
- **Ladeleistung/-zeit bei Kälte** (nicht Teil der Optimierung, nur zur Einordnung): Idaho National
  Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500 Schnellladevorgänge) – bei 0 °C nach
  gleicher Ladezeit 36 % weniger Ladestand als bei 25 °C, Schnellladen bis zu 3-mal langsamer. Das ist
  überwiegend ein Leistungseffekt (die Ladesteuerung drosselt den Strom zum Zellschutz), kein reiner
  Energie-Effizienz-Effekt – deshalb bewusst getrennt vom Ladewirkungsgrad oben.
- **Heizen während der Fahrt**: entnimmt Energie aus dem eigenen Akku und erhöht die Batterietemperatur,
  begrenzt durch zwei reale Grenzen statt beliebig schneller, unbegrenzter Erwärmung:
  - die **Heizleistung** (3–8 kW typisch für große Batteriepakete, z. B. Tesla Model 3 mit 6 kW als
    Standardwert) begrenzt, wie schnell Energie überhaupt zugeführt werden kann, und
  - der **Wärmeverlust an die kalte Außenluft** während des Heizens führt zu einer exponentiellen
    Annäherung an eine Gleichgewichtstemperatur statt eines linearen Anstiegs (Newtonsches
    Abkühlungsgesetz rückwärts). Die thermische Zeitkonstante (9 Stunden) ist ein Erfahrungswert aus
    einer realen Abkühlkurve einer Nissan-LEAF-Fallstudie.

  Die verfügbare Heizdauer ergibt sich aus der Fahrzeit des vorangehenden Abschnitts (Distanz durch
  Geschwindigkeit, ebenfalls einstellbar). Vereinfachung: die Batterie nimmt beim Fahren eines
  Abschnitts dessen Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte hinweg) – Heizen
  wirkt nur im unmittelbar vorangehenden Abschnitt.

**Modellzuordnung**: ressourcenbeschränkter kürzester Weg – der Akkustand ist die Ressource, in
SOC-Stufen diskretisiert. Dieselbe Problemfamilie wie die Kürzeste-Wege-Linie der Konzepte-Reihe.

## Methodik

Dynamische Programmierung über (Haltepunkt, Akkustand): je Ladestopp wird über eine feine,
numpy-vektorisierte Rastersuche über Heizdauer und Lademenge die energieminimale Kombination gesucht
(`kosten_bei_stopp` / `_kosten_batch` in `lade_planung.py`), die äußere DP (`plane_route`) verkettet
das über alle Stopps zur global energieminimalen Strategie. Exakt bis auf die Diskretisierung – gegen
eine deutlich feinere Auflösung geprüft (`tests/test_lade_planung.py`), Abweichung unter 3 %.

## Dateien

Struktur und Namenskonvention (`lade_*`-Präfix) folgen dem übrigen Demo-Portfolio (siehe z. B.
`dj_*` der Dijkstra-Demo oder `vrp_*` der VRP-Demo):

- `lade_constants.py` – Regler-Wertebereiche, Standardwerte und die drei Beispielstrecken (Presets)
- `lade_modell.py` – physikalisches Modell: temperaturabhängiger Verbrauch, temperaturabhängiger
  Ladewirkungsgrad, zeit-/leistungsbegrenzte Batterieheizung, Datenklassen für Fahrzeug und Strecke
- `lade_planung.py` – dynamische Programmierung über (Haltepunkt, Akkustand) mit lokaler,
  vektorisierter Heiz-/Ladesuche an jedem Stopp
- `lade_szenario.py` – baut die `Strecke` aus Start/Etappen/Temperatur und verwaltet den Session State
  der frei einstellbaren Route (Presets, Anzahl Ladesäulen, Distanzen)
- `lade_visualisierung.py` – Plotly-Diagramme (Akkustand über die Strecke, Netzenergie über die
  Außentemperatur)
- `app.py` – reine Streamlit-Oberflächen-Orchestrierung
- `tests/` – Korrektheitstests (Energiebilanz an jedem Stopp, Heizen nie schlechter als ohne Heizen,
  Diskretisierungs-Konvergenz, Batch-/Einzelsuche stimmen überein, AppTest-Smoke-Tests für Presets und
  die konfigurierbare Route)

## Zusammenhänge zu anderen Stücken des Portfolios

- **[Fernverkehr: Lenkzeiten und Elektro-Lkw](https://sebastianhanisch-fernverkehr-demo.streamlit.app/)**
  hat bereits feste Ladesäulen, Reichweite und Ladestopps für Elektro-Lkw – dort geht es aber um die
  Tourkosten mehrerer Fahrzeuge unter Fahrerregeln, mit Laden proportional zur Energie und ohne
  Temperatureffekt. Diese Demo ergänzt genau das Fehlende: eine einzelne Strecke, energieminimal, mit
  Temperaturphysik bei Verbrauch **und** Ladewirkungsgrad – kein Duplikat, sondern die thermische
  Tiefe, die dort bewusst außen vor blieb.
- **[Zentralität](https://sebastianhanisch-centrality-demo.streamlit.app/)** und
  **[Strukturkennzahlen und Nullmodelle](https://sebastianhanisch-strukturkennzahlen-demo.streamlit.app/)**
  sind die anderen Analyse-Karten der Graphen-und-Netzwerke-Linie – dieselbe Grundidee (eine Kennzahl
  berechnen und interpretieren, kein Verfahrensvergleich), andere Kennzahlen.
- Modell und Algorithmus (ressourcenbeschränkter kürzester Weg: Akkustand als Ressource, dynamische
  Programmierung über diskretisierte Zustände) folgen demselben Muster wie die
  **[Kürzeste-Wege-Linie](https://sebastianhanisch.net/konzepte-kuerzeste-wege.html)** der
  Konzepte-Reihe.

## Lokal ausführen

```
pip install -r requirements.txt
streamlit run app.py
```

## Verifikation

```
pip install pytest numpy
pytest
```

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) –
Operations Research und Machine Learning.
