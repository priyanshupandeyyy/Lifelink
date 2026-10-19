// mongo_queries.js - the same operations as the PyMongo code, in mongosh syntax.
// Run after `python main.py` has created and seeded the data:
//     mongosh lifelink_db mongo_queries.js
// or paste sections into mongosh one at a time.

use("lifelink_db");
const cutoff = new Date(Date.now() - 90 * 24 * 3600 * 1000);

// ---------------------------------------------------------------- VALIDATION
// (main.py already creates these; shown here for the report/viva)
db.runCommand({
  collMod: "donors",
  validationLevel: "strict",
  validationAction: "error",
  validator: { $jsonSchema: {
    bsonType: "object",
    required: ["name","blood_group","age","gender","phone","city","is_available","total_donations","registered_on"],
    properties: {
      blood_group: { enum: ["A+","A-","B+","B-","AB+","AB-","O+","O-"] },
      age: { bsonType: "int", minimum: 18, maximum: 65 },
      phone: { bsonType: "string", pattern: "^[6-9][0-9]{9}$" }
    }
  }}
});
// To inspect the real validator:
db.getCollectionInfos({ name: "donors" })[0].options.validator;

// This must FAIL (code 121, Document failed validation):
// db.donors.insertOne({ name: "X", blood_group: "C+", age: 15, gender: "Male",
//   phone: "123", city: "Amritsar", is_available: true, total_donations: 0, registered_on: new Date() });

// -------------------------------------------------------------------- CREATE
db.donors.insertOne({
  name: "Demo Donor", blood_group: "O-", age: NumberInt(27), gender: "Female",
  phone: "9876500000", city: "Amritsar", is_available: true,
  total_donations: NumberInt(0), last_donation_date: null,
  registered_on: new Date()
});
// NOTE: in mongosh, numbers are doubles by default - use NumberInt() for "int" fields.

// ---------------------------------------------------------------------- READ
db.donors.find(
  { blood_group: { $in: ["O+","O-"] }, city: "Amritsar", is_available: true },
  { _id: 0, name: 1, blood_group: 1, phone: 1 });

db.donors.find(
  { age: { $gte: 18, $lte: 50 },
    $or: [{ last_donation_date: null }, { last_donation_date: { $lte: cutoff } }] },
  { _id: 0, name: 1, age: 1, total_donations: 1 }
).sort({ total_donations: -1 }).limit(5);

db.donors.find({ name: { $regex: "^Gur", $options: "i" } }, { _id: 0, name: 1, city: 1 });
db.donors.find({ "medical_conditions.0": { $exists: true } }, { _id: 0, name: 1, medical_conditions: 1 });
db.requests.countDocuments({ status: "open", urgency: "critical" });
db.donors.find({ blood_group: "O+", city: "Amritsar" }).explain("executionStats");

// -------------------------------------------------------------------- UPDATE
db.donors.updateOne({ phone: "9876500000" }, { $set: { phone: "9876599999" } });
db.donors.updateOne({ phone: "9876599999" }, { $push: { medical_conditions: "Mild anaemia" } });
db.donors.updateOne({ phone: "9876599999" }, { $addToSet: { medical_conditions: "Mild anaemia" } });
db.donors.updateMany({ last_donation_date: { $gt: cutoff } }, { $set: { is_available: false } });
db.donors.updateMany(
  { $or: [{ last_donation_date: null }, { last_donation_date: { $lte: cutoff } }] },
  { $set: { is_available: true } });
db.requests.findOneAndUpdate(
  { status: "open", urgency: "critical" },
  { $set: { status: "fulfilled", fulfilled_on: new Date() } },
  { sort: { requested_on: 1 }, returnDocument: "after" });

// -------------------------------------------------------------------- DELETE
db.donors.deleteOne({ phone: "9876599999" });
db.requests.deleteMany({ status: "cancelled", requested_on: { $lt: new Date(Date.now() - 30*24*3600*1000) } });

// ------------------------------------------------------------- AGGREGATIONS
// 1. Donors per blood group
db.donors.aggregate([
  { $group: { _id: "$blood_group", donors: { $sum: 1 }, avg_age: { $avg: "$age" },
              available: { $sum: { $cond: ["$is_available", 1, 0] } } } },
  { $project: { _id: 0, blood_group: "$_id", donors: 1, available: 1, avg_age: { $round: ["$avg_age", 1] } } },
  { $sort: { donors: -1 } }
]);

// 2. Blood collected per hospital ($lookup join)
db.donations.aggregate([
  { $match: { status: "completed" } },
  { $group: { _id: "$hospital_id", units: { $sum: "$units" }, donations: { $sum: 1 }, avg_hb: { $avg: "$hemoglobin" } } },
  { $lookup: { from: "hospitals", localField: "_id", foreignField: "_id", as: "h" } },
  { $unwind: "$h" },
  { $project: { _id: 0, hospital: "$h.name", city: "$h.city", units: 1, donations: 1, avg_hemoglobin: { $round: ["$avg_hb", 2] } } },
  { $sort: { units: -1 } }
]);

// 3. Monthly donation trend
db.donations.aggregate([
  { $match: { status: "completed" } },
  { $group: { _id: { $dateToString: { format: "%Y-%m", date: "$donation_date" } }, units: { $sum: "$units" } } },
  { $sort: { _id: 1 } },
  { $project: { _id: 0, month: "$_id", units: 1 } }
]);

// 4. Top 5 donors
db.donations.aggregate([
  { $match: { status: "completed" } },
  { $group: { _id: "$donor_id", times: { $sum: 1 }, last_donated: { $max: "$donation_date" } } },
  { $sort: { times: -1, last_donated: -1 } },
  { $limit: 5 },
  { $lookup: { from: "donors", localField: "_id", foreignField: "_id", as: "d" } },
  { $unwind: "$d" },
  { $project: { _id: 0, donor: "$d.name", blood_group: "$d.blood_group", city: "$d.city", times: 1, last_donated: 1 } }
]);

// 5. Open demand vs available donors (sub-pipeline $lookup)
db.requests.aggregate([
  { $match: { status: "open" } },
  { $group: { _id: "$blood_group", units_needed: { $sum: "$units_needed" }, open_requests: { $sum: 1 } } },
  { $lookup: { from: "donors", let: { bg: "$_id" },
      pipeline: [ { $match: { $expr: { $eq: ["$blood_group", "$$bg"] }, is_available: true } }, { $count: "n" } ],
      as: "avail" } },
  { $project: { _id: 0, blood_group: "$_id", units_needed: 1, open_requests: 1,
                available_donors: { $ifNull: [{ $arrayElemAt: ["$avail.n", 0] }, 0] } } },
  { $sort: { units_needed: -1 } }
]);

// 6. Age distribution
db.donors.aggregate([
  { $bucket: { groupBy: "$age", boundaries: [18, 26, 36, 46, 66], default: "other",
               output: { donors: { $sum: 1 }, avg_age: { $avg: "$age" } } } }
]);

// 7. Total stock per blood group (scarcest first)
db.hospitals.aggregate([
  { $project: { stock: { $objectToArray: "$blood_stock" } } },
  { $unwind: "$stock" },
  { $group: { _id: "$stock.k", units_in_stock: { $sum: "$stock.v" } } },
  { $sort: { units_in_stock: 1 } }
]);

// 8. Dashboard with $facet
db.donors.aggregate([
  { $facet: {
      by_city: [{ $group: { _id: "$city", donors: { $sum: 1 } } }, { $sort: { donors: -1 } }],
      by_gender: [{ $group: { _id: "$gender", donors: { $sum: 1 } } }],
      totals: [{ $group: { _id: null, donors: { $sum: 1 }, lifetime_donations: { $sum: "$total_donations" } } }]
  } }
]);

// 9. Average fulfilment time (hours) by urgency
db.requests.aggregate([
  { $match: { status: "fulfilled" } },
  { $group: { _id: "$urgency", requests: { $sum: 1 },
              avg_hours: { $avg: { $divide: [{ $subtract: ["$fulfilled_on", "$requested_on"] }, 3600000] } } } },
  { $project: { _id: 0, urgency: "$_id", requests: 1, avg_hours: { $round: ["$avg_hours", 1] } } },
  { $sort: { avg_hours: 1 } }
]);

// 10. Eligible donors by city
db.donors.aggregate([
  { $match: { $or: [{ last_donation_date: null }, { last_donation_date: { $lte: cutoff } }] } },
  { $group: { _id: "$city", eligible: { $sum: 1 }, groups: { $addToSet: "$blood_group" } } },
  { $sort: { eligible: -1 } }
]);
