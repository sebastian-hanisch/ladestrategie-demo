"""Tests der Fahrzeug-Piktogramme und des Stylesheets des festen Kopfes (lade_piktogramme.py)."""

import sys
import xml.dom.minidom
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lade_constants import FAHRZEUGTYP_NAMEN  # noqa: E402
from lade_piktogramme import (  # noqa: E402
    FAHRZEUG_SVG_BLITZ,
    FAHRZEUG_SVG_KOERPER,
    HINTERGRUND_DUNKEL,
    HINTERGRUND_HELL,
    fahrzeug_piktogramm,
    kopf_css,
)


def test_jeder_fahrzeugtyp_hat_ein_piktogramm():
    assert set(FAHRZEUG_SVG_KOERPER) == set(FAHRZEUGTYP_NAMEN)
    assert set(FAHRZEUG_SVG_BLITZ) == set(FAHRZEUGTYP_NAMEN)


@pytest.mark.parametrize("typ", FAHRZEUGTYP_NAMEN)
def test_svg_ist_wohlgeformtes_xml_mit_viewbox(typ):
    for svg in (FAHRZEUG_SVG_KOERPER[typ], FAHRZEUG_SVG_BLITZ[typ]):
        dok = xml.dom.minidom.parseString(svg)
        assert dok.documentElement.tagName == "svg"
        assert dok.documentElement.getAttribute("viewBox") == "0 0 140 52"


def test_die_vier_piktogramme_unterscheiden_sich():
    koerper = list(FAHRZEUG_SVG_KOERPER.values())
    assert len(set(koerper)) == len(koerper)


@pytest.mark.parametrize("typ", FAHRZEUGTYP_NAMEN)
def test_html_element_traegt_den_typ_und_ein_aria_label(typ):
    html = fahrzeug_piktogramm(typ)
    assert f'data-typ="{typ}"' in html and f'aria-label="{typ}"' in html
    assert "<svg" not in html  # Streamlit filtert Inline-SVG; die Zeichnung kommt über CSS-Masken


def test_unbekannter_typ_wird_abgelehnt():
    with pytest.raises(KeyError):
        fahrzeug_piktogramm("Fahrrad")


def test_stylesheet_hat_masken_fuer_alle_typen_und_klebt_den_wrapper():
    css = kopf_css(False)
    for typ in FAHRZEUGTYP_NAMEN:
        assert f'.lade-piktogramm[data-typ="{typ}"]::before' in css
        assert f'.lade-piktogramm[data-typ="{typ}"]::after' in css
    assert 'stLayoutWrapper"]:has(> .st-key-kopf)' in css
    assert "position: sticky" in css


def test_hintergrund_folgt_dem_streamlit_design():
    assert HINTERGRUND_DUNKEL in kopf_css(True) and HINTERGRUND_HELL not in kopf_css(True)
    assert HINTERGRUND_HELL in kopf_css(False) and HINTERGRUND_DUNKEL not in kopf_css(False)
    assert "__HINTERGRUND__" not in kopf_css(True) + kopf_css(False)
