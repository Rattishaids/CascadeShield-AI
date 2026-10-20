# Data provenance and licensing

## Included Chennai road database

The two files below are adapted from OpenStreetMap and are distributed under the
[Open Data Commons Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The database attribution is **© OpenStreetMap contributors**. This notice applies
to these road databases, independently of the licensing of project source code.
The original contributor and licensing information is at
[OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

| Included file | Bytes | SHA-256 |
| --- | ---: | --- |
| `data/processed/chennai_osm/road_graph.json` | 9,160,346 | `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60` |
| `data/processed/chennai_osm/roads.geojson` | 4,712,750 | `d714bab06c2eeb022eab54dac8a8224ca6c5330579579fa66938e35c6497f478` |

These ordinary Git files are included in GitHub Download ZIP. They require no
Git LFS checkout, historical research dataset or live Overpass request to run.
The backend loads them from the configured local network directory and imports
the network geometry into its own PostgreSQL schema.

The source was acquired through `https://overpass-api.de/api/interpreter` for
central Chennai, bounding box south/west/north/east
`[13.04, 80.24, 13.095, 80.29]`. Its OSM base timestamp is
`2026-10-09T05:33:21Z`. The original 7,984,665-byte extract is preserved locally
outside this release; its SHA-256 is
`38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`.

Adaptations include highway/access filtering, connected graph construction,
directed edges, supported turn restrictions and map segment export. Missing
speeds use explicitly labelled simulation assumptions; they are not observed
traffic speeds or asserted legal speed limits. See
[preparation script](scripts/prepare_chennai_network.py),
[configuration](config/chennai_network.json),
[acquisition provenance](data/metadata/chennai_network_provenance.json) and
[network report](reports/CHENNAI_NETWORK.md). Reacquiring current OSM data may
produce a different snapshot; the bundled files preserve this study's network.

Keep this attribution and ODbL notice with redistributed copies. Publicly used
adapted databases must comply with ODbL share-alike and source-availability
requirements. A copy of the official license is included in
[LICENSES/ODbL-1.0.txt](LICENSES/ODbL-1.0.txt). Its text was retrieved through the
web tool from the official
[plain-text license](https://opendatacommons.org/licenses/odbl/odbl-10.txt),
which is linked by the official legal-code page. The license copy's SHA-256 is
`842dd7ef80e82fb9d2629535ebcf6e370a73bd6b281abcfaf4315a985826d96a`.

The optional raster basemap requests public OpenStreetMap tiles at runtime.
Those tiles are not bundled or bulk downloaded. Their use is subject to the
[OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
Local vector roads, routing and simulation do not depend on online raster tiles.

## Simulated operations, study reports and model artifacts

Trucks, loads, incidents, warehouses, docks, drivers, deliveries, benchmarks and
model training targets in the simulator are explicitly simulated. Real map
geometry does not make their operational outcomes observed freight data.
The included small Milestone 4 model bundle was trained on those declared
simulated operations. It is optional; default simulation uses deterministic
methods and remains available when the model service is absent.

Historical benchmark numbers and model artifact bytes are preserved. Large
training corpora, row-level prediction exports and policy traces are omitted
from the download. The release is not an archive of every study input/output;
the research documentation identifies what additional regeneration is required.

No project-wide source-code or model-artifact reuse license was found in the
original project. This release does not invent one. Publication and permission
to run the requested demonstration do not imply a new MIT, Apache or other
general reuse grant. The owner can select a source/model license in a later
change. OpenStreetMap and third-party package licenses remain applicable.

## Excluded historical research datasets

Only manifests, schema descriptions, acquisition scripts and quality reports
are retained. No raw or processed records from the following cohorts are
needed by the simulator or included in this release:

| Source | Recorded licensing status | Release treatment |
| --- | --- | --- |
| UK DfT road safety | Open Government Licence 3.0 | Excluded; use acquisition pipeline and source terms |
| Cambridge logistics sites | CC BY 4.0 | Excluded; source authors' site and modelled-bay inventory remains a separate cohort |
| Olist Brazil e-commerce | CC BY-NC-SA 4.0 in acquired catalog | Excluded; do not assume unrestricted commercial redistribution |
| Porto taxi | Catalog license unknown | Excluded and quarantined pending explicit permission |
| NYC taxi repository | No explicit reuse license identified | Excluded and quarantined pending explicit permission |
| Birmingham OSM and ERA5 weather | ODbL and CC BY 4.0 respectively; provider API terms also apply | Excluded; not joined to Chennai operations |
| Traccar fleet telemetry | No authorized fleet dataset supplied | No telemetry records included |

See [dataset inventory](reports/DATASET_INVENTORY.md),
[source inventory](data/metadata/source_inventory.json) and
[missing data requirements](reports/MISSING_DATA_REQUIREMENTS.md). The table
records acquisition-time findings; it does not grant rights over excluded data.
Anyone reacquiring a dataset must check its current terms and use their own
authorized account where required.
