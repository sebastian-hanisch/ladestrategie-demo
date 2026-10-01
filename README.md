# Ladestrategie: E-Lieferfahrzeug im Winter – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-ladestrategie-demo.streamlit.app/)**

Fall-Demo (Transport & Tourenplanung) für die Website "Sebastian Hanisch – Operations Research und
Machine Learning": ein E-Lieferfahrzeug fährt eine feste Strecke mit **gegebenen**
Schnellladesäulen-Positionen (keine Streckenwahl – die Standorte gibt es, wo sie gebaut wurden).
Entschieden wird an jeder Säule nur, wie viel geladen und wie viel vorher geheizt wird. Kälte erhöht
den Verbrauch beim Fahren und senkt den Ladewirkungsgrad; Heizen kostet selbst Energie, kann sich aber
lohnen. Gesucht ist die Strategie mit dem geringsten Netzenergieverbrauch über die ganze Strecke.

## Warum dieses Problem

Reichweite und Ladestopps für Elektrofahrzeuge sind im Portfolio nicht neu (`fernverkehr-demo`), aber
bisher ohne Temperatureffekt gerechnet. Zwei reale, in unabhängigen Studien belegte Effekte fehlten:
Kälte erhöht den Verbrauch beim Fahren **und** verschlechtert den Ladewirkungsgrad (kalte Zellen haben
mehr Innenwiderstand, mehr Ladeenergie geht als Wärme verloren). Das öffnet eine echte Entscheidung,
die es ohne Temperatureffekt nicht gäbe: lohnt es sich, vor einem Ladestopp Akkuenergie in die
Vorwärmung der Batterie zu stecken, damit an der Säule weniger verloren geht? Die Antwort ist nicht
immer Ja – bei milder Kälte oder wenig Ladebedarf kostet das Heizen mehr, als es einspart.

## Modell

- **Strecke**: feste Abfolge aus Start, Schnellladesäulen und Ziel mit gegebenen Distanzen – keine
  Streckenwahl, nur Lade-/Heizentscheidungen an jeder Säule.
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
- **Heizen**: entnimmt Energie aus dem eigenen Akku (vor einem Stopp), erhöht die Batterietemperatur
  entsprechend ihrer Wärmekapazität (~450 kg Zellpaket, spezifische Wärmekapazität ~1,0 kJ/(kg·K)) und
  verbessert dadurch den Ladewirkungsgrad an diesem Stopp. Vereinfachung: die Batterie nimmt beim
  Fahren eines Abschnitts dessen Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte),
  Heizen wirkt nur unmittelbar vor dem nächsten Stopp, ohne Leistungsgrenze (nur die Energiebilanz
  zählt).

**Modellzuordnung**: ressourcenbeschränkter kürzester Weg – der Akkustand ist die Ressource, in
SOC-Stufen diskretisiert. Dieselbe Problemfamilie wie die Kürzeste-Wege-Linie der Konzepte-Reihe.

## Methodik

Dynamische Programmierung über (Haltepunkt, Akkustand): je Ladestopp wird über eine feine Rastersuche
die energieminimale Kombination aus Heizmenge und Lademenge gesucht (`kosten_bei_stopp`), die äußere
DP (`plane_route`) verkettet das über alle Stopps zur global energieminimalen Strategie. Exakt bis auf
die SOC-Diskretisierung – gegen eine deutlich feinere Auflösung geprüft (`test_feinere_diskretisierung_aendert_ergebnis_kaum`,
Abweichung < 3 %). Reine Standardbibliothek, kein Solver.

## Zusammenhänge zu anderen Stücken des Portfolios

[Fernverkehr: Lenkzeiten und Elektro-Lkw](https://sebastianhanisch-fernverkehr-demo.streamlit.app/) hat
bereits feste Ladesäulen, Reichweite und Ladestopps für Elektro-Lkw – dort aber als Tourkosten-Frage
über mehrere Fahrzeuge unter Fahrerregeln, Laden proportional zur Energie, ohne Temperatureffekt.
Diese Demo ergänzt das Fehlende: eine einzelne Strecke, energieminimal, mit der Temperaturphysik bei
Verbrauch **und** Ladewirkungsgrad – kein Duplikat, sondern die thermische Tiefe, die dort bewusst
außen vor blieb.

## Dateien

- `modell.py` – physikalisches Modell: temperaturabhängiger Verbrauch, temperaturabhängiger
  Ladewirkungsgrad, Batterieheizung, Datenklassen für Fahrzeug und Strecke
- `planung.py` – dynamische Programmierung über (Haltepunkt, Akkustand) mit lokaler Heiz-/Ladesuche an
  jedem Stopp
- `app.py` – die Streamlit-Oberfläche
- `tests/` – Korrektheitstests (Energiebilanz an jedem Stopp, Heizen nie schlechter als ohne Heizen,
  Diskretisierungs-Konvergenz, AppTest-Smoke-Tests)

## Lokal ausführen

```
pip install -r requirements.txt
streamlit run app.py
```

## Verifikation

```
pip install pytest
pytest
```

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) –
Operations Research und Machine Learning.
