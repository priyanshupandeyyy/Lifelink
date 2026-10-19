"""
schema.py - Document design, $jsonSchema validation rules and indexes for LifeLink.

Four collections:
  donors     - people registered to donate blood
  hospitals  - hospitals / blood banks, with embedded blood_stock sub-document
  donations  - one document per donation (references donors and hospitals)
  requests   - blood requests raised by hospitals

Design choices (useful for the viva):
  * blood_stock is EMBEDDED in hospitals  -> always read together, small and bounded.
  * address is EMBEDDED in donors         -> one-to-one, never queried alone.
  * donations are a SEPARATE collection   -> unbounded growth (a donor can donate
    for decades), so embedding them would risk the 16 MB document limit.
    They REFERENCE donor_id / hospital_id and are joined with $lookup.
  * total_donations and last_donation_date are stored on the donor (denormalised)
    so "who is eligible to donate today?" is a single fast query.
"""
from pymongo import ASCENDING, DESCENDING

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
PHONE_PATTERN = "^[6-9][0-9]{9}$"          # 10-digit Indian mobile number

DONOR_SCHEMA = {
    "bsonType": "object",
    "required": ["name", "blood_group", "age", "gender", "phone", "city",
                 "is_available", "total_donations", "registered_on"],
    "additionalProperties": False,
    "properties": {
        "_id": {"bsonType": "objectId"},
        "name": {"bsonType": "string", "minLength": 2, "maxLength": 60,
         "pattern": "^[A-Za-z][A-Za-z .'-]*$"},
        "blood_group": {"enum": BLOOD_GROUPS,
                        "description": "must be one of the 8 ABO/Rh groups"},
        "age": {"bsonType": "int", "minimum": 18, "maximum": 65,
                "description": "donors must be 18-65 years old"},
        "gender": {"enum": ["Male", "Female", "Other"]},
        "phone": {"bsonType": "string", "pattern": PHONE_PATTERN},
        "email": {"bsonType": "string",
                  "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"},
        "city": {"bsonType": "string"},
        "address": {
            "bsonType": "object",
            "required": ["district", "pincode"],
            "properties": {
                "district": {"bsonType": "string"},
                "pincode": {"bsonType": "string", "pattern": "^[0-9]{6}$"},
            },
        },
        "is_available": {"bsonType": "bool"},
        "total_donations": {"bsonType": "int", "minimum": 0},
        "last_donation_date": {"bsonType": ["date", "null"]},
        "medical_conditions": {"bsonType": "array",
                               "items": {"bsonType": "string"}},
        "registered_on": {"bsonType": "date"},
    },
}

HOSPITAL_SCHEMA = {
    "bsonType": "object",
    "required": ["name", "license_no", "city", "phone", "blood_stock"],
    "additionalProperties": False,
    "properties": {
        "_id": {"bsonType": "objectId"},
        "name": {"bsonType": "string", "minLength": 3},
        "license_no": {"bsonType": "string", "pattern": "^PB-BB-[0-9]{4}$"},
        "city": {"bsonType": "string"},
        "phone": {"bsonType": "string", "pattern": PHONE_PATTERN},
        "blood_stock": {
            "bsonType": "object",
            "required": BLOOD_GROUPS,
            "additionalProperties": False,
            "properties": {bg: {"bsonType": "int", "minimum": 0}
                           for bg in BLOOD_GROUPS},
        },
    },
}

DONATION_SCHEMA = {
    "bsonType": "object",
    "required": ["donor_id", "hospital_id", "blood_group", "units",
                 "hemoglobin", "donation_date", "status"],
    "additionalProperties": False,
    "properties": {
        "_id": {"bsonType": "objectId"},
        "donor_id": {"bsonType": "objectId"},
        "hospital_id": {"bsonType": "objectId"},
        "blood_group": {"enum": BLOOD_GROUPS},
        "units": {"bsonType": "int", "minimum": 1, "maximum": 2},
        "hemoglobin": {"bsonType": "double", "minimum": 12.5, "maximum": 20.0,
                       "description": "g/dL; below 12.5 is not acceptable"},
        "donation_date": {"bsonType": "date"},
        "status": {"enum": ["completed", "deferred"]},
    },
}

REQUEST_SCHEMA = {
    "bsonType": "object",
    "required": ["hospital_id", "patient_name", "blood_group", "units_needed",
                 "urgency", "status", "requested_on"],
    "additionalProperties": False,
    "properties": {
        "_id": {"bsonType": "objectId"},
        "hospital_id": {"bsonType": "objectId"},
        "patient_name": {"bsonType": "string", "minLength": 2},
        "blood_group": {"enum": BLOOD_GROUPS},
        "units_needed": {"bsonType": "int", "minimum": 1, "maximum": 10},
        "urgency": {"enum": ["critical", "high", "normal"]},
        "status": {"enum": ["open", "fulfilled", "cancelled"]},
        "requested_on": {"bsonType": "date"},
        "fulfilled_on": {"bsonType": "date"},
    },
}

SCHEMAS = {
    "donors": DONOR_SCHEMA,
    "hospitals": HOSPITAL_SCHEMA,
    "donations": DONATION_SCHEMA,
    "requests": REQUEST_SCHEMA,
}


def create_collections(db):
    """Drop and recreate every collection with its validator (strict, error)."""
    for name, schema in SCHEMAS.items():
        db.drop_collection(name)
        db.create_collection(
            name,
            validator={"$jsonSchema": schema},
            validationLevel="strict",     # validate all inserts AND updates
            validationAction="error",     # reject invalid writes
        )
    print(f"Created collections with validators: {', '.join(SCHEMAS)}")


def create_indexes(db):
    """Indexes chosen to match the queries used in crud_operations/aggregations."""
    db.donors.create_index([("phone", ASCENDING)], unique=True, name="uniq_phone")
    db.donors.create_index([("blood_group", ASCENDING), ("city", ASCENDING)],
                           name="bg_city")
    db.donors.create_index([("last_donation_date", ASCENDING)], name="last_don")
    db.hospitals.create_index([("license_no", ASCENDING)], unique=True,
                              name="uniq_license")
    db.donations.create_index([("donor_id", ASCENDING),
                               ("donation_date", DESCENDING)], name="donor_date")
    db.donations.create_index([("hospital_id", ASCENDING)], name="hospital")
    db.requests.create_index([("status", ASCENDING), ("urgency", ASCENDING)],
                             name="status_urgency")
    print("Created indexes on donors, hospitals, donations, requests")
