# Milestone 4 data audit

Initial inspection date: **2026-10-16**, Asia/Calcutta. This audit reads existing acquired bytes, all processed CSV records, their provenance, the snapshot exporter and the completed Milestone 3 results. Historical reports and source files are preserved.

The repository contains **18 eligible historical research tables with 2,414,128 CSV rows, and zero linked observed Chennai freight training examples**. Rows include geographical entities, payment/review records and a derived order-outcome table. They are neither independent freight trips nor 2.41 million labeled examples.

Every one of the 18 processed CSV files was scanned through its last record: row counts and ordered headers agree with `data/metadata/processed_manifest.json`. All 12 original manifest raw assets and all 18 processed files match their stored SHA-256 values. The Chennai raw extract, graph and map were separately hashed. Results and all actual columns are recorded in [milestone_4_data_audit.json](../data/metadata/milestone_4_data_audit.json).

At the initial inspection, PostgreSQL on port 55432 timed out and the backend on port 8080 refused connections. After the existing services were started, the read-only verifier executed against **PostgreSQL 17.5 / PostGIS 3.5.2**: all **18 tables / 2,414,128 rows** agree with their manifests and import provenance, typed views evaluate successfully, and geometry validity/SRID checks pass. No quarantined Porto/NYC assets are imported. Evidence is in [milestone4_historical_database_verification.json](milestone4_historical_database_verification.json) and the audit manifest. No database replacement, research-table mutation or new historical import was performed.

## Historical tables actually present

| Cohort / table | Rows | Relevant recorded fields | Timestamp availability | Defensible use and missing labels |
| --- | ---: | --- | --- | --- |
| GB 2024 `collision` | 100,927 | Collision ID, coordinates, severity, vehicle/casualty count, road/speed-limit and weather-condition codes | `date`, `time`, minute-level local wall time; ETL adds `collision_datetime_local` without inventing a UTC offset | Police-reported injury collision analysis. No trip duration, closure length, shipment deadline/completion or logistics cascade. |
| GB 2024 `vehicle` | 183,514 | Collision ID, vehicle reference/type, manoeuvre, journey purpose and driver attributes | Collision time only through its explicit parent collision key | Vehicles involved in injury collisions. No continuous vehicle trips, assigned freight driver duties or dock history. |
| GB 2024 `casualty` | 128,272 | Collision/vehicle/casualty references, casualty class and injury severity | Collision time through the parent key | Injury outcomes, not delivery or downstream operational outcomes. |
| England/Wales `logistics_sites` | 47,683 | `category`, latitude/longitude, `sqm`, `bays`, added source row number | Static publication 2023-11-01; no per-site observation/effective dates | Site distribution. `bays` is the source authors' modeled estimate, not measured dock capacity or service. No shipments, schedules or real facility identifier. |
| Brazil `olist_customers_dataset` | 99,441 | Customer IDs, ZIP prefix, city/state | No event timestamp | Order-linked customer geography within Brazil only. |
| Brazil `olist_products_dataset` | 32,951 | Product ID/category, size/weight and description attributes | No event timestamp | Order-linked item attributes. No observed cargo-to-truck assignment. |
| Brazil `olist_sellers_dataset` | 3,095 | Seller ID, ZIP prefix, city/state | No event timestamp | Seller geography; no assertion that a seller ZIP is a depot or warehouse. |
| Brazil `olist_orders_dataset` | 99,441 | Order/customer IDs, status, purchase/approval/carrier/customer dates, estimated delivery date | Local wall time to seconds for lifecycle events, 2016–2018; timezone not supplied; estimate generally calendar date at midnight | Separate observed Brazil order lead-time/calendar-lateness study is possible. No vehicle route, driver, dock, road incident or intervention linkage. |
| Brazil `delivery_outcomes` | 99,441 | Order ID/status, renamed actual/estimated dates, `delivery_delay_days`, `late_by_calendar_date` | Derived from the preceding dates; no new observations | Existing ETL-derived calendar-date labels, not a second independent order cohort. Missing/ineligible outcomes stay blank. |
| Brazil `olist_geolocation_dataset` | 1,000,163 | ZIP prefix, coordinates, city/state | No event timestamp | Multiple ZIP-associated points, not GPS trajectories. Repeated locations are retained. |
| Brazil `olist_order_items_dataset` | 112,650 | Order/item/product/seller IDs, shipping limit, price/freight | `shipping_limit_date`; recorded range includes a 2020 outlier | Item/order relationships. Shipping limit is not truck departure or delivery completion. |
| Brazil `olist_order_payments_dataset` | 103,886 | Order ID, payment sequence/type/installments/value | No payment event timestamp | Payment attributes only when available at a declared prediction cutoff. |
| Brazil `olist_order_reviews_dataset` | 99,224 | Order/review IDs, score/comments, review dates | Review creation/answer timestamps, generally after service | Post-outcome diagnostics. Review score/text/time are unsafe purchase-time predictors. |
| Brazil `product_category_name_translation` | 71 | Portuguese/English category names | No event timestamp | Lookup dictionary, not training outcomes. |
| Birmingham `osm_nodes` | 128,744 | OSM node ID, coordinates, edit version/timestamp | Requested map snapshot 2024-01-01T00:00:00Z; individual timestamps are edit times | Real map geography, no measured travel time or operational event. |
| Birmingham `osm_ways` | 29,202 | OSM way ID, node IDs, tags, edit version/timestamp | Same historical map snapshot | Real geometry/tags. Tagged speed limits are not measured traffic speed. |
| Birmingham `osm_segments` | 136,639 | Way/segment indices, endpoint IDs/coordinates, tags | Inherited map snapshot, no traffic timestamps | ETL-derived consecutive node pairs. These are not independent journeys. |
| Birmingham `weather_hourly` | 8,784 | ERA5 temperature, humidity, rain/precipitation, snow, wind and code at returned grid cell | 2024-01-01T00:00 through 2024-12-31T23:00 UTC, hourly | Provider-modeled reanalysis at one requested location. Not direct station observations, as-issued forecasts, truck exposure or observed disruption labels. |

The SQL schemas are `cs_gb_2024`, `cs_england_wales_static`, `cs_brazil_olist` and `cs_birmingham_2024`. Full names, actual columns, source hashes, processed hashes, row checks and individual provenance categories are in the machine-readable manifest. `data/metadata/processed_manifest.json` documents the original transformations and column origins.

## Licenses and geographical separation

The downloaded source evidence establishes GB DfT **Open Government Licence v3.0**, Cambridge **CC BY 4.0**, Olist **CC BY-NC-SA 4.0**, OSM **ODbL 1.0**, and Open-Meteo data **CC BY 4.0** with separate hosted-service terms. Existing acquisition metadata retains source URLs and license-evidence URLs. These are the recorded licenses of the acquired versions; no new legal or source-status verification is implied.

Porto's 540,159,049-byte taxi ZIP remains quarantined because the acquired catalog says `Unknown` license. Its previously validated `train.csv` has 1,710,670 taxi rows, 2013-07-01 through 2014-06-30, with ID/call/taxi/timestamp/polyline fields. Potential taxi travel-time supervision does not establish a freight label or permission to reuse it. No Porto derivative is used here.

NYC's three original CSVs remain quarantined because repository data reuse permission is unresolved. They contain 100,000 and 5,000 driver samples and 578,956 medallion/driver mappings, rather than timestamped trajectories or delivery outcomes. Public access does not supply a missing license. No NYC derivative is used here.

Traccar provides software and a documented authenticated API, but no authorized operator server, devices, fleet records, consent or evaluation period were supplied. Its Apache-2.0 software license does not license other people's fleet data. There is no Traccar training table.

Overpass Turbo is a query interface to OSM, not an independent dataset. GB collisions, England/Wales sites, Brazilian orders, Porto taxis, NYC mappings, Birmingham weather and Chennai simulated operations are never joined as a single operation.

## Actual Olist outcome availability

A fresh full-file read finds 99,441 orders, 96,478 with status `delivered`, 2,965 missing customer-delivery timestamps, 1,783 missing carrier timestamps and 160 missing approval timestamps. Existing defensible calendar-date labels exist for **96,470** rows: **6,534 late**, **89,936 on time**; **2,971** rows have missing/ineligible labels. These reproduce the earlier domain audit rather than filling blanks. `delivered` status alone is insufficient to manufacture an outcome.

An independent Brazil study could predict order-level calendar lateness or lead time using only fields available by its declared cutoff. Cancellation/censoring, duplicated customer identities across splits, timezones, delivery-estimate availability, calendar-day versus timestamp semantics and temporal train/test separation would need explicit treatment. Milestone 4's Chennai simulator models do **not** train on this cohort or present its dates as observed Chennai road travel time. A separate Brazil model is not claimed as implemented or evaluated.

## Chennai geography and simulator evidence

The real Chennai OSM acquisition is bounded to `[13.04, 80.24, 13.095, 80.29]`, source timestamp `2026-10-09T05:33:21Z`, ODbL 1.0, with OpenStreetMap contributor attribution. It contains real mapped roads; simulated warehouse coordinates on these roads are not observed logistics premises.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/raw/chennai_osm/central_chennai.json` | 7,984,665 | `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d` |
| `data/processed/chennai_osm/road_graph.json` | 9,160,346 | `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60` |
| `data/processed/chennai_osm/roads.geojson` | 4,712,750 | `d714bab06c2eeb022eab54dac8a8224ca6c5330579579fa66938e35c6497f478` |

The graph contains 12,386 nodes, 23,907 directed edges and 10 supported node-via turn restrictions. Missing road speeds and configured truck speeds remain labeled assumptions; OSM edit timestamps do not validate speeds. Geographic coverage, filtering and unsupported restrictions remain documented in `reports/CHENNAI_NETWORK.md`.

The existing Milestone 2 export directory has **five graph-snapshot JSON files**, with two-truck/8-node demonstration states at clocks 1000 or 1352.6 seconds. Several are repeat exports of closely related demonstration setups. They are useful converter examples, not five independent operations or a sufficient training/evaluation set. Graph node features use allowlists and availability masks. `predictions` contains rule-derived estimates; `realizedLabels` is separate and contains only authoritative simulated outcomes already observed by export time. Training must pair an earlier input snapshot with later outcomes externally. A completed snapshot must not predict its own already-completed target.

Milestone 3's 260 policy rows cover **20 paired scenarios, four profiles and seeds 11/22/33/44/55** on this one road network. Policies/ablations share scenario inputs and are correlated alternatives, not 260 independent operations. Per-policy summary metrics, terminal realized impacts, decision traces and hypothetical counterfactual forecasts have different meanings. `MODEL_ROLLOUT_FORECAST` is never converted into an observed label. Seeds 44 and 55 are already reported/exposed despite the historical prospective assessment tag, so all five old seeds are development/history only for Milestone 4. Fresh final assessment identities must be frozen before tuning.

## Provenance categories and valid supervision

1. **Observed historical data:** source records such as GB injury reports, Brazil lifecycle dates and mapped geography. They retain their own geography, period, permissions and missingness.
2. **Derived estimates or assumptions:** source-author modeled bays, ERA5 reanalysis, ETL calendar-date differences, route/speed assumptions, rule ETA/risk and forecast-dependent graph edges. Derived labels can be valid when their observed inputs and exact definition are retained; they do not create another observed event.
3. **Simulated logistics data/outcomes:** configured trucks, drivers, docks, deadlines, schedules, incidents, authoritative future road arrival/service/delivery/impact events. These can train and assess a model of this simulator only. Their validity depends on cutoff controls, censoring and independent scenario groups; they do not establish field performance or incident causality.

The supported training targets and censoring rules are specified in [MILESTONE_4_LABEL_DEFINITIONS.md](MILESTONE_4_LABEL_DEFINITIONS.md). New corpus rows and split counts are published only after actual generation. The audit manifest does not silently count planned examples as acquired examples.

## Real-world validation gaps

No observed Chennai HGV GPS traces/travel times, legal driver-duty records, queue/service distributions, warehouse reservation/occupancy logs, delivery deadlines/completions, linked disruption exposure or approved intervention outcomes exist in this repository. Therefore truck speeds, service-time distributions, driver availability, deadline distributions, disruption frequency/severity/duration and decision effectiveness cannot be calibrated or validated against a Chennai operator. Olist's fulfillment times do not identify road travel or dock service; GB crash counts do not identify Chennai disruption frequency; Cambridge's modeled bays do not validate simulated Chennai docks. No unsupported cross-domain calibration is performed.

Scaling experiments on this bounded map can measure software runtime and simulator outcomes. They cannot establish transfer across road networks, operators, countries or field distribution shifts. Learned uncertainty/calibration evaluated on generated examples is conditional on that generator. Independent lawfully linked fleet records and operator validation remain prerequisites for deployment claims.
