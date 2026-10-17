"""Unabhängiges Orakel für die Lade-/Heizplanung (`plane_route`).

Rechenweg des Orakels (anders als die DP der Demo): Bei **fester** Heizdauer je Stopp ist das Laden ein
lineares Programm (Lademengen g_j >= 0, Akkustand-Schranken, Reserve bei jeder Ankunft), gelöst mit
`scipy.optimize.linprog` (HiGHS). Die Heizdauern werden außen auf einem Raster abgesucht; die
Batterietemperatur kommt aus einer numerischen Integration (RK4) der Wärme-ODE statt aus der geschlossenen
Formel der Demo. Das Ergebnis ist ein kontinuierliches Optimum (ohne SOC-Stufen) bis auf das Heizraster.

Geprüft wird: (1) die Demo ist nie billiger als das kontinuierliche Optimum (sonst wäre ihr Plan unzulässig),
(2) sie liegt höchstens etwa eine SOC-Stufe (Kapazität/Stufenzahl, geteilt durch den schlechtesten
Ladewirkungsgrad) je Ladestopp darüber, (3) ein Halt, an dem nichts geladen werden muss, kostet 0 kWh und
der ausgegebene Akkustand fällt dort nicht unter den Ankunftsstand."""

import itertools
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("scipy")
from scipy.optimize import linprog  # noqa: E402

from lade_modell import Fahrzeug, Segment, Strecke, waermekapazitaet_kwh_pro_grad  # noqa: E402
from lade_planung import plane_route  # noqa: E402

AUFLOESUNG = 300  # Standard von plane_route


def _eta(t_batt: float) -> float:
    t = min(20.0, max(-20.0, t_batt))
    return 0.80 + 0.15 * (t + 20.0) / 40.0


def _t_batt(t_aussen: float, h: float, p_kw: float, c_kwh_k: float) -> float:
    """dT/dt = 0,9*P/C - (T - T_aussen)/9 per RK4 integriert (statt geschlossener Formel)."""
    if h <= 0:
        return t_aussen
    f = lambda t: p_kw * 0.9 / c_kwh_k - (t - t_aussen) / 9.0  # noqa: E731
    n, dt, t = 40, h / 40, t_aussen
    for _ in range(n):
        k1 = f(t)
        k2 = f(t + dt / 2 * k1)
        k3 = f(t + dt / 2 * k2)
        k4 = f(t + dt * k3)
        t += dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return t


def _verbrauch_km(basis: float, t: float) -> float:
    return basis * (1 + 0.356 / 26.6 * max(0.0, 20.0 - t))


def _lp_bei_heizdauern(dist, t, basis, q, s0, reserve, p_kw, hs):
    """Minimale Netzenergie bei festen Heizdauern hs (eine je Ladesäule), oder None (unzulässig)."""
    m = len(hs)
    c_k = waermekapazitaet_kwh_pro_grad(q)
    kosten = np.array([1.0 / _eta(_t_batt(t, h, p_kw, c_k)) for h in hs])
    verbrauch = [_verbrauch_km(basis, t) * d for d in dist]
    a1 = s0 - verbrauch[0]
    if a1 < reserve - 1e-9:
        return None
    a_ub, b_ub = [], []
    for j in range(m):
        basis_j = a1 + sum(-p_kw * hs[i] - verbrauch[i + 1] for i in range(j))  # Ankunft j ohne Ladungen
        zeile = np.zeros(m)
        zeile[:j] = 1.0
        a_ub.append(-zeile)  # Ankunft - Heizenergie >= Reserve (die Reserve gilt bei JEDER Ankunft)
        b_ub.append(basis_j - p_kw * hs[j] - reserve)
        zeile2 = np.zeros(m)
        zeile2[: j + 1] = 1.0
        a_ub.append(zeile2)  # Abfahrt <= Kapazität
        b_ub.append(q - (basis_j - p_kw * hs[j]))
    ende = a1 + sum(-p_kw * hs[i] - verbrauch[i + 1] for i in range(m))
    a_ub.append(-np.ones(m))  # Ziel >= Reserve
    b_ub.append(ende - reserve)
    r = linprog(kosten, A_ub=np.array(a_ub), b_ub=np.array(b_ub), bounds=[(0, None)] * m, method="highs")
    return float(r.fun) if r.status == 0 else None


def _orakel(dist, t, basis, q, s0, reserve, v, p_kw, raster):
    m = len(dist) - 1
    s0 = min(s0, q)
    a1 = s0 - _verbrauch_km(basis, t) * dist[0]
    t_max = [dist[j] / v for j in range(m)]
    if p_kw > 0:
        t_max[0] = min(t_max[0], max(a1 - reserve, 0.0) / p_kw)
    achsen = [np.linspace(0.0, t_max[j] if p_kw > 0 else 0.0, raster if p_kw > 0 else 1) for j in range(m)]
    beste = None
    for hs in itertools.product(*achsen):
        w = _lp_bei_heizdauern(dist, t, basis, q, s0, reserve, p_kw, list(hs))
        if w is not None and (beste is None or w < beste):
            beste = w
    return beste


def _demo(dist, t, basis, q, s0, reserve, v, p_kw):
    namen = ["Start"] + [f"Halt {i + 1}" for i in range(len(dist) - 1)] + ["Ziel"]
    strecke = Strecke(namen=namen, segmente=[Segment(d, t) for d in dist])
    fz = Fahrzeug(kapazitaet_kwh=q, basisverbrauch_kwh_km=basis, start_soc_kwh=s0, reserve_kwh=reserve,
                  geschwindigkeit_kmh=v, heizleistung_kw=p_kw)
    return plane_route(strecke, fz)


def _zufallsinstanz(rng: random.Random, m: int):
    q = rng.choice([60, 80, 100, 350])
    basis = round(rng.uniform(0.15, 0.45) * (q / 80) ** 0.5, 2)
    t = float(rng.randrange(-20, 11))
    v = float(rng.choice([40, 80, 120]))
    p_kw = float(rng.choice([3.0, 6.0, 25.0]))
    s0 = q * rng.choice([0.6, 0.8, 1.0])
    reserve = rng.choice([0.0, 0.05 * q])
    reichweite = q / _verbrauch_km(basis, t)
    dist = [float(rng.randrange(20, int(0.8 * reichweite) + 1, 5)) for _ in range(m + 1)]
    return dist, t, basis, q, s0, reserve, v, p_kw


def test_halt_ohne_ladebedarf_kostet_nichts_und_der_akkustand_faellt_nicht():
    """Voller Akku, kurze Strecke mit Zwischenhalt: Laden ist nirgends nötig. Die gerundete Stufe darf
    weder Ladung erzwingen noch den Akkustand beim Halt absenken."""
    for q, basis in [(620, 0.54), (80, 0.32), (350, 1.3)]:
        dist = [60.0, 50.0]
        erg = _demo(dist, 10.0, basis, q, q * 0.9, 0.0, 99.0, 6.0)
        assert erg.erreichbar
        assert erg.netzenergie_gesamt_kwh == pytest.approx(0.0, abs=1e-9)
        for s in erg.stopps:
            assert s.geladen_kwh == 0.0
            assert s.abfahrt_soc_kwh >= s.ankunft_soc_kwh - 1e-9
        erwartet_ziel = q * 0.9 - _verbrauch_km(basis, 10.0) * sum(dist)
        assert erg.ankunft_ziel_soc_kwh == pytest.approx(erwartet_ziel, abs=1e-6)


@pytest.mark.parametrize("m", [1, 2])
def test_plan_gegen_kontinuierliches_lp_orakel(m):
    rng = random.Random(1000 + m)
    geprueft = 0
    versuche = 0
    while geprueft < (8 if m == 1 else 3) and versuche < 200:
        versuche += 1
        inst = _zufallsinstanz(rng, m)
        dist, t, basis, q, s0, reserve, v, p_kw = inst
        erg = _demo(*inst)
        o = _orakel(dist, t, basis, q, s0, reserve, v, p_kw, raster=61 if m == 1 else 9)
        assert (o is None) == (not erg.erreichbar), inst
        if o is None:
            continue
        geprueft += 1
        stufe_je_stopp = q / AUFLOESUNG / 0.80
        # (1) nie billiger als das kontinuierliche Optimum (Orakel-Raster: kleine Toleranz)
        assert erg.netzenergie_gesamt_kwh >= o - 0.01 * max(o, 1.0) - 1e-6, (inst, erg.netzenergie_gesamt_kwh, o)
        # (2) höchstens etwa eine SOC-Stufe je Ladestopp darüber
        assert erg.netzenergie_gesamt_kwh <= o + m * stufe_je_stopp + 0.01 * max(o, 1.0), (inst, erg.netzenergie_gesamt_kwh, o)
    assert geprueft >= (8 if m == 1 else 3)
