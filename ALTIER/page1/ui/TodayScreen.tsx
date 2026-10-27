/**
 * ALTIER · page1/ui/TodayScreen.tsx
 * ---------------------------------
 * Page 1, "Today's Fit". Expo / React Native.
 *
 * LAYOUT follows page1/ui/reference/alta_home_reference.png and alta_flows_reference.png:
 *   status bar · calendar + streak / centred wordmark / help + bell
 *   week strip — seven days, each showing what was logged, today underlined, future days ghosted
 *   a full-width pill ("Ask ALTIER" in the reference; here it carries the "something special" wish)
 *   "Good afternoon, <name>" with a right-hand read (weather in ALTA; her vibe here)
 *   THE FLAT-LAY GRID — each garment as its own cut-out tile, loose two-column collage,
 *     which is the reference's own idiom and what the outfit is meant to look like
 *   "Today's suggestions" hairline divider
 *   the cards: why · palette · her read · the rules · how clear her taste is getting
 *   five-item bottom nav with the black circle in the middle
 *
 * PALETTE is ALTIER's, not ALTA's: baby pink ground, black type. The reference is white; every
 * other token — radii, tracking, the pill shapes, the nav, the collage — is taken from it.
 *
 * WHAT THIS SCREEN IS RESPONSIBLE FOR BEYOND LOOKING RIGHT
 *   ALTIER is not a stylist grading her. It helps her find her own aesthetic. That shows up in
 *   the UI, not only in the engines:
 *     · MEASURED reads are shown as self-knowledge, never as a verdict, and a borderline label
 *       renders as borderline rather than as a clean word.
 *     · RULES are labelled convention and carry their source and a confidence she moved. Where
 *       one disagrees with a look she likes it renders as a dissenting opinion, not a warning.
 *     · The VIBE is labelled interpretation and is editable. It overrides nothing.
 *     · Every garment attribute from a live search is tagged "as searched, not verified".
 *     · The written reason says whether a model phrased it, and exactly what the model added.
 *   Dropping any of that turns a careful system into a confident one.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

/* ---------------- tokens ---------------- */
const C = {
  pink: "#FBECF1",      // the ground
  pink2: "#F6DBE3",
  rose: "#D97A94",
  roseDark: "#C25E7B",
  ink: "#141110",       // type
  muted: "#B29AA1",
  card: "#FFFFFF",
  line: "#F1DDE4",
  ghost: "#F2E4EA",     // future days in the week strip
  warn: "#8A6A2F",
  warnBg: "#FBF3E2",
};

const R = { card: 20, tile: 14, pill: 999 };

const API_BASE =
  process.env.EXPO_PUBLIC_ALTIER_API ??
  (globalThis as any).ALTIER_API_BASE ??
  "http://localhost:8000";

const OCCASIONS = ["casual", "gym", "work", "party", "date"] as const;
const MOODS = ["easy", "sharp", "soft", "bold", "cosy"] as const;
type Occasion = (typeof OCCASIONS)[number];
type Mood = (typeof MOODS)[number];

/* ---------------- server shapes ---------------- */
type Swatch = { hex: string; name: string; kind: string };

/** One garment. Shown as its own cut-out tile, flat, never styled on a body.
 *  A live search result also carries a price, a retailer and a buy link — all real or absent,
 *  never defaulted — plus `as_searched`, which is the honest status of its attributes. */
type Piece = {
  slot: "layer" | "top" | "dress" | "bottom" | "shoes" | "accessory" | "look";
  name: string;
  colors: string[];
  image_url?: string;
  /* What this garment IS, in words — the colour name plus whichever of neckline, waist and
     silhouette apply to this slot. Shown on the tile, and the same words the ChatGPT prompt is
     built from, so the picture and the card cannot describe different clothes. */
  attributes?: {
    colour?: string; colour_hex?: string;
    neckline?: string; waist?: string; silhouette?: string;
  };
  price_text?: string | null;
  retailer?: string | null;
  product_link?: string | null;
  verified?: boolean;
  as_searched?: { terms: string[] } | null;
};

type AppliedRule = {
  id: string; attribute: string; recommends: string;
  confidence: number; source: string; goal: string;
};

/** A rule from one of the three advice engines. `keyed_on` appears only on accessory rules and
 *  says whether the rule hangs off a MEASURED read or off the interpreted vibe — a difference
 *  of two whole steps in how much it should be believed, so the card shows it. */
type AdviceRule = {
  id: string; attribute: string; recommends: string; avoid?: string;
  reason: string; goal: string; confidence: number;
  source_detail: { name: string; kind?: string };
  keyed_on?: "measured undertone" | "interpreted vibe";
  axis?: string;
};
type Advice = {
  rules: AdviceRule[];
  note: string | null;
  conflicts?: {
    axis: string;
    chosen: { recommends: string; confidence: number; because: string[] };
    also_matched: { recommends: string; confidence: number; because: string[] };
  }[];
};

/** Seventeen measured facial features. Material, shown as self-knowledge. `saturated` names the
 *  ones pinned to a clamp bound, which describe the constant rather than her face. */
type FaceFeatures = {
  eyes: Record<string, number>;
  brows: Record<string, number>;
  cheeks: Record<string, number>;
  lips: Record<string, number>;
  saturated: string[];
};
type Dissent = {
  rule_id: string; attribute: string; value: string; reason: string;
  source: string; confidence: number; overruled_by_taste: boolean;
};
type SizeEstimate = {
  cm: Record<string, number>;
  cm_range: Record<string, [number, number]>;
  confidence: number; notes: string[];
};
type TodayResponse = {
  look: { id: string; title: string };
  pieces: Piece[];
  score: number;
  reason: string;
  reason_source: "gemini" | "deterministic";
  reason_fallback: string | null;
  reason_model_added: string;
  reason_verbatim: { copied: number; required: number };
  /* Built server-side from the tiles' own attributes. With no product photos yet, this text is
     what actually produces the picture. */
  avatar_prompt: { prompt: string; unverified: string[]; note: string | null };
  dissent?: Dissent[];
  palette_swatches: Swatch[];
  palette_guidance: string | null;
  coloring: {
    line: string; undertone: string; depth: string; contrast: string;
    note: string | null; borderline: string[];
  };
  body: { line: string; shape: string | null; confidence: number | null; size_estimate: SizeEstimate | null };
  rules_applied: AppliedRule[];
  hairstyle: Advice;
  pose: Advice;
  accessory: Advice;
  face_shape: {
    shape: string | null;
    ratios: Record<string, number> | null;
    features: FaceFeatures | null;
    confidence: number | null;
  };
  pool: { source: string; considered: number; note: string; occasion_filter: { note: string | null } };
  taste: { available: boolean; pins: number; coherence: number | null };
};
type VibeRead = {
  proposal: { phrase: string; confidence: number; warnings: string[] };
  confirmed: { phrase: string; edited: boolean } | null;
};
type ConvergenceRead = { score: number | null; ready: boolean; headline: string };
type AskResponse = {
  answer: string; abstained: boolean; reason: string | null; grounded: boolean;
  source: "gemini" | "retrieval-only" | "gate"; profile_used: string | null;
  citations: { n: number; title: string; section: string; snippet: string }[];
};

/* ---------------- week strip ---------------- */
const DAY_LABELS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function weekDays(today: Date) {
  const start = new Date(today);
  start.setDate(today.getDate() - today.getDay());
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return {
      key: d.toISOString().slice(0, 10),
      label: DAY_LABELS[i],
      n: d.getDate(),
      isToday: d.toDateString() === today.toDateString(),
      /* Future days are ghosted, exactly as in the reference. Nothing is drawn there: an
         outfit shown for a day that has not happened is a suggestion never made. */
      isFuture: d > today,
    };
  });
}

/* Garment tiles are not all one size in the reference — a top or a pair of trousers reads
   larger than a pair of sunglasses. Height by slot keeps the collage feeling hand-laid. */
const TILE_HEIGHT: Record<Piece["slot"], number> = {
  dress: 190, top: 165, bottom: 165, layer: 165, shoes: 120, accessory: 120, look: 190,
};
const SLOT_LABEL: Record<Piece["slot"], string> = {
  layer: "Layer", top: "Top", dress: "Dress", bottom: "Bottom",
  shoes: "Shoes", accessory: "Accessory", look: "The look",
};

/* ---------------- screen ---------------- */
export default function TodayScreen({
  accessToken,
  apiBase = API_BASE,
  userName = "you",
  avatarUri = null,
}: {
  accessToken?: string | null;
  apiBase?: string;
  userName?: string;
  /** You, or the avatar you generated by hand. ALTIER has no image API. */
  avatarUri?: string | null;
}) {
  const [occasion, setOccasion] = useState<Occasion>("casual");
  const [mood, setMood] = useState<Mood | null>(null);
  const [special, setSpecial] = useState("");
  const [data, setData] = useState<TodayResponse | null>(null);
  const [vibe, setVibe] = useState<VibeRead | null>(null);
  const [convergence, setConvergence] = useState<ConvergenceRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voted, setVoted] = useState<"up" | "down" | null>(null);
  const [showRules, setShowRules] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);

  const week = useMemo(() => weekDays(new Date()), []);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  const headers = useMemo(() => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (accessToken) h.Authorization = `Bearer ${accessToken}`;
    return h;
  }, [accessToken]);

  const fetchToday = useCallback(async () => {
    setLoading(true);
    setError(null);
    setVoted(null);
    try {
      const res = await fetch(`${apiBase}/today`, {
        method: "POST",
        headers,
        body: JSON.stringify({ occasion, mood, special: special.trim() || null, k: 3 }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.detail ?? `request failed (${res.status})`);
        setData(null);
      } else {
        setData(body as TodayResponse);
      }
    } catch {
      setError(`could not reach ALTIER at ${apiBase}`);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [apiBase, headers, occasion, mood, special]);

  const fetchSideReads = useCallback(async () => {
    /* The vibe and the convergence read are secondary: if either fails the outfit still
       renders. Neither is allowed to take the page down with it. */
    try {
      const v = await fetch(`${apiBase}/vibe`, { method: "POST", headers, body: "{}" });
      if (v.ok) setVibe(await v.json());
    } catch { /* leave it absent */ }
    try {
      const c = await fetch(`${apiBase}/convergence`, { headers });
      if (c.ok) setConvergence(await c.json());
    } catch { /* leave it absent */ }
  }, [apiBase, headers]);

  useEffect(() => { fetchToday(); }, [occasion, mood]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fetchSideReads(); }, [fetchSideReads]);

  /* Ask ALTIER — a question in words, answered ONLY from the sourced rule bases (vecdb RAG on the
     server). The server checks every citation; an answer it could not ground never reaches here. */
  const [askQ, setAskQ] = useState("");
  const [askRes, setAskRes] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const askAltier = useCallback(async () => {
    const q = askQ.trim();
    if (q.length < 2 || asking) return;
    setAsking(true);
    try {
      const res = await fetch(`${apiBase}/ask`, { method: "POST", headers, body: JSON.stringify({ question: q }) });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setAskRes({ answer: d.detail ?? `Ask is unavailable (HTTP ${res.status}).`, abstained: true, reason: "unavailable",
          grounded: true, source: "gate", profile_used: null, citations: [] });
      } else {
        setAskRes(await res.json());
      }
    } catch {
      setAskRes({ answer: `could not reach ALTIER at ${apiBase}`, abstained: true, reason: "offline",
        grounded: true, source: "gate", profile_used: null, citations: [] });
    } finally {
      setAsking(false);
    }
  }, [apiBase, headers, askQ, asking]);

  const sendFeedback = useCallback(async (liked: boolean) => {
    if (!data) return;
    setVoted(liked ? "up" : "down");
    try {
      await fetch(`${apiBase}/feedback`, {
        method: "POST", headers,
        body: JSON.stringify({ look_id: data.look.id, liked, occasion, mood }),
      });
    } catch { /* a lost vote is not worth an error banner over today's outfit */ }
  }, [apiBase, headers, data, occasion, mood]);

  /* The see-it-on-me prompt is built by the server, not here. It has to describe the same
     garments the tiles claim — same colour words, same neckline, same silhouette — and a second
     copy of that assembly in the UI would be a second thing to drift. */
  const avatarPrompt = data?.avatar_prompt;

  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* top bar */}
        <View style={s.topbar}>
          <View style={s.topSide}>
            <Ionicons name="calendar-outline" size={21} color={C.ink} />
            <View style={s.streak}>
              <Ionicons name="flame" size={15} color={C.rose} />
              <Text style={s.streakN}>{data ? 1 : 0}</Text>
            </View>
          </View>
          <Text style={s.wordmark}>ALTIER</Text>
          <View style={s.topSide}>
            <Ionicons name="help-circle-outline" size={21} color={C.ink} />
            <View>
              <Ionicons name="notifications-outline" size={21} color={C.ink} />
              <View style={s.bellDot} />
            </View>
          </View>
        </View>

        {/* week strip */}
        <View style={s.week}>
          {week.map((day) => (
            <View key={day.key} style={s.day}>
              <Text style={[s.dayLabel, day.isToday && s.dayLabelOn]}>{day.label}</Text>
              <Text style={[s.dayNum, day.isToday && s.dayNumOn]}>{day.n}</Text>
              <View style={[s.dayTile, day.isFuture && s.dayTileGhost]}>
                {day.isToday && data
                  ? data.pieces.slice(0, 4).map((p, i) => (
                      <View key={i} style={[s.dayChip, { backgroundColor: p.colors[0] ?? C.pink2 }]} />
                    ))
                  : null}
              </View>
              {day.isToday && <View style={s.dayUnderline} />}
            </View>
          ))}
        </View>

        {/* the wish pill — "Ask Alta" in the reference */}
        <View style={s.askPill}>
          <Ionicons name="sparkles-outline" size={17} color={C.roseDark} />
          <TextInput
            style={s.askInput}
            value={special}
            onChangeText={setSpecial}
            onSubmitEditing={fetchToday}
            returnKeyType="search"
            placeholder="Ask ALTIER — something special?"
            placeholderTextColor={C.muted}
          />
          {special.length > 0 && (
            <Pressable onPress={fetchToday} hitSlop={8}>
              <Ionicons name="arrow-forward-circle" size={24} color={C.ink} />
            </Pressable>
          )}
        </View>

        {/* greeting + her vibe, where ALTA puts the weather */}
        <View style={s.greetRow}>
          <Text style={s.greet}>{greeting},{"\n"}{userName}</Text>
          <View style={s.vibeBox}>
            <Text style={s.vibeLabel}>YOUR VIBE</Text>
            <Text style={s.vibePhrase} numberOfLines={2}>
              {vibe?.confirmed?.phrase || vibe?.proposal?.phrase || "not yet"}
            </Text>
            {/* Interpretation, and it is editable. It never overrides a measured read. */}
            <Text style={s.vibeTag}>your read · tap to edit</Text>
          </View>
        </View>

        {/* occasion */}
        <Text style={s.sectionLabel}>WHAT'S THE OCCASION?</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.pillRow}>
          {OCCASIONS.map((o) => (
            <Pressable key={o} onPress={() => setOccasion(o)} style={[s.pill, occasion === o && s.pillOn]}>
              <Text style={[s.pillTxt, occasion === o && s.pillTxtOn]}>{o}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* mood */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow}>
          {MOODS.map((m) => (
            <Pressable key={m} onPress={() => setMood(mood === m ? null : m)} style={[s.chip, mood === m && s.chipOn]}>
              <Text style={[s.chipTxt, mood === m && s.chipTxtOn]}>{m}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {loading && (
          <View style={s.skeletonWrap}>
            <View style={s.skeletonRow}>
              <View style={[s.skeleton, { height: 165 }]} />
              <View style={[s.skeleton, { height: 165 }]} />
            </View>
            <ActivityIndicator color={C.roseDark} />
          </View>
        )}

        {error && !loading && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Nothing to show</Text>
            <Text style={s.footnote}>{error}</Text>
            <Pressable onPress={fetchToday} style={s.blackBtn}>
              <Text style={s.blackBtnTxt}>Try again</Text>
            </Pressable>
          </View>
        )}

        {data && !loading && data.pieces.length === 0 && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Nothing matched</Text>
            <Text style={s.footnote}>Loosen the occasion, or clear what you asked for.</Text>
          </View>
        )}

        {data && !loading && data.pieces.length > 0 && (
          <>
            <Text style={s.lookTitle}>{data.look.title}</Text>

            {/* THE FLAT-LAY — each garment its own cut-out tile, never worn on a body */}
            <View style={s.flatlay}>
              {data.pieces.map((piece, i) => (
                <View key={`${piece.slot}-${i}`} style={s.tile}>
                  <View style={[s.tileImage, { height: TILE_HEIGHT[piece.slot] ?? 165 }]}>
                    {piece.image_url ? (
                      <Image source={{ uri: piece.image_url }} style={s.tileImg} resizeMode="contain" />
                    ) : (
                      /* No image API and no live search result yet. The garment's colour
                         stands in — never a broken frame, never an invented photograph. */
                      piece.colors.map((hex, j) => (
                        <View key={j} style={[s.tileBand, { backgroundColor: hex }]} />
                      ))
                    )}
                  </View>
                  <Text style={s.tileSlot}>{SLOT_LABEL[piece.slot] ?? piece.slot}</Text>
                  <Text style={s.tileName} numberOfLines={2}>{piece.name}</Text>

                  {/* Exactly what ALTIER looked for. Without these the tile says "a top" and
                      the reader has no way to tell what was actually asked for. */}
                  {piece.attributes && (
                    <View style={s.attrRow}>
                      {(["colour", "neckline", "waist", "silhouette"] as const)
                        .map((k) => piece.attributes?.[k])
                        .filter((v): v is string => Boolean(v))
                        .map((v) => (
                          <View key={v} style={s.attrChip}>
                            <Text style={s.attrTxt}>{v.replace(/-/g, " ")}</Text>
                          </View>
                        ))}
                    </View>
                  )}

                  {piece.price_text && (
                    <Text style={s.tilePrice}>
                      {piece.price_text}{piece.retailer ? ` · ${piece.retailer}` : ""}
                    </Text>
                  )}
                  {piece.product_link && (
                    <Pressable onPress={() => Linking.openURL(piece.product_link!)} style={s.buyBtn}>
                      <Text style={s.buyTxt}>Buy</Text>
                    </Pressable>
                  )}
                  {/* The query asked for these; the retailer's text matched. Nobody checked
                      the garment. Saying so is not optional. */}
                  {piece.verified === false && piece.as_searched && (
                    <Text style={s.asSearched}>as searched, not verified</Text>
                  )}
                </View>
              ))}
            </View>

            {/* see it on me — manual handoff, by design */}
            <Pressable onPress={() => setShowPrompt(!showPrompt)} style={s.blackBtnWide}>
              <Ionicons name="sparkles" size={16} color="#fff" />
              <Text style={s.blackBtnTxt}>See it on me</Text>
            </Pressable>
            {showPrompt && avatarPrompt && (
              <View style={s.card}>
                <Text style={s.kicker}>PASTE THIS INTO CHATGPT</Text>
                <Text selectable style={s.promptTxt}>{avatarPrompt.prompt}</Text>
                <Text style={s.footnote}>
                  ALTIER has no image generator. Make the picture in the ChatGPT app and bring it
                  back — then you can post it.
                </Text>
                {avatarPrompt.note && (
                  <Text style={s.footnote}>{avatarPrompt.note}</Text>
                )}
              </View>
            )}

            <View style={s.divider}>
              <View style={s.dividerLine} />
              <Text style={s.dividerTxt}>Today's suggestions</Text>
              <View style={s.dividerLine} />
            </View>

            {/* why */}
            <View style={s.card}>
              <View style={s.rowBetween}>
                <Text style={s.kicker}>WHY THIS</Text>
                <Text style={s.badge}>
                  {data.reason_source === "gemini" ? "phrased by ALTIER" : "from the numbers"}
                </Text>
              </View>
              <Text style={s.reason}>{data.reason}</Text>
              {data.reason_source === "gemini" && (
                <Text style={s.footnote}>
                  {data.reason_verbatim.copied} of {data.reason_verbatim.required} sentences were
                  written by the engines and copied word for word. The writing model added only:
                  "{data.reason_model_added}"
                </Text>
              )}
              {data.reason_fallback && (
                <Text style={s.footnote}>Written version not used: {data.reason_fallback}</Text>
              )}

              <View style={s.voteRow}>
                <Pressable onPress={() => sendFeedback(true)} style={[s.vote, voted === "up" && s.voteOn]}>
                  <Text style={s.voteEmoji}>👍</Text><Text style={s.voteTxt}>This is me</Text>
                </Pressable>
                <Pressable onPress={() => sendFeedback(false)} style={[s.vote, voted === "down" && s.voteOn]}>
                  <Text style={s.voteEmoji}>👎</Text><Text style={s.voteTxt}>Not me</Text>
                </Pressable>
              </View>
              {voted && <Text style={s.footnote}>Noted. That is you naming your taste, not tuning a model.</Text>}
            </View>

            {/* dissent — a rule that disagrees speaks, it does not veto */}
            {data.dissent?.filter((d) => d.overruled_by_taste).map((d) => (
              <View key={d.rule_id} style={[s.card, s.dissentCard]}>
                <Text style={s.kicker}>A CONVENTION DISAGREES</Text>
                <Text style={s.reason}>{d.reason}</Text>
                <Text style={s.footnote}>
                  {d.source} · confidence {Math.round(d.confidence * 100)}%. You keep choosing
                  looks like this, so it stays. This is an opinion, not a rule.
                </Text>
              </View>
            ))}

            {/* palette */}
            <View style={s.card}>
              <Text style={s.kicker}>YOUR COLOURS · MEASURED</Text>
              <View style={s.swatchWrap}>
                {data.palette_swatches.map((sw) => (
                  <View key={sw.hex} style={s.swatchCol}>
                    <View style={[s.swatch, { backgroundColor: sw.hex }]} />
                    <Text style={s.swatchName} numberOfLines={1}>{sw.name}</Text>
                  </View>
                ))}
              </View>
              {data.palette_guidance && <Text style={s.guidance}>{data.palette_guidance}</Text>}
            </View>

            {/* her read — self-knowledge, not a verdict */}
            <View style={s.card}>
              <Text style={s.kicker}>WHAT YOU'RE MADE OF · MEASURED</Text>
              <Text style={s.readLine}>{data.coloring.line}</Text>
              {data.coloring.note && (
                <View style={s.borderline}>
                  <Text style={s.borderlineTitle}>This one was close</Text>
                  <Text style={s.borderlineTxt}>{data.coloring.note}</Text>
                </View>
              )}
              <Text style={s.footnote}>
                Measured from your photo — CIELAB hue angle and ITA. Facts about you to build on,
                not a verdict on what suits you.
              </Text>

              {data.face_shape?.shape ? (
                <>
                  <View style={s.hr} />
                  <Text style={s.readLine}>{data.face_shape.shape} face</Text>
                  <Text style={s.footnote}>
                    From four ratios measured off your face mesh. The ratios are reliable; which
                    of seven words they become is a convention with uncalibrated cut points, and
                    this one is held at {Math.round((data.face_shape.confidence ?? 0) * 100)}%.
                  </Text>
                  {data.face_shape.features ? (
                    <FaceFeatureRows features={data.face_shape.features} />
                  ) : null}
                </>
              ) : null}

              <View style={s.hr} />
              <Text style={s.readLine}>{data.body.line}</Text>
              {data.body.size_estimate && (
                <View style={s.estimate}>
                  <Text style={s.estimateTitle}>Rough estimate — not a measurement</Text>
                  {Object.entries(data.body.size_estimate.cm).map(([part, cm]) => {
                    const range = data.body.size_estimate!.cm_range[part];
                    return (
                      <Text key={part} style={s.estimateLine}>
                        {part.replace(/_/g, " ")}: about {cm} cm ({range[0]}–{range[1]})
                      </Text>
                    );
                  })}
                  <Text style={s.estimateNote}>{data.body.size_estimate.notes[0]}</Text>
                </View>
              )}
            </View>

            {/* the rules — evidence, with sources */}
            {data.rules_applied.length > 0 && (
              <View style={s.card}>
                <Pressable onPress={() => setShowRules(!showRules)} style={s.rowBetween}>
                  <Text style={s.kicker}>THE EVIDENCE · CONVENTION</Text>
                  <Ionicons name={showRules ? "chevron-up" : "chevron-down"} size={17} color={C.muted} />
                </Pressable>
                <Text style={s.footnote}>
                  Styling convention, not fact. No study backs any of it, and your thumbs move
                  these numbers.
                </Text>
                {showRules && data.rules_applied.map((r) => (
                  <View key={r.id} style={s.rule}>
                    <View style={s.rowBetween}>
                      <Text style={s.ruleAttr}>{r.attribute}</Text>
                      <Text style={s.ruleConf}>{Math.round(r.confidence * 100)}%</Text>
                    </View>
                    <Text style={s.ruleTxt}>{r.recommends}</Text>
                    <Text style={s.ruleMeta}>{r.source} · assumes: {r.goal}</Text>
                  </View>
                ))}
              </View>
            )}

            <AdviceCard
              kicker="HAIR · CONVENTION"
              standing={"From a standard cosmetology textbook (Milady Ch.14). Widely taught, and "
                + "supported by no study. It optimises for the illusion of an oval face, which "
                + "is an aesthetic position you are free to reject."}
              advice={data.hairstyle}
              emptyLabel="No hair advice yet — your face shape has not been read."
            />

            <AdviceCard
              kicker="POSE · UNSOURCED"
              standing={"The least grounded advice here. Studio practice passed on by "
                + "demonstration, with no standard text and no study behind it — which is why "
                + "these numbers sit below everything else on this page. Easy to test in a "
                + "mirror, and your thumbs should outweigh it quickly."}
              advice={data.pose}
              emptyLabel="No posing advice for this profile yet."
            />

            <AdviceCard
              kicker="ACCESSORIES · MIXED"
              standing={"Metal temperature keys on your MEASURED undertone. Everything else keys "
                + "on your vibe, which is itself an interpretation — so those are the least "
                + "confident suggestions ALTIER makes, and each line says which it is."}
              advice={data.accessory}
              emptyLabel="Nothing to suggest here yet."
            />

            {/* the point of the app */}
            {convergence && (
              <View style={s.card}>
                <Text style={s.kicker}>HOW CLEAR YOUR TASTE IS GETTING</Text>
                <Text style={s.reason}>{convergence.headline}</Text>
                <Text style={s.footnote}>
                  A rough read, not a score of you. It tracks whether you are changing your mind
                  less, not whether you use the app more.
                </Text>
              </View>
            )}

            <Text style={s.poolNote}>{data.pool.note}</Text>
            {data.pool.occasion_filter?.note && <Text style={s.poolNote}>{data.pool.occasion_filter.note}</Text>}
            {!data.taste.available && (
              <Text style={s.poolNote}>
                Your own taste is not in this yet. Upload pins and ALTIER will lead with what you save.
              </Text>
            )}
          </>
        )}

        {/* Ask ALTIER — outside the data block on purpose: it works before onboarding too */}
        <View style={s.card}>
          <Text style={s.kicker}>ASK ALTIER · CITED OR REFUSED</Text>
          <Text style={s.footnote}>
            Answers come only from the sourced rule bases, every sentence cited and every citation
            checked. A question they cannot answer is refused, not improvised.
          </Text>
          <View style={s.askRow}>
            <TextInput
              style={s.askField}
              value={askQ}
              onChangeText={setAskQ}
              onSubmitEditing={askAltier}
              returnKeyType="send"
              placeholder="e.g. which necklines suit me, and why?"
              placeholderTextColor={C.muted}
            />
            <Pressable onPress={askAltier} hitSlop={8} disabled={asking}>
              <Ionicons name={asking ? "hourglass-outline" : "arrow-forward-circle"} size={26} color={C.ink} />
            </Pressable>
          </View>
          {askRes && (
            <>
              <Text style={s.reason}>{askRes.answer}</Text>
              {askRes.citations.map((c) => (
                <Text key={c.n} style={s.ruleMeta}>[{c.n}] {c.title}{c.section ? ` › ${c.section}` : ""}</Text>
              ))}
              <Text style={s.footnote}>
                {askRes.source === "gemini"
                  ? "Written by the model from the cited sources; citations verified."
                  : askRes.source === "retrieval-only"
                  ? "The matching rules themselves — no model text was used."
                  : "Refused: nothing in the sources is close enough to answer this."}
                {askRes.profile_used ? ` Read against your profile: ${askRes.profile_used}.` : ""}
              </Text>
            </>
          )}
        </View>

        <View style={{ height: 28 }} />
      </ScrollView>

      {/* bottom nav — five slots, black circle in the middle, as in the reference */}
      <View style={s.nav}>
        <Ionicons name="home" size={23} color={C.ink} />
        <Ionicons name="shirt-outline" size={23} color={C.muted} />
        <View style={s.navPlus}><Ionicons name="add" size={26} color="#fff" /></View>
        <Ionicons name="search-outline" size={23} color={C.muted} />
        {avatarUri
          ? <Image source={{ uri: avatarUri }} style={s.navAvatar} />
          : <View style={s.navAvatarEmpty}><Text style={s.navAvatarTxt}>{userName.charAt(0).toUpperCase()}</Text></View>}
      </View>
    </View>
  );
}

/** The measured facial features, shown as material rather than as a judgement.
 *
 *  Nothing here recommends anything and no advice engine keys on them — they are the raw facts
 *  of her face, which is what Page 1 is supposed to hand her. Features pinned to a clamp bound
 *  are struck through, because they describe the constant inside the measuring code rather than
 *  describing her. */
function FaceFeatureRows({ features }: { features: FaceFeatures }) {
  const groups: (keyof Omit<FaceFeatures, "saturated">)[] = ["eyes", "brows", "cheeks", "lips"];
  return (
    <View style={s.features}>
      {groups.map((group) => (
        <View key={group} style={s.featureRow}>
          <Text style={s.featureGroup}>{group}</Text>
          <View style={s.featureChips}>
            {Object.entries(features[group]).map(([key, value]) => {
              const dead = features.saturated.includes(`${group}.${key}`);
              return (
                <View key={key} style={[s.featureChip, dead && s.featureChipDead]}>
                  <Text style={[s.featureTxt, dead && s.featureTxtDead]}>
                    {key.replace(/_/g, " ")} {value}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>
      ))}
      {features.saturated.length > 0 && (
        <Text style={s.footnote}>
          Struck-through values sat on a measurement limit, so they describe the measuring code
          rather than your face. Ignore them.
        </Text>
      )}
    </View>
  );
}

/** The three advice engines render through ONE component on purpose.
 *
 *  They differ in exactly one thing that matters — how much is behind them — and that
 *  difference is carried by `standing` and by each rule's own confidence, not by three
 *  hand-built layouts that could quietly start making one look more authoritative than another.
 *
 *  `standing` is the engine's epistemic status in her words, and it is not decoration: hair
 *  cites a standard cosmetology textbook, posing cites nothing at all, and accessory advice
 *  mostly sits on a vibe read that is itself interpretation. */
function AdviceCard({
  kicker,
  standing,
  advice,
  emptyLabel,
}: {
  kicker: string;
  standing: string;
  advice?: Advice;
  emptyLabel: string;
}) {
  if (!advice) return null;

  /* Nothing to say is a real answer. An engine with no matching rule prints its own reason
     rather than a default, which would be indistinguishable from a real suggestion. */
  if (!advice.rules.length) {
    return (
      <View style={s.card}>
        <Text style={s.kicker}>{kicker}</Text>
        <Text style={s.footnote}>{advice.note ?? emptyLabel}</Text>
      </View>
    );
  }

  return (
    <View style={s.card}>
      <Text style={s.kicker}>{kicker}</Text>
      <Text style={s.footnote}>{standing}</Text>

      {advice.rules.map((rule) => (
        <View key={rule.id} style={s.advice}>
          <View style={s.rowBetween}>
            {/* Where a rule says what it hangs off, show it. "measured undertone" and
                "interpreted vibe" are very different amounts of ground to stand on. */}
            <Text style={s.adviceKeyedOn}>{rule.keyed_on ?? rule.goal}</Text>
            <Text style={s.ruleConf}>{Math.round(rule.confidence * 100)}%</Text>
          </View>
          <Text style={s.adviceTxt}>{rule.recommends}</Text>
          {rule.avoid ? <Text style={s.adviceAvoid}>Not: {rule.avoid}</Text> : null}
          <Text style={s.ruleMeta}>{rule.reason}</Text>
          <Text style={s.ruleMeta}>{rule.source_detail?.name}</Text>
        </View>
      ))}

      {/* Two rules can suggest opposite things — your shape says turn, the occasion says stand
          square. The more confident one is shown; saying the other existed is more honest than
          dropping it silently. */}
      {advice.conflicts?.map((conflict, i) => (
        <Text key={i} style={s.conflict}>
          Your {conflict.also_matched.because.join(" and ")} suggested the opposite here:
          "{conflict.also_matched.recommends}" They disagree about {conflict.axis}, so the more
          confident one is shown.
        </Text>
      ))}
    </View>
  );
}

/* ---------------- styles ---------------- */
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.pink },
  scroll: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 100 },

  topbar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topSide: { flexDirection: "row", alignItems: "center", gap: 10, width: 74 },
  streak: { flexDirection: "row", alignItems: "center", gap: 2 },
  streakN: { fontWeight: "800", fontSize: 13, color: C.ink },
  wordmark: { fontWeight: "900", fontSize: 22, letterSpacing: 2, color: C.ink },
  bellDot: { position: "absolute", top: -1, right: 0, width: 7, height: 7, borderRadius: 4, backgroundColor: C.rose },

  week: { flexDirection: "row", justifyContent: "space-between", marginTop: 18 },
  day: { alignItems: "center", width: 42 },
  dayLabel: { fontSize: 9.5, fontWeight: "700", color: C.muted, letterSpacing: 0.4 },
  dayLabelOn: { color: C.ink },
  dayNum: { fontSize: 13, fontWeight: "600", color: C.muted, marginTop: 2 },
  dayNumOn: { color: C.ink, fontWeight: "800" },
  dayTile: { width: 36, height: 50, borderRadius: 9, marginTop: 6, backgroundColor: C.pink2, overflow: "hidden", flexDirection: "row", flexWrap: "wrap" },
  dayTileGhost: { backgroundColor: C.ghost },
  dayChip: { width: "50%", height: "50%" },
  dayUnderline: { width: 26, height: 2.5, borderRadius: 2, backgroundColor: C.ink, marginTop: 5 },

  askPill: { flexDirection: "row", alignItems: "center", gap: 9, backgroundColor: C.card, borderRadius: R.pill, paddingHorizontal: 16, paddingVertical: 13, marginTop: 18 },
  askInput: { flex: 1, fontSize: 14, color: C.ink, padding: 0 },
  askRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 10, backgroundColor: C.pink, borderRadius: R.pill, paddingHorizontal: 14, paddingVertical: 9 },
  askField: { flex: 1, fontSize: 13.5, color: C.ink, padding: 0 },

  greetRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginTop: 22, gap: 14 },
  greet: { fontWeight: "800", fontSize: 24, lineHeight: 28, color: C.ink, flexShrink: 1 },
  vibeBox: { alignItems: "flex-end", maxWidth: 150 },
  vibeLabel: { fontSize: 9, letterSpacing: 1.4, color: C.muted, fontWeight: "700" },
  vibePhrase: { fontSize: 14, fontWeight: "700", color: C.ink, textAlign: "right", marginTop: 3 },
  vibeTag: { fontSize: 9.5, color: C.muted, marginTop: 3 },

  sectionLabel: { fontSize: 9.5, letterSpacing: 1.8, color: C.muted, fontWeight: "700", marginTop: 22, marginBottom: 9 },
  pillRow: { flexDirection: "row" },
  pill: { paddingHorizontal: 17, paddingVertical: 8.5, borderRadius: R.pill, backgroundColor: C.card, marginRight: 8 },
  pillOn: { backgroundColor: C.ink },
  pillTxt: { fontSize: 13, fontWeight: "600", color: C.ink, textTransform: "capitalize" },
  pillTxtOn: { color: "#fff" },
  chipRow: { flexDirection: "row", marginTop: 9 },
  chip: { paddingHorizontal: 13, paddingVertical: 6.5, borderRadius: R.pill, marginRight: 7, borderWidth: 1, borderColor: C.line },
  chipOn: { backgroundColor: C.pink2, borderColor: C.rose },
  chipTxt: { fontSize: 12, color: C.muted, textTransform: "capitalize" },
  chipTxtOn: { color: C.ink, fontWeight: "700" },

  skeletonWrap: { marginTop: 20, gap: 14, alignItems: "center" },
  skeletonRow: { flexDirection: "row", gap: 12, alignSelf: "stretch" },
  skeleton: { flex: 1, backgroundColor: C.card, borderRadius: R.tile, opacity: 0.6 },

  lookTitle: { fontWeight: "800", fontSize: 19, lineHeight: 24, color: C.ink, marginTop: 22 },

  flatlay: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 14 },
  tile: { flexGrow: 1, flexBasis: "45%", backgroundColor: C.card, borderRadius: R.tile, padding: 10 },
  tileImage: { borderRadius: 10, overflow: "hidden", flexDirection: "row", backgroundColor: C.pink },
  tileImg: { width: "100%", height: "100%" },
  tileBand: { flex: 1 },
  tileSlot: { fontSize: 9, letterSpacing: 1.4, textTransform: "uppercase", color: C.roseDark, fontWeight: "700", marginTop: 9 },
  tileName: { fontSize: 12.5, lineHeight: 17, color: C.ink, fontWeight: "600", marginTop: 2 },
  tilePrice: { fontSize: 11.5, color: C.ink, marginTop: 4, fontWeight: "600" },
  buyBtn: { marginTop: 8, backgroundColor: C.ink, borderRadius: R.pill, paddingVertical: 7, alignItems: "center" },
  buyTxt: { color: "#fff", fontSize: 12, fontWeight: "700" },
  asSearched: { fontSize: 9.5, color: C.muted, marginTop: 6, fontStyle: "italic" },
  attrRow: { flexDirection: "row", flexWrap: "wrap", gap: 5, marginTop: 7 },
  attrChip: { backgroundColor: C.pink, borderRadius: R.pill, paddingHorizontal: 8, paddingVertical: 3 },
  attrTxt: { fontSize: 9.5, color: C.ink, fontWeight: "600" },

  blackBtnWide: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: C.ink, borderRadius: R.pill, paddingVertical: 14, marginTop: 16 },
  blackBtn: { alignSelf: "flex-start", backgroundColor: C.ink, borderRadius: R.pill, paddingHorizontal: 18, paddingVertical: 9, marginTop: 12 },
  blackBtnTxt: { color: "#fff", fontSize: 13.5, fontWeight: "700" },
  promptTxt: { fontSize: 12.5, lineHeight: 19, color: C.ink, marginTop: 9 },

  divider: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 26 },
  dividerLine: { flex: 1, height: 1, backgroundColor: C.line },
  dividerTxt: { color: C.muted, fontSize: 12.5 },

  card: { backgroundColor: C.card, borderRadius: R.card, padding: 17, marginTop: 14 },
  dissentCard: { backgroundColor: C.warnBg },
  cardTitle: { fontWeight: "800", fontSize: 15.5, color: C.ink },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  kicker: { fontSize: 9.5, letterSpacing: 1.6, textTransform: "uppercase", color: C.roseDark, fontWeight: "700" },
  badge: { fontSize: 9.5, color: C.muted },
  reason: { fontSize: 14, lineHeight: 21, color: C.ink, marginTop: 9 },
  footnote: { fontSize: 11, lineHeight: 16.5, color: C.muted, marginTop: 9 },
  poolNote: { fontSize: 11, lineHeight: 16.5, color: C.muted, marginTop: 12, paddingHorizontal: 4 },

  voteRow: { flexDirection: "row", gap: 10, marginTop: 15 },
  vote: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, borderRadius: R.pill, borderWidth: 1, borderColor: C.line, paddingVertical: 11 },
  voteOn: { backgroundColor: C.pink2, borderColor: C.rose },
  voteEmoji: { fontSize: 14 },
  voteTxt: { fontSize: 12.5, color: C.ink, fontWeight: "600" },

  swatchWrap: { flexDirection: "row", flexWrap: "wrap", gap: 9, marginTop: 13 },
  swatchCol: { width: 50, alignItems: "center" },
  swatch: { width: 36, height: 36, borderRadius: 10 },
  swatchName: { fontSize: 8.5, color: C.muted, marginTop: 4, textAlign: "center" },
  guidance: { fontSize: 12.5, lineHeight: 19, color: C.ink, marginTop: 13 },

  readLine: { fontSize: 15, fontWeight: "700", color: C.ink, marginTop: 9, textTransform: "capitalize" },
  hr: { height: 1, backgroundColor: C.line, marginVertical: 15 },
  borderline: { backgroundColor: C.warnBg, borderRadius: 12, padding: 11, marginTop: 10 },
  borderlineTitle: { fontSize: 11, fontWeight: "700", color: C.warn },
  borderlineTxt: { fontSize: 11, lineHeight: 16.5, color: C.warn, marginTop: 4 },
  estimate: { backgroundColor: C.warnBg, borderRadius: 12, padding: 12, marginTop: 12 },
  estimateTitle: { fontSize: 11, fontWeight: "700", color: C.warn },
  estimateLine: { fontSize: 12, color: C.ink, marginTop: 5, textTransform: "capitalize" },
  estimateNote: { fontSize: 10.5, lineHeight: 15.5, color: C.warn, marginTop: 8 },

  advice: { marginTop: 13, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.line },
  adviceKeyedOn: { fontSize: 9, letterSpacing: 1.2, textTransform: "uppercase", color: C.muted, fontWeight: "700", flexShrink: 1, marginRight: 8 },
  adviceTxt: { fontSize: 13.5, lineHeight: 19, color: C.ink, fontWeight: "600", marginTop: 6 },
  adviceAvoid: { fontSize: 12, lineHeight: 17, color: C.muted, marginTop: 4 },
  conflict: { fontSize: 10.5, lineHeight: 15.5, color: C.warn, backgroundColor: C.warnBg, borderRadius: 10, padding: 9, marginTop: 12 },

  features: { marginTop: 12 },
  featureRow: { marginTop: 9 },
  featureGroup: { fontSize: 9, letterSpacing: 1.2, textTransform: "uppercase", color: C.roseDark, fontWeight: "700" },
  featureChips: { flexDirection: "row", flexWrap: "wrap", gap: 5, marginTop: 5 },
  featureChip: { backgroundColor: C.pink, borderRadius: R.pill, paddingHorizontal: 8, paddingVertical: 3 },
  featureChipDead: { backgroundColor: "transparent", borderWidth: 1, borderColor: C.line },
  featureTxt: { fontSize: 9.5, color: C.ink },
  featureTxtDead: { color: C.muted, textDecorationLine: "line-through" },

  rule: { marginTop: 13, paddingTop: 11, borderTopWidth: 1, borderTopColor: C.line },
  ruleAttr: { fontSize: 9.5, letterSpacing: 1.4, textTransform: "uppercase", color: C.muted, fontWeight: "700" },
  ruleConf: { fontSize: 11, color: C.roseDark, fontWeight: "700" },
  ruleTxt: { fontSize: 12.5, lineHeight: 18, color: C.ink, marginTop: 5 },
  ruleMeta: { fontSize: 10, color: C.muted, marginTop: 5 },

  nav: { position: "absolute", bottom: 0, left: 0, right: 0, height: 76, backgroundColor: C.card, borderTopWidth: 1, borderTopColor: C.line, flexDirection: "row", justifyContent: "space-around", alignItems: "center", paddingBottom: 10 },
  navPlus: { width: 48, height: 48, borderRadius: 24, backgroundColor: C.ink, alignItems: "center", justifyContent: "center" },
  navAvatar: { width: 27, height: 27, borderRadius: 14 },
  navAvatarEmpty: { width: 27, height: 27, borderRadius: 14, backgroundColor: C.ink, alignItems: "center", justifyContent: "center" },
  navAvatarTxt: { color: "#fff", fontSize: 11, fontWeight: "700" },
});
