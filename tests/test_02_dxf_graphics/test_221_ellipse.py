# Copyright (c) 2019-2022, Manfred Moitzi
# License: MIT License
import pytest
import math

import ezdxf
from ezdxf.audit import Auditor
from ezdxf.math import Vec3
from ezdxf.entities.ellipse import Ellipse, MIN_RATIO, MAX_RATIO
from ezdxf.lldxf.tagwriter import TagCollector, basic_tags_from_text

ELLIPSE = """0
ELLIPSE
5
0
330
0
100
AcDbEntity
8
0
100
AcDbEllipse
10
0.0
20
0.0
30
0.0
11
1.0
21
0.0
31
0.0
40
1.0
41
0.0
42
6.283185307179586
"""


@pytest.fixture
def entity():
    return Ellipse.from_text(ELLIPSE)


def test_registered():
    from ezdxf.entities.factory import ENTITY_CLASSES

    assert "ELLIPSE" in ENTITY_CLASSES


def test_default_init():
    entity = Ellipse()
    assert entity.dxftype() == "ELLIPSE"
    assert entity.dxf.handle is None
    assert entity.dxf.owner is None


def test_default_new():
    entity = Ellipse.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": 7,
            "ratio": 0.5,
            "center": (1, 2, 3),
            "major_axis": (4, 5, 6),
            "start_param": 10,
            "end_param": 20,
        },
    )
    assert entity.dxf.layer == "0"
    assert entity.dxf.color == 7
    assert entity.dxf.center == (1, 2, 3)
    assert entity.dxf.major_axis == (4, 5, 6)
    assert entity.dxf.ratio == 0.5
    assert entity.dxf.start_param == 10
    assert entity.dxf.end_param == 20


def test_extrusion_can_not_be_a_null_vector():
    e = Ellipse.new(dxfattribs={"extrusion": (0, 0, 0)})
    assert e.dxf.extrusion == (0, 0, 1), "expected default extrusion"


def test_major_axis_can_not_be_a_null_vector():
    pytest.raises(ValueError, Ellipse.new, dxfattribs={"major_axis": (0, 0, 0)})


@pytest.mark.parametrize("ratio", [-2, -1, 0, 1, 2])
def test_ratio_is_always_valid(ratio):
    e = Ellipse.new(dxfattribs={"ratio": ratio})
    assert MIN_RATIO <= abs(e.dxf.ratio) <= MAX_RATIO


@pytest.mark.parametrize("ratio", [-1, -0.5, -1e-9])
def test_ratio_can_be_negative(ratio):
    e = Ellipse.new(dxfattribs={"ratio": ratio})
    assert e.dxf.ratio < 0


def test_load_from_text(entity):
    assert entity.dxf.layer == "0"
    assert entity.dxf.color == 256, "default color is 256 (by layer)"
    assert entity.dxf.center == (0, 0, 0)
    assert entity.dxf.major_axis == (1, 0, 0)
    assert entity.dxf.ratio == 1
    assert entity.dxf.start_param == 0
    assert entity.dxf.end_param == math.pi * 2


def test_get_start_and_end_vertex():
    ellipse = Ellipse.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "center": (1, 2, 3),
            "major_axis": (4, 3, 0),
            "ratio": 0.7,
            "start_param": math.pi / 2,
            "end_param": math.pi,
            "extrusion": (0, 0, -1),
        },
    )

    start, end = list(
        ellipse.vertices(
            [
                ellipse.dxf.start_param,
                ellipse.dxf.end_param,
            ]
        )
    )
    # test values from BricsCAD
    assert start.isclose(Vec3(3.1, -0.8, 3), abs_tol=1e-6)
    assert end.isclose(Vec3(-3, -1, 3), abs_tol=1e-6)

    # for convenience, but Ellipse.vertices is much more efficient:
    assert ellipse.start_point.isclose(Vec3(3.1, -0.8, 3), abs_tol=1e-6)
    assert ellipse.end_point.isclose(Vec3(-3, -1, 3), abs_tol=1e-6)


def test_write_dxf():
    entity = Ellipse.from_text(ELLIPSE)
    result = TagCollector.dxftags(entity)
    expected = basic_tags_from_text(ELLIPSE)
    assert result == expected


def test_from_arc():
    from ezdxf.entities.arc import Arc

    arc = Arc.new(dxfattribs={"center": (2, 2, 2), "radius": 3})
    ellipse = Ellipse.from_arc(arc)
    assert ellipse.dxf.center == (2, 2, 2)
    assert ellipse.dxf.major_axis == (3, 0, 0)
    assert ellipse.dxf.ratio == 1
    assert ellipse.dxf.start_param == 0
    assert math.isclose(ellipse.dxf.end_param, math.tau)


class TestEllipseParameters:
    @pytest.fixture(scope="class")
    def msp(self):
        doc = ezdxf.new()
        return doc.modelspace()

    def test_adding_ellipse_with_too_big_ratio(self, msp):
        with pytest.raises(ezdxf.DXFValueError):
            msp.add_ellipse(center=(0, 0), major_axis=(1, 0), ratio=2.0)

    def test_adding_ellipse_with_too_small_ratio(self, msp):
        # update: 2022-12-15: min ratio is 1e-10
        ellipse = msp.add_ellipse(center=(0, 0), major_axis=(1, 0), ratio=0.0)
        assert ellipse.dxf.ratio >= 1e-10

    def test_adding_ellipse_with_invalid_major_axis(self, msp):
        with pytest.raises(ezdxf.DXFValueError):
            msp.add_ellipse(center=(0, 0), major_axis=(0, 0), ratio=0.5)

    def test_audit_max_ratio(self, msp):
        ellipse = msp.add_ellipse((0, 0), (1, 0))
        # can only happen for loaded DXF files
        ellipse.dxf.__dict__["ratio"] = 2.0  # hack
        auditor = Auditor(ellipse.doc)
        ellipse.audit(auditor)
        assert len(auditor.fixes) == 1
        assert ellipse.dxf.ratio == 0.5
        assert ellipse.dxf.major_axis.isclose((0.0, 2.0))

    def test_audit_min_ratio(self, msp):
        ellipse = msp.add_ellipse((0, 0), (1, 0))
        # can only happen for loaded DXF files
        ellipse.dxf.__dict__["ratio"] = 1e-11  # hack
        auditor = Auditor(ellipse.doc)
        ellipse.audit(auditor)
        assert len(auditor.fixes) == 1
        # update: 2022-12-15: min ratio is 1e-10
        assert ellipse.dxf.ratio == 1e-10
        assert ellipse.dxf.major_axis.isclose((1.0, 0.0)), "should not changed"

    def test_audit_invalid_major_axis(self, msp):
        ellipse = msp.add_ellipse((0, 0), (1, 0))
        # can only happen for loaded DXF files
        ellipse.dxf.__dict__["major_axis"] = Vec3(0, 0, 0)  # hack
        auditor = Auditor(ellipse.doc)
        ellipse.audit(auditor)
        auditor.empty_trashcan()
        assert len(auditor.fixes) == 1
        assert ellipse.is_alive is False, "invalid ellipse should be deleted"


# tests for swap_axis() are done in test_648_construction_ellipse.py
# tests for params() are done in test_648_construction_ellipse.py

MALFORMED_ELLIPSE = """0
ELLIPSE
5
0
62
7
330
0
6
LT_EZDXF
8
LY_EZDXF
100
AcDbEllipse
10
1.0
20
2.0
30
3.0
100
AcDbEllipse
11
1.0
21
0.0
31
0.0
40
1.0
41
0.0
42
6.283185307179586
"""


def test_malformed_ellipse():
    ellipse = Ellipse.from_text(MALFORMED_ELLIPSE)
    assert ellipse.dxf.layer == "LY_EZDXF"
    assert ellipse.dxf.linetype == "LT_EZDXF"
    assert ellipse.dxf.color == 7
    assert ellipse.dxf.center.isclose((1, 2, 3))
    assert ellipse.dxf.major_axis.isclose((1, 0, 0))
    assert ellipse.dxf.ratio == 1
    assert ellipse.dxf.start_param == 0
    assert ellipse.dxf.end_param == math.pi * 2
