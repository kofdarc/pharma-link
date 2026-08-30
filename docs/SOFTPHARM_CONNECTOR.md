# SoftPharm connector setup

## Supported integration

This is a safe export-based integration for pharmacies that continue to use SoftPharm as
their local point of sale. It does not use an undocumented SoftPharm API or write to the
SoftPharm database.

- SoftPharm exports stock to CSV.
- The HealthConnect connector reads the completed export and sends changed stock levels
  through signed HTTPS requests.
- Duplicate rows for batches or expiry dates are combined by SoftPharm item code.
- HealthConnect writes open online orders to a local CSV worksheet for pharmacy staff to
  enter into SoftPharm.

SoftPharm remains authoritative for local sales, accounting, purchasing and official
pharmacy records. HealthConnect remains responsible for online search, ordering and delivery.

## 1. Prepare the SoftPharm export

Configure or manually save a stock report to a fixed location such as:

```text
C:\SoftPharmExports\stock.csv
```

The export needs one column for each of the following:

| Required | Preferred but optional |
|---|---|
| Product/item code | Selling price |
| Product description | Purchase cost |
| Available quantity | Expiry date |
| | Supplier |

The item code must be stable between exports. A barcode or MoPH code is preferable when it
is available. The connector only supports CSV directly; save Excel reports as CSV first.

The export should be written to a temporary filename and renamed to `stock.csv` only after
it completes. The connector also rejects files modified less than ten seconds ago.

## 2. Install the connector

Install Python 3.10 or newer on the pharmacy's Windows computer. Copy these files into
`C:\HealthConnect`:

```text
pharmalink_connector.py
connector.softpharm.example.json
```

Rename the configuration file to `connector.json`. Open the real SoftPharm CSV and replace
the example values under `source.columns` with its exact column headings. Matching is
case-insensitive and ignores spaces around headings.

The example headings are placeholders, not documented SoftPharm schema names.

## 3. Configure credentials safely

Create an integration key in the HealthConnect pharmacy workspace. Put its key ID in
`connector.json`. Store the one-time secret in the Windows user environment rather than the
JSON file:

```powershell
[Environment]::SetEnvironmentVariable("PHARMALINK_SECRET", "REPLACE_WITH_SECRET", "User")
```

Open a new PowerShell window after setting it. Never use SoftPharm staff or database
credentials for this connector.

## 4. Set the export safety thresholds

The template enables two protections:

```json
"safety": {
  "enabled": true,
  "minimum_rows": 10,
  "maximum_drop_fraction": 0.5
}
```

- `minimum_rows` rejects implausibly small exports.
- `maximum_drop_fraction` rejects a sudden drop of more than 50 percent compared with the
  last accepted export.

For a pharmacy with about 4,000 unique products, a practical `minimum_rows` is 500 to 1,000.
Tune it below normal inventory size but above any plausible partial report. If a pharmacy
really removes more than half of its catalog, confirm the export is complete, temporarily
adjust the threshold to the expected reduction, and run a reviewed full synchronization.

## 5. Test and perform the initial sync

From PowerShell:

```powershell
cd C:\HealthConnect
python pharmalink_connector.py --config connector.json --check
python pharmalink_connector.py --config connector.json --full
```

`--check` reads the export but does not synchronize stock. After the first full sync, staff
must resolve any unmatched SoftPharm item codes in the HealthConnect SKU mapping screen.

## 6. Schedule synchronization

Create a Windows Task Scheduler task that runs every five minutes:

```text
Program: python
Arguments: C:\HealthConnect\pharmalink_connector.py --config C:\HealthConnect\connector.json --once
Start in: C:\HealthConnect
```

Run the task as the same Windows user that owns `PHARMALINK_SECRET`. Enable automatic retry
when the task fails.

The connector stores `connector.state.json` in its working directory. Keep this file: it is
the local change snapshot that makes synchronization efficient.

## 7. Process incoming orders

Open orders are written atomically to:

```text
C:\HealthConnect\incoming-orders.csv
```

The worksheet contains order reference, status, customer contact, delivery information,
handover code, item name and quantity. Staff should:

1. Enter the order into SoftPharm as a held invoice or sale.
2. Accept the order in HealthConnect.
3. Prepare the items and mark the order ready.
4. Complete the SoftPharm transaction at handover.

The worksheet is cleared to its header when there are no open HealthConnect orders, so a
completed order is not mistaken for a new one.

## Current limitation

HealthConnect v1 stores aggregate SoftPharm availability in one synthetic inventory batch
per mapped medicine. When several SoftPharm batch rows share an item code, their quantities
are summed and the earliest valid ISO expiry (`YYYY-MM-DD`) is retained. This is a
conservative proof-of-concept approximation, not full batch reconciliation.

Do not advertise automatic SoftPharm order creation, direct database integration or an
official SoftPharm API. None of those interfaces is documented by the information currently
available to the project.
