import express from 'express';
import puppeteer from 'puppeteer-core';
import cors from 'cors';

const app = express();
const PORT = process.env.PORT || 4000;

// Allow requests from your Vercel frontend
app.use(cors({
  origin: ['https://bg-remover-silk.vercel.app/yt-download'], // replace with your Vercel URL
}));

app.get('/download', async (req, res) => {
  const { url } = req.query;
  if (!url) return res.status(400).send('Missing url parameter');

  try {
    const browser = await puppeteer.launch({
      headless: true,
      executablePath: '/usr/bin/chromium', // system Chromium in Render
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'networkidle2' });

    const videoUrl = await page.evaluate(() => {
      const playerResponse = window.ytInitialPlayerResponse;
      if (!playerResponse) return null;
      const formats = playerResponse.streamingData?.formats || [];
      // Pick first combined audio+video mp4
      const stream = formats.find(f => f.mimeType.includes('video/mp4'));
      return stream?.url || null;
    });

    await browser.close();

    if (!videoUrl) return res.status(500).send('Unable to extract video URL');

    // ✅ Return JSON instead of redirecting
    res.json({ downloadUrl: videoUrl });

  } catch (err) {
    console.error(err);
    res.status(500).send('Error fetching video: ' + err.message);
  }
});

app.listen(PORT, () => {
  console.log(`YouTube Puppeteer server running at http://localhost:${PORT}`);
});