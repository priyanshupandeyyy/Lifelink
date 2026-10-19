"""
crud_operations.py - Create / Read / Update / Delete demos plus validation tests.
Each function prints its result so it can be shown directly in the demo.
"""
from datetime import datetime, timedelta, timezone

from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, WriteError

from db import show


# ======================================================================
# VALIDATION DEMO
# ======================================================================
def demo_validation(db):
    now = datetime.now(timezone.utc)
    valid = {"name": "Test Donor", "blood_group": "B+", "age": 30, "gender": "Male",
             "phone": "9111111111", "city": "Amritsar", "is_available": True,
             "total_donations": 0, "registered_on": now}

    bad_cases = {
        "Invalid blood group 'C+'": {**valid, "blood_group": "C+", "phone": "9111111112"},
        "Under-age donor (15)": {**valid, "age": 15, "phone": "9111111113"},
        "Bad phone number '12345'": {**valid, "phone": "12345"},
        "Missing required field 'city'": {k: v for k, v in valid.items()
                                          if k != "city"} | {"phone": "9111111114"},
        "Unknown extra field 'salary'": {**valid, "salary": 5000, "phone": "9111111115"},
        "Age stored as string": {**valid, "age": "30", "phone": "9111111116"},
    }
    print("\n=== VALIDATION: invalid inserts must be rejected ===")
    for label, doc in bad_cases.items():
        try:
            db.donors.insert_one(doc)
            print(f"[UNEXPECTED] '{label}' was accepted")
        except WriteError as e:
            print(f"[REJECTED] {label}  (error code {e.code}: document failed validation)")

    # Validation also applies to UPDATES (validationLevel = strict)
    donor = db.donors.find_one()
    try:
        db.donors.update_one({"_id": donor["_id"]}, {"$set": {"age": 150}})
        print("[UNEXPECTED] update to age=150 was accepted")
    except WriteError as e:
        print(f"[REJECTED] Update age -> 150  (error code {e.code})")

    # The unique index is a second layer of integrity
    try:
        db.donors.insert_one({**valid, "phone": donor["phone"]})
    except DuplicateKeyError:
        print("[REJECTED] Duplicate phone number (unique index uniq_phone)")


# ======================================================================
# CREATE
# ======================================================================
def demo_create(db):
    print("\n=== CREATE ===")
    now = datetime.now(timezone.utc)
    donor = {
        "name": "Demo Donor", "blood_group": "O-", "age": 27, "gender": "Female",
        "phone": "9876500000", "email": "demo.donor@example.com", "city": "Amritsar",
        "address": {"district": "Amritsar", "pincode": "143001"},
        "is_available": True, "total_donations": 0, "last_donation_date": None,
        "medical_conditions": [], "registered_on": now,
    }
    res = db.donors.insert_one(donor)
    print("insert_one  -> inserted_id:", res.inserted_id)

    more = [
        {"name": "Batch Donor One", "blood_group": "A+", "age": 35, "gender": "Male",
         "phone": "9876500001", "city": "Ludhiana", "is_available": True,
         "total_donations": 0, "registered_on": now},
        {"name": "Batch Donor Two", "blood_group": "AB-", "age": 41, "gender": "Female",
         "phone": "9876500002", "city": "Patiala", "is_available": True,
         "total_donations": 0, "registered_on": now},
    ]
    res = db.donors.insert_many(more)
    print("insert_many -> inserted", len(res.inserted_ids), "documents")

    # Record a real donation: insert donation + update donor + update hospital stock
    hospital = db.hospitals.find_one({"city": "Amritsar"})
    db.donations.insert_one({
        "donor_id": donor["_id"], "hospital_id": hospital["_id"], "blood_group": "O-",
        "units": 1, "hemoglobin": 14.2, "donation_date": now, "status": "completed"})
    db.donors.update_one({"_id": donor["_id"]}, {
        "$inc": {"total_donations": 1},
        "$set": {"last_donation_date": now, "is_available": False}})
    db.hospitals.update_one({"_id": hospital["_id"]}, {"$inc": {"blood_stock.O-": 1}})
    print("Recorded donation: donations + donors + hospitals.blood_stock updated")
    return donor["_id"]


# ======================================================================
# READ
# ======================================================================
def demo_read(db):
    print("\n=== READ ===")
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    show("1. Available O+/O- donors in Amritsar (filter + $in + projection)",
         list(db.donors.find(
             {"blood_group": {"$in": ["O+", "O-"]}, "city": "Amritsar",
              "is_available": True},
             {"_id": 0, "name": 1, "blood_group": 1, "phone": 1})))

    show("2. Top 5 eligible donors, age 18-50 (comparison + $or + sort + limit)",
         list(db.donors.find(
             {"age": {"$gte": 18, "$lte": 50},
              "$or": [{"last_donation_date": None},
                      {"last_donation_date": {"$lte": cutoff}}]},
             {"_id": 0, "name": 1, "age": 1, "total_donations": 1})
             .sort("total_donations", DESCENDING).limit(5)))

    show("3. Names starting with 'Gur' (regex, case-insensitive)",
         list(db.donors.find({"name": {"$regex": "^Gur", "$options": "i"}},
                             {"_id": 0, "name": 1, "city": 1})))

    show("4. Donors who declared a medical condition (array/exists query)",
         list(db.donors.find({"medical_conditions.0": {"$exists": True}},
                             {"_id": 0, "name": 1, "medical_conditions": 1}).limit(5)))

    show("5. Open critical requests (count_documents)",
         db.requests.count_documents({"status": "open", "urgency": "critical"}))

    show("6. find_one by unique phone number",
         db.donors.find_one({"phone": "9876500000"}, {"_id": 0, "name": 1, "city": 1}))

    plan = db.donors.find({"blood_group": "O+", "city": "Amritsar"}) \
        .explain()["queryPlanner"]["winningPlan"]
    stage = plan.get("inputStage", plan).get("stage", plan.get("stage"))
    show("7. explain(): index used for blood_group+city lookup", f"winning stage -> {stage}")


# ======================================================================
# UPDATE
# ======================================================================
def demo_update(db):
    print("\n=== UPDATE ===")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=90)

    r = db.donors.update_one({"phone": "9876500000"}, {"$set": {"phone": "9876599999"}})
    print("update_one ($set)          -> modified:", r.modified_count)

    r = db.donors.update_one({"phone": "9876599999"},
                             {"$push": {"medical_conditions": "Mild anaemia"}})
    print("update_one ($push)         -> modified:", r.modified_count)

    r = db.donors.update_one({"phone": "9876599999"},
                             {"$addToSet": {"medical_conditions": "Mild anaemia"}})
    print("update_one ($addToSet dup) -> modified:", r.modified_count, "(0 = no duplicate added)")

    r = db.donors.update_many(
        {"last_donation_date": {"$gt": cutoff}}, {"$set": {"is_available": False}})
    print("update_many (recent donors unavailable) -> modified:", r.modified_count)

    r = db.donors.update_many(
        {"$or": [{"last_donation_date": None}, {"last_donation_date": {"$lte": cutoff}}]},
        {"$set": {"is_available": True}})
    print("update_many (eligible donors available) -> modified:", r.modified_count)

    r = db.hospitals.update_one(
        {"license_no": "PB-BB-9999"},
        {"$set": {"name": "Upsert Demo Blood Bank", "city": "Amritsar", "phone": "9999999999",
                  "blood_stock": {bg: 0 for bg in
                                  ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]}}},
        upsert=True)
    print("update_one (upsert new hospital) -> upserted_id:", r.upserted_id)

    done = db.requests.find_one_and_update(
        {"status": "open", "urgency": "critical"},
        {"$set": {"status": "fulfilled", "fulfilled_on": now}},
        sort=[("requested_on", 1)], return_document=ReturnDocument.AFTER)
    show("find_one_and_update: oldest critical request marked fulfilled",
         {k: done[k] for k in ("patient_name", "blood_group", "status")} if done else None)


# ======================================================================
# DELETE
# ======================================================================
def demo_delete(db):
    print("\n=== DELETE ===")
    r = db.donors.delete_one({"phone": "9876599999"})
    print("delete_one (demo donor)           -> deleted:", r.deleted_count)

    r = db.donors.delete_many({"name": {"$regex": "^Batch Donor"}})
    print("delete_many (batch demo donors)   -> deleted:", r.deleted_count)

    r = db.hospitals.delete_one({"license_no": "PB-BB-9999"})
    print("delete_one (upserted hospital)    -> deleted:", r.deleted_count)

    old = datetime.now(timezone.utc) - timedelta(days=30)
    r = db.requests.delete_many({"status": "cancelled", "requested_on": {"$lt": old}})
    print("delete_many (old cancelled requests) -> deleted:", r.deleted_count)
