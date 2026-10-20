# Actual dataset columns

Column names below are read from acquired files, including ZIP members. Source identifiers remain strings. Processed-column origins and transformations are in data/metadata/processed_manifest.json.

## dft_collision_2024

Actual rows/elements: 100,927

**columns:** `collision_index`, `collision_year`, `collision_ref_no`, `location_easting_osgr`, `location_northing_osgr`, `longitude`, `latitude`, `police_force`, `collision_severity`, `number_of_vehicles`, `number_of_casualties`, `date`, `day_of_week`, `time`, `local_authority_district`, `local_authority_ons_district`, `local_authority_highway`, `local_authority_highway_current`, `first_road_class`, `first_road_number`, `road_type`, `speed_limit`, `junction_detail_historic`, `junction_detail`, `junction_control`, `second_road_class`, `second_road_number`, `pedestrian_crossing_human_control_historic`, `pedestrian_crossing_physical_facilities_historic`, `pedestrian_crossing`, `light_conditions`, `weather_conditions`, `road_surface_conditions`, `special_conditions_at_site`, `carriageway_hazards_historic`, `carriageway_hazards`, `urban_or_rural_area`, `did_police_officer_attend_scene_of_accident`, `trunk_road_flag`, `lsoa_of_accident_location`, `enhanced_severity_collision`, `collision_injury_based`, `collision_adjusted_severity_serious`, `collision_adjusted_severity_slight`

**key_columns:** `collision_index`

## dft_vehicle_2024

Actual rows/elements: 183,514

**columns:** `collision_index`, `collision_year`, `collision_ref_no`, `vehicle_reference`, `vehicle_type`, `towing_and_articulation`, `vehicle_manoeuvre_historic`, `vehicle_manoeuvre`, `vehicle_direction_from`, `vehicle_direction_to`, `vehicle_location_restricted_lane_historic`, `vehicle_location_restricted_lane`, `junction_location`, `skidding_and_overturning`, `hit_object_in_carriageway`, `vehicle_leaving_carriageway`, `hit_object_off_carriageway`, `first_point_of_impact`, `vehicle_left_hand_drive`, `journey_purpose_of_driver_historic`, `journey_purpose_of_driver`, `sex_of_driver`, `age_of_driver`, `age_band_of_driver`, `engine_capacity_cc`, `propulsion_code`, `age_of_vehicle`, `generic_make_model`, `driver_imd_decile`, `lsoa_of_driver`, `escooter_flag`, `driver_distance_banding`

**key_columns:** `collision_index`, `vehicle_reference`

## dft_casualty_2024

Actual rows/elements: 128,272

**columns:** `collision_index`, `collision_year`, `collision_ref_no`, `vehicle_reference`, `casualty_reference`, `casualty_class`, `sex_of_casualty`, `age_of_casualty`, `age_band_of_casualty`, `casualty_severity`, `pedestrian_location`, `pedestrian_movement`, `car_passenger`, `bus_or_coach_passenger`, `pedestrian_road_maintenance_worker`, `casualty_type`, `casualty_imd_decile`, `lsoa_of_casualty`, `enhanced_casualty_severity`, `casualty_injury_based`, `casualty_adjusted_severity_serious`, `casualty_adjusted_severity_slight`, `casualty_distance_banding`, `escooter_flag`

**key_columns:** `collision_index`, `casualty_reference`

## cambridge_sites

Actual rows/elements: 47,683

**columns:** `category`, `latitude`, `longitude`, `sqm`, `bays`

**key_columns:**

## olist:olist_customers_dataset.csv

Actual rows/elements: 99,441

**columns:** `customer_id`, `customer_unique_id`, `customer_zip_code_prefix`, `customer_city`, `customer_state`

**key_columns:** `customer_id`

## olist:olist_products_dataset.csv

Actual rows/elements: 32,951

**columns:** `product_id`, `product_category_name`, `product_name_lenght`, `product_description_lenght`, `product_photos_qty`, `product_weight_g`, `product_length_cm`, `product_height_cm`, `product_width_cm`

**key_columns:** `product_id`

## olist:olist_sellers_dataset.csv

Actual rows/elements: 3,095

**columns:** `seller_id`, `seller_zip_code_prefix`, `seller_city`, `seller_state`

**key_columns:** `seller_id`

## olist:olist_orders_dataset.csv

Actual rows/elements: 99,441

**columns:** `order_id`, `customer_id`, `order_status`, `order_purchase_timestamp`, `order_approved_at`, `order_delivered_carrier_date`, `order_delivered_customer_date`, `order_estimated_delivery_date`

**key_columns:** `order_id`

## olist:olist_geolocation_dataset.csv

Actual rows/elements: 1,000,163

**columns:** `geolocation_zip_code_prefix`, `geolocation_lat`, `geolocation_lng`, `geolocation_city`, `geolocation_state`

**key_columns:**

## olist:olist_order_items_dataset.csv

Actual rows/elements: 112,650

**columns:** `order_id`, `order_item_id`, `product_id`, `seller_id`, `shipping_limit_date`, `price`, `freight_value`

**key_columns:** `order_id`, `order_item_id`

## olist:olist_order_payments_dataset.csv

Actual rows/elements: 103,886

**columns:** `order_id`, `payment_sequential`, `payment_type`, `payment_installments`, `payment_value`

**key_columns:** `order_id`, `payment_sequential`

## olist:olist_order_reviews_dataset.csv

Actual rows/elements: 99,224

**columns:** `review_id`, `order_id`, `review_score`, `review_comment_title`, `review_comment_message`, `review_creation_date`, `review_answer_timestamp`

**key_columns:**

## olist:product_category_name_translation.csv

Actual rows/elements: 71

**columns:** `product_category_name`, `product_category_name_english`

**key_columns:** `product_category_name`

## porto:train.csv

Actual rows/elements: 1,710,670

**columns:** `TRIP_ID`, `CALL_TYPE`, `ORIGIN_CALL`, `ORIGIN_STAND`, `TAXI_ID`, `TIMESTAMP`, `DAY_TYPE`, `MISSING_DATA`, `POLYLINE`

**key_columns:** `TRIP_ID`

## nyc_Medallion_Sample_100k

Actual rows/elements: 100,000

**columns:** `medallion`, `hack_license`, `medallion_index`, `driver_index`

**key_columns:**

## nyc_Medallion_Sample_5k

Actual rows/elements: 5,000

**columns:** `medallion`, `hack_license`, `medallion_index`, `driver_index`

**key_columns:**

## nyc_medallion_mapping_key

Actual rows/elements: 578,956

**columns:** `medallion`, `hack_license`, `medallion_index`, `driver_index`, `company_owned`

**key_columns:**

## osm_birmingham_2024

Actual rows/elements: 157,946

**columns:** `changeset`, `id`, `lat`, `lon`, `nodes`, `tags`, `timestamp`, `type`, `uid`, `user`, `version`

**node_columns:** `changeset`, `id`, `lat`, `lon`, `tags`, `timestamp`, `type`, `uid`, `user`, `version`

**way_columns:** `changeset`, `id`, `nodes`, `tags`, `timestamp`, `type`, `uid`, `user`, `version`

## weather_birmingham_2024

Actual rows/elements: 8,784

**columns:** `latitude`, `longitude`, `generationtime_ms`, `utc_offset_seconds`, `timezone`, `timezone_abbreviation`, `elevation`, `hourly_units`, `hourly`

**hourly_columns:** `time`, `temperature_2m`, `relative_humidity_2m`, `precipitation`, `rain`, `snowfall`, `wind_speed_10m`, `weather_code`

Units: {'time': 'iso8601', 'temperature_2m': '°C', 'relative_humidity_2m': '%', 'precipitation': 'mm', 'rain': 'mm', 'snowfall': 'cm', 'wind_speed_10m': 'm/s', 'weather_code': 'wmo code'}

## Traccar API contract (no records acquired)

The downloaded OpenAPI specification describes positions and route reports. Its schema is documentation, not evidence that any fleet records are available. Inspect data/metadata/evidence/traccar_openapi.yaml for the exact contract. No columns for an unavailable fleet dataset are invented.
