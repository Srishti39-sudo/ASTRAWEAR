# ALTIER — running it

Everything runs on this Mac. The colour, palette, contrast, body, face, rules, taste, vibe and
convergence engines are all local: SigLIP on the M1's GPU, MediaPipe, the ONNX face-parsing net,
and the colour maths. **Gemini is optional** — with no key the card renders identically, because
the engines write every claim and the model only phrases the framing.

## Start it

```bash
cd ~/ASTRAWEAR/ALTIER
./start.sh                      # binds 0.0.0.0:8000 so your phone can reach it
```

Check it: <http://localhost:8000/health> — `vecdb` and `knowledge` report whether Ask ALTIER and the product pool are live.

```bash
cd ~/ASTRAWEAR/ALTIER/app
npx expo start                  # scan the QR with Expo Go on your phone
```

## Reaching it from your phone

**Same wifi (today):** `app/.env` holds `EXPO_PUBLIC_ALTIER_API=http://192.168.29.196:8000`.
That address is this Mac on your current network and **changes when you join a different one**.
Re-run the address line below and edit `app/.env` when it does.

```bash
ipconfig getifaddr en0
```

**Anywhere (next):** install Tailscale on the Mac and the phone, sign in to both with the same
account, then use the Mac's Tailscale name in `app/.env`. Free personal plan, six users and
unlimited devices. It builds a private encrypted mesh — nothing is exposed to the internet and
there is no port forwarding. This is the right answer and it takes about twenty minutes.

**The Mac must stay awake.** If it sleeps, your agent is down. Either run `caffeinate -i ./start.sh`
or set Energy Saver to prevent sleeping on power. This is the thing that will actually bite you.

## Keys

`page1/.env` (chmod 600, git-ignored). Only `GEMINI_API_KEY` is set, reused from `backend/.env`.

| key | state | what it costs you |
| --- | --- | --- |
| `GEMINI_API_KEY` | set | nothing. Free tier. Optional anyway |
| `SUPABASE_*` | empty | nothing. Profiles live in memory; the API says `persisted: false` |
| `SERPAPI_KEY` | empty | no live shopping results. Tiles show colour blocks; `POST /pool/ingest` says so |
| `VECDB_DIR` | empty (defaults to `~/vectorDB`) | without vecdb + faiss-cpu, `/ask` returns 503 and `/today` ranks the seed looks |

Nothing is hardcoded and no response ever returns a key. `/health` reports only whether one
is present.

## Calibrating the body estimate to you

The pipeline guesses depth = 0.72 × width, a population average, and that guess is most of the
error in the centimetre estimate. One tape session replaces it with your own ratio.

```bash
python -m page1.engines.__main_calibrate \
    --front front.jpg --side side.jpg --height 165 \
    --bust 88 --waist 70 --hip 96
```

**The first run cannot tell you your error.** It solves for the depth that reproduces your tape
figures, so comparing against those same figures returns zero by construction. The tool refuses
to report that as accuracy.

Take a second photo another day and run with `--test`, which uses the saved ratios instead of
solving new ones. That number is real, and it contains everything calibration does not remove:
clothing, posture, how you stood, the lens, and the height you typed.

| worst error | what to show on the card |
| --- | --- |
| under 2 cm | the number, with its band |
| 2–5 cm | "about 88 cm", with the band |
| over 5 cm | shape and ratios only. Leave the centimetres off |

The shape and the ratios are scale-free and do not depend on any of this, so they ship either way.

## Tests

```bash
python -m page1.tests.run_all
```

## Not built

Live shopping search wired into `/today`, the wardrobe catalogue, the post-to-feed step, and
pages 2–4. See the README's "Known limits" for what is weakest and why.
