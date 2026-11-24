# Setup

## 1. Token genereren (één keer, voor elk kind apart)
Voer uit in een terminal (Windows of Mac, maakt niet uit):
```
python3 -c "import secrets; print(secrets.token_hex(16))"
```
Doe dit twee keer: één token voor je zoon, één ander token voor je dochter.
Gebruik nooit hetzelfde token voor beide apparaten.

## 2. Op de laptop van je zoon (Windows)
- Zet `AUTH_TOKEN` in `child_client_windows.py` op het eerste token.
- `pip install flask mss psutil pillow`
- Start het script. Er verschijnt een zichtbare UAC-prompt (dat hoort zo).

## 3. Op de MacBook van je dochter (macOS)
- Zet `AUTH_TOKEN` in `child_client_mac.py` op het tweede token.
- `python3 -m pip install flask mss psutil pillow rumps`
- Start het script. Er verschijnt een 🔒-icoontje in de menubalk — zo is
  altijd zichtbaar dat het actief is.
- Wil je dat het automatisch opstart? Maak een LaunchAgent-plist aan die
  `python3 /pad/naar/child_client_mac.py` bij inloggen start. Zeg het als je
  daar hulp bij wilt, dat zet ik dan ook klaar.

## 4. Op jouw Windows 11 pc (het panel)
- `pip install flask mss psutil pillow requests`
- Open `parent_control_panel.py`. Er zijn twee tabbladen.
- Vul bij elk tabblad het bijpassende token in (bovenin het tabblad).
- Zodra het kind-script draait, verschijnt het apparaat automatisch als
  "verbonden" zodra het token klopt.

## Let op
- Deze tool is nog steeds krachtig (schermdeling, app-blokkade, extern
  commando's uitvoeren). Bewaar de tokens net zo geheim als een wachtwoord,
  en zorg dat dit alleen op je eigen thuisnetwerk draait — niet via
  portforwarding naar het internet openzetten.
- Overweeg je dochter (en zoon) te vertellen dat dit erop staat. Niet
  verplicht wettelijk, maar het voorkomt dat het aanvoelt als stiekem
  bespioneerd worden, en het menubalk-icoontje op de Mac maakt toch al
  duidelijk dat er iets actief is.
