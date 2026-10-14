"""Cartes d'identité : photos de téléphone redressées et toujours verticales."""
from PIL import Image

from administration.carte_identite_pdf import portrait_photo


def _phone_photo(path):
    """Capteur en paysage (400×300) + étiquette EXIF « tourner de 90° » (orientation 6),
    comme un téléphone tenu verticalement."""
    image = Image.new("RGB", (400, 300), "white")
    image.paste((255, 0, 0), (0, 0, 100, 300))  # bande rouge : devient le haut après rotation (orientation 6)
    exif = Image.Exif()
    exif[0x0112] = 6
    image.save(path, "JPEG", exif=exif.tobytes())


def test_phone_photo_is_rotated_upright_and_portrait(tmp_path):
    path = tmp_path / "p.jpg"
    _phone_photo(path)
    reader = portrait_photo(str(path), 18 / 24)
    w, h = reader.getSize()
    assert h > w  # vertical
    assert abs(w / h - 18 / 24) < 0.02
    image = Image.open(reader.fileName) if hasattr(reader, "fileName") and isinstance(reader.fileName, str) else reader._image
    top = image.getpixel((w // 2, 2))
    bottom = image.getpixel((w // 2, h - 3))
    assert top[0] > 200 and top[1] < 80       # le haut (rouge) est bien en haut
    assert bottom[1] > 200                    # le bas est blanc


def test_landscape_photo_without_exif_is_cropped_to_portrait(tmp_path):
    path = tmp_path / "l.jpg"
    Image.new("RGB", (800, 400), "blue").save(path, "JPEG")
    w, h = portrait_photo(str(path), 0.75).getSize()
    assert h > w and abs(w / h - 0.75) < 0.02


def test_square_frame(tmp_path):
    path = tmp_path / "p.jpg"
    _phone_photo(path)
    w, h = portrait_photo(str(path), 1).getSize()
    assert abs(w - h) <= 1
