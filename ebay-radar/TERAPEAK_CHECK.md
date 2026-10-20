# Terapeak-Check (monatlich, mit Claude)

Auslöser: Telegram-Erinnerung am Monatsersten („Monatlicher Terapeak-Check“) oder der Nutzer schreibt „Terapeak-Check“.
Voraussetzung: Chrome offen, im Seller Hub als hjtc.vault eingeloggt (Login macht der Nutzer selbst). Nur lesen, nichts ändern.

## Welche Sets
Die in der Telegram-Erinnerung genannten Präfixe (Register: Server `~/ebay-radar/neuheiten_register.json`, 14–90 Tage alt, nicht 🔴) plus laufende Kernlinien (HP 25th, Stranger Things).

## Abfragen je Set (Terapeak-URL)
`https://www.ebay.de/sh/research?marketplace=<EBAY-DE|ALL>&keywords=<suchwörter>&dayRange=<30|90|365>&categoryId=0&tabName=SOLD&tz=Europe%2FBerlin&minPrice=<…>&offset=<0,50,…>&limit=50`
1. DE, 30 Tage, minPrice=10 → erste DE-Einzelverkäufe ≥ 10 €
2. DE, 90 Tage, ohne Preisfilter → Hobby-Box-Preis DE
3. ALL, 90 Tage → Hobby-Box-Preis weltweit, Median je Code-Familie (Präfix-XX)
Daten werden clientseitig gerendert: pro Seite navigieren, dann Text parsen (Zeile „, Vorschau des Bildes anzeigen“ → Titel, danach Preis, Versand, Menge).
Achtung: Mit Preisfilter berechnete Mediane sind nach oben verzerrt – Familienpreise immer ohne Filter oder je Familie abfragen.

## Bewertung (geeicht 20.10.2026, siehe berichte/scouting/2026-10-20_Eichung_neue_Sets.md)
- 🟢 bestätigt: Hobby-Box DE ≥ 40 % über weltweit **oder** ≥ 5 DE-Einzelverkäufe ≥ 10 € in 30 Tagen
- 🔴 abgeschrieben: Box DE ≈ weltweit und keine DE-Einzelverkäufe nach 60 Tagen
- Max. EK je Familie: `ebay_radar.max_ek(vk, einstellungen)`. **vk = P25 der letzten 30 Tage** (neue Sets fallen nach dem Launch stark – 90-Tage-Mediane enthalten Launch-Preise, Fehler vom 20.10.: GEM Patronus 51 € statt real ~25–36 €). DE-Werte, wenn ≥ 5 Verkäufe, sonst weltweit. Gegradete Karten (PSA/BGS/CGC), Sets und Lots ausschließen. In ¥ mit Tageskurs (api.frankfurter.dev).
- Plausibilität mit dem Nutzer abgleichen: Er kennt die realen Preise seiner Franchises (HP, Dune) oft besser.

## Ergebnis
Bericht `berichte/scouting/JJJJ-MM-TT_Terapeak-Check.md`; Franchise-Liste `FRANCHISE_DE` in `ebay_neuheiten.py` anpassen, wenn sich eine Einstufung als falsch erweist.
