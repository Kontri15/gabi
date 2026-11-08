# Pre Gabi

Narodeninová stránka s pesničkou „Gabka, Gabka“.

- `index.html` – celá stránka (text piesne a časy sú v `CONFIG` v spodnej časti súboru)
- `song.mp3` – pesnička

## Video `video/`

Krátke lifestyle video (Reels / TikTok / Shorts, 1080×1920, 20 s) z horských záberov.

- `tatry_reel.mp4` – hotové video s hudbou, zvukovými efektmi a titulkami
- `tatry_reel_bez_hudby.mp4` – rovnaké video len so zvukovými efektmi a ruchmi (na pridanie trendového zvuku priamo v aplikácii)
- `tatry_reel_cover.jpg` – titulný obrázok (cover)
- `render.sh` – celé video sa dá znova vyrenderovať: `./render.sh <priečinok so zdrojovými klipmi>`
- strih a časovanie sú v `timeline.py`, titulky v `make_captions.py`, hudba a efekty v `build_audio.py`
- fonty: Instrument Serif a DM Mono (SIL Open Font License, `fonts/`)
