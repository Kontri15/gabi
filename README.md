# Pre Gabi

Narodeninová stránka s pesničkou „Gabka, Gabka“.

- `index.html` – celá stránka (text piesne a časy sú v `CONFIG` v spodnej časti súboru)
- `song.mp3` – pesnička

## Video `video/`

Krátke lifestyle video (Reels / TikTok / Shorts, 1080×1920, 20 s) z horských záberov.

- `tatry_reel.mp4` – hotové video s hookom „Winter is coming.“ (jediný text), hudbou a efektmi
- `tatry_reel_zima_prichadza.mp4` – alternatívny hook po slovensky „Zima prichádza.“ (na A/B test)
- `tatry_reel_bez_hudby.mp4` – hlavná verzia len so zvukovými efektmi a ruchmi (na pridanie trendového zvuku priamo v aplikácii)
- `tatry_reel_cover.jpg` – titulný obrázok (cover)
- hook sa vyberá premennou `HOOK` (`winter`, `zima`), text je v `timeline.py`
- `render.sh` – celé video sa dá znova vyrenderovať: `./render.sh <priečinok so zdrojovými klipmi>`
- strih a časovanie sú v `timeline.py`, titulok v `make_captions.py`, hudba a efekty v `build_audio.py`
- fonty: Instrument Serif a DM Mono (SIL Open Font License, `fonts/`)
