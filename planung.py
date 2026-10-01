"""Energieminimale Lade-/Heizstrategie entlang einer festen Strecke: dynamische Programmierung über
(Haltepunkt, Akkustand), mit einer lokalen Optimierung über die Heizdauer an jedem Ladestopp.

Die Route ist fest (keine Streckenwahl) - entschieden wird an jedem der festen Ladesäulen nur, wie viel
geladen und wie viel vorher geheizt wird. Das ist ein ressourcenbeschränktes Kürzeste-Wege-Problem: der
Akkustand ist die Ressource, in SOC-Stufen diskretisiert (Schichten-DAG, exakt bis auf die
Diskretisierung - siehe tests/test_planung.py für die Konvergenzprüfung gegen eine feinere Auflösung).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from modell import (
    ETA_KALT,
    ETA_WARM,
    HEIZ_WIRKUNGSGRAD,
    T_ETA_KALT_C,
    T_ETA_WARM_C,
    WAERMEKAPAZITAET_KWH_PRO_GRAD,
    Fahrzeug,
    Strecke,
    ladewirkungsgrad,
    temperaturanstieg_durch_heizen,
    verbrauch_kwh_km,
)

UNERREICHBAR = float("inf")


@dataclass(frozen=True)
class Stopp:
    """Die optimale Entscheidung an einem Ladehalt: Ankunft, Heizen, Ladung, Abfahrt."""

    name: str
    ankunft_soc_kwh: float
    heiz_soc_kwh: float
    batterietemperatur_beim_laden_c: float
    geladen_kwh: float
    netzenergie_kwh: float
    abfahrt_soc_kwh: float


@dataclass(frozen=True)
class Ergebnis:
    strecke: Strecke
    heizen_erlaubt: bool
    stopps: list[Stopp]
    ankunft_ziel_soc_kwh: float
    netzenergie_gesamt_kwh: float
    erreichbar: bool


def kosten_bei_stopp(
    ankunft_soc_kwh: float,
    abfahrt_soc_kwh: float,
    aussentemperatur_c: float,
    heizen_erlaubt: bool,
    heiz_aufloesung: int = 60,
) -> tuple[float, float] | None:
    """Minimale aus dem Netz gezogene Energie, um von `ankunft_soc_kwh` auf `abfahrt_soc_kwh` zu
    kommen, optimal über die Heizmenge vor dem Stopp gesucht (feine, aber endliche Rastersuche - die
    Zielfunktion ist nicht garantiert konvex, ein Raster ist hier robuster als eine Ableitung).
    Gibt (netzenergie_kwh, beste_heiz_soc_kwh) zurück, oder None, wenn nicht erreichbar."""
    bedarf_kwh = abfahrt_soc_kwh - ankunft_soc_kwh
    if bedarf_kwh <= 1e-9:
        return 0.0, 0.0
    max_heiz_soc = ankunft_soc_kwh if heizen_erlaubt else 0.0
    bester: tuple[float, float] | None = None
    schritte = heiz_aufloesung if max_heiz_soc > 0 else 0
    for i in range(schritte + 1):
        heiz_soc = max_heiz_soc * i / schritte if schritte else 0.0
        delta_t = temperaturanstieg_durch_heizen(heiz_soc)
        batterietemp = aussentemperatur_c + delta_t
        eta = ladewirkungsgrad(batterietemp)
        soc_nach_heizen = ankunft_soc_kwh - heiz_soc
        geladen = abfahrt_soc_kwh - soc_nach_heizen
        if geladen < -1e-9:
            continue
        geladen = max(0.0, geladen)
        netzenergie = geladen / eta
        if bester is None or netzenergie < bester[0]:
            bester = (netzenergie, heiz_soc)
    return bester


def _kosten_batch(
    ankunft_soc_kwh: float,
    abfahrt_kandidaten_kwh: "np.ndarray",
    aussentemperatur_c: float,
    heizen_erlaubt: bool,
    heiz_aufloesung: int = 60,
) -> tuple["np.ndarray", "np.ndarray"]:
    """Wie `kosten_bei_stopp`, aber für alle `abfahrt_kandidaten_kwh` auf einmal (numpy) - dieselbe
    Suche über die Heizmenge, nur als Matrix statt als Python-Doppelschleife. Rein eine
    Performance-Variante (der DP-Zustandsraum macht sonst eine Python-Schleife je Sekunde langsam);
    `test_kosten_batch_stimmt_mit_der_einzelnen_suche_ueberein` prüft, dass beide dasselbe liefern."""
    max_heiz_soc = ankunft_soc_kwh if heizen_erlaubt else 0.0
    schritte = heiz_aufloesung if max_heiz_soc > 0 else 0
    heiz_kandidaten = np.linspace(0.0, max_heiz_soc, schritte + 1)  # (H,)

    delta_t = heiz_kandidaten * HEIZ_WIRKUNGSGRAD / WAERMEKAPAZITAET_KWH_PRO_GRAD
    batterietemp = aussentemperatur_c + delta_t
    t_geklemmt = np.clip(batterietemp, T_ETA_KALT_C, T_ETA_WARM_C)
    anteil = (t_geklemmt - T_ETA_KALT_C) / (T_ETA_WARM_C - T_ETA_KALT_C)
    eta = ETA_KALT + anteil * (ETA_WARM - ETA_KALT)  # (H,)

    soc_nach_heizen = ankunft_soc_kwh - heiz_kandidaten  # (H,)
    geladen = abfahrt_kandidaten_kwh[None, :] - soc_nach_heizen[:, None]  # (H, K)
    unerreichbar = geladen < -1e-9
    geladen = np.clip(geladen, 0.0, None)
    netzenergie = geladen / eta[:, None]  # (H, K)
    netzenergie[unerreichbar] = np.inf

    beste_idx = np.argmin(netzenergie, axis=0)  # (K,)
    beste_kosten = netzenergie[beste_idx, np.arange(netzenergie.shape[1])]
    beste_heiz = heiz_kandidaten[beste_idx]

    kein_bedarf = abfahrt_kandidaten_kwh - ankunft_soc_kwh <= 1e-9
    beste_kosten = np.where(kein_bedarf, 0.0, beste_kosten)
    beste_heiz = np.where(kein_bedarf, 0.0, beste_heiz)
    return beste_kosten, beste_heiz


def plane_route(
    strecke: Strecke,
    fahrzeug: Fahrzeug,
    heizen_erlaubt: bool = True,
    soc_aufloesung: int = 300,
) -> Ergebnis:
    """Energieminimaler Lade-/Heizplan über die ganze Strecke (dynamische Programmierung über
    Haltepunkt × diskretisierten Akkustand)."""
    n = len(strecke.namen)
    bucket_kwh = fahrzeug.kapazitaet_kwh / soc_aufloesung
    buckets = [round(i * bucket_kwh, 9) for i in range(soc_aufloesung + 1)]

    def _bucket_index(soc: float) -> int:
        return max(0, min(soc_aufloesung, round(soc / bucket_kwh)))

    # dp[stopp][bucket] = (minimale Netzenergie bisher, vorgaenger_bucket, Stopp-Info)
    dp: list[list[float]] = [[UNERREICHBAR] * (soc_aufloesung + 1) for _ in range(n)]
    herkunft: list[list[int | None]] = [[None] * (soc_aufloesung + 1) for _ in range(n)]
    stopp_info: list[list[Stopp | None]] = [[None] * (soc_aufloesung + 1) for _ in range(n)]

    start_bucket = _bucket_index(min(fahrzeug.start_soc_kwh, fahrzeug.kapazitaet_kwh))
    dp[0][start_bucket] = 0.0
    buckets_arr = np.array(buckets)

    for i in range(len(strecke.segmente)):
        segment = strecke.segmente[i]
        ist_ziel = i + 1 == n - 1
        for b in range(soc_aufloesung + 1):
            if dp[i][b] == UNERREICHBAR:
                continue
            ankunft_naechster = buckets[b] - verbrauch_kwh_km(fahrzeug.basisverbrauch_kwh_km, segment.temperatur_c) * segment.distanz_km
            if ankunft_naechster < -1e-9:
                continue
            ankunft_naechster = max(0.0, ankunft_naechster)
            ziel_bucket_ankunft = _bucket_index(ankunft_naechster)

            if ist_ziel:
                # Am Ziel wird nicht geladen - Ankunft muss nur die Reserve erfüllen.
                if ankunft_naechster + 1e-9 < fahrzeug.reserve_kwh:
                    continue
                kosten = dp[i][b]
                if kosten < dp[i + 1][ziel_bucket_ankunft]:
                    dp[i + 1][ziel_bucket_ankunft] = kosten
                    herkunft[i + 1][ziel_bucket_ankunft] = b
                    stopp_info[i + 1][ziel_bucket_ankunft] = None
                continue

            # Ladestopp: ueber alle erreichbaren Abfahrt-Buckets >= Ankunft suchen (vektorisiert -
            # eine Python-Schleife je Ankunfts-Bucket statt je (Ankunft, Abfahrt)-Paar).
            abfahrt_kandidaten = buckets_arr[ziel_bucket_ankunft:]
            kosten_arr, heiz_arr = _kosten_batch(ankunft_naechster, abfahrt_kandidaten, segment.temperatur_c, heizen_erlaubt)
            for k, ab_bucket in enumerate(range(ziel_bucket_ankunft, soc_aufloesung + 1)):
                netzenergie = float(kosten_arr[k])
                if not (netzenergie < UNERREICHBAR):
                    continue
                heiz_soc = float(heiz_arr[k])
                gesamt = dp[i][b] + netzenergie
                if gesamt < dp[i + 1][ab_bucket] - 1e-12:
                    dp[i + 1][ab_bucket] = gesamt
                    herkunft[i + 1][ab_bucket] = b
                    batterietemp = segment.temperatur_c + temperaturanstieg_durch_heizen(heiz_soc)
                    stopp_info[i + 1][ab_bucket] = Stopp(
                        name=strecke.namen[i + 1],
                        ankunft_soc_kwh=ankunft_naechster,
                        heiz_soc_kwh=heiz_soc,
                        batterietemperatur_beim_laden_c=batterietemp,
                        geladen_kwh=max(0.0, buckets[ab_bucket] - (ankunft_naechster - heiz_soc)),
                        netzenergie_kwh=netzenergie,
                        abfahrt_soc_kwh=buckets[ab_bucket],
                    )

    letzte = dp[n - 1]
    bester_bucket = min(range(soc_aufloesung + 1), key=lambda b: letzte[b])
    if letzte[bester_bucket] == UNERREICHBAR:
        return Ergebnis(strecke=strecke, heizen_erlaubt=heizen_erlaubt, stopps=[], ankunft_ziel_soc_kwh=0.0, netzenergie_gesamt_kwh=UNERREICHBAR, erreichbar=False)

    pfad_stopps: list[Stopp] = []
    b = bester_bucket
    for i in range(n - 1, 0, -1):
        if stopp_info[i][b] is not None:
            pfad_stopps.append(stopp_info[i][b])
        b = herkunft[i][b]

    pfad_stopps.reverse()
    return Ergebnis(
        strecke=strecke,
        heizen_erlaubt=heizen_erlaubt,
        stopps=pfad_stopps,
        ankunft_ziel_soc_kwh=buckets[bester_bucket],
        netzenergie_gesamt_kwh=letzte[bester_bucket],
        erreichbar=True,
    )
