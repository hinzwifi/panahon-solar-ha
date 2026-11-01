# Technical Context & Reverse-Engineering Reference: DOST-PAGASA PANaHON (`com.dostpagasa.panahon`)

> **Purpose**: Complete technical reference extracted from `PANaHON_+Weather+App_1.1.3_APKPure.xapk` (`com.dostpagasa.panahon` v1.1.3), detailing why the mobile app lags on modern phones, how its internal Flutter AOT (`package:nowcast/*`) API client works, why its Philippine weather forecast is so accurate, and how it integrates into Home Assistant for Philippine Solar PV & Battery System planning.

---

## 1. Why the PANaHON App Is Laggy on Modern Phones

Inspection of `PANaHON_+Weather+App_1.1.3_APKPure.xapk` reveals three architectural bottlenecks:
1. **32-Bit Only (`armeabi-v7a`) Native Binaries**:
   - The split bundle contains `com.dostpagasa.panahon.apk` + `config.armeabi_v7a.apk` (`lib/armeabi-v7a/libapp.so` and `lib/armeabi-v7a/libflutter.so`) with **no 64-bit `arm64-v8a` split**. On modern 64-bit Snapdragon/MediaTek phones, it runs in 32-bit compatibility mode or software binary translation.
2. **Heavy Embedded WebViews & YouTube Iframe Players**:
   - `package:nowcast/src/features/maps/presentation/pages/maps_page.dart` (`@878002313`) spins up `flutter_inappwebview` loading `https://panahon.gov.ph/?embed=panahon-mobile` inside the Flutter widget tree.
   - `package:nowcast/src/features/forecast/presentation/pages/youtube_player_page.dart` (`@863010948`) loads an embedded YouTube iframe (`https://www.youtube.com/iframe_api`) alongside continuous `ShimmerSkeleton` shaders.
3. **Why Morphe Patch CLI Alone Only Patches the Shell**:
   - `morphe-cli.jar` patches `AndroidManifest.xml` and Dalvik `classes.dex` (which in Flutter only hosts the thin Java/Kotlin plugin wrappers). All PANaHON business logic and REST API endpoints live inside the compiled Dart AOT snapshot (`lib/armeabi-v7a/libapp.so`).
   - We added [`DebloatPanahonPatch.kt`](file:///home/hinzwifi/Music/morphe-tcl/patches/src/main/kotlin/app/template/patches/panahon/DebloatPanahonPatch.kt) and [`patch_panahon.sh`](file:///home/hinzwifi/Music/panahon-ha/patch_panahon.sh) to merge the split XAPK and strip background telemetry while forcing `android:hardwareAccelerated="true"`, **and** built a native Home Assistant integration so you never have to open the laggy app.

---

## 2. Why PANaHON's Philippine Forecast Is Accurate

Internal attribution strings in `lib/armeabi-v7a/libapp.so` (`package:nowcast/src/features/forecast/presentation/pages/forecast_default_page.dart` `@222353329`) reveal:
> *"By integrating numerical weather forecasts from the European Centre for Medium-Range Weather Forecasts (ECMWF). Location Forecast is based on data and products of the ECMWF."*

Specifically, PANaHON combines:
1. **ECMWF IFS High-Resolution Numerical Weather Forecasts** for hourly and 5-day location forecasts (`Nowcast`, `HourlyForecast`, `DailyForecast`).
2. **DOST-PAGASA Ground-Truth Station Telemetry** from nationwide **Automatic Weather Stations (AWS)** (`AutomaticObservation`) and **Synoptic Stations** (`ManualObservation`), which directly measure **`solar_radiation_avg` ($\text{W/m}^2$)**, `air_temperature_avg`, `relative_humidity_avg`, `heat_index_avg`, `precip_1h`, `precip_3h`, `accumulated_rain`, `wind_speed`, and `barometric_pressure_avg`.

---

## 3. Reverse-Engineered REST API Specification (`https://api.mobile.panahon.gov.ph/api/v1`)

### 3.1 Dart Service & Model Architecture (`package:nowcast/*`)
- `package:nowcast/services/api_http_service.dart` (`@828397250`)
- `package:nowcast/services/weather_api_service.dart` (`@848075807`)
- `package:nowcast/services/observation_api_service.dart` (`@850402376`)
- `package:nowcast/services/alerts_api_service.dart` (`@844377867`)
- `package:nowcast/services/version_service.dart`
- `package:nowcast/models/weather_dashboard_data.dart`
- `package:nowcast/models/nowcast.dart` (`Nowcast.fromJson`)
- `package:nowcast/models/hourly_forecast.dart` (`HourlyForecast.fromJson`)
- `package:nowcast/models/daily_forecast.dart` (`DailyForecast.fromJson`)
- `package:nowcast/models/automatic_observation.dart` (`AutomaticObservation.fromJson`)
- `package:nowcast/models/manual_observation.dart` (`ManualObservation.fromJson`)
- `package:nowcast/models/city_outlook.dart`
- `package:nowcast/models/alert.dart`

### 3.2 Complete Endpoint Map

| Category | Method | Endpoint URL | Purpose & Query / Payload Parameters |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `https://api.mobile.panahon.gov.ph/api/v1/auth/register-device` | Registers generated Ed25519 `public_key` & `device_id` (`_registerDevice@828397250`) |
| **Auth** | `POST` | `https://api.mobile.panahon.gov.ph/api/v1/auth/challenge` | Requests cryptographic challenge nonce for `device_id` |
| **Auth** | `POST` | `https://api.mobile.panahon.gov.ph/api/v1/auth/verify` | Verifies Ed25519 `signature` over challenge, returns Bearer `access_token` |
| **Forecast** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/nowcast/dashboard` | Returns `nowcast`, `hourly_forecast` (24h), `daily_forecast` (5-day), and `public_weather_forecast` for `latitude` & `longitude` (`_fetchDashboardJson@848075807`) |
| **Search** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/location/search` | Searches Philippine barangays/cities/municipalities and returns coordinates |
| **Outlook** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/city-outlook/philippine-cities` | Multi-day PAGASA outlook for major Philippine cities |
| **Outlook** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/city-outlook/philippine-tourist-areas` | Multi-day PAGASA outlook for Philippine tourist areas |
| **Outlook** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/city-outlook/asian-cities` | Regional outlook for Asian cities |
| **AWS Live** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/observation/automatic` | Near-real-time PAGASA Automatic Weather Station (AWS) telemetry (`solar_radiation_avg`, `air_temperature_avg`, `relative_humidity_avg`, `heat_index_avg`, `rainfall`, `wind_speed`, `barometric_pressure_avg`) |
| **AWS Hist** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/observation/automatic/historical-data` | 24-hour historical series for an AWS `site_id` (`ObservationHist.fromJson`) |
| **Synoptic** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/observation/manual` | PAGASA Synoptic Station manual observations (`accumulated_rain`, `precip_1h`, `precip_3h`, `heat_index`, `wind_direction`) |
| **Synoptic Hist** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/observation/manual/historical-data` | Historical synoptic station series |
| **Alerts** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/alerts` | PAGASA Severe Weather Bulletins, Tropical Cyclone Wind Signals (`tropical_cyclone`), Heavy Rainfall Warnings, and `flood_alerts` |
| **Version** | `GET` | `https://api.mobile.panahon.gov.ph/api/v1/version` | Returns `minimum_version` and `latest_version` |

### 3.3 Authentication & Caching Headers (`ApiHttpService`)
- `X-Device-Id`: UUID / device identifier persisted in `FlutterSecureStorage` (`device_key_auth`)
- `X-Auth-Provider`: Firebase App Check / Ed25519 provider header
- `Authorization`: `Bearer <access_token>`
- `If-None-Match`: ETag string cached per URL (`nowcast_etags_by_url`, `observation_api_etags`, `alerts_etag`) to receive `304 Not Modified` and reuse cached JSON (`nowcast_bodies_by_url`).

### 3.4 Key JSON Telemetry Fields for Solar System Planning
From `AutomaticObservation.fromJson` and `Nowcast.fromJson`:
- `solar_radiation_avg`: Average global horizontal solar irradiance ($\text{W/m}^2$)
- `air_temperature_avg` / `temperature`: Ambient air temperature ($^\circ\text{C}$)
- `relative_humidity_avg`: Relative humidity ($\%$)
- `heat_index_avg` / `heat_index` / `heat_index_description` / `hindex_desc`: Philippine apparent temperature ($^\circ\text{C}$)
- `rainfall` / `accumulated_rain` / `precip_1h` / `precip_3h` / `rainfall_description`: Precipitation ($\text{mm}$)
- `wind_speed` / `wind_direction` / `wind_deviation`: Wind telemetry
- `barometric_pressure_avg`: Atmospheric pressure ($\text{hPa}$)
- `site_id` / `observed_at` / `issued_at` / `valid_until_at`

---

## 4. Dual-Source Home Assistant Solar Architecture

Because `api.mobile.panahon.gov.ph` gates unauthenticated requests behind Firebase App Check + Ed25519 challenge-response (`403 Forbidden` without a registered device token), our Home Assistant extension (`custom_components/panahon_solar` and `panahon_solar_service.py`) implements a **Dual-Source Engine**:
1. **Source A — Authorized PANaHON Mobile API (`api.mobile.panahon.gov.ph/api/v1`)**:
   - Used automatically whenever `PANAHON_ACCESS_TOKEN` and `PANAHON_DEVICE_ID` are set in `.env` (or Home Assistant Config Flow), complete with `If-None-Match` ETag caching.
2. **Source B — Zero-Auth ECMWF IFS + Solar Irradiance Engine (Automatic Default/Fallback)**:
   - Queries the exact **ECMWF IFS** numerical weather model that PANaHON uses for its Location Forecast (`model=ecmwf_ifs025` / best-match tropical multi-model blend) + live shortwave solar radiation (`shortwave_radiation`, `direct_normal_irradiance`, `diffuse_radiation`, `global_tilted_irradiance`) for your exact Philippine coordinates.
   - Computes **Philippine Tropical PV Cell Temperature Derating**:
     $$\text{T}_{\text{cell}} = \text{T}_{\text{air}} + \frac{\text{NOCT} - 20}{800} \cdot G_{\text{POA}}$$
     $$\text{P}_{\text{PV}} = \text{P}_{\text{kWp}} \cdot \frac{G_{\text{POA}}}{1000} \cdot \eta_{\text{sys}} \cdot \left[1 + \gamma \left(\text{T}_{\text{cell}} - 25^\circ\text{C}\right)\right]$$
     where $\gamma = -0.35\%/^\circ\text{C}$, accurately modeling midday thermal losses on Philippine rooftops.
