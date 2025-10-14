import fetch from "node-fetch";
import express from "express";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const app = express();
const PORT = process.env.PORT || 3000;

// --- Global USD→KWD rate ---
let USD_TO_KWD = 0.308;

// --- Interfaces ---
interface ExchangeData {
  rates: { KWD: number };
}

interface GoldData {
  price: number;
}

// --- Fetch USD→KWD ---
async function fetchUSDToKWD(): Promise<void> {
  try {
    const res = await fetch("https://open.er-api.com/v6/latest/USD");
    const data = (await res.json()) as ExchangeData;
    if (data?.rates?.KWD) {
      USD_TO_KWD = data.rates.KWD + 0.002;
      console.log("✅ Updated USD→KWD:", USD_TO_KWD.toFixed(3));
    }
  } catch (err) {
    console.error("❌ Error fetching USD/KWD:", err);
  }
}

// --- Fetch Gold Price ---
async function fetchGold(): Promise<void> {
  try {
    const res = await fetch("https://api.gold-api.com/price/XAU");
    const data = (await res.json()) as GoldData;

    const pricePerOunce = data.price;
    const pricePerGramUSD = pricePerOunce / 31.1035;
    const price24K_KWD = pricePerGramUSD * USD_TO_KWD;

    console.log(`🟡 24K Gold: ${price24K_KWD.toFixed(3)} KWD/g`);

    // --- Save to MongoDB ---
    await prisma.goldRate.create({
      data: {
        ouncePrice: pricePerOunce,
        gramPriceKWD: price24K_KWD,
      },
    });

    console.log("💾 Saved to DB at", new Date().toLocaleTimeString());
  } catch (err) {
    console.error("❌ Error fetching or saving gold price:", err);
  }
}

// --- Auto-clean old data and summarize daily averages ---
async function cleanupAndSummarize(): Promise<void> {
  const now = new Date();
  const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  // 1️⃣ Delete data older than 1 week
  await prisma.goldRate.deleteMany({
    where: { createdAt: { lt: oneWeekAgo } },
  });

  // 2️⃣ Summarize yesterday
  const yesterdayStart = new Date();
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  yesterdayStart.setHours(0, 0, 0, 0);

  const yesterdayEnd = new Date(yesterdayStart);
  yesterdayEnd.setHours(23, 59, 59, 999);

  const yesterdayRates = await prisma.goldRate.findMany({
    where: { createdAt: { gte: yesterdayStart, lte: yesterdayEnd } },
  });

  if (yesterdayRates.length > 0) {
    const avg =
      yesterdayRates.reduce((sum, r) => sum + r.gramPriceKWD, 0) /
      yesterdayRates.length;

    await prisma.dailyGoldRate.upsert({
      where: { date: yesterdayStart },
      update: { avgPriceKWD: avg },
      create: { date: yesterdayStart, avgPriceKWD: avg },
    });

    await prisma.goldRate.deleteMany({
      where: { createdAt: { gte: yesterdayStart, lte: yesterdayEnd } },
    });

    console.log("📊 Averaged and cleaned yesterday’s data.");
  }
}

// --- Schedule tasks ---
setInterval(async () => {
  await fetchUSDToKWD();
  await fetchGold();
  await cleanupAndSummarize();
}, 60_000); // every 1 minute

// --- Simple /ping endpoint for UptimeRobot ---
app.get("/ping", (req, res) => {
  res.status(200).send("🟢 Alive and tracking gold rates.");
});

// --- Start server ---
app.listen(PORT, () => {
  console.log(`🚀 Gold rate tracker running on port ${PORT}`);
});