"""
seed_data.py - Generates a reproducible synthetic dataset (random.seed(42)).

All names, phone numbers and hospitals are fictional sample data.
Result: 6 hospitals, 40 donors, ~150 donations, 25 blood requests.
"""
import random
from datetime import datetime, timedelta, timezone

from pymongo import UpdateOne

from schema import BLOOD_GROUPS

CITIES = {  # city -> (district, pincode)
    "Amritsar": ("Amritsar", "143001"),
    "Ludhiana": ("Ludhiana", "141001"),
    "Jalandhar": ("Jalandhar", "144001"),
    "Patiala": ("Patiala", "147001"),
    "Bathinda": ("Bathinda", "151001"),
    "Mohali": ("SAS Nagar", "160055"),
}
FIRST = ["Gurpreet", "Harjot", "Simran", "Manpreet", "Jaspreet", "Navdeep",
         "Amandeep", "Kiran", "Gurmeet", "Rupinder", "Pooja", "Ankit",
         "Arjun", "Neha", "Rohit", "Sukhdeep", "Tanvi", "Karan", "Mehak", "Vikram"]
LAST = ["Singh", "Kaur", "Sharma", "Gill", "Sandhu", "Verma", "Bajwa",
        "Dhillon", "Mehta", "Grewal", "Chopra", "Sidhu"]
BG_WEIGHTS = [22, 2, 30, 2, 7, 1, 34, 2]          # rough Indian distribution
CONDITIONS = [[], [], [], [], ["Hypertension"], ["Diabetes"], ["Asthma"]]


def _name():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def seed(db):
    random.seed(42)
    now = datetime.now(timezone.utc)

    # ---- hospitals -------------------------------------------------------
    hospital_names = ["Sanjeevani Multispeciality Hospital", "Jeevan Jyoti Blood Bank",
                      "Asha Kiran Medical Centre", "Raksha Care Hospital",
                      "Prem Nagar Civil Blood Centre", "Navjeevan Health Institute"]
    hospitals = []
    for i, (city, hname) in enumerate(zip(CITIES, hospital_names), start=1):
        hospitals.append({
            "name": hname,
            "license_no": f"PB-BB-{1000 + i}",
            "city": city,
            "phone": f"99999{i:05d}",
            "blood_stock": {bg: random.randint(0, 12) for bg in BLOOD_GROUPS},
        })
    db.hospitals.insert_many(hospitals)           # adds _id to each dict
    hospital_by_city = {h["city"]: h["_id"] for h in hospitals}

    # ---- donors ----------------------------------------------------------
    phones, donors = set(), []
    while len(donors) < 40:
        phone = random.choice("6789") + "".join(random.choices("0123456789", k=9))
        if phone in phones:
            continue
        phones.add(phone)
        city = random.choice(list(CITIES))
        name = _name()
        donor = {
            "name": name,
            "blood_group": random.choices(BLOOD_GROUPS, BG_WEIGHTS)[0],
            "age": random.randint(18, 60),
            "gender": random.choice(["Male", "Female"]),
            "phone": phone,
            "city": city,
            "address": {"district": CITIES[city][0], "pincode": CITIES[city][1]},
            "is_available": True,
            "total_donations": 0,
            "last_donation_date": None,
            "medical_conditions": random.choice(CONDITIONS),
            "registered_on": now - timedelta(days=random.randint(200, 700)),
        }
        if random.random() < 0.6:
            donor["email"] = name.lower().replace(" ", ".") + f"{len(donors)}@example.com"
        donors.append(donor)
    db.donors.insert_many(donors)

    # ---- donations -------------------------------------------------------
    donations, per_donor, per_hospital = [], {}, {}
    for _ in range(150):
        donor = random.choice(donors)
        hospital_id = (hospital_by_city[donor["city"]] if random.random() < 0.7
                       else random.choice(hospitals)["_id"])
        when = now - timedelta(days=random.randint(1, 365), hours=random.randint(0, 23))
        status = "deferred" if random.random() < 0.08 else "completed"
        donations.append({
            "donor_id": donor["_id"],
            "hospital_id": hospital_id,
            "blood_group": donor["blood_group"],
            "units": 1,
            "hemoglobin": round(random.uniform(12.5, 17.5), 1),
            "donation_date": when,
            "status": status,
        })
        if status == "completed":
            n, last = per_donor.get(donor["_id"], (0, None))
            per_donor[donor["_id"]] = (n + 1, max(when, last) if last else when)
            key = (hospital_id, donor["blood_group"])
            per_hospital[key] = per_hospital.get(key, 0) + 1
    db.donations.insert_many(donations)

    # Keep denormalised donor fields and hospital stock consistent with donations
    cutoff = now - timedelta(days=90)
    db.donors.bulk_write([
        UpdateOne({"_id": d["_id"]}, {"$set": {
            "total_donations": per_donor.get(d["_id"], (0, None))[0],
            "last_donation_date": per_donor.get(d["_id"], (0, None))[1],
            "is_available": (d["_id"] not in per_donor
                             or per_donor[d["_id"]][1] <= cutoff),
        }}) for d in donors])
    db.hospitals.bulk_write([
        UpdateOne({"_id": hid}, {"$inc": {f"blood_stock.{bg}": units}})
        for (hid, bg), units in per_hospital.items()])

    # ---- requests --------------------------------------------------------
    requests = []
    for _ in range(25):
        status = random.choices(["open", "fulfilled", "cancelled"], [12, 10, 3])[0]
        asked = now - timedelta(days=random.randint(4, 60), hours=random.randint(0, 23))
        req = {
            "hospital_id": random.choice(hospitals)["_id"],
            "patient_name": _name(),
            "blood_group": random.choices(BLOOD_GROUPS, BG_WEIGHTS)[0],
            "units_needed": random.randint(1, 4),
            "urgency": random.choices(["critical", "high", "normal"], [3, 4, 5])[0],
            "status": status,
            "requested_on": asked,
        }
        if status == "fulfilled":
            req["fulfilled_on"] = asked + timedelta(hours=random.randint(2, 72))
        requests.append(req)
    db.requests.insert_many(requests)

    counts = {c: db[c].count_documents({})
              for c in ("hospitals", "donors", "donations", "requests")}
    print("Seeded:", counts)
    return counts
