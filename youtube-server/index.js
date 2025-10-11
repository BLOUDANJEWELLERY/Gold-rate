import express from 'express';
import puppeteer from 'puppeteer';
import cors from 'cors';

const app = express();
const PORT = process.env.PORT || 4000;

// Allow Vercel frontend to call this server
app.use(cors({
  origin: ['https://bg-remover-silk.vercel.app/yt-download'], // Replace with your Vercel URL
}));

app.get('/download', async (req, res) => {
  const { url } = req.query;

  if (!url) return res.status(400).send('Missing url parameter');

  try {
    // Launch Puppeteer
    const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'networkidle2' });

    // Extract video URL from YouTube player
    const videoUrl = await page.evaluate(() => {
      const playerResponse = window.ytInitialPlayerResponse;
      if (!playerResponse) return null;

      const formats = playerResponse.streamingData?.formats || [];
      // Pick the first combined audio+video stream
      const stream = formats.find(f => f.mimeType.includes('video/mp4'));
      return stream?.url || null;
    });

    await browser.close();

    if (!videoUrl) return res.status(500).send('Unable to extract video URL');

    // Redirect browser to the direct video URL for download
    res.redirect(videoUrl);

  } catch (err) {
    console.error(err);
    res.status(500).send('Error fetching video: ' + err.message);
  }
});

app.listen(PORT, () => {
  console.log(`YouTube Puppeteer server running at http://localhost:${PORT}`);
});