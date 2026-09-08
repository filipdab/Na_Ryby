# Rybackie Prognozy

Skrypt na Raspberry Pi, który co tydzień generuje i wysyła mailem prognozę warunków wędkarskich na nadchodzący weekend.

## Co dokładnie robi

1. **Pogoda** — pobiera prognozę godzinową (temperatura, wiatr, ciśnienie, zachmurzenie, opady) z Open-Meteo dla najbliższej soboty i niedzieli, osobno dla dnia (6:00–17:00) i wieczoru (18:00–22:00), wraz z trendem ciśnienia z 2 dni wcześniej.
2. **Faza Księżyca** — liczona lokalnie (bez zewnętrznego API) dla obu dni.
3. **Indeks aktywności ryb (1–10)** — lokalny, regułowy wskaźnik uwzględniający trend ciśnienia, siłę wiatru, zachmurzenie, opady i fazę Księżyca — liczony osobno dla dnia i wieczoru każdego dnia.
4. **Analiza AI** — wszystkie powyższe dane trafiają do modelu Claude Haiku 4.5 (Anthropic API), który pisze krótką ocenę warunków na sobotę i niedzielę (dzień/wieczór) plus jedną praktyczną rekomendację.
5. **E-mail** — gotowy raport wysyłany jest jako czytelny, mobilny HTML (kolorowe karty z indeksem aktywności) do listy odbiorców, z wersją plain-text jako fallback.

Skrypt ma wbudowane ponawianie zapytań (retry z backoffem) zarówno dla Open-Meteo, jak i Anthropic API, na wypadek chwilowych błędów 429/5xx.

## Harmonogram

Uruchamiany przez `cron`, domyślnie w piątek wieczorem:

```
0 18 * * 5 /usr/bin/python3 /home/pi/rybackie_prognozy.py >> /home/pi/rybackie_prognozy.log 2>&1
```

## Wymagania

- Python 3.7+ (kompatybilny ze starszymi Raspberry Pi OS)
- `pip3 install -r requirements.txt`
- Klucz API Anthropic (https://console.anthropic.com/settings/keys)
- Hasło aplikacji (App Password) do konta e-mail nadawcy, jeśli używasz Gmaila

## Konfiguracja

Dane wrażliwe (lokalizacja łowiska, adresy e-mail, klucze API) **nie są wpisane w kodzie** — wczytywane są ze zmiennych środowiskowych. Skopiuj `.env.example` do `.env` i uzupełnij:

| Zmienna | Opis |
|---|---|
| `ANTHROPIC_API_KEY` | Klucz API do modelu Claude |
| `EMAIL_FROM` | Adres e-mail nadawcy |
| `EMAIL_TO` | Adresy odbiorców, oddzielone przecinkiem |
| `EMAIL_PASSWORD` | Hasło aplikacji do konta nadawcy |
| `SMTP_SERVER` / `SMTP_PORT` | Domyślnie `smtp.gmail.com` / `465` |
| `LATITUDE` / `LONGITUDE` | Współrzędne łowiska |
| `LOCATION_NAME` | Nazwa łowiska w treści maila |

> Skrypt czyta te zmienne z `os.environ`, więc jeśli wolisz, ustaw je zamiast pliku `.env` bezpośrednio w `crontab` albo `/etc/environment`.

## Struktura repo

```
rybackie-prognozy/
├── rybackie_prognozy.py   # główny skrypt
├── requirements.txt       # zależności Pythona
├── .env.example           # przykładowa konfiguracja (bez prawdziwych danych)
└── README.md
```
