# LifeLink – Blood Donation & Request Management (MongoDB + PyMongo)

CSE494 – Intelligent NoSQL Databases, Academic Task 2.

**Problem:** Hospitals often struggle to find eligible donors of the right blood group quickly.
LifeLink stores donors, hospitals, donations and urgent requests, enforces data quality with
validation rules, and answers questions such as *"which blood groups are scarce?"* and
*"who can donate today?"* using aggregation pipelines.

## Run it

```bash
pip install -r requirements.txt
# start MongoDB (local: `mongod`, or set MONGO_URI to an Atlas connection string)
python main.py                 # reset + seed + run everything
python main.py --only agg      # just aggregations (add --keep to reuse data)
mongosh lifelink_db mongo_queries.js   # same queries in mongosh
```

Take screenshots of the terminal output of `python main.py` (one per section: setup,
validation, CRUD, aggregations) for the report.

## Files

| File | Purpose |
|---|---|
| `schema.py` | Document design, `$jsonSchema` validators, indexes |
| `db.py` | PyMongo connection + output helper |
| `seed_data.py` | Synthetic dataset (6 hospitals, 40 donors, ~150 donations, 25 requests) |
| `crud_operations.py` | Validation tests + Create/Read/Update/Delete demos |
| `aggregations.py` | 10 aggregation pipelines |
| `main.py` | Runs the whole demo |
| `mongo_queries.js` | mongosh equivalents of all queries |

## Design decisions (for the viva)

- **Embedded:** `address` in donors, `blood_stock` in hospitals – read together, small, bounded.
- **Referenced:** `donations` link to `donor_id` and `hospital_id` – they grow without limit, so
  embedding would risk the 16 MB document cap. Joined with `$lookup`.
- **Denormalised:** `total_donations`, `last_donation_date`, `is_available` live on the donor so
  eligibility is one indexed query instead of a join.
- **Validation:** `$jsonSchema` with `validationLevel: strict`, `validationAction: error`
  (applies to inserts and updates), `additionalProperties: false`, enums, regex patterns, ranges.
  A unique index on `phone` / `license_no` adds a second integrity layer.
- **Indexes:** `(blood_group, city)` for donor search, `last_donation_date` for eligibility,
  `(donor_id, donation_date)` for history, `(status, urgency)` for the request queue.
  `explain()` is demonstrated in the Read section.
- **Not used:** multi-document transactions (need a replica set). Recording a donation updates
  three collections in sequence; with a replica set this would be wrapped in `session.with_transaction`.


## Interactive menu (user-friendly CRUD)

After `python main.py` has seeded the database, run `python menu.py`. A numbered menu lets the
user add / search / update / delete donors, record donations, raise and fulfil blood requests and
view the 10 reports, without typing any MongoDB query. Every action runs through PyMongo and
is checked by the same validation rules.