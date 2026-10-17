# dev-audio

Served by nginx at `/audio/` in docker-compose, so `AUDIO_BASE_URL=/audio` resolves the
bucket-relative `audio_path` values in the database (for example `seed/listening-cafe.mp3`).

The two seed files are placeholder tones of the right length (10 s and 8 s), not speech.
Replace them with real recordings when available. In production, audio lives in S3 behind
a CDN and `AUDIO_BASE_URL` points there.
