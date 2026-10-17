"""Reusable SVG symbols from Schemdraw, rendered without a GUI backend.

The project layout, source tracking and engineering data remain owned by GridEasy.
Only the switch geometry comes from Schemdraw; no global backend settings are changed.
"""
from functools import lru_cache
from xml.etree import ElementTree as ET

import schemdraw
import schemdraw.elements as elements


@lru_cache(maxsize=1)
def isolator_geometry() -> str:
    drawing = schemdraw.Drawing(canvas="svg", show=False, margin=0,
                                inches_per_unit=1 / 72, lw=0.08)
    drawing.add(elements.Switch().at((0, 0)).down().length(1))
    root = ET.fromstring(drawing.get_imagedata("svg"))
    # Retain vector paths, not the backend's minimum-sized viewport. The switch
    # anchors are (0,0) and (0,1) in SVG coordinates, allowing exact wire joins.
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    return "".join(ET.tostring(child, encoding="unicode") for child in root)


def isolator_svg(x: float, y: float) -> str:
    # Existing layout wires terminate at y-6 and y+7 (13 drawing pixels).
    return (f'<g data-symbol-provider="schemdraw" aria-label="Isolator" '
            f'transform="translate({x},{y - 6}) scale(13)">{isolator_geometry()}</g>')
