# Fishing Forecast

Automatyczny skrypt generujący cotygodniową prognozę warunków wędkarskich, wysyłaną mailem w formie czytelnego, mobilnego raportu HTML.

## Jak to działa

1. **Pobranie danych pogodowych** — skrypt pobiera aktualne dane pogodowe (temperatura, ciśnienie, wiatr, opady) z darmowego API [Open-Meteo](https://open-meteo.com/).
2. **Analiza AI** — dane pogodowe przekazywane są do modelu Claude Haiku (Anthropic API), który ocenia, jak warunki atmosferyczne wpłyną na aktywność ryb.
3. **Generowanie raportu** — wynik analizy prezentowany jest w postaci wskaźnika aktywności wędkarskiej z kolorowym oznaczeniem (np. zielony = dobre warunki, czerwony = słabe warunki).
4. **Wysyłka e-mail** — gotowy raport HTML wysyłany jest automatycznie do zdefiniowanej listy odbiorców.

## Harmonogram

Skrypt uruchamiany jest cyklicznie za pomocą `cron` na Raspberry Pi — domyślnie w każdy piątek, tak aby prognoza była dostępna na nadchodzący weekend.

## Wymagania

- Python 3.9+
- Klucz API Open-Meteo (opcjonalnie — publiczne endpointy nie wymagają klucza)
- Klucz API Anthropic (Claude)
- Konto SMTP do wysyłki e-maili

## Instalacja

```bash
git clone <adres-repo>
cd fishing-forecast
pip install -r requirements.txt
cp .env.example .env
# uzupełnij zmienne w pliku .env
```

## Konfiguracja

Wszystkie wrażliwe dane (klucze API, dane SMTP, lista odbiorców) konfigurowane są przez zmienne środowiskowe w pliku `.env`:

| Zmienna | Opis |
|---|---|
| `ANTHROPIC_API_KEY` | Klucz API do modelu Claude |
| `LATITUDE` / `LONGITUDE` | Współrzędne lokalizacji łowiska |
| `SMTP_HOST` / `SMTP_PORT` | Serwer SMTP |
| `SMTP_USER` / `SMTP_PASSWORD` | Dane logowania do skrzynki nadawczej |
| `RECIPIENTS` | Lista adresów e-mail (oddzielone przecinkiem) |

## Uruchomienie cron (Raspberry Pi)

```bash
crontab -e
```

Dodaj wpis uruchamiający skrypt w każdy piątek o 8:00:

```
0 8 * * 5 /usr/bin/python3 /home/pi/fishing-forecast/fishing_forecast.py >> /home/pi/fishing-forecast/logs/run.log 2>&1
```

## Struktura repo

```
fishing-forecast/
├── fishing_forecast.py   # główny skrypt
├── requirements.txt      # zależności Pythona
├── .env.example          # przykładowa konfiguracja
├── logs/                 # logi z uruchomień (cron)
└── README.md
```

## Licencja

Projekt do użytku prywatnego / wewnętrznego.
