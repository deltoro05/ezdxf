#  Copyright (c) 2022, Manfred Moitzi
#  License: MIT License
from typing import Union, List, Sequence
import os
import struct
import uuid
import base64
import datetime

from ezdxf.math import Vec3, normal_vector_3p
from ezdxf.render import MeshTransformer, MeshVertexMerger, MeshBuilder
from ezdxf import __version__


class UnsupportedFileFormat(Exception):
    pass


class ParsingError(Exception):
    pass


def stl_readfile(filename: Union[str, os.PathLike]) -> MeshTransformer:
    """Read ascii or binary `STL`_ file content as :class:`ezdxf.render.MeshTransformer`
    instance.

    Raises:
        ParsingError: vertex parsing error or invalid/corrupt data

    """
    with open(filename, "rb") as fp:
        buffer = fp.read()
    if buffer.startswith(b"solid"):
        s = buffer.decode("ascii", errors="ignore")
        return stl_loads(s)
    else:
        return stl_loadb(buffer)


def stl_loads(content: str) -> MeshTransformer:
    """Load a mesh from an ascii `STL`_ content string as :class:`ezdxf.render.MeshTransformer`
    instance.

    Raises:
        ParsingError: vertex parsing error

    """
    # http://www.fabbers.com/tech/STL_Format#Sct_ASCII
    # This implementation is not very picky and grabs only lines which start
    # with "vertex" or "endloop" and ignores the rest.
    def parse_vertex(line: str) -> Vec3:
        data = line.split()
        return Vec3(float(data[1]), float(data[2]), float(data[3]))

    mesh = MeshVertexMerger()
    face: List[Vec3] = []
    for num, line in enumerate(content.split("\n"), start=1):
        line = line.strip(" \r")
        if line.startswith("vertex"):
            try:
                face.append(parse_vertex(line))
            except (IndexError, ValueError):
                raise ParsingError(f"STL parsing error in line {num}: {line}")
        elif line.startswith("endloop"):
            if len(face) == 3:
                mesh.add_face(face)
            face.clear()
    return MeshTransformer.from_builder(mesh)


def stl_loadb(buffer: bytes) -> MeshTransformer:
    """Load a mesh from a binary `STL`_ data :class:`ezdxf.render.MeshTransformer`
    instance.

    Raises:
        ParsingError: invalid/corrupt data or not a binary STL file

    """
    # http://www.fabbers.com/tech/STL_Format#Sct_ASCII
    index = 80
    n_faces = struct.unpack_from("<I", buffer, index)[0]
    index += 4

    mesh = MeshVertexMerger()
    for _ in range(n_faces):
        try:
            face = struct.unpack_from("<12fH", buffer, index)
        except struct.error:
            raise ParsingError("binary STL parsing error")
        index += 50
        v1 = Vec3(face[3:6])
        v2 = Vec3(face[6:9])
        v3 = Vec3(face[9:12])
        mesh.add_face((v1, v2, v3))
    return MeshTransformer.from_builder(mesh)


def off_readfile(filename: Union[str, os.PathLike]) -> MeshTransformer:
    """Read `OFF`_ file content as :class:`ezdxf.render.MeshTransformer`
    instance.

    Raises:
        ParsingError: vertex or face parsing error

    """
    with open(filename, "rt", encoding="ascii", errors="ignore") as fp:
        content = fp.read()
    return off_loads(content)


def off_loads(content: str) -> MeshTransformer:
    """Load a mesh from a `OFF`_ content string as :class:`ezdxf.render.MeshTransformer`
    instance.

    Raises:
        ParsingError: vertex or face parsing error

    """
    # https://en.wikipedia.org/wiki/OFF_(file_format)
    mesh = MeshVertexMerger()
    lines: List[str] = []
    for line in content.split("\n"):
        line = line.strip(" \n\r")
        # "OFF" in a single line
        if line.startswith("#") or line == "OFF" or line == "":
            continue
        lines.append(line)

    if len(lines) == 0:
        raise ParsingError(f"OFF format parsing error: no data")

    if lines[0].startswith("OFF"):
        # OFF v f e
        lines[0] = lines[0][4:]

    n = lines[0].split()
    try:
        n_vertices, n_faces = int(n[0]), int(n[1])
    except ValueError:
        raise ParsingError(f"OFF format parsing error: {lines[0]}")

    if len(lines) < n_vertices + n_faces:
        raise ParsingError(f"OFF format parsing error: invalid data count")

    for vertex in lines[1 : n_vertices + 1]:
        v = vertex.split()
        try:
            vtx = Vec3(float(v[0]), float(v[1]), float(v[2]))
        except (ValueError, IndexError):
            raise ParsingError(f"OFF format vertex parsing error: {vertex}")
        mesh.vertices.append(vtx)

    index = n_vertices + 1
    face_indices = []
    for face in lines[index : index + n_faces]:
        f = face.split()
        try:
            vertex_count = int(f[0])
        except ValueError:
            raise ParsingError(f"OFF format face parsing error: {face}")
        for index in range(vertex_count):
            try:
                face_indices.append(int(f[1 + index]))
            except (ValueError, IndexError):
                raise ParsingError(
                    f"OFF format face index parsing error: {face}"
                )
        mesh.faces.append(tuple(face_indices))
        face_indices.clear()
    return MeshTransformer.from_builder(mesh)


def obj_readfile(filename: Union[str, os.PathLike]) -> List[MeshTransformer]:
    """Read `OBJ`_ file content as list of :class:`ezdxf.render.MeshTransformer`
    instances.

    Raises:
        ParsingError: vertex or face parsing error

    """
    with open(filename, "rt", encoding="ascii", errors="ignore") as fp:
        content = fp.read()
    return obj_loads(content)


def obj_loads(content: str) -> List[MeshTransformer]:
    """Load one or more meshes from an `OBJ`_ content string as list of
    :class:`ezdxf.render.MeshTransformer` instances.

    Raises:
        ParsingError: vertex parsing error

    """
    # https://en.wikipedia.org/wiki/Wavefront_.obj_file
    # This implementation is not very picky and grabs only lines which start
    # with "v", "g" or "f" and ignores the rest.
    def parse_vertex(l: str) -> Vec3:
        v = l.split()
        return Vec3(float(v[0]), float(v[1]), float(v[2]))

    def parse_face(l: str) -> Sequence[int]:
        return tuple(int(s.split("/")[0]) for s in l.split())

    vertices: List[Vec3] = [Vec3()]  # 1-indexed
    meshes: List[MeshTransformer] = []
    mesh = MeshVertexMerger()
    for num, line in enumerate(content.split("\n"), start=1):
        line = line.strip(" \r")
        if line.startswith("v"):
            try:
                vtx = parse_vertex(line[2:])
            except (IndexError, ValueError):
                raise ParsingError(
                    f"OBJ vertex parsing error in line {num}: {line}"
                )
            vertices.append(vtx)
        elif line.startswith("f"):
            try:
                mesh.add_face(vertices[i] for i in parse_face(line[2:]))
            except ValueError:
                raise ParsingError(
                    f"OBJ face parsing error in line {num}: {line}"
                )
            except IndexError:
                raise ParsingError(
                    f"OBJ face index error (n={len(vertices)}) in line {num}: {line}"
                )

        elif line.startswith("g") and len(mesh.vertices) > 0:
            meshes.append(MeshTransformer.from_builder(mesh))
            mesh = MeshVertexMerger()

    if len(mesh.vertices) > 0:
        meshes.append(MeshTransformer.from_builder(mesh))
    return meshes


def stl_dumps(mesh: MeshBuilder) -> str:
    """Returns the `STL`_ data as string for the given `mesh`.
    This function triangulates the meshes automatically because the `STL`_
    format supports only triangles as faces.

    This function does not check if the mesh obey the
    `STL`_ format `rules <http://www.fabbers.com/tech/STL_Format>`_:

        - The direction of the face normal is outward.
        - The face vertices are listed in counter-clockwise order when looking
          at the object from the outside (right-hand rule).
        - Each triangle must share two vertices with each of its adjacent triangles.
        - The object represented must be located in the all-positive octant
          (non-negative and nonzero).

    """
    lines: List[str] = [f"solid STL generated by ezdxf {__version__}"]
    for face in mesh.tessellation(max_vertex_count=3):
        if len(face) < 3:
            continue
        try:
            n = normal_vector_3p(face[0], face[1], face[2])
        except ZeroDivisionError:
            continue
        n = n.round(8)
        lines.append(f"  facet normal {n.x} {n.y} {n.z}")
        lines.append("    outer loop")
        for v in face:
            lines.append(f"      vertex {v.x} {v.y} {v.z}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid\n")
    return "\n".join(lines)


STL_SIGNATURE = (b"STL generated ezdxf" + b" " * 80)[:80]


def stl_dumpb(mesh: MeshBuilder) -> bytes:
    """Returns the `STL`_ binary data as bytes for the given `mesh`.

    For more information see function: :func:`stl_dumps`
    """
    data: List[bytes] = [STL_SIGNATURE, b"0000"]
    count = 0
    for face in mesh.tessellation(max_vertex_count=3):
        try:
            n = normal_vector_3p(face[0], face[1], face[2])
        except ZeroDivisionError:
            continue
        count += 1
        values = list(n.xyz)
        for v in face:
            values.extend(v.xyz)
        values.append(0)
        data.append(struct.pack("<12fH", *values))
    data[1] = struct.pack("<I", count)
    return b"".join(data)


def off_dumps(mesh: MeshBuilder) -> str:
    """Returns the `OFF`_ data as string for the given `mesh`.
    The `OFF`_ format supports ngons as faces.

    """
    lines: List[str] = ["OFF", f"{len(mesh.vertices)} {len(mesh.faces)} 0"]
    for v in mesh.vertices:
        v = v.round(6)
        lines.append(f"{v.x} {v.y} {v.z}")
    for face in mesh.open_faces():
        lines.append(f"{len(face)} {' '.join(str(i) for i in face)}")
    lines[-1] += "\n"
    return "\n".join(lines)


def obj_dumps(mesh: MeshBuilder) -> str:
    """Returns the `OBJ`_ data as string for the given `mesh`.
    The `OBJ`_ format supports ngons as faces.

    """
    lines: List[str] = [f"# OBJ generated by ezdxf {__version__}"]
    for v in mesh.vertices:
        v = v.round(6)
        lines.append(f"v {v.x} {v.y} {v.z}")
    for face in mesh.open_faces():
        # OBJ is 1-index
        lines.append("f " + " ".join(str(i + 1) for i in face))
    lines[-1] += "\n"
    return "\n".join(lines)


def scad_dumps(mesh: MeshBuilder) -> str:
    """Returns the `OpenSCAD`_ `polyhedron`_ definition as string for the given
    `mesh`. `OpenSCAD`_ supports ngons as faces.

    .. Important::

        `OpenSCAD`_ requires the face normals pointing inwards, the method
        :meth:`~ezdxf.render.MeshBuilder.flip_normals` of the
        :class:`~ezdxf.render.MeshBuilder` class can flip the normals
        inplace.

    """
    # polyhedron( points = [ [X0, Y0, Z0], [X1, Y1, Z1], ... ], faces = [ [P0, P1, P2, P3, ...], ... ], convexity = N);   // 2014.03 & later
    lines: List[str] = ["polyhedron(points = ["]
    for v in mesh.vertices:
        v = v.round(6)
        lines.append(f"  [{v.x}, {v.y}, {v.z}],")
    # OpenSCAD accept the last ","
    lines.append("], faces = [")
    for face in mesh.open_faces():
        lines.append("  [" + ", ".join(str(i) for i in face) + "],")
    # OpenSCAD accept the last ","
    lines.append("], convexity = 10);\n")
    return "\n".join(lines)


def ply_dumpb(mesh: MeshBuilder) -> bytes:
    """Returns the `PLY`_ binary data as bytes for the given `mesh`.
    The `PLY`_ format supports ngons as faces.

    """
    if any(len(f) > 255 for f in mesh.faces):
        face_hdr_fmt = b"property list int int vertex_index"
        face_fmt = "<i{}i"
    else:
        face_hdr_fmt = b"property list uchar int vertex_index"
        face_fmt = "<B{}i"

    header: bytes = b"\n".join(
        [
            b"ply",
            b"format binary_little_endian 1.0",
            b"comment generated by ezdxf " + __version__.encode(),
            b"element vertex " + str(len(mesh.vertices)).encode(),
            b"property float x",
            b"property float y",
            b"property float z",
            b"element face " + str(len(mesh.faces)).encode(),
            face_hdr_fmt,
            b"end_header\n",
        ]
    )
    data: List[bytes] = [header]
    for vertex in mesh.vertices:
        data.append(struct.pack("<3f", vertex.x, vertex.y, vertex.z))
    for face in mesh.open_faces():
        count = len(face)
        fmt = face_fmt.format(count)
        data.append(struct.pack(fmt, count, *face))
    return b"".join(data)


def make_id() -> str:
    id_ = base64.urlsafe_b64encode(uuid.uuid4().bytes)[:22]
    return id_.decode()


def ifc4_dumps(mesh: MeshBuilder) -> str:
    """Returns the `IFC4`_ string for the given `mesh`. The SI units are fixed
    to meters.

    .. warning::

        This is a very dirty template based exporter and the exported
        data may not be importable by all CAD applications.

    """

    def make_header():
        date = datetime.datetime.now().isoformat()[:-7]
        content_record = 28
        return (
            f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView_V2.0]'),'2;1');
FILE_NAME('undefined.ifc','{date}',('Undefined'),('Undefined'),'ezdxf {__version__}','ezdxf {__version__}','Undefined');
FILE_SCHEMA(('IFC4'));
ENDSEC;

DATA;
#1= IFCPROJECT('{make_id()}',#2,'MeshExport',$,$,$,$,(#7),#13);
#2= IFCOWNERHISTORY(#3,#6,$,$,$,$,$,0);
#3= IFCPERSONANDORGANIZATION(#4,#5,$);
#4= IFCPERSON($,$,'mozman',$,$,$,$,$);
#5= IFCORGANIZATION($,'mozman',$,$,$);
#6= IFCAPPLICATION(#5,'{__version__}','ezdxf','ezdxf');
#7= IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.000000000000000E-05,#8,#12);
#8= IFCAXIS2PLACEMENT3D(#9,#10,#11);
#9= IFCCARTESIANPOINT((0.,0.,0.));
#10= IFCDIRECTION((0.,0.,1.));
#11= IFCDIRECTION((1.,0.,0.));
#12= IFCDIRECTION((1.,0.));
#13= IFCUNITASSIGNMENT((#14,#15,#16,#17,#18,#19));
#14= IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#15= IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#16= IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#17= IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#18= IFCSIUNIT(*,.TIMEUNIT.,$,.SECOND.);
#19= IFCSIUNIT(*,.MASSUNIT.,$,.GRAM.);
#20= IFCLOCALPLACEMENT($,#8);
#21= IFCBUILDING('{make_id()}',#2,'MeshExport',$,$, #20,$,$,.ELEMENT.,$,$,$);
#23= IFCBUILDINGELEMENTPROXY('{make_id()}',#2,$,$,$,#24,#25,$,$);
#24= IFCLOCALPLACEMENT(#20,#8);
#25= IFCPRODUCTDEFINITIONSHAPE($,$,(#26));
#26= IFCSHAPEREPRESENTATION(#27,'Body','MeshExport',(#{content_record}));
#27= IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,#7,$,.MODEL_VIEW.,$);
""",
            content_record,
        )

    def make_polygon_face_set(idx: int):
        def add_line(line):
            nonlocal idx
            lines.append(f"#{idx}= {line}")
            idx += 1
        lines: List[str] = []
        face_records = ",".join(
            [f"#{idx + i + 2}" for i in range(len(mesh.faces))])
        # the first record #idx has to define the top level entity:
        add_line(f"IFCPOLYGONALFACESET(#{idx + 1},$,({face_records}), $);")  # 28
        vertices = ",".join([str(v.xyz) for v in mesh.vertices])
        add_line(f"IFCCARTESIANPOINTLIST3D(({vertices}));")  # 29
        for face in mesh.open_faces():
            indices = ",".join(str(i + 1) for i in face)
            add_line(f"IFCINDEXEDPOLYGONALFACE(({indices}));")
        return "\n".join(lines) + "\n", idx

    def make_epilog(idx: int):
        def add_line(line):
            nonlocal idx
            lines.append(f"#{idx}= {line}")
            idx += 1
        # records < 28 from template header have always the same number
        # fmt: off
        lines: List[str] = []
        add_line("IFCCOLOURRGB($,1.,1.,1.);")
        add_line(f"IFCSURFACESTYLESHADING(#{idx-1},0.);")
        add_line(f"IFCSURFACESTYLE($,.POSITIVE.,(#{idx-1}));")
        add_line(f"IFCPRESENTATIONSTYLEASSIGNMENT((#{idx-1}));")
        add_line(f"IFCSTYLEDITEM(#28,(#{idx-1}),$);")
        add_line(f"IFCPRESENTATIONLAYERWITHSTYLE('0',$,(#26),$,.T.,.F.,.F.,(#{idx+1}));")
        add_line(f"IFCSURFACESTYLE($,.POSITIVE.,(#{idx+1}));")
        add_line(f"IFCSURFACESTYLESHADING(#{idx+1},0.);")
        add_line("IFCCOLOURRGB($,1.,1.,1.);")
        add_line(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('{make_id()}',#2,$,$,(#23),#21);")
        add_line(f"IFCRELAGGREGATES('{make_id()}',#2,$,$,#1,(#21));")
        add_line("IFCLOCALPLACEMENT(#20,#8);")
        # fmt: on
        lines.extend(["ENDSEC;", "END-ISO-10303-21;"])
        return "\n".join(lines)

    header, index = make_header()
    content, index = make_polygon_face_set(index)
    epilog = make_epilog(index)
    return header + content + epilog
