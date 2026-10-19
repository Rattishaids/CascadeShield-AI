# Dataset inventory

Generated from downloaded evidence and file scans at 2026-10-08T18:05:37.618283+00:00.

All nine requested sources were checked. GB 2024 is a bounded context pilot. Brazil, Portugal and NYC are independent cohorts. No combined operational dataset or experimental result is asserted.

| Source | Region | Actual acquisition | License / reuse | Scope and relevance |
|---|---|---|---|---|
| [dft](https://www.gov.uk/government/statistical-data-sets/road-safety-open-data) | Great Britain (not Northern Ireland) | 4 raw files; 50,029,612 bytes | Open Government Licence v3.0 | Police-reported injury collisions, vehicles and casualties; not all disruptions or road closures |
| [porto](https://www.kaggle.com/datasets/crailtap/taxi-trajectory) | Porto, Portugal | 1 raw files; 540,159,049 bytes | Unknown | Taxi mobility proxy, not freight operations; separate cohort |
| [nyc](https://github.com/walterwzhang/NYC-Taxi-2013-Data) | New York City, United States | 3 raw files; 53,430,263 bytes | No repository LICENSE identified; reuse permission unresolved | 2013 taxi driver samples/mapping and processing code; linked balanced-panel host must be checked |
| [cambridge](https://www.repository.cam.ac.uk/items/3d0eb1ad-d077-4e4e-84cb-79af35f0b163) | England and Wales | 1 raw files; 1,903,727 bytes | CC BY 4.0 | Static logistics-site locations, floor areas and author-modelled loading bays; no shipments or measured capacities |
| [olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | Brazil | 1 raw files; 44,717,580 bytes | CC BY-NC-SA 4.0 | E-commerce orders, items, sellers and delivery dates; independent Brazil cohort with no road-incident or cascade links |
| [overpass](https://overpass-turbo.eu/) | Query-defined Birmingham pilot bbox, England | Interface for the OSM extract; same underlying dataset | OSM data: ODbL 1.0; Turbo is a query interface, not an independent dataset | Read-only Overpass API extracts OSM historical road geometry and tags |
| [osm](https://www.openstreetmap.org/) | Global source; bounded Birmingham pilot acquired through Overpass | 1 raw files; 39,418,344 bytes | ODbL 1.0; attribution to OpenStreetMap contributors | Same dataset as Overpass extract; count once, not as independent evidence |
| [traccar](https://www.traccar.org/) | User-owned server and devices; none supplied | no_public_fleet_dataset | Apache-2.0 software does not license any fleet records | Authenticated /api/positions and /api/reports/route; no public evaluation fleet data identified |
| [weather](https://open-meteo.com/) | Requested Birmingham point and returned ERA5 grid cell only | 1 raw files; 429,534 bytes | CC BY 4.0 data; free hosted API is for non-commercial use subject to terms/rate limits | 2024 hourly ERA5 reanalysis; provider-modelled weather, not direct station observations or as-issued forecasts |

## dft

Source: https://www.gov.uk/government/statistical-data-sets/road-safety-open-data

License evidence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

**landing page status:** retrieved

**selected period:** 2024

**scope note:** Complete selected annual tables. Full 1979-latest and overlapping multi-year extracts are inventoried on the source page but not downloaded; bounded disk budget.

**Observed record date ranges:** [{'date': {'min': '2024-01-01T00:00:00', 'max': '2024-12-31T00:00:00'}}]

## porto

Source: https://www.kaggle.com/datasets/crailtap/taxi-trajectory

License evidence: https://www.kaggle.com/datasets/crailtap/taxi-trajectory

**landing page status:** retrieved

**catalog metadata:** {'ref': 'crailtap/taxi-trajectory', 'title': 'Taxi Trajectory Data', 'totalBytes': 540159049, 'lastUpdated': '2018-04-12T11:41:23.04Z', 'licenseName': 'Unknown'}

**reuse gate:** QUARANTINED until an explicit data license/permission is verified; Kaggle Unknown is not a license.

**Observed record date ranges:** [{'TIMESTAMP_UTC': {'min': '2013-07-01T00:00:53+00:00', 'max': '2014-06-30T23:59:56+00:00'}}]

## nyc

Source: https://github.com/walterwzhang/NYC-Taxi-2013-Data

License evidence: https://github.com/walterwzhang/NYC-Taxi-2013-Data

**landing page status:** retrieved

**temporal note:** Repository describes 2013; supplied mapping and sample ID CSVs may have no timestamps and are not the balanced-panel operational records.

**reuse gate:** QUARANTINED: no explicit repository data reuse license identified. Public accessibility does not establish permission.

## cambridge

Source: https://www.repository.cam.ac.uk/items/3d0eb1ad-d077-4e4e-84cb-79af35f0b163

License evidence: https://creativecommons.org/licenses/by/4.0/

**landing page status:** retrieved

**citation metadata:** [['citation_title', 'Research data supporting &quot;Logistics sites in England and Wales: Location, size, type and loading bays&quot;'], ['citation_author', 'De Saxe, Christopher'], ['citation_author', 'Ainalis, Daniel'], ['citation_author', 'Cebon, David'], ['citation_publication_date', '2023-11-01T10:28:34Z'], ['citation_keywords', 'electrification; factories; freight; heavy goods vehicles; retail; transport; warehouses'], ['citation_abstract_html_url', 'https://www.repository.cam.ac.uk/handle/1810/358738'], ['citation_doi', 'https://doi.org/10.17863/CAM.102176'], ['citation_pdf_url', 'https://www.repository.cam.ac.uk/bitstreams/57021e51-e0ee-4bd3-a2ca-fbf584268e2d/download']]

**temporal note:** Static published research inventory; per-site observation/effective dates are not supplied. Publication date is not a measurement date.

## olist

Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

License evidence: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

**landing page status:** retrieved

**catalog metadata:** {'ref': 'olistbr/brazilian-ecommerce', 'title': 'Brazilian E-Commerce Public Dataset by Olist', 'totalBytes': 44717580, 'lastUpdated': '2021-10-01T19:08:27.97Z', 'licenseName': 'CC BY-NC-SA 4.0'}

**Observed record date ranges:** [{'order_purchase_timestamp': {'min': '2016-09-04T21:15:19', 'max': '2018-10-17T17:30:18'}, 'order_delivered_carrier_date': {'min': '2016-10-08T10:34:01', 'max': '2018-09-11T19:48:28'}, 'order_delivered_customer_date': {'min': '2016-10-11T13:46:32', 'max': '2018-10-17T13:22:46'}, 'order_estimated_delivery_date': {'min': '2016-09-30T00:00:00', 'max': '2018-11-12T00:00:00'}}, {'shipping_limit_date': {'min': '2016-09-19T00:15:34', 'max': '2020-04-09T22:35:08'}}, {'review_creation_date': {'min': '2016-10-02T00:00:00', 'max': '2018-08-31T00:00:00'}, 'review_answer_timestamp': {'min': '2016-10-07T18:32:28', 'max': '2018-10-29T12:27:35'}}]

## overpass

Source: https://overpass-turbo.eu/

License evidence: https://www.openstreetmap.org/copyright

**landing page status:** retrieved

**requested snapshot utc:** 2024-01-01T00:00:00Z

**bbox south west north east:** [52.42, -1.99, 52.55, -1.78]

**limitations:** Road geometry only. HGV restrictions, turn restrictions, road speeds and completeness require validation. Ways intersecting bbox can extend beyond it.

## osm

Source: https://www.openstreetmap.org/

License evidence: https://www.openstreetmap.org/copyright

**landing page status:** retrieved

**requested snapshot utc:** 2024-01-01T00:00:00Z

**bbox south west north east:** [52.42, -1.99, 52.55, -1.78]

**limitations:** Road geometry only. HGV restrictions, turn restrictions, road speeds and completeness require validation. Ways intersecting bbox can extend beyond it.

## traccar

Source: https://www.traccar.org/

License evidence: https://raw.githubusercontent.com/traccar/traccar/master/LICENSE.txt

**landing page status:** retrieved

**api contract:** {'server_url': 'User-supplied authorized server; none supplied', 'api_version_in_downloaded_contract': '6.16.0', 'endpoints': ['GET /api/positions', 'GET /api/reports/route?deviceId=...&from=...&to=...'], 'authentication': ['HTTP Basic', 'Bearer API key'], 'route_report_schema': 'array of Position objects; schema is not acquired fleet records', 'speed_unit': 'knots (per Position schema)', 'data_size_and_period': 'Unavailable until authorized server/devices/time window are provided'}

**missing requirements:** Authorized server URL, account/token, permitted device IDs, time range and fleet-data consent/license. Demo records are excluded from research data.

## weather

Source: https://open-meteo.com/

License evidence: https://open-meteo.com/en/licence

**landing page status:** retrieved

**request parameters:** {'latitude': 52.4862, 'longitude': -1.8904, 'start_date': '2024-01-01', 'end_date': '2024-12-31', 'timezone': 'UTC', 'models': 'era5', 'hourly': 'temperature_2m,relative_humidity_2m,precipitation,rain,snowfall,wind_speed_10m,weather_code', 'wind_speed_unit': 'ms'}

**limitations:** One requested point, not GB-wide weather. Reanalysis can contain information unavailable at prediction time; not a forecast feature without availability-time controls.

**Observed record date ranges:** [{'time_utc': {'min': '2024-01-01T00:00', 'max': '2024-12-31T23:00'}}]

## Scope limits

Only complete 2024 annual DfT tables were selected. The multi-gigabyte 1979-latest archive and overlapping annual/multi-year extracts are not downloaded. The checked source page preserves their links and advertised sizes. The configured per-file limit is 1.5 GiB, total raw limit 3.5 GiB, with a 2 GiB free-space reserve.

OSM coverage is a Birmingham road-geometry pilot (south/west/north/east: 52.42, -1.99, 52.55, -1.78), as of 2024-01-01T00:00:00Z, not the global map or a validated HGV routing graph. Weather is one requested Birmingham location for 2024, not every collision/site location. Cambridge is a static inventory published in 2023; per-site effective dates are unavailable. No Cambridge sites are asserted to be active in 2024.

Kaggle source versions may change. Exact acquired bytes are identified by SHA256 and the HTTP ETag/Last-Modified when supplied. Catalog lastUpdated is dataset metadata, not a record observation date. NYC repository downloads are pinned to the recorded commit.
