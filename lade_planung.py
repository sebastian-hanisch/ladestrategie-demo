"""Energieminimale Lade-/Heizstrategie entlang einer festen Strecke: dynamische Programmierung über
(Haltepunkt, Akkustand), mit einer lokalen Optimierung über die Heizdauer an jedem Ladestopp.

Die Route ist fest (keine Streckenwahl) - entschieden wird an jedem der festen Ladesäulen nur, wie viel
geladen und wie lange vorher (während der Fahrt des letzten Abschnitts, nicht erst am Stopp selbst)
geheizt wird. Das ist ein ressourcenbeschränktes Kürzeste-Wege-Problem: der Akkustand ist die Ressource,
in SOC-Stufen diskretisiert (Schichten-DAG, exakt bis auf die Diskretisierung - siehe
tests/test_lade_planung.py für die Konvergenzprüfung gegen eine feinere Auflösung).

Zweites Kriterium Zeit: Heizen während der Fahrt kostet keine Zeit, Laden schon (Ladekurve und
Temperaturfaktor in lade_ladekurve.py, dazu eine Pauschale je Ladehalt). `plane_route` minimiert
Energie + Zeitwert · Ladezeit (Skalarisierung, Zeitwert in kWh je Stunde); `pareto_front` fährt dafür ein
Raster von Zeitwerten ab. Zeitwert 0 ist der energieminimale Plan, bei Gleichstand der schnellere. Die
Skalarisierung findet nur die Punkte auf der konvexen Hülle der Front - Punkte in Lücken kann sie nicht
treffen (siehe tests/test_pareto_ladestrategie.py, dort gegen eine vollständige Aufzählung geprüft).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from lade_ladekurve import (
    LADELEISTUNG_KW_STANDARD,
    ladeleistung_temperaturfaktor,
    ladezeit_h as berechne_ladezeit_h,
    ladezeit_integral,
)
from lade_modell import (
    ETA_KALT,
    ETA_WARM,
    HEIZ_WIRKUNGSGRAD,
    T_ETA_KALT_C,
    T_ETA_WARM_C,
    WAERMEKAPAZITAET_KWH_PRO_GRAD,
    WAERMEVERLUST_ZEITKONSTANTE_H,
    Fahrzeug,
    Strecke,
    batterietemperatur_nach_heizen,
    ladewirkungsgrad,
    verbrauch_kwh_km,
)

UNERREICHBAR = float("inf")


@dataclass(frozen=True)
class Stopp:
    """Die optimale Entscheidung an einem Ladehalt: Ankunft, Heizen, Ladung, Abfahrt."""

    name: str
    ankunft_soc_kwh: float
    heiz_dauer_h: float
    heiz_energie_kwh: float
    batterietemperatur_beim_laden_c: float
    geladen_kwh: float
    netzenergie_kwh: float
    abfahrt_soc_kwh: float
    ladezeit_h: float = 0.0  # Ladedauer inkl. Stopp-Pauschale (Heizen während der Fahrt kostet keine Zeit)


@dataclass(frozen=True)
class Ergebnis:
    strecke: Strecke
    heizen_erlaubt: bool
    stopps: list[Stopp]
    ankunft_ziel_soc_kwh: float
    netzenergie_gesamt_kwh: float
    erreichbar: bool
    ladezeit_gesamt_h: float = 0.0
    fahrzeit_h: float = 0.0
    zeitwert_kwh_pro_h: float = 0.0

    @property
    def gesamtzeit_h(self) -> float:
        """Reine Fahrzeit plus alle Ladezeiten."""
        return self.fahrzeit_h + self.ladezeit_gesamt_h




def kosten_bei_stopp(
    ankunft_soc_kwh: float,
    abfahrt_soc_kwh: float,
    aussentemperatur_c: float,
    segment_zeit_h: float,
    heizleistung_kw: float,
    heizen_erlaubt: bool,
    heiz_aufloesung: int = 400,
    waermekapazitaet_kwh_pro_grad: float = WAERMEKAPAZITAET_KWH_PRO_GRAD,
    *,
    zeitwert_kwh_pro_h: float = 0.0,
    kapazitaet_kwh: float = 80.0,
    ladeleistung_kw: float = LADELEISTUNG_KW_STANDARD,
    pauschale_h: float = 0.0,
    reserve_kwh: float = 0.0,
) -> tuple[float, float, float] | None:
    """Minimale Kosten (Netzenergie + Zeitwert · Ladezeit), um von `ankunft_soc_kwh` auf
    `abfahrt_soc_kwh` zu kommen, optimal über die Heizdauer während der letzten `segment_zeit_h` Stunden
    vor dem Stopp gesucht (feine, aber endliche Rastersuche - die Zielfunktion ist nicht garantiert
    konvex, ein Raster ist hier robuster als eine Ableitung). Die Heizdauer ist begrenzt durch die
    verfügbare Zeit (segment_zeit_h) UND durch die verfügbare Akkuenergie oberhalb der Reserve
    (heizleistung_kw * Dauer ≤ ankunft_soc_kwh - reserve_kwh).
    Gibt (netzenergie_kwh, beste_heiz_dauer_h, ladezeit_h) zurück, oder None, wenn nicht erreichbar."""
    bedarf_kwh = abfahrt_soc_kwh - ankunft_soc_kwh
    if bedarf_kwh <= 1e-9:
        return 0.0, 0.0, 0.0
    verfuegbar_kwh = max(0.0, ankunft_soc_kwh - reserve_kwh)
    max_dauer_h = min(segment_zeit_h, verfuegbar_kwh / heizleistung_kw) if heizen_erlaubt and heizleistung_kw > 0 else 0.0
    bester: tuple[float, float, float] | None = None
    beste_kosten = float("inf")
    schritte = heiz_aufloesung if max_dauer_h > 0 else 0
    for i in range(schritte + 1):
        heiz_dauer_h = max_dauer_h * i / schritte if schritte else 0.0
        batterietemp = batterietemperatur_nach_heizen(aussentemperatur_c, heiz_dauer_h, heizleistung_kw, waermekapazitaet_kwh_pro_grad)
        eta = ladewirkungsgrad(batterietemp)
        heiz_energie = heizleistung_kw * heiz_dauer_h
        soc_nach_heizen = ankunft_soc_kwh - heiz_energie
        geladen = abfahrt_soc_kwh - soc_nach_heizen
        if geladen < -1e-9:
            continue
        geladen = max(0.0, geladen)
        netzenergie = geladen / eta
        zeit_h = (
            float(berechne_ladezeit_h(max(0.0, soc_nach_heizen), abfahrt_soc_kwh, kapazitaet_kwh, ladeleistung_kw, batterietemp, pauschale_h))
            if geladen > 1e-9
            else 0.0
        )
        kosten = netzenergie + zeitwert_kwh_pro_h * zeit_h
        if kosten < beste_kosten:
            beste_kosten = kosten
            bester = (netzenergie, heiz_dauer_h, zeit_h)
    return bester


def _kosten_batch(
    ankunft_soc_kwh: float,
    abfahrt_kandidaten_kwh: "np.ndarray",
    aussentemperatur_c: float,
    segment_zeit_h: float,
    heizleistung_kw: float,
    heizen_erlaubt: bool,
    heiz_aufloesung: int = 400,
    waermekapazitaet_kwh_pro_grad: float = WAERMEKAPAZITAET_KWH_PRO_GRAD,
    *,
    zeitwert_kwh_pro_h: float = 0.0,
    kapazitaet_kwh: float = 80.0,
    ladeleistung_kw: float = LADELEISTUNG_KW_STANDARD,
    pauschale_h: float = 0.0,
    reserve_kwh: float = 0.0,
) -> tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
    """Wie `kosten_bei_stopp`, aber für alle `abfahrt_kandidaten_kwh` auf einmal (numpy) - dieselbe
    Suche über die Heizdauer, nur als Matrix statt als Python-Doppelschleife. Rein eine
    Performance-Variante (der DP-Zustandsraum macht sonst eine Python-Schleife je Sekunde langsam);
    `test_kosten_batch_stimmt_mit_der_einzelnen_suche_ueberein` prüft, dass beide dasselbe liefern.
    Gibt (netzenergie, heizdauer, ladezeit) je Kandidat zurück (inf bei Unerreichbarkeit)."""
    verfuegbar_kwh = max(0.0, ankunft_soc_kwh - reserve_kwh)
    max_dauer_h = min(segment_zeit_h, verfuegbar_kwh / heizleistung_kw) if heizen_erlaubt and heizleistung_kw > 0 else 0.0
    schritte = heiz_aufloesung if max_dauer_h > 0 else 0
    heiz_kandidaten_h = np.linspace(0.0, max_dauer_h, schritte + 1)  # (H,)

    # batterietemperatur_nach_heizen() vektorisiert (identische Formel, siehe lade_modell.py):
    heizrate_pro_h = heizleistung_kw * HEIZ_WIRKUNGSGRAD / waermekapazitaet_kwh_pro_grad
    k = 1.0 / WAERMEVERLUST_ZEITKONSTANTE_H
    batterietemp = aussentemperatur_c + (heizrate_pro_h / k) * (1.0 - np.exp(-k * heiz_kandidaten_h))
    t_geklemmt = np.clip(batterietemp, T_ETA_KALT_C, T_ETA_WARM_C)
    anteil = (t_geklemmt - T_ETA_KALT_C) / (T_ETA_WARM_C - T_ETA_KALT_C)
    eta = ETA_KALT + anteil * (ETA_WARM - ETA_KALT)  # (H,)

    heiz_energie = heizleistung_kw * heiz_kandidaten_h  # (H,)
    soc_nach_heizen = ankunft_soc_kwh - heiz_energie  # (H,)
    geladen = abfahrt_kandidaten_kwh[None, :] - soc_nach_heizen[:, None]  # (H, K)
    unerreichbar = geladen < -1e-9
    geladen = np.clip(geladen, 0.0, None)
    netzenergie = geladen / eta[:, None]  # (H, K)

    # Ladezeit = (τ(Ende) - τ(Anfang)) · Q / P / g(T) + Pauschale - τ hängt nur von der Zeile (H) bzw. Spalte (K)
    # ab, die (H, K)-Matrix entsteht also aus einer Differenz zweier Vektoren (dieselbe Formel wie
    # lade_ladekurve.ladezeit_h, nur ohne die Matrix mehrfach auszuwerten).
    tau_anfang = ladezeit_integral(np.clip(soc_nach_heizen, 0.0, None) / kapazitaet_kwh)  # (H,)
    tau_ende = ladezeit_integral(abfahrt_kandidaten_kwh / kapazitaet_kwh)  # (K,)
    skala = (kapazitaet_kwh / ladeleistung_kw) / ladeleistung_temperaturfaktor(batterietemp)  # (H,)

    spalten = np.arange(netzenergie.shape[1])
    if zeitwert_kwh_pro_h > 0.0:
        zeit = (tau_ende[None, :] - tau_anfang[:, None]) * skala[:, None] + pauschale_h
        zeit = np.where(geladen > 1e-9, zeit, 0.0)  # (H, K)
        kosten = netzenergie + zeitwert_kwh_pro_h * zeit
        kosten[unerreichbar] = np.inf
        beste_idx = np.argmin(kosten, axis=0)  # (K,)
        beste_energie = np.where(np.isinf(kosten[beste_idx, spalten]), np.inf, netzenergie[beste_idx, spalten])
        beste_zeit = zeit[beste_idx, spalten]
    else:
        # Zeitwert 0: die Energie allein entscheidet, die Ladezeit wird nur für die gewählte Heizdauer gebraucht.
        netzenergie[unerreichbar] = np.inf
        beste_idx = np.argmin(netzenergie, axis=0)
        beste_energie = netzenergie[beste_idx, spalten]
        beste_geladen = geladen[beste_idx, spalten]
        beste_zeit = np.where(
            beste_geladen > 1e-9, (tau_ende - tau_anfang[beste_idx]) * skala[beste_idx] + pauschale_h, 0.0
        )
    beste_dauer = heiz_kandidaten_h[beste_idx]

    kein_bedarf = abfahrt_kandidaten_kwh - ankunft_soc_kwh <= 1e-9
    beste_energie = np.where(kein_bedarf, 0.0, beste_energie)
    beste_dauer = np.where(kein_bedarf, 0.0, beste_dauer)
    beste_zeit = np.where(kein_bedarf, 0.0, beste_zeit)
    return beste_energie, beste_dauer, beste_zeit


def plane_route(
    strecke: Strecke,
    fahrzeug: Fahrzeug,
    heizen_erlaubt: bool = True,
    soc_aufloesung: int = 300,
    zeitwert_kwh_pro_h: float = 0.0,
    heiz_aufloesung: int = 400,
) -> Ergebnis:
    """Lade-/Heizplan über die ganze Strecke (dynamische Programmierung über Haltepunkt ×
    diskretisierten Akkustand), der Netzenergie + Zeitwert · Ladezeit minimiert. Mit Zeitwert 0 (Standard)
    ist das der energieminimale Plan, bei Energiegleichstand der mit der kürzeren Ladezeit.

    Der Zustand ist die Abfahrt-SOC-Stufe; zu jeder Stufe wird zusätzlich der **exakte** Akkustand des
    besten Labels mitgeführt (`soc_exakt`). Geladen wird nur auf Stufenwerte, wer nicht lädt, fährt mit
    seinem exakten Akkustand weiter (Stufe = abgerundeter Index). So rundet die Diskretisierung weder
    einen Start- noch einen Ankunftsstand auf oder ab: ein Halt, an dem nichts geladen werden muss,
    kostet genau 0 kWh. Die Sicherheitsreserve gilt bei jeder Ankunft (Säule und Ziel); Vorheizen darf
    sie nicht unterschreiten.

    Die Labels liegen je Haltepunkt als numpy-Arrays über die SOC-Stufen (Kosten, Energie, Zeit, exakter
    Akkustand, Herkunft, Heizdauer, Lade-Art); die `Stopp`-Objekte entstehen erst beim Zurückverfolgen."""
    n = len(strecke.namen)
    K = soc_aufloesung
    bucket_kwh = fahrzeug.kapazitaet_kwh / K
    buckets_arr = np.array([round(i * bucket_kwh, 9) for i in range(K + 1)])
    reserve = fahrzeug.reserve_kwh

    def _bucket_unten(soc: float) -> int:
        return max(0, min(K, int(math.floor(soc / bucket_kwh + 1e-9))))

    # Je Haltepunkt ein Array über die Stufen: Kosten (Energie + Zeitwert · Zeit), die beiden Bestandteile,
    # exakter Akkustand, Herkunfts-Stufe, Heizdauer beim Laden, Art (0 = Start/Ziel, 1 = ohne Laden, 2 = geladen)
    dp = [np.full(K + 1, np.inf) for _ in range(n)]
    energie = [np.zeros(K + 1) for _ in range(n)]
    zeit_h = [np.zeros(K + 1) for _ in range(n)]
    soc_exakt = [np.zeros(K + 1) for _ in range(n)]
    herkunft = [np.full(K + 1, -1, dtype=int) for _ in range(n)]
    heiz_dauer = [np.zeros(K + 1) for _ in range(n)]
    art = [np.zeros(K + 1, dtype=int) for _ in range(n)]

    start_soc = min(fahrzeug.start_soc_kwh, fahrzeug.kapazitaet_kwh)
    start_bucket = _bucket_unten(start_soc)
    dp[0][start_bucket] = 0.0
    soc_exakt[0][start_bucket] = start_soc

    def _setze_einzeln(i: int, bucket: int, kosten: float, e: float, z: float, soc: float, von: int, a: int) -> None:
        """Label eintragen, wenn besser: billiger gewinnt; bei Kostengleichheit die kürzere Zeit, danach der
        höhere Akkustand."""
        alt_k, alt_z = dp[i][bucket], zeit_h[i][bucket]
        besser = kosten < alt_k - 1e-12 or (
            kosten <= alt_k + 1e-12 and (z < alt_z - 1e-12 or (z <= alt_z + 1e-12 and soc > soc_exakt[i][bucket]))
        )
        if besser:
            dp[i][bucket], energie[i][bucket], zeit_h[i][bucket] = kosten, e, z
            soc_exakt[i][bucket], herkunft[i][bucket], heiz_dauer[i][bucket], art[i][bucket] = soc, von, 0.0, a

    for i in range(len(strecke.segmente)):
        segment = strecke.segmente[i]
        segment_zeit_h = segment.distanz_km / fahrzeug.geschwindigkeit_kmh
        ist_ziel = i + 1 == n - 1
        verbrauch_segment = verbrauch_kwh_km(fahrzeug.basisverbrauch_kwh_km, segment.temperatur_c) * segment.distanz_km
        for b in range(K + 1):
            if dp[i][b] == UNERREICHBAR:
                continue
            ankunft_naechster = soc_exakt[i][b] - verbrauch_segment
            if ankunft_naechster < max(0.0, reserve) - 1e-9:
                continue  # Reserve bei der Ankunft nicht gehalten (Reserve 0: Akku leer gefahren)
            ankunft_naechster = max(0.0, ankunft_naechster)
            k0, e0, z0 = dp[i][b], energie[i][b], zeit_h[i][b]

            if ist_ziel:
                # Am Ziel wird nicht geladen - Ankunft muss nur die Reserve erfüllen (oben geprüft).
                _setze_einzeln(i + 1, _bucket_unten(ankunft_naechster), k0, e0, z0, ankunft_naechster, b, 0)
                continue

            # Option 1: nicht laden (und nicht heizen) - mit exaktem Akkustand weiterfahren.
            _setze_einzeln(i + 1, _bucket_unten(ankunft_naechster), k0, e0, z0, ankunft_naechster, b, 1)

            # Option 2: auf eine höhere Stufe laden - über alle Stufen strikt über der Ankunft, alle
            # Kandidaten auf einmal (numpy).
            erste = int(np.searchsorted(buckets_arr, ankunft_naechster + 1e-9, side="left"))
            if erste > K:
                continue
            kosten_arr, heiz_dauer_arr, zeit_arr = _kosten_batch(
                ankunft_naechster, buckets_arr[erste:], segment.temperatur_c, segment_zeit_h, fahrzeug.heizleistung_kw, heizen_erlaubt,
                heiz_aufloesung,
                waermekapazitaet_kwh_pro_grad=fahrzeug.waermekapazitaet_kwh_pro_grad,
                zeitwert_kwh_pro_h=zeitwert_kwh_pro_h, kapazitaet_kwh=fahrzeug.kapazitaet_kwh,
                ladeleistung_kw=fahrzeug.ladeleistung_kw, pauschale_h=fahrzeug.stopp_pauschale_h, reserve_kwh=reserve,
            )
            gesamt = k0 + kosten_arr + zeitwert_kwh_pro_h * zeit_arr  # inf bei Unerreichbarkeit
            neu_zeit = z0 + zeit_arr
            neu_soc = buckets_arr[erste:]
            alt_k, alt_z, alt_soc = dp[i + 1][erste:], zeit_h[i + 1][erste:], soc_exakt[i + 1][erste:]
            besser = np.isfinite(gesamt) & (
                (gesamt < alt_k - 1e-12)
                | (
                    (gesamt <= alt_k + 1e-12)
                    & ((neu_zeit < alt_z - 1e-12) | ((neu_zeit <= alt_z + 1e-12) & (neu_soc > alt_soc)))
                )
            )
            if besser.any():
                ziel_idx = erste + np.nonzero(besser)[0]
                quelle = np.nonzero(besser)[0]
                dp[i + 1][ziel_idx] = gesamt[quelle]
                energie[i + 1][ziel_idx] = e0 + kosten_arr[quelle]
                zeit_h[i + 1][ziel_idx] = neu_zeit[quelle]
                soc_exakt[i + 1][ziel_idx] = neu_soc[quelle]
                herkunft[i + 1][ziel_idx] = b
                heiz_dauer[i + 1][ziel_idx] = heiz_dauer_arr[quelle]
                art[i + 1][ziel_idx] = 2

    letzte = dp[n - 1]
    bester_bucket = min(range(K + 1), key=lambda b: (letzte[b], zeit_h[n - 1][b], -soc_exakt[n - 1][b]))
    fahrzeit_h = strecke.distanz_gesamt_km / fahrzeug.geschwindigkeit_kmh
    if letzte[bester_bucket] == UNERREICHBAR:
        return Ergebnis(
            strecke=strecke, heizen_erlaubt=heizen_erlaubt, stopps=[], ankunft_ziel_soc_kwh=0.0,
            netzenergie_gesamt_kwh=UNERREICHBAR, erreichbar=False, ladezeit_gesamt_h=UNERREICHBAR,
            fahrzeit_h=fahrzeit_h, zeitwert_kwh_pro_h=zeitwert_kwh_pro_h,
        )

    # Zurückverfolgen: Stopp-Objekte erst hier bauen. Beim Laden an Haltepunkt i (Stufe b) ist die Ankunft der
    # exakte Akkustand des Vorgänger-Labels minus Streckenverbrauch.
    pfad_stopps: list[Stopp] = []
    b = bester_bucket
    for i in range(n - 1, 0, -1):
        vorher = int(herkunft[i][b])
        segment = strecke.segmente[i - 1]
        ankunft = max(0.0, soc_exakt[i - 1][vorher] - verbrauch_kwh_km(fahrzeug.basisverbrauch_kwh_km, segment.temperatur_c) * segment.distanz_km)
        if art[i][b] == 1:
            pfad_stopps.append(Stopp(
                name=strecke.namen[i], ankunft_soc_kwh=ankunft, heiz_dauer_h=0.0, heiz_energie_kwh=0.0,
                batterietemperatur_beim_laden_c=segment.temperatur_c, geladen_kwh=0.0, netzenergie_kwh=0.0, abfahrt_soc_kwh=ankunft,
            ))
        elif art[i][b] == 2:
            h = float(heiz_dauer[i][b])
            heiz_energie = fahrzeug.heizleistung_kw * h
            pfad_stopps.append(Stopp(
                name=strecke.namen[i],
                ankunft_soc_kwh=ankunft,
                heiz_dauer_h=h,
                heiz_energie_kwh=heiz_energie,
                batterietemperatur_beim_laden_c=batterietemperatur_nach_heizen(
                    segment.temperatur_c, h, fahrzeug.heizleistung_kw, fahrzeug.waermekapazitaet_kwh_pro_grad
                ),
                geladen_kwh=max(0.0, buckets_arr[b] - (ankunft - heiz_energie)),
                netzenergie_kwh=float(energie[i][b] - energie[i - 1][vorher]),
                abfahrt_soc_kwh=float(buckets_arr[b]),
                ladezeit_h=float(zeit_h[i][b] - zeit_h[i - 1][vorher]),
            ))
        b = vorher

    pfad_stopps.reverse()
    return Ergebnis(
        strecke=strecke,
        heizen_erlaubt=heizen_erlaubt,
        stopps=pfad_stopps,
        ankunft_ziel_soc_kwh=float(soc_exakt[n - 1][bester_bucket]),
        netzenergie_gesamt_kwh=float(energie[n - 1][bester_bucket]),
        erreichbar=True,
        ladezeit_gesamt_h=float(zeit_h[n - 1][bester_bucket]),
        fahrzeit_h=fahrzeit_h,
        zeitwert_kwh_pro_h=zeitwert_kwh_pro_h,
    )


ZEITWERT_SCHNELLSTER_PLAN = 1e5  # kWh je Stunde: so groß, dass praktisch nur noch die Zeit zählt
ZEITWERT_UNTERGRENZE = 0.02  # darunter unterscheidet sich der Plan nicht mehr spürbar vom energieminimalen
ZEITWERT_MIN_VERHAELTNIS = 1.2  # Zeitwert-Intervalle enger als 20 % werden nicht weiter geteilt
FRONT_MIN_ZEITGEWINN_H = 2.0 / 60.0  # Pläne, die weniger als zwei Minuten auseinanderliegen, gelten als derselbe ...
FRONT_MIN_ENERGIEGEWINN_ANTEIL = 0.001  # ... ebenso Pläne, die weniger als 0,1 % Energie auseinanderliegen
FRONT_MAX_LAEUFE = 30


def _kleinster_energieunterschied_kwh(energie_kwh: float, stufe_kwh: float) -> float:
    """Energieunterschiede darunter gelten als Rauschen: 0,1 % der Netzenergie, mindestens eine SOC-Stufe
    (so fein löst die Diskretisierung Energie überhaupt auf, geteilt durch den schlechtesten Ladewirkungsgrad)."""
    return max(FRONT_MIN_ENERGIEGEWINN_ANTEIL * max(1.0, energie_kwh), stufe_kwh / ETA_KALT)


def _nah_beieinander(langsam: Ergebnis, schnell: Ergebnis, stufe_kwh: float) -> bool:
    """Lohnt es sich nicht, zwischen diesen beiden Plänen weiter nach Zwischenpunkten zu suchen?"""
    return (
        langsam.gesamtzeit_h - schnell.gesamtzeit_h < FRONT_MIN_ZEITGEWINN_H
        or schnell.netzenergie_gesamt_kwh - langsam.netzenergie_gesamt_kwh < _kleinster_energieunterschied_kwh(langsam.netzenergie_gesamt_kwh, stufe_kwh)
    )


def pareto_front(
    strecke: Strecke,
    fahrzeug: Fahrzeug,
    heizen_erlaubt: bool = True,
    soc_aufloesung: int = 300,
    heiz_aufloesung: int = 400,
) -> list[Ergebnis]:
    """Nicht dominierte Pläne (Netzenergie gegen Gesamtzeit), nach Gesamtzeit aufsteigend (vorn der
    schnellste, hinten der energieminimale Plan). Leer, wenn das Ziel nicht erreichbar ist.

    Skalarisierung mit adaptiver Suche: Zuerst die beiden Extreme (Zeitwert 0 und sehr groß), dann wird
    der Zeitwert zwischen zwei noch merklich verschiedenen Plänen geometrisch halbiert, bis Zwischenpunkte
    weniger als eine Minute oder 0,2 % Energie auseinanderliegen. Das findet nur Punkte der konvexen Hülle
    der Front und rechnet nur so viele Läufe, wie die Front tatsächlich Struktur hat (bei einer Front aus
    einem Punkt genau zwei)."""
    laeufe = 0
    stufe_kwh = fahrzeug.kapazitaet_kwh / soc_aufloesung

    def lauf(zeitwert: float) -> Ergebnis:
        nonlocal laeufe
        laeufe += 1
        return plane_route(strecke, fahrzeug, heizen_erlaubt, soc_aufloesung, zeitwert_kwh_pro_h=zeitwert, heiz_aufloesung=heiz_aufloesung)

    energieminimal = lauf(0.0)
    if not energieminimal.erreichbar:
        return []
    schnellster = lauf(ZEITWERT_SCHNELLSTER_PLAN)
    gefunden: list[Ergebnis] = [energieminimal, schnellster]

    def verfeinere(z_klein: float, langsam: Ergebnis, z_gross: float, schnell: Ergebnis) -> None:
        if laeufe >= FRONT_MAX_LAEUFE or _nah_beieinander(langsam, schnell, stufe_kwh):
            return
        if z_klein > 0 and z_gross / z_klein < ZEITWERT_MIN_VERHAELTNIS:
            return
        mitte = math.sqrt(max(z_klein, ZEITWERT_UNTERGRENZE / 2) * z_gross)
        if mitte <= ZEITWERT_UNTERGRENZE:
            return
        zwischen = lauf(mitte)
        gefunden.append(zwischen)
        verfeinere(z_klein, langsam, mitte, zwischen)
        verfeinere(mitte, zwischen, z_gross, schnell)

    verfeinere(0.0, energieminimal, ZEITWERT_SCHNELLSTER_PLAN, schnellster)

    # Nicht dominierte Pläne nach Gesamtzeit; Pläne, die sich nur in Diskretisierungsrauschen unterscheiden,
    # werden zusammengefasst (bei fast gleicher Zeit gewinnt der energieärmere, bei fast gleicher Energie der schnellere).
    gefunden.sort(key=lambda e: (round(e.gesamtzeit_h, 9), e.netzenergie_gesamt_kwh))
    nicht_dominiert: list[Ergebnis] = []
    for e in gefunden:
        if not nicht_dominiert or e.netzenergie_gesamt_kwh < nicht_dominiert[-1].netzenergie_gesamt_kwh - 1e-9:
            nicht_dominiert.append(e)
    front: list[Ergebnis] = []
    for e in nicht_dominiert:
        if front and e.gesamtzeit_h - front[-1].gesamtzeit_h < FRONT_MIN_ZEITGEWINN_H:
            front[-1] = e
        elif front and front[-1].netzenergie_gesamt_kwh - e.netzenergie_gesamt_kwh < _kleinster_energieunterschied_kwh(e.netzenergie_gesamt_kwh, stufe_kwh):
            continue
        else:
            front.append(e)
    # Der energieminimale Plan (Zeitwert 0) bleibt als langsames Ende der Front erhalten, auch wenn er nur um
    # Rauschen sparsamer ist als der Nachbar - so liegt der Plan der App bei Zeitwert 0 immer auf der Front.
    if front[-1] is not energieminimal and energieminimal.gesamtzeit_h > front[-1].gesamtzeit_h and energieminimal.netzenergie_gesamt_kwh < front[-1].netzenergie_gesamt_kwh - 1e-9:
        front.append(energieminimal)
    return front


def front_hat_zielkonflikt(front: list[Ergebnis], fahrzeug: Fahrzeug, soc_aufloesung: int = 300) -> bool:
    """Gibt es zwischen dem schnellsten und dem energieminimalen Plan einen merklichen Unterschied (mindestens
    zwei Minuten Zeit und mindestens eine SOC-Stufe bzw. 0,1 % Energie)? Sonst gibt es nichts abzuwägen."""
    if len(front) < 2:
        return False
    schnell, langsam = front[0], front[-1]
    stufe_kwh = fahrzeug.kapazitaet_kwh / soc_aufloesung
    return not _nah_beieinander(langsam, schnell, stufe_kwh)
