import numpy as np
from PIL import Image

from lofi import loop


def test_code_loop_is_seamless_and_moves(tmp_path):
    w, h = 320, 180
    img = (np.random.default_rng(1).random((h, w, 3)) * 255).astype(np.uint8)
    Image.fromarray(img).save(tmp_path / "key.png")
    anchors = {"window": [0.1, 0.1, 0.4, 0.6], "lamp": [0.8, 0.3], "record": [0.6, 0.75, 0.06], "steam": [0.3, 0.7]}
    scene = loop.Scene(tmp_path / "key.png", None, anchors,
                       ["rain", "lamp_flicker", "steam", "dust", "record", "fireflies", "tv_flicker", "neon_flicker", "sunbeam_dust"],
                       seconds=8, fps=30, w=w, h=h)
    first, wrapped, second = scene.frame(0), scene.frame(scene.n), scene.frame(1)
    assert np.array_equal(first, wrapped)                      # periodic: the frame after the last is the first
    assert np.abs(first.astype(int) - second.astype(int)).mean() > 0.5   # and it actually moves
