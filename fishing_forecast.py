#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rybackie_prognozy.py
---------------------
Skrypt na Raspberry Pi, który:
1. Pobiera prognozę pogody (Open-Meteo, bez klucza API) dla najbliższej soboty i niedzieli.
2. Liczy fazę i oświetlenie Księżyca dla obu dni (lokalnie, bez zewnętrznego API).
3. Wysyła zebrane dane do Claude (Anthropic API, model Haiku 4.5 - tani i szybki),
   który ocenia warunki na ryby osobno dla dnia i wieczoru, dla soboty i niedzieli.
4. Wysyła krótkie podsumowanie mailem.

Uruchamiaj przez cron w piątek wieczorem, np. o 18:00:
    0 18 * * 5 /usr/bin/python3 /home/pi/rybackie_prognozy.py >> /home/pi/rybackie_prognozy.log 2>&1

Wymagane biblioteki:
    pip3 install requests

Skąd wziąć klucz do Anthropic API:
    1. Wejdź na https://console.anthropic.com/settings/keys
    2. Zaloguj się, kliknij "Create Key", skopiuj klucz (zaczyna się od sk-ant-...).
    Koszt: model Haiku 4.5 kosztuje $1/mln tokenów wejściowych i $5/mln wyjściowych.
    Jedno uruchomienie tego skryptu to ok. 1500-2500 tokenów łącznie, czyli grosze
    rocznie przy jednym mailu na tydzień. Nowe konta dostają też darmowe kredyty startowe.

Wymagane zmienne środowiskowe (ustaw np. w /etc/environment albo w crontab,
albo w pliku .env obok skryptu - patrz .env.example):
    ANTHROPIC_API_KEY   - klucz do Anthropic API (patrz wyżej)
    EMAIL_PASSWORD      - hasło aplikacji do konta e-mail nadawcy (np. Gmail App Password)
    EMAIL_FROM          - adres e-mail nadawcy
    EMAIL_TO            - adresy odbiorców, oddzielone przecinkiem
    LATITUDE / LONGITUDE - współrzędne łowiska
    LOCATION_NAME       - nazwa łowiska wyświetlana w mailu
"""

from __future__ import annotations  # kompatybilność ze starszym Pythonem (np. 3.7 na starszych Raspberry Pi OS)

import os
import sys
import json
import math
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta, datetime

import requests

# ============================== KONFIGURACJA ==============================
# Dane wrażliwe (lokalizacja, adresy e-mail, klucze) wczytywane są ze
# zmiennych środowiskowych / pliku .env - patrz .env.example w repo.

LATITUDE = float(os.environ.get("LATITUDE", "52.4989"))
LONGITUDE = float(os.environ.get("LONGITUDE", "21.0822"))
LOCATION_NAME = os.environ.get("LOCATION_NAME", "Arciechów (Zalew Zegrzyński)")

# Ustawienia e-mail (przykład dla Gmaila)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = [e.strip() for e in os.environ.get("EMAIL_TO", "").split(",") if e.strip()]
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# Klucz do Anthropic API (https://console.anthropic.com/settings/keys)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"  # najtańszy aktualny model: $1/$5 za mln tokenów

# ============================================================================


def log(wiadomosc: str, blad: bool = False) -> None:
    """Wypisuje linię logu z datą i godziną (np. do przekierowania do pliku .log przez cron)."""
    znacznik = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    strumien = sys.stderr if blad else sys.stdout
    print(f"[{znacznik}] {wiadomosc}", file=strumien)


def najblizszy_weekend() -> tuple[date, date]:
    """Zwraca (sobota, niedziela) najbliższego weekendu (jeśli dziś sobota, zwraca dziś + jutro)."""
    dzis = date.today()
    dni_do_soboty = (5 - dzis.weekday()) % 7  # poniedziałek=0 ... sobota=5
    sobota = dzis + timedelta(days=dni_do_soboty)
    niedziela = sobota + timedelta(days=1)
    return sobota, niedziela


def faza_ksiezyca(d: date) -> dict:
    """Liczy przybliżoną fazę i procent oświetlenia Księżyca dla danej daty (bez API)."""
    znany_now = date(2000, 1, 6)  # znana data nowiu
    dlugosc_cyklu = 29.53058867  # dni (miesiąc synodyczny)
    dni_od_nowiu = (d - znany_now).days
    faza = (dni_od_nowiu % dlugosc_cyklu) / dlugosc_cyklu  # 0.0 - 1.0

    if faza < 0.03 or faza > 0.97:
        nazwa = "Nów"
    elif faza < 0.22:
        nazwa = "Sierp przybywający"
    elif faza < 0.28:
        nazwa = "Pierwsza kwadra"
    elif faza < 0.47:
        nazwa = "Garb przybywający"
    elif faza < 0.53:
        nazwa = "Pełnia"
    elif faza < 0.72:
        nazwa = "Garb ubywający"
    elif faza < 0.78:
        nazwa = "Ostatnia kwadra"
    else:
        nazwa = "Sierp ubywający"

    oswietlenie_proc = round((1 - math.cos(2 * math.pi * faza)) / 2 * 100)

    return {"faza": nazwa, "oswietlenie_proc": oswietlenie_proc}


def pobierz_surowe_dane_pogodowe() -> dict:
    """Jedno zapytanie do Open-Meteo pokrywające obie daty (sobota + niedziela) plus trend ciśnienia."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join([
            "temperature_2m",
            "precipitation_probability",
            "weathercode",
            "windspeed_10m",
            "winddirection_10m",
            "surface_pressure",
            "cloudcover",
        ]),
        "daily": ",".join([
            "sunrise", "sunset", "precipitation_sum", "windspeed_10m_max",
        ]),
        "timezone": "Europe/Warsaw",
        "windspeed_unit": "ms",
        "past_days": 2,
        "forecast_days": 10,
    }
    ostatni_blad = None
    for probe in range(4):  # kilka prób na wypadek chwilowego przeciążenia API (5xx/429)
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and probe < 3:
                czekaj = 5 * (probe + 1)
                log(f"[info] Open-Meteo zwróciło {resp.status_code}, ponawiam za {czekaj}s...")
                time.sleep(czekaj)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            ostatni_blad = e
            if probe < 3:
                czekaj = 5 * (probe + 1)
                log(f"[info] Błąd połączenia z Open-Meteo ({e}), ponawiam za {czekaj}s...")
                time.sleep(czekaj)

    raise RuntimeError(f"Nie udało się pobrać danych z Open-Meteo po kilku próbach: {ostatni_blad}")


def wyciagnij_dane_dla_dnia(surowe: dict, target_date: date) -> dict:
    """Wyciąga uśrednione dane dzienne/wieczorne + fazę księżyca dla jednego dnia z surowej odpowiedzi API."""
    hourly = surowe["hourly"]
    times = hourly["time"]
    target_str = target_date.isoformat()

    def bucket(godz_min, godz_max):
        temps, winds, winddirs, press, clouds, precs = [], [], [], [], [], []
        for i, t in enumerate(times):
            d, godz = t.split("T")
            h = int(godz.split(":")[0])
            if d == target_str and godz_min <= h <= godz_max:
                temps.append(hourly["temperature_2m"][i])
                winds.append(hourly["windspeed_10m"][i])
                winddirs.append(hourly["winddirection_10m"][i])
                press.append(hourly["surface_pressure"][i])
                clouds.append(hourly["cloudcover"][i])
                precs.append(hourly["precipitation_probability"][i])
        if not temps:
            return None
        srednia_ms = sum(winds) / len(winds)
        return {
            "temp_min": min(temps), "temp_max": max(temps),
            "wiatr_srednia_ms": round(srednia_ms, 1),
            "wiatr_srednia_kmh": round(srednia_ms * 3.6, 1),
            "wiatr_srednia_wezly": round(srednia_ms * 1.943844, 1),
            "wiatr_kierunek": round(sum(winddirs) / len(winddirs)),
            "cisnienie_hpa": round(sum(press) / len(press), 1),
            "zachmurzenie_proc": round(sum(clouds) / len(clouds)),
            "opady_prawdopodobienstwo_proc": max(precs) if precs else 0,
        }

    # Trend ciśnienia: średnie ciśnienie z 2 dni przed target_date
    trend_press = []
    for i, t in enumerate(times):
        d = t.split("T")[0]
        if d < target_str:
            trend_press.append(hourly["surface_pressure"][i])
    cisnienie_wczesniej = round(sum(trend_press) / len(trend_press), 1) if trend_press else None

    sunrise = sunset = None
    if "daily" in surowe:
        for i, d in enumerate(surowe["daily"]["time"]):
            if d == target_str:
                sunrise = surowe["daily"]["sunrise"][i].split("T")[1]
                sunset = surowe["daily"]["sunset"][i].split("T")[1]

    dzien = bucket(6, 17)
    wieczor = bucket(18, 22)
    ksiezyc = faza_ksiezyca(target_date)

    return {
        "data": target_str,
        "dzien_tygodnia": target_date.strftime("%A"),
        "dzien": dzien,      # 6:00-17:00
        "wieczor": wieczor,  # 18:00-22:00
        "cisnienie_srednie_2dni_wczesniej_hpa": cisnienie_wczesniej,
        "wschod_slonca": sunrise,
        "zachod_slonca": sunset,
        "ksiezyc": ksiezyc,
        "indeks_aktywnosci_ryb_dzien": oblicz_indeks_aktywnosci(dzien, cisnienie_wczesniej, ksiezyc) if dzien else None,
        "indeks_aktywnosci_ryb_wieczor": oblicz_indeks_aktywnosci(wieczor, cisnienie_wczesniej, ksiezyc) if wieczor else None,
    }


def analiza_ai(lokalizacja: str, dane_sobota: dict, dane_niedziela: dict) -> str:
    """Wysyła dane pogodowe (sobota + niedziela) do Claude i prosi o ocenę warunków na ryby."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Brak ANTHROPIC_API_KEY w zmiennych środowiskowych. "
            "Klucz zrobisz na https://console.anthropic.com/settings/keys"
        )

    system_prompt = (
        "Jesteś doświadczonym wędkarzem i analitykiem pogody. Na podstawie danych "
        "pogodowych i fazy Księżyca oceniasz, jakie będą warunki na ryby w sobotę "
        "i niedzielę, osobno dla pory dziennej i wieczornej każdego dnia. Bierz pod "
        "uwagę: ciśnienie i jego trend (stabilne lub lekko spadające jest zwykle "
        "dobre, gwałtowne zmiany złe), siłę i kierunek wiatru, zachmurzenie, "
        "temperaturę, opady oraz fazę Księżyca (okolice nowiu i pełni zwykle "
        "sprzyjają większej aktywności ryb). W danych znajdziesz też pole "
        "indeks_aktywnosci_ryb_dzien/wieczor (liczbowy wynik 1-10 wyliczony regułowo) "
        "- potraktuj go jako punkt odniesienia, ale oceniaj też własnym osądem na podstawie "
        "wszystkich danych, nie kopiuj tej liczby bezmyślnie. "
        "Odpowiadaj krótko, po polsku, w formie:\n"
        "SOBOTA: 1 zdanie ogólnej oceny, potem 1-2 zdania dla dnia i 1-2 zdania dla wieczoru.\n"
        "NIEDZIELA: analogicznie.\n"
        "Na końcu jedno zdanie: który dzień/pora wygląda najlepiej i jedno praktyczne "
        "zalecenie (np. metoda/miejsce/pora). Bez zbędnego wstępu i bez nagłówków markdown."
    )

    user_content = (
        f"Lokalizacja: {lokalizacja}\n\n"
        f"Dane na sobotę:\n{json.dumps(dane_sobota, ensure_ascii=False, indent=2)}\n\n"
        f"Dane na niedzielę:\n{json.dumps(dane_niedziela, ensure_ascii=False, indent=2)}"
    )

    ostatni_blad = None
    for probe in range(4):  # kilka prób na wypadek chwilowego przeciążenia API (5xx/429)
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}],
                },
                timeout=60,
            )
            if resp.status_code in (429, 500, 502, 503, 529) and probe < 3:
                czekaj = 5 * (probe + 1)
                log(f"[info] Anthropic API zwróciło {resp.status_code}, ponawiam za {czekaj}s...")
                time.sleep(czekaj)
                continue
            resp.raise_for_status()
            result = resp.json()
            if result.get("stop_reason") == "max_tokens":
                log("[ostrzeżenie] Odpowiedź AI została ucięta przez limit tokenów (max_tokens).")
            return "".join(block.get("text", "") for block in result.get("content", []))
        except requests.exceptions.RequestException as e:
            ostatni_blad = e
            if probe < 3:
                czekaj = 5 * (probe + 1)
                log(f"[info] Błąd połączenia z Anthropic API ({e}), ponawiam za {czekaj}s...")
                time.sleep(czekaj)

    raise RuntimeError(f"Nie udało się uzyskać odpowiedzi z Anthropic API po kilku próbach: {ostatni_blad}")


def ikona_pogody(zachmurzenie_proc: int, opady_proc: int) -> str:
    """Dobiera emoji pogodowe na podstawie zachmurzenia i szansy opadów."""
    if opady_proc >= 50:
        return "🌧️"
    if opady_proc >= 25:
        return "🌦️"
    if zachmurzenie_proc >= 80:
        return "☁️"
    if zachmurzenie_proc >= 45:
        return "⛅"
    if zachmurzenie_proc >= 15:
        return "🌤️"
    return "☀️"


def oblicz_indeks_aktywnosci(dane_pory: dict, cisnienie_trend, ksiezyc: dict) -> dict:
    """Lokalny (bez AI) indeks aktywności ryb 1-10, liczony z prostych reguł wędkarskich."""
    punkty = 5.0  # punkt startowy (neutralny)

    # Trend ciśnienia - stabilne/lekko spadające dobre, gwałtowne zmiany złe
    if cisnienie_trend is not None:
        delta = dane_pory["cisnienie_hpa"] - cisnienie_trend
        if abs(delta) <= 2:
            punkty += 2.5
        elif -6 <= delta < -2:
            punkty += 1.5  # łagodny spadek - często dobry na brania
        elif delta >= 6 or delta <= -8:
            punkty -= 2.5  # gwałtowna zmiana
        elif delta > 2:
            punkty -= 1.0  # szybki wzrost - zwykle gorzej

    # Wiatr
    w = dane_pory["wiatr_srednia_ms"]
    if 1 <= w <= 4:
        punkty += 1.5
    elif 4 < w <= 7:
        punkty += 0.5
    elif w > 10:
        punkty -= 2.5
    elif w > 7:
        punkty -= 1.0

    # Zachmurzenie - lekkie/umiarkowane zachmurzenie zwykle sprzyja
    z = dane_pory["zachmurzenie_proc"]
    if 40 <= z <= 85:
        punkty += 1.0
    elif z < 10:
        punkty -= 0.5  # ostre słońce, zwłaszcza latem - gorzej

    # Opady
    op = dane_pory["opady_prawdopodobienstwo_proc"]
    if op < 20:
        punkty += 0.5
    elif op >= 70:
        punkty -= 2.0
    elif op >= 40:
        punkty -= 1.0

    # Faza księżyca - okolice nowiu/pełni sprzyjają aktywności
    oswietlenie = ksiezyc["oswietlenie_proc"]
    if oswietlenie <= 10 or oswietlenie >= 90:
        punkty += 1.5
    elif 40 <= oswietlenie <= 60:
        punkty += 0.0
    else:
        punkty += 0.5

    wynik = max(1, min(10, round(punkty)))

    if wynik >= 8:
        etykieta, kolor = "Bardzo dobre", "#16a34a"
    elif wynik >= 6:
        etykieta, kolor = "Dobre", "#65a30d"
    elif wynik >= 4:
        etykieta, kolor = "Umiarkowane", "#ca8a04"
    elif wynik >= 2:
        etykieta, kolor = "Słabe", "#ea580c"
    else:
        etykieta, kolor = "Bardzo słabe", "#dc2626"

    return {"wynik": wynik, "etykieta": etykieta, "kolor": kolor}


def zbuduj_karte_pory_dnia(pora_nazwa: str, dane_pory: dict, ksiezyc: dict, cisnienie_trend=None) -> str:
    """Buduje pojedynczą 'kartę' (Dzień lub Wieczór) z danymi w pionie - czytelne na telefonie."""
    if not dane_pory:
        return ""
    ikona = ikona_pogody(dane_pory["zachmurzenie_proc"], dane_pory["opady_prawdopodobienstwo_proc"])
    indeks = oblicz_indeks_aktywnosci(dane_pory, cisnienie_trend, ksiezyc)

    def wiersz(etykieta: str, wartosc: str) -> str:
        return f"""
        <tr>
          <td style="padding:6px 0;color:#64748b;font-size:13px;width:50%;">{etykieta}</td>
          <td style="padding:6px 0;color:#0f172a;font-size:13px;font-weight:600;text-align:right;">{wartosc}</td>
        </tr>"""

    wiersze = (
        wiersz("Temperatura", f"{dane_pory['temp_min']:.0f}–{dane_pory['temp_max']:.0f}°C")
        + wiersz("Wiatr", f"{dane_pory['wiatr_srednia_ms']} m/s ({dane_pory['wiatr_srednia_kmh']} km/h, {dane_pory['wiatr_srednia_wezly']} kn)")
        + wiersz("Zachmurzenie", f"{dane_pory['zachmurzenie_proc']}%")
        + wiersz("Szansa opadów", f"{dane_pory['opady_prawdopodobienstwo_proc']}%")
        + wiersz("Ciśnienie", f"{dane_pory['cisnienie_hpa']:.0f} hPa")
        + wiersz("Księżyc", f"🌙 {ksiezyc['faza']} ({ksiezyc['oswietlenie_proc']}%)")
    )

    return f"""
    <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:10px;
                  margin-bottom:12px;font-family:Arial,Helvetica,sans-serif;">
      <tr>
        <td style="padding:12px 14px 4px;">
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="font-size:15px;font-weight:700;color:#0f172a;">{pora_nazwa}</td>
              <td style="font-size:26px;text-align:right;">{ikona}</td>
            </tr>
          </table>
          <table style="width:100%;border-collapse:collapse;margin-top:8px;">
            <tr>
              <td style="background-color:{indeks['kolor']};border-radius:6px;padding:6px 10px;">
                <span style="color:#ffffff;font-size:13px;font-weight:700;">🐟 Indeks aktywności: {indeks['wynik']}/10</span>
                <span style="color:#ffffff;font-size:12px;opacity:0.9;"> — {indeks['etykieta']}</span>
              </td>
            </tr>
          </table>
          <table style="width:100%;border-collapse:collapse;border-top:1px solid #e2e8f0;margin-top:8px;">
            {wiersze}
          </table>
        </td>
      </tr>
    </table>"""


def zbuduj_sekcje_dnia(nazwa_dnia: str, data_str: str, dane_dnia: dict) -> str:
    """Buduje sekcję dla jednego dnia (Sobota lub Niedziela) z dwiema kartami: Dzień i Wieczór."""
    trend = dane_dnia.get("cisnienie_srednie_2dni_wczesniej_hpa")
    karta_dzien = zbuduj_karte_pory_dnia("☀️ Dzień", dane_dnia["dzien"], dane_dnia["ksiezyc"], trend)
    karta_wieczor = zbuduj_karte_pory_dnia("🌙 Wieczór", dane_dnia["wieczor"], dane_dnia["ksiezyc"], trend)

    return f"""
    <div style="margin-bottom:20px;">
      <h3 style="font-size:16px;color:#ffffff;background-color:#0f172a;margin:0 0 12px;
                 padding:8px 14px;border-radius:8px;font-family:Arial,Helvetica,sans-serif;">
        {nazwa_dnia} <span style="font-weight:400;color:#cbd5e1;font-size:12px;">({data_str})</span>
      </h3>
      {karta_dzien}
      {karta_wieczor}
    </div>"""


def zbuduj_html_maila(lokalizacja: str, sobota: date, niedziela: date,
                       dane_sobota: dict, dane_niedziela: dict, podsumowanie_ai: str) -> str:
    sekcja_sobota = zbuduj_sekcje_dnia("Sobota", sobota.strftime("%d.%m.%Y"), dane_sobota)
    sekcja_niedziela = zbuduj_sekcje_dnia("Niedziela", niedziela.strftime("%d.%m.%Y"), dane_niedziela)
    podsumowanie_html = podsumowanie_ai.replace("\n", "<br>")

    return f"""\
    <html>
      <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
      <body style="font-family:Arial,Helvetica,sans-serif;background-color:#f1f5f9;padding:12px;margin:0;">
        <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <div style="background-color:#0f172a;color:#ffffff;padding:16px 18px;">
            <h2 style="margin:0;font-size:18px;">🎣 Warunki na ryby</h2>
            <p style="margin:4px 0 0;color:#cbd5e1;font-size:13px;">{lokalizacja}</p>
            <p style="margin:2px 0 0;color:#94a3b8;font-size:12px;">
              Weekend {sobota.strftime('%d.%m')} – {niedziela.strftime('%d.%m.%Y')}
            </p>
          </div>
          <div style="padding:16px 16px 4px;">
            {sekcja_sobota}
            {sekcja_niedziela}
          </div>
          <div style="padding:0 18px 18px;">
            <h3 style="font-size:15px;color:#0f172a;border-top:1px solid #e2e8f0;padding-top:16px;margin-top:0;">
              Ocena AI
            </h3>
            <p style="font-size:14px;line-height:1.6;color:#1e293b;">{podsumowanie_html}</p>
          </div>
          <div style="background-color:#f8fafc;padding:12px 18px;color:#94a3b8;font-size:11px;">
            Wiadomość wygenerowana automatycznie przez rybackie_prognozy.py
          </div>
        </div>
      </body>
    </html>"""


def wyslij_mail(temat: str, tresc_plain: str, tresc_html: str) -> None:
    if not EMAIL_PASSWORD:
        raise RuntimeError("Brak EMAIL_PASSWORD w zmiennych środowiskowych.")
    if not EMAIL_FROM or not EMAIL_TO:
        raise RuntimeError("Brak EMAIL_FROM lub EMAIL_TO w zmiennych środowiskowych.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = temat
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(tresc_plain, "plain", "utf-8"))
    msg.attach(MIMEText(tresc_html, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


def main():
    try:
        sobota, niedziela = najblizszy_weekend()
        log(f"[info] Sprawdzam pogodę na {sobota.isoformat()} i {niedziela.isoformat()}...")

        surowe = pobierz_surowe_dane_pogodowe()
        dane_sobota = wyciagnij_dane_dla_dnia(surowe, sobota)
        dane_niedziela = wyciagnij_dane_dla_dnia(surowe, niedziela)

        log("[info] Wysyłam dane do AI po analizę...")
        podsumowanie = analiza_ai(LOCATION_NAME, dane_sobota, dane_niedziela)

        temat = (
            f"Warunki na ryby - {LOCATION_NAME}, weekend "
            f"{sobota.strftime('%d.%m')}-{niedziela.strftime('%d.%m.%Y')}"
        )
        tresc_plain = (
            f"Łowisko: {LOCATION_NAME}\n"
            f"Sobota: {sobota.strftime('%d.%m.%Y')} | Niedziela: {niedziela.strftime('%d.%m.%Y')}\n\n"
            f"{podsumowanie}\n\n"
            "---\n"
            "Wiadomość wygenerowana automatycznie przez rybackie_prognozy.py"
        )
        tresc_html = zbuduj_html_maila(LOCATION_NAME, sobota, niedziela, dane_sobota, dane_niedziela, podsumowanie)

        log("[info] Wysyłam e-mail...")
        wyslij_mail(temat, tresc_plain, tresc_html)
        log("[info] Gotowe - e-mail wysłany.")

    except Exception as e:
        log(f"[błąd] {e}", blad=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
