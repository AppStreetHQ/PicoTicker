import time

import picounicorn

import font3x5

CHAR_SPACING = 1
OFF = (0, 0, 0)


class Display:
    def __init__(self):
        self.pu = picounicorn.PicoUnicorn()
        self.width = self.pu.get_width()
        self.height = self.pu.get_height()
        self.y_offset = (self.height - font3x5.HEIGHT) // 2
        self.pu.clear()

    def clear(self):
        self.pu.clear()

    def _draw_column(self, x, bits, color):
        if not (0 <= x < self.width):
            return
        for row in range(font3x5.HEIGHT):
            y = self.y_offset + row
            if 0 <= y < self.height:
                lit = bits[row] == "#"
                self.pu.set_pixel(x, y, *(color if lit else OFF))

    def scroll_text(self, text, color, speed=0.4):
        """Scroll a line of text right-to-left across the display once."""
        columns = []
        for char in text:
            glyph = font3x5.glyph_for(char)
            for col in range(font3x5.WIDTH):
                columns.append([row[col] for row in glyph])
            columns.extend([["."] * font3x5.HEIGHT] * CHAR_SPACING)

        total_cols = len(columns)
        blank = ["."] * font3x5.HEIGHT
        for offset in range(-self.width, total_cols):
            for x in range(self.width):
                src = offset + x
                bits = columns[src] if 0 <= src < total_cols else blank
                self._draw_column(x, bits, color)
            time.sleep(speed)
        self.pu.clear()
