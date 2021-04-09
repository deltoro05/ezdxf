#  Copyright (c) 2021, Manfred Moitzi
#  License: MIT License
from typing import Iterable
import pathlib
import random
import ezdxf
from ezdxf import zoom, print_config
from ezdxf.math import Matrix44
from ezdxf.tools import fonts
from ezdxf.tools import text_layout

DIR = pathlib.Path('~/Desktop/Outbox').expanduser()
STYLE = 'Style0'
FONT = 'OpenSans-Regular.ttf'
COLUMN_HEIGHT = 12

print_config()

doc = ezdxf.new()
msp = doc.modelspace()
style = doc.styles.new(STYLE, dxfattribs={'font': FONT})


def measure_space(font):
    return font.text_width(' X') - font.text_width('X')


class SizedFont:
    def __init__(self, height: float):
        self.height = float(height)
        self.font = fonts.make_font(FONT, self.height)
        self.space = measure_space(self.font)

    def text_width(self, text: str):
        return self.font.text_width(text)


fix_sized_fonts = [
    SizedFont(0.18),
    SizedFont(0.35),
    SizedFont(0.50),
    SizedFont(0.70),
    SizedFont(1.00),
]


class FrameRenderer(text_layout.ContentRenderer):
    def __init__(self, color):
        self.color = color

    def render(self, left: float, bottom: float, right: float,
               top: float, m: Matrix44 = None) -> None:
        pline = msp.add_lwpolyline(
            [(left, top), (right, top), (right, bottom), (left, bottom)],
            close=True, dxfattribs={'color': self.color},
        )
        if m:
            pline.transform(m)

    def line(self, x1: float, y1: float, x2: float, y2: float,
             m: Matrix44 = None) -> None:
        pass


class TextRenderer(text_layout.ContentRenderer):
    def __init__(self, text, attribs):
        self.text = text
        self.attribs = attribs
        self.line_attribs = {'color': attribs['color']}

    def render(self, left: float, bottom: float, right: float,
               top: float, m: Matrix44 = None):
        text = msp.add_text(self.text, dxfattribs=self.attribs)
        text.set_pos((left, bottom), align='LEFT')
        if m:
            text.transform(m)

    def line(self, x1: float, y1: float, x2: float, y2: float,
             m: Matrix44 = None) -> None:
        line = msp.add_line((x1, y1), (x2, y2), dxfattribs=self.line_attribs)
        if m:
            line.transform(m)


class Word(text_layout.Text):
    def __init__(self, text: str, font: SizedFont, stroke: int = 0):
        attribs = {
            'color': random.choice((1, 2, 3, 4, 6, 7, 7)),
            'height': font.height,
            'style': STYLE,
        }
        super().__init__(
            width=font.text_width(text),
            height=font.height,
            stroke=stroke,
            renderer=TextRenderer(text, attribs),
        )


def uniform_content(count: int, size=1):
    font = fix_sized_fonts[size]
    for word in text_layout.lorem_ipsum(count):
        yield Word(word, font)
        yield text_layout.Space(font.space)


def random_sized_content(count: int):
    def size():
        return random.choice([0, 1, 1, 1, 1, 1, 2, 3])

    for word in text_layout.lorem_ipsum(count):
        font = fix_sized_fonts[size()]
        yield Word(word, font)
        yield text_layout.Space(font.space)


def stroke_groups(words: Iterable[str]):
    group = []
    count = 0
    stroke = 0
    for word in words:
        if count == 0:
            if group:
                yield group, stroke
            count = random.randint(1, 4)
            group = [word]
            stroke = random.choice([0, 0, 0, 0, 1, 1, 1, 2, 2, 4])
        else:
            count -= 1
            group.append(word)

    if group:
        yield group, stroke


def stroked_content(count: int, size=1):
    font = fix_sized_fonts[size]
    groups = stroke_groups(text_layout.lorem_ipsum(count))
    for group, stroke in groups:
        continue_stroke = stroke + 8 if stroke else 0
        for word in group[:-1]:
            yield Word(word, font=font, stroke=continue_stroke)
            yield text_layout.Space(font.space)
        yield Word(group[-1], font=font, stroke=stroke)
        yield text_layout.Space(font.space)


def create_layout(align, content):
    # Build the content:
    paragraph = text_layout.FlowText(align=align)
    paragraph.append_content(content)

    # Start the layout engine and set default column width:
    layout = text_layout.Layout(width=8, margins=(0.5,),
                                renderer=FrameRenderer(2))

    # Append the first column with default width and a content height of 12 drawing
    # units. At least the first column has to be created by the client.
    layout.append_column(height=COLUMN_HEIGHT, gutter=1)

    # Append the content. The content will be distributed across the available
    # columns and automatically overflow into adjacent columns if necessary.
    # Creates new columns if required by cloning the last column.
    layout.append_paragraphs([paragraph])

    # Content and total size is always up to date, only the final location
    # has to be updated by calling Layout.place().
    print()
    print(f"Layout has {len(layout)} columns.")
    print(f"Layout total width: {layout.total_width}")
    print(f"Layout total height: {layout.total_height}")

    for n, column in enumerate(layout, start=1):
        print()
        print(f"  {n}. column has {len(column)} paragraph(s)")
        print(f"  Column total width: {column.total_width}")
        print(f"  Column total height: {column.total_height}")

    # It is recommended to place the layout at origin (0, 0) and use a
    # transformation matrix to move the layout to the final location in
    # the DXF target layout, the model space in this example.
    # Set final layout location in the xy-plane with alignment:
    layout.place(align=text_layout.LayoutAlignment.BOTTOM_LEFT)

    # It is possible to add content after calling place(), but place has to be
    # called again before calling render().

    return layout


FlowTextAlignment = text_layout.FlowTextAlignment
ALIGNMENTS = [
    FlowTextAlignment.LEFT,
    FlowTextAlignment.RIGHT,
    FlowTextAlignment.CENTER,
    FlowTextAlignment.JUSTIFIED
]


def create(content, y):
    x = 0
    for align in ALIGNMENTS:
        layout = create_layout(align, content)
        m = Matrix44.translate(x, y, 0)
        layout.render(m)
        x += layout.total_width + 2


dy = COLUMN_HEIGHT + 3
create(list(uniform_content(200)), 0)
create(list(random_sized_content(200)), dy)
create(list(stroked_content(200)), 2 * dy)

zoom.extents(msp, factor=1.1)
doc.saveas(str(DIR / "simple_layout.dxf"))
