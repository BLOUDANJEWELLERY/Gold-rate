"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_fetch_1 = __importDefault(require("node-fetch"));
const client_1 = require("@prisma/client");
const prisma = new client_1.PrismaClient();
// --- Global USD→KWD rate ---
let USD_TO_KWD = 0.308;
// --- Fetch USD→KWD ---
async function fetchUSDToKWD() {
    try {
        const res = await (0, node_fetch_1.default)("https://open.er-api.com/v6/latest/USD");
        const data = (await res.json());
        if (data?.rates?.KWD) {
            USD_TO_KWD = data.rates.KWD + 0.002;
            console.log("✅ Updated USD→KWD:", USD_TO_KWD.toFixed(3));
        }
    }
    catch (err) {
        console.error("❌ Error fetching USD/KWD:", err);
    }
}
// --- Fetch and Save Gold Price ---
async function fetchGold() {
    try {
        const res = await (0, node_fetch_1.default)("https://api.gold-api.com/price/XAU");
        const data = (await res.json());
        const pricePerOunce = data.price;
        const pricePerGramUSD = pricePerOunce / 31.1035;
        const price24K_KWD = pricePerGramUSD * USD_TO_KWD;
        console.log(`🟡 24K Gold: ${price24K_KWD.toFixed(3)} KWD/g`);
        // --- Save new rate ---
        await prisma.goldRate.create({
            data: {
                ouncePrice: pricePerOunce,
                gramPriceKWD: price24K_KWD,
            },
        });
        console.log("💾 Saved to DB at", new Date().toLocaleTimeString());
        // --- Run cleanup and aggregation ---
        await cleanupAndAggregate();
    }
    catch (err) {
        console.error("❌ Error fetching or saving gold price:", err);
    }
}
// --- Cleanup and Aggregate Historical Data ---
async function cleanupAndAggregate() {
    try {
        const now = new Date();
        // 1️⃣ DELETE RECORDS OLDER THAN 7 DAYS
        const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        const deleted = await prisma.goldRate.deleteMany({
            where: { timestamp: { lt: oneWeekAgo } },
        });
        if (deleted.count > 0) {
            console.log(`🧹 Deleted ${deleted.count} old records (older than 1 week).`);
        }
        // 2️⃣ COMPRESS YESTERDAY'S RECORDS
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        yesterday.setHours(0, 0, 0, 0);
        const todayStart = new Date(now);
        todayStart.setHours(0, 0, 0, 0);
        // Get yesterday’s records
        const yRecords = await prisma.goldRate.findMany({
            where: {
                timestamp: {
                    gte: yesterday,
                    lt: todayStart,
                },
            },
        });
        if (yRecords.length > 10) { // only compress if there’s enough data
            const avgOunce = yRecords.reduce((sum, r) => sum + r.ouncePrice, 0) / yRecords.length;
            const avgGram = yRecords.reduce((sum, r) => sum + r.gramPriceKWD, 0) / yRecords.length;
            // Delete yesterday’s detailed records
            await prisma.goldRate.deleteMany({
                where: {
                    timestamp: {
                        gte: yesterday,
                        lt: todayStart,
                    },
                },
            });
            // Save a single averaged entry for that day
            await prisma.goldRate.create({
                data: {
                    ouncePrice: avgOunce,
                    gramPriceKWD: avgGram,
                    timestamp: yesterday, // marks it for that day
                },
            });
            console.log(`📊 Compressed ${yRecords.length} records into daily average for ${yesterday.toDateString()}`);
        }
    }
    catch (err) {
        console.error("❌ Error during cleanup/aggregation:", err);
    }
}
// --- Run every 1 minute ---
setInterval(async () => {
    await fetchUSDToKWD();
    await fetchGold();
}, 60 * 1000); // 1 minute
console.log("🚀 Gold rate tracker started...");
