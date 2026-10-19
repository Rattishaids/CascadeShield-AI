# Data quality report

Validation covers all acquired rows, not a sample. Whole-file checksums are verified before ETL. ZIP archives passed CRC validation during download. Details for every column are in data_quality.json.

| Dataset / ZIP member | Rows | Exact duplicate rows beyond first | Duplicate declared keys | Missing key rows | Nonzero rule violations |
|---|---:|---:|---:|---:|---|
| dft_collision_2024 | 100,927 | 0 | 0 | 0 | {} |
| dft_vehicle_2024 | 183,514 | 0 | 0 | 0 | {} |
| dft_casualty_2024 | 128,272 | 0 | 0 | 0 | {} |
| cambridge_sites | 47,683 | 100 | 0 | 0 | {'missing_or_invalid_coordinates': 1} |
| olist:olist_customers_dataset.csv | 99,441 | 0 | 0 | 0 | {} |
| olist:olist_products_dataset.csv | 32,951 | 0 | 0 | 0 | {} |
| olist:olist_sellers_dataset.csv | 3,095 | 0 | 0 | 0 | {} |
| olist:olist_orders_dataset.csv | 99,441 | 0 | 0 | 0 | {} |
| olist:olist_geolocation_dataset.csv | 1,000,163 | 261831 | 0 | 0 | {'outside_generous_Brazil_bounds': 31} |
| olist:olist_order_items_dataset.csv | 112,650 | 0 | 0 | 0 | {} |
| olist:olist_order_payments_dataset.csv | 103,886 | 0 | 0 | 0 | {} |
| olist:olist_order_reviews_dataset.csv | 99,224 | 0 | 0 | 0 | {} |
| olist:product_category_name_translation.csv | 71 | 0 | 0 | 0 | {} |
| porto:train.csv | 1,710,670 | 3 | 81 | 0 | {'empty_polyline': 5901, 'source_missing_data_flag_true': 10} |
| nyc_Medallion_Sample_100k | 100,000 | 0 | 0 | 0 | {} |
| nyc_Medallion_Sample_5k | 5,000 | 0 | 0 | 0 | {} |
| nyc_medallion_mapping_key | 578,956 | 0 | 0 | 0 | {} |
| osm_birmingham_2024 | 157,946 | n/a | n/a | n/a | {} |
| weather_birmingham_2024 | 8,784 | n/a | n/a | n/a | {} |

## Missingness, dates and source limitations

### dft_collision_2024

Nonzero blank counts: {}

Observed dates: {'date': {'min': '2024-01-01T00:00:00', 'max': '2024-12-31T00:00:00'}}

### dft_vehicle_2024

Nonzero blank counts: {}

Observed dates: {}

### dft_casualty_2024

Nonzero blank counts: {}

Observed dates: {}

### cambridge_sites

Nonzero blank counts: {}

Observed dates: {}

Observed categories: {'factory': 13551, 'retail': 6441, 'warehouse': 27691}

Matches publisher count: True

### olist:olist_customers_dataset.csv

Nonzero blank counts: {}

Observed dates: {}

### olist:olist_products_dataset.csv

Nonzero blank counts: {'product_category_name': 610, 'product_name_lenght': 610, 'product_description_lenght': 610, 'product_photos_qty': 610, 'product_weight_g': 2, 'product_length_cm': 2, 'product_height_cm': 2, 'product_width_cm': 2}

Observed dates: {}

### olist:olist_sellers_dataset.csv

Nonzero blank counts: {}

Observed dates: {}

### olist:olist_orders_dataset.csv

Nonzero blank counts: {'order_approved_at': 160, 'order_delivered_carrier_date': 1783, 'order_delivered_customer_date': 2965}

Observed dates: {'order_purchase_timestamp': {'min': '2016-09-04T21:15:19', 'max': '2018-10-17T17:30:18'}, 'order_delivered_carrier_date': {'min': '2016-10-08T10:34:01', 'max': '2018-09-11T19:48:28'}, 'order_delivered_customer_date': {'min': '2016-10-11T13:46:32', 'max': '2018-10-17T13:22:46'}, 'order_estimated_delivery_date': {'min': '2016-09-30T00:00:00', 'max': '2018-11-12T00:00:00'}}

### olist:olist_geolocation_dataset.csv

Nonzero blank counts: {}

Observed dates: {}

### olist:olist_order_items_dataset.csv

Nonzero blank counts: {}

Observed dates: {'shipping_limit_date': {'min': '2016-09-19T00:15:34', 'max': '2020-04-09T22:35:08'}}

### olist:olist_order_payments_dataset.csv

Nonzero blank counts: {}

Observed dates: {}

### olist:olist_order_reviews_dataset.csv

Nonzero blank counts: {'review_comment_title': 87658, 'review_comment_message': 58274}

Observed dates: {'review_creation_date': {'min': '2016-10-02T00:00:00', 'max': '2018-08-31T00:00:00'}, 'review_answer_timestamp': {'min': '2016-10-07T18:32:28', 'max': '2018-10-29T12:27:35'}}

### olist:product_category_name_translation.csv

Nonzero blank counts: {}

Observed dates: {}

### porto:train.csv

Nonzero blank counts: {'ORIGIN_CALL': 1345900, 'ORIGIN_STAND': 904091}

Observed dates: {'TIMESTAMP_UTC': {'min': '2013-07-01T00:00:53+00:00', 'max': '2014-06-30T23:59:56+00:00'}}

Quarantined: license Unknown; no processed research derivative created.

### nyc_Medallion_Sample_100k

Nonzero blank counts: {}

Observed dates: {}

Quarantined: no explicit dataset license identified; no processed research derivative created.

### nyc_Medallion_Sample_5k

Nonzero blank counts: {}

Observed dates: {}

Quarantined: no explicit dataset license identified; no processed research derivative created.

### nyc_medallion_mapping_key

Nonzero blank counts: {}

Observed dates: {}

Quarantined: no explicit dataset license identified; no processed research derivative created.

### osm_birmingham_2024

Nonzero blank counts: {}

Observed dates: No observed record timestamp supplied

### weather_birmingham_2024

Nonzero blank counts: {}

Observed dates: {'time_utc': {'min': '2024-01-01T00:00', 'max': '2024-12-31T23:00'}}

Expected hours: 8784; matches: True.

## Relationship checks

```json
{
  "dft": {
    "collision_rows_with_vehicle_count_mismatch": 0,
    "collision_rows_with_casualty_count_mismatch": 0,
    "note": "Counts checked across acquired annual tables. Timestamp-to-UTC conversion needs explicit handling of DST ambiguity; no weather join was performed."
  },
  "olist_orphan_references": {}
}
```

## Interpretation

- DfT coded missing/unknown/not-applicable values are preserved. Blank counts alone are not full semantic missingness. Exact raw code counts and the downloaded official codebook are provided; code meanings vary by field.
- Exact duplicate source rows are retained, including Cambridge sites and Olist geolocation rows. No facility IDs, geocodes or unique ZIP-prefix centroids were invented.
- Invalid or geographically unexpected source coordinates remain in source files and processed text. PostGIS geometry is NULL when coordinates are globally invalid; geographic study-area filters require an explicit protocol.
- Olist outcomes use actual-minus-estimated delivery calendar dates for delivered orders with both dates. Actual delivery dates and derived outcomes must not become prediction-time features.
- Taxicab trips are passenger-mobility proxies. Porto and NYC are not evidence of freight cascades, and their reuse permissions remain unresolved.
- Cambridge bays and ERA5 weather are source-provider modelled quantities, clearly labelled. They are not generated by this project, measured loading-bay capacities or raw station observations.
- No evaluation has been run and no ML models were trained. The acquired sources cannot establish intervention effectiveness or observed logistics cascading disruption ground truth.

**Olist temporal review:** Purchase timestamps span 2016-09-04T21:15:19 to 2018-10-17T17:30:18; source shipping_limit_date extends to 2020-04-09T22:35:08. A shipping deadline is a different time concept from purchase/event time. Review these values before choosing a cohort; they were preserved rather than forced into the purchase-year range.

## Additional source-specific audits

See domain_quality.json for exact DfT semantic code labels/counts, OSM snapshot/tag coverage and observed Olist outcome counts.

Olist observed outcome counts: {'order_rows': 99441, 'status:delivered': 96478, 'observed_delivered_outcomes': 96470, 'late_by_calendar_date': 6534, 'status:invoiced': 314, 'outcome_missing_or_not_delivered': 2971, 'status:shipped': 1107, 'status:processing': 301, 'status:unavailable': 609, 'status:canceled': 625, 'status:created': 5, 'status:approved': 2}

Additional Olist chronology/value violations: {'order_delivered_carrier_date_before_purchase': 166}

OSM elements edited after requested historical snapshot: 0

Counts use the downloaded 2024_code_list labels. The classification is a transparent label-pattern audit, not an exhaustive clinical/semantic interpretation. Source codes remain unchanged; not-applicable is separated from missing/unknown. Read exact labels before analysis.
