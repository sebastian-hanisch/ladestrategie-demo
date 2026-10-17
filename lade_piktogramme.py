"""Piktogramme der vier Fahrzeugtypen und das Stylesheet des festen Kopfes - getrennt von der Oberfläche, wie
lade_visualisierung.py.

Streamlit filtert in `st.html` / `st.markdown` Inline-SVG heraus. Die Piktogramme stehen deshalb als SVG in CSS-Masken
(`mask-image` mit Data-URI) an einem leeren `<span>`: der Strich füllt sich mit der Textfarbe (`currentColor`) und
bleibt damit in hellem und dunklem Design lesbar, der Blitz als Hinweis auf den Elektroantrieb mit der Akzentfarbe."""

from __future__ import annotations

from urllib.parse import quote

FARBE_BLITZ = "#D68A2E"
_RAHMEN_KOERPER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 52" fill="none" stroke="#000" stroke-width="3.2" '
    'stroke-linecap="round" stroke-linejoin="round">{inhalt}</svg>'
)
_RAHMEN_BLITZ = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 52"><path d="{blitz}" fill="#000"/></svg>'


def _raeder(*xs: int) -> str:
    return "".join(f'<circle cx="{x}" cy="40" r="6.5"/><circle cx="{x}" cy="40" r="1.8" fill="#000"/>' for x in xs)


def _blitz(x: float, y: float, s: float = 1.0) -> str:
    """Pfad eines kleinen Blitzes, links oben bei (x, y), um den Faktor s skaliert."""
    punkte = [(4, 0), (0, 7), (3.2, 7), (2, 13), (7, 5), (3.8, 5), (5.5, 0)]
    pfad = " ".join(f"{'M' if i == 0 else 'L'}{x + px * s:.1f} {y + py * s:.1f}" for i, (px, py) in enumerate(punkte))
    return pfad + " Z"


_FAHRZEUGE = {
    "Pkw": dict(
        inhalt=(
            '<path d="M12 40 V30 Q12 27 15 26 L31 23 L42 12 Q44 10 47 10 H82 Q85 10 87 12 L99 24 L118 28 Q124 29 124 34 V40 H112"/>'
            '<path d="M36 40 H88"/>'
            '<path d="M45 23 L52 14 H66 V23 Z M72 23 V14 H81 L90 23 Z"/>'
            + _raeder(26, 100)
        ),
        blitz=_blitz(62, 28, 1.3),
    ),
    "Lieferwagen": dict(
        inhalt=(
            '<path d="M10 40 V14 Q10 10 14 10 H82 V40"/>'
            '<path d="M82 18 H100 Q103 18 105 20.5 L119 32 Q122 34 122 37 V40 H112"/>'
            '<path d="M36 40 H88"/>'
            '<path d="M88 22 H98 L108 31 H88 Z"/>'
            + _raeder(26, 100)
        ),
        blitz=_blitz(42, 17, 1.6),
    ),
    "Elektrobus": dict(
        inhalt=(
            '<rect x="8" y="8" width="124" height="32" rx="5"/>'
            '<path d="M8 28 H132"/>'
            '<path d="M18 13 H34 V24 H18 Z M40 13 H56 V24 H40 Z M62 13 H78 V24 H62 Z M84 13 H100 V24 H84 Z M106 13 H122 V24 H106 Z"/>'
            + _raeder(30, 104)
        ),
        blitz=_blitz(64.5, 29.2, 0.8),
    ),
    "Elektro-Lkw": dict(
        inhalt=(
            '<path d="M6 40 V8 Q6 6 8 6 H80 Q82 6 82 8 V40"/>'
            '<path d="M86 40 V16 Q86 13 89 13 H106 Q109 13 111 16 L122 29 Q124 32 124 35 V40 H117"/>'
            '<path d="M91 18 H104 L113 29 H91 Z"/>'
            '<path d="M60 40 H81 M30 40 H40"/>'
            + _raeder(18, 48, 100)
        ),
        blitz=_blitz(33, 10, 1.6),
    ),
}

# Eigenständige SVG-Dokumente je Fahrzeugtyp (Körper in Strichen, Blitz gefüllt) - Grundlage der CSS-Masken.
FAHRZEUG_SVG_KOERPER = {name: _RAHMEN_KOERPER.format(inhalt=teile["inhalt"]) for name, teile in _FAHRZEUGE.items()}
FAHRZEUG_SVG_BLITZ = {name: _RAHMEN_BLITZ.format(blitz=teile["blitz"]) for name, teile in _FAHRZEUGE.items()}


def fahrzeug_piktogramm(typ: str) -> str:
    """HTML-Element des Piktogramms (die Zeichnung kommt aus den Masken in KOPF_CSS, Typ wie in
    lade_constants.FAHRZEUGTYPEN)."""
    if typ not in _FAHRZEUGE:
        raise KeyError(typ)
    return f'<span class="lade-piktogramm" data-typ="{typ}" role="img" aria-label="{typ}"></span>'


def _daten_uri(svg: str) -> str:
    return "url('data:image/svg+xml," + quote(svg, safe="/:=,;") + "')"


def _maskenregeln() -> str:
    regeln = []
    for name in _FAHRZEUGE:
        regeln.append(
            f'.lade-piktogramm[data-typ="{name}"]::before {{ -webkit-mask-image: {_daten_uri(FAHRZEUG_SVG_KOERPER[name])}; mask-image: {_daten_uri(FAHRZEUG_SVG_KOERPER[name])}; }}'
        )
        regeln.append(
            f'.lade-piktogramm[data-typ="{name}"]::after {{ -webkit-mask-image: {_daten_uri(FAHRZEUG_SVG_BLITZ[name])}; mask-image: {_daten_uri(FAHRZEUG_SVG_BLITZ[name])}; }}'
        )
    return "\n".join(regeln)


# Hintergrundfarben der beiden Standard-Designs von Streamlit; der feste Kopf braucht einen deckenden Hintergrund,
# damit der darunter durchlaufende Inhalt nicht durchscheint.
HINTERGRUND_HELL = "#ffffff"
HINTERGRUND_DUNKEL = "#0e1117"


def kopf_css(dunkel: bool) -> str:
    """Stylesheet des festen Kopfes (Überschrift + Piktogramm). `position: sticky` hält den Container im
    Scrollbereich oben; `top` lässt Platz für die feste Streamlit-Kopfleiste."""
    return _KOPF_CSS.replace("__HINTERGRUND__", HINTERGRUND_DUNKEL if dunkel else HINTERGRUND_HELL)


_KOPF_CSS = (
    """
<style>
/* Streamlit legt um einen Container mit key einen Wrapper gleicher Höhe: dieser muss kleben, sonst endet das
   Kleben mit dem Wrapper. Der Container selbst klebt als Rückfall für Versionen ohne Wrapper. */
[data-testid="stLayoutWrapper"]:has(> .st-key-kopf),
.st-key-kopf {
  position: sticky;
  top: 3.75rem;
  z-index: 990;
  background-color: __HINTERGRUND__;
}
.st-key-kopf {
  padding: 0.25rem 0 0.5rem 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.3);
  gap: 0.25rem;
}
.st-key-kopf h1 { font-size: 1.5rem; padding: 0; line-height: 1.25; }
.lade-fahrzeug { display: flex; align-items: center; gap: 0.75rem; margin-top: 0.4rem; }
.lade-fahrzeug-name { font-size: 1rem; font-weight: 600; }
.lade-piktogramm { position: relative; display: inline-block; width: 8.6rem; height: 3.2rem; }
.lade-piktogramm::before, .lade-piktogramm::after {
  content: ""; position: absolute; inset: 0;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
  -webkit-mask-position: left center; mask-position: left center;
  -webkit-mask-size: contain; mask-size: contain;
}
@media (max-width: 640px) {
  .st-key-kopf h1 { font-size: 1.15rem; }
  .lade-piktogramm { width: 5.6rem; height: 2.1rem; }
  .lade-fahrzeug { margin-top: 0.4rem; }
}
.lade-piktogramm::before { background-color: currentColor; }
.lade-piktogramm::after { background-color: """
    + FARBE_BLITZ
    + """; }
"""
    + _maskenregeln()
    + """
</style>
"""
)
