# Download status

## Successfully downloaded original data files

| Asset | Local original bytes | Bytes | SHA256 |
|---|---|---:|---|
| dft_collision_2024 | `data/raw/dft/collision_2024.csv` | 19,208,488 | `32a78f4662e309160f37b1ea2b82017e85e07b62a022d680da7140e88706a17c` |
| dft_vehicle_2024 | `data/raw/dft/vehicle_2024.csv` | 20,296,911 | `1a60f65f07a44454bc03c63b35d6741f41c9dfbb05a26753406aef8bff4ae6cd` |
| dft_casualty_2024 | `data/raw/dft/casualty_2024.csv` | 10,439,101 | `838aad605a6ac638973f09248ef3a730dbd1de30ac8fc79dfd536e7d4a47b0f8` |
| dft_data_guide | `data/raw/dft/data_guide.xlsx` | 85,112 | `51b08606ef3dad1ae5d4c8726241b022fc8e4bbdc910ef0e5cc2fb92b054fc12` |
| cambridge_sites | `data/raw/cambridge/final_dataset.csv` | 1,903,727 | `db67429d3e1b019c2d1f8d044851dd9c473f8404bbe673b9219e7ffe5037a28c` |
| porto_archive | `data/raw/porto/dataset.zip` | 540,159,049 | `9ce0c1edc234581e51d367256576869776a2554b9b60bfd492fe01771078913a` |
| nyc_Medallion_Sample_100k | `data/raw/nyc/Medallion_Sample_100k.csv` | 7,642,693 | `cc98d9b4893bdc67e38a5ba6f58fe2d50858f903a29f3fbfcf10d6924d32681f` |
| nyc_Medallion_Sample_5k | `data/raw/nyc/Medallion_Sample_5k.csv` | 382,228 | `9f7feac559f727425b176f17b2a66e08b779b568ec0e2c10b70964b4c7e868de` |
| nyc_medallion_mapping_key | `data/raw/nyc/medallion_mapping_key.csv` | 45,405,342 | `6ba0652ff2affba41d663061318b4cca535e7e9254d01b20fad525db4124dc72` |
| weather_birmingham_2024 | `data/raw/weather/birmingham_era5_2024.json` | 429,534 | `7423378362835e3c5d622b2fccaee6d382c27d1b8dbb3fa774e66c672ec41813` |
| olist_archive | `data/raw/olist/dataset.zip` | 44,717,580 | `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784` |
| osm_birmingham_2024 | `data/raw/osm/birmingham_2024-01-01.json` | 39,418,344 | `d055612e77a38dbaeb65a81a4c7731c5151dedcced46beea33c016367c1f76a1` |

## Failed or restricted requests

These are recorded attempts, not inferred missing data. A later successful retry does not erase a failed request.

| Source / asset | Request | Recorded failure | Subsequently acquired / resolution |
|---|---|---|---|
| olist / olist_discovery | discovery | 'olist' | Corrected missing Olist source configuration; public archive subsequently downloaded and catalog license verified. Original error detail retained. |
| nyc / evidence_nyc_balanced_panel_host | https://public-data.chicagobooth.edu/oeystein-daljord/NYC-2013-Taxi-Data-Balanced/ | ConnectionError | False |
| osm / osm_birmingham_2024 | https://overpass-api.de/api/interpreter | HTTP 504 | True |
| olist / olist_catalog | https://www.kaggle.com/api/v1/datasets/list?search=brazilian-ecommerce | existing_file_checksum_missing_or_changed | Preserved first-attempt catalog bytes as olist_catalog_first_attempt_evidence; independently re-fetched official catalog under tracked path. No original bytes overwritten. |
| nyc / evidence_nyc_balanced_panel_host | https://public-data.chicagobooth.edu/oeystein-daljord/NYC-2013-Taxi-Data-Balanced/ | ConnectionError | False |

## Unavailable or withheld research data

- Traccar: no authorized server, account, devices or fleet-data permission supplied. No public fleet dataset was identified; demo records were not acquired.
- NYC: linked Chicago Booth balanced-panel host was checked separately. Repository samples/mapping do not constitute the complete 2013 balanced panel. Repository dataset reuse license is unresolved; only raw inspection/validation is permitted by this pipeline.
- Porto: live Kaggle catalog license is Unknown. If the archive is available it is quarantined, validated and excluded from processed research data and database imports.
- Historical DfT archive and global OSM dump: deliberately outside the bounded acquisition scope described in the inventory.

For a Kaggle authentication restriction, configure ~/.kaggle/kaggle.json (or KAGGLE_USERNAME/KAGGLE_KEY or KAGGLE_API_TOKEN) locally and rerun the affected source. Never send credentials in chat. Public successful downloads need no authentication.
