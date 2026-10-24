"""Scan d'un code-barres EAN-13 par la caméra (caméra virtuelle de Chromium : une vidéo générée ici), puis carte produit et enregistrement du repas."""
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from tests.e2e.conftest import DEMO_EMAIL, DEMO_PASSWORD, login, tab  # noqa: F401  (comptes de démo)

L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_modules(code: str) -> str:
    d = [int(c) for c in code]
    bits = "101"
    for i, p in enumerate(PARITY[d[0]]):
        bits += (L if p == "L" else G)[d[i + 1]]
    bits += "01010"
    for x in d[7:]:
        bits += R[x]
    return bits + "101"


def write_y4m(path: Path, code: str, w: int = 640, h: int = 480, frames: int = 20) -> None:
    """Vidéo Y4M (I420) d'un EAN-13 noir sur blanc, centré, avec marges blanches."""
    mod = 4
    bits = ean13_modules(code)
    x0, y0, bh = (w - len(bits) * mod) // 2, (h - 220) // 2, 220
    row = bytearray([235] * w)
    for i, b in enumerate(bits):
        if b == "1":
            row[x0 + i * mod:x0 + (i + 1) * mod] = bytes([16]) * mod
    y_plane = b"".join(bytes(row) if y0 <= y < y0 + bh else bytes([235]) * w for y in range(h))
    frame = b"FRAME\n" + y_plane + bytes([128]) * (w * h // 2)
    path.write_bytes(f"YUV4MPEG2 W{w} H{h} F10:1 Ip A1:1 C420jpeg\n".encode() + frame * frames)


@pytest.fixture
def cam_page(base_url: str, tmp_path: Path):
    video = tmp_path / "ean.y4m"
    write_y4m(video, "3017620422003")
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")
        args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-video-capture={video}"]
        b = p.chromium.launch(executable_path=exe, args=args) if exe else p.chromium.launch(args=args)
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="fr-FR", service_workers="block", base_url=base_url, permissions=["camera"])
        pg = ctx.new_page()
        pg.set_default_timeout(20_000)
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg
        ctx.close()
        b.close()
        assert not errors, errors


def open_scanner(pg: Page) -> None:
    login(pg)
    tab(pg, "Nutrition")
    pg.get_by_role("button", name="Produit emballé").click()
    pg.get_by_role("button", name="Scanner le code-barres").click()


def test_live_scan_reads_ean13_shows_card_and_saves_meal(cam_page: Page, base_url: str):
    pg = cam_page
    pg.add_init_script("delete window.BarcodeDetector;")  # comme Safari iOS : pas de détecteur natif, donc la bibliothèque auto-hébergée (zxing-wasm)
    wasm = []
    pg.on("request", lambda r: wasm.append(r.url) if r.url.endswith(".wasm") or "/vendor/" in r.url else None)
    open_scanner(pg)
    expect(pg.locator("input#bc-code")).to_have_value("3017620422003")
    expect(pg.locator(".scan")).to_have_count(0)  # le scanner se ferme, la caméra est libérée
    assert {u.rsplit("/", 1)[1] for u in wasm} == {"barcode-detector.js", "zxing_reader.wasm"} and all(u.startswith(base_url) for u in wasm)
    card = pg.locator(".prod")
    expect(card).to_contain_text("Biscuit d'essai")
    expect(card).to_contain_text("Marque d'essai")
    expect(card).to_contain_text("300 g")
    expect(card).to_contain_text("Nutri-Score C")
    expect(card).to_contain_text("Éco-Score B")
    expect(card).to_contain_text("480 kcal")
    expect(pg.locator(".prod-img")).to_be_visible()
    assert pg.evaluate("document.querySelector('.prod-img').naturalWidth") == 1  # image servie par notre serveur (CSP img-src 'self')
    grams = pg.locator("#bc-grams")
    expect(grams).to_have_value("30")  # portion proposée
    grams.fill("50")
    expect(card).to_contain_text("≈ 240 kcal pour 50 g")
    pg.get_by_role("button", name="Enregistrer comme repas").click()
    expect(pg.get_by_text("Biscuit d'essai").first).to_be_visible()


def test_scanner_stops_camera_on_close(cam_page: Page):
    pg = cam_page
    pg.add_init_script("""window.__tracks = []; const g = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async (c) => { const s = await g(c); window.__tracks.push(...s.getTracks()); return s; };""")
    open_scanner(pg)
    pg.get_by_role("button", name="Arrêter le scan").click()
    expect(pg.locator(".scan")).to_have_count(0)
    assert pg.evaluate("window.__tracks.length > 0 && window.__tracks.every((t) => t.readyState === 'ended')")


def test_denied_camera_explains_and_keeps_manual_entry(browser, base_url: str):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, locale="fr-FR", service_workers="block", base_url=base_url)
    pg = ctx.new_page()
    pg.add_init_script("navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('no', 'NotAllowedError'));")
    open_scanner(pg)
    expect(pg.locator(".scan-status")).to_contain_text("Accès à la caméra refusé")
    expect(pg.get_by_role("button", name="Prendre une photo")).to_be_visible()
    pg.get_by_role("button", name="Arrêter le scan").click()
    pg.locator("input#bc-code").fill("0000000000000")  # saisie manuelle toujours possible
    pg.get_by_role("button", name="Chercher").click()
    expect(pg.locator(".error")).to_contain_text("Produit")
    ctx.close()


def test_header_allows_camera_for_self(base_url: str):
    import urllib.request
    assert "camera=(self)" in urllib.request.urlopen(base_url + "/healthz").headers["Permissions-Policy"]
