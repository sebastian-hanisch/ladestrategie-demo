"""Physikalisches Modell: temperaturabhängiger Verbrauch, temperaturabhängiger Ladewirkungsgrad,
Batterieheizung. Reine Funktionen und Datenklassen, keine Optimierung (siehe planung.py).

Kalibrierung, mit echten Quellen (keine frei erfundenen Zahlen):

- Verbrauch bei Kälte: AAA-Wintertest 2025 (Chevrolet Equinox EV, Tesla Model Y, Ford Mustang Mach-E),
  bei -6,6 °C im Schnitt 35,6 % geringere Effizienz. Referenztemperatur 20 °C (nahe der optimalen
  Betriebstemperatur von Li-Ion-Zellen), linear zunehmender Mehrverbrauch darunter.
- Ladewirkungsgrad bei Kälte: Innenwiderstand von LFP-Zellen bei -20 °C ca. 3x so hoch wie bei
  Raumtemperatur (mehrere Studien zu Li-Ion-Zellen bei tiefen Temperaturen) - mehr Innenwiderstand
  bedeutet mehr ohmschen Verlust (I²R) je geladener Kilowattstunde. Kalibriert auf plausible
  Eckwerte (95 % bei ≥20 °C, 80 % bei -20 °C), linear dazwischen - die Literatur belegt die Richtung
  und Größenordnung des Effekts, nicht diese exakte Kurve.
- Ladeleistung/-zeit bei Kälte (nur zur Einordnung angezeigt, nicht Teil der Optimierung): Idaho
  National Laboratory, empirische Studie an Nissan-LEAF-Taxis (~500 DC-Schnellladevorgänge) - bei
  0 °C nach derselben Ladezeit 36 % weniger Ladestand als bei 25 °C; Schnellladen kann bis zu 3x
  länger dauern. Das ist überwiegend ein Leistungs-/Zeiteffekt (die Ladesteuerung drosselt den Strom
  zum Zellschutz), kein reiner Energie-Effizienz-Effekt - deshalb hier bewusst getrennt von der
  Wirkungsgrad-Kurve oben und nicht in die Verbrauchsoptimierung einbezogen.
- Vorkonditionierung: vorgewärmte Batterien laden nachweislich schneller und gewinnen einen Teil der
  kältebedingt verlorenen Reichweite zurück - der Mechanismus hinter der Heizen-Option unten.

Vereinfachung, die diese Demo bewusst trifft: die Batterie nimmt beim Fahren eines Abschnitts dessen
Außentemperatur an (kein Wärmespeicher über mehrere Abschnitte); heizen lässt sich nur unmittelbar vor
einem Ladestopp, aus dem eigenen Akkustand. Realistische Fahrzeuge isolieren den Akku und heizen nicht
beliebig schnell - hier zählt nur die Energiebilanz, keine Heizleistungsgrenze.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------- Verbrauch ----------

VERBRAUCH_T_REF_C = 20.0
VERBRAUCH_ALPHA_PRO_GRAD = 0.356 / (20.0 - (-6.6))  # AAA: 35,6 % Mehrverbrauch bei -6,6 °C


def verbrauch_kwh_km(basis_kwh_km: float, temperatur_c: float) -> float:
    """Verbrauch je km bei gegebener Außentemperatur - steigt linear unter 20 °C (AAA-kalibriert)."""
    kaeltezuschlag = max(0.0, VERBRAUCH_T_REF_C - temperatur_c) * VERBRAUCH_ALPHA_PRO_GRAD
    return basis_kwh_km * (1.0 + kaeltezuschlag)


# ---------- Ladewirkungsgrad ----------

ETA_WARM = 0.95
ETA_KALT = 0.80
T_ETA_WARM_C = 20.0
T_ETA_KALT_C = -20.0


def ladewirkungsgrad(batterietemperatur_c: float) -> float:
    """Anteil der aus dem Netz gezogenen Energie, der tatsächlich in der Batterie landet - sinkt bei
    kalter Batterie (höherer Innenwiderstand, mehr ohmscher Verlust je geladener kWh)."""
    t = max(T_ETA_KALT_C, min(T_ETA_WARM_C, batterietemperatur_c))
    anteil = (t - T_ETA_KALT_C) / (T_ETA_WARM_C - T_ETA_KALT_C)
    return ETA_KALT + anteil * (ETA_WARM - ETA_KALT)


# ---------- Batterieheizung ----------

WAERMEKAPAZITAET_KWH_PRO_GRAD = 0.125  # ~450 kg Zellpaket, spez. Wärmekapazität ~1,0 kJ/(kg·K)
HEIZ_WIRKUNGSGRAD = 0.9  # Anteil der aus dem Akku entnommenen Heizenergie, der die Zellen tatsächlich erwärmt


def temperaturanstieg_durch_heizen(heiz_soc_kwh: float) -> float:
    """Temperaturanstieg der Batterie (°C) bei Entnahme von `heiz_soc_kwh` aus dem Akku fürs Heizen."""
    return heiz_soc_kwh * HEIZ_WIRKUNGSGRAD / WAERMEKAPAZITAET_KWH_PRO_GRAD


# ---------- Fahrzeug, Strecke ----------


@dataclass(frozen=True)
class Fahrzeug:
    kapazitaet_kwh: float
    basisverbrauch_kwh_km: float  # bei Referenztemperatur 20 °C
    start_soc_kwh: float
    reserve_kwh: float = 0.0  # Sicherheitsreserve, die am Ziel mindestens übrig bleiben muss


@dataclass(frozen=True)
class Segment:
    distanz_km: float
    temperatur_c: float


@dataclass(frozen=True)
class Strecke:
    """Eine Route mit Start, festen Ladesäulen-Positionen (gegeben, nicht Teil der Optimierung) und
    Ziel. `namen` hat ein Element mehr als `segmente` (Start und Ziel eingeschlossen)."""

    namen: list[str]
    segmente: list[Segment]

    def __post_init__(self) -> None:
        if len(self.namen) != len(self.segmente) + 1:
            raise ValueError("namen muss genau ein Element mehr haben als segmente")

    @property
    def distanz_gesamt_km(self) -> float:
        return sum(s.distanz_km for s in self.segmente)

    @property
    def ladestationen(self) -> list[str]:
        """Alle Haltepunkte außer Start und Ziel."""
        return self.namen[1:-1]
