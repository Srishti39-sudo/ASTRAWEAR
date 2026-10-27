import { useState } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

/* ---------------- palette (baby pink + black) ---------------- */
const C = {
  pink: "#FBECF1",
  pink2: "#F6DBE3",
  rose: "#D97A94",
  roseDark: "#C25E7B",
  ink: "#141110",
  muted: "#B29AA1",
  card: "#FFFFFF",
  line: "#F1DDE4",
};

/* ---------------- data ---------------- */
// each past day = the outfit you actually wore (two dominant colours stand in for the photo)
const WEEK = [
  { d: "SUN", n: 30, wore: ["#C9B79B", "#6B5B4A"] }, // beige/brown
  { d: "MON", n: 31, wore: ["#7FB0A3", "#2E2E2E"] }, // sage/black
  { d: "TUE", n: 1,  wore: ["#C7A15A", "#3A2E1E"] }, // camel
  { d: "WED", n: 2,  wore: ["#6E8CC4", "#1A1A1A"] }, // blue/black
  { d: "THU", n: 3,  wore: ["#E7A8BC", "#8A5A66"] }, // pink
  { d: "FRI", n: 4,  wore: ["#6E8CC4", "#141110"], today: true }, // today = suggested
  { d: "SAT", n: 5,  wore: null }, // future = empty
];

// suggestions swap by occasion
type Look = {
  fit: string;
  why: string;
  palette: string[];
  tip: string;
  pose: string;
};
const OCCASIONS: Record<string, Look> = {
  Casual: {
    fit: "Black high-waist jeans + cornflower blue top.",
    why: "Blue sits in your cool palette and plays off your contrast — sharp, not washed out. Trust it.",
    palette: ["#6E8CC4", "#141110", "#F6C9D6"],
    tip: "Contrast is queen. Deep hair + fair skin = wear clear, saturated colours. Muddy beige flattens you.",
    pose: "Chin down, eyes up, weight on your back leg, one hand loose. Editorial — not a stiff selfie.",
  },
  Gym: {
    fit: "Black high-waist leggings + sage sculpt top.",
    why: "Monochrome black lengthens the line; sage is your best neutral-cool — energising without clashing.",
    palette: ["#7FB0A3", "#141110", "#DCE6E2"],
    tip: "Athleisure rule: keep it tonal, add ONE pop. Head-to-toe black + a sage top reads intentional, not lazy.",
    pose: "Side-on, shoulders back, phone at hip height — shows the fit's shape, not just your face.",
  },
  Work: {
    fit: "Tailored trousers + crisp white shirt.",
    why: "Structure signals authority; white near your face lifts your high contrast beautifully.",
    palette: ["#1F2A44", "#FFFFFF", "#B9A07C"],
    tip: "For work, muted + sharp beats loud. Navy, white, camel — clean lines do the talking.",
    pose: "Straight on, chin level, hands relaxed. Confident and still reads best in structured looks.",
  },
  Party: {
    fit: "Wine satin slip + strappy heels.",
    why: "Jewel tones on high-contrast colouring = stunning. Wine deepens your intensity instead of fighting it.",
    palette: ["#6E1E38", "#141110", "#D9A7B4"],
    tip: "Night out = go saturated and rich. Jewel tones (wine, emerald, sapphire) were made for your contrast.",
    pose: "Slight turn, weight on one leg, chin down. Movement in the fabric > flat and forward.",
  },
  Date: {
    fit: "Baby pink knit + straight-leg jeans.",
    why: "Soft rose near your face makes your undertone glow — warm, approachable, still you.",
    palette: ["#F6C9D6", "#EFE3D4", "#141110"],
    tip: "Soft colours close to the face, structure below. Let one gentle colour do the softening.",
    pose: "Relaxed, half-smile, hands in pockets. Ease reads as confidence on a date.",
  },
};
const OCC_LIST = Object.keys(OCCASIONS);

/* ---------------- screen ---------------- */
export default function StylistHome() {
  const [occ, setOcc] = useState("Casual");
  const look = OCCASIONS[occ];
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning," : hour < 17 ? "Good afternoon," : "Good evening,";

  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {/* top bar */}
        <View style={s.topbar}>
          <View style={s.side}>
            <Ionicons name="calendar-outline" size={22} color={C.ink} />
            <View style={s.streak}>
              <Ionicons name="flame" size={16} color={C.rose} />
              <Text style={s.streakN}>6</Text>
            </View>
          </View>
          <Text style={s.wm}>WEARD</Text>
          <View style={s.side}>
            <Ionicons name="help-circle-outline" size={22} color={C.ink} />
            <View>
              <Ionicons name="notifications-outline" size={22} color={C.ink} />
              <View style={s.bellDot} />
            </View>
          </View>
        </View>

        {/* week strip — the outfit you wore each day */}
        <View style={s.week}>
          {WEEK.map((day) => (
            <View key={day.n} style={s.day}>
              <Text style={[s.dl, day.today && s.dlOn]}>{day.d}</Text>
              {day.wore ? (
                <View style={[s.thumb, day.today && s.thumbOn]}>
                  <View style={[s.thumbHalf, { backgroundColor: day.wore[0] }]} />
                  <View style={[s.thumbHalf, { backgroundColor: day.wore[1] }]} />
                </View>
              ) : (
                <View style={[s.thumb, s.thumbEmpty]} />
              )}
              {day.today && <View style={s.underline} />}
              <View style={[s.dnWrap, day.today && s.dnWrapOn]}>
                <Text style={[s.dn, day.today && s.dnOn]}>{day.n}</Text>
              </View>
            </View>
          ))}
        </View>

        {/* occasion selector */}
        <Text style={s.occLabel}>WHAT'S THE OCCASION?</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.occRow}>
          {OCC_LIST.map((o) => (
            <Pressable key={o} onPress={() => setOcc(o)} style={[s.pill, occ === o && s.pillOn]}>
              <Text style={[s.pillTxt, occ === o && s.pillTxtOn]}>{o}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* ask weard */}
        <Pressable style={s.ask}>
          <Ionicons name="chatbubble-ellipses-outline" size={19} color={C.roseDark} />
          <Text style={s.askTxt}>Ask weard</Text>
        </Pressable>

        {/* greeting + weather */}
        <View style={s.greetRow}>
          <Text style={s.greet}>{greet}{"\n"}Srishti</Text>
          <View style={s.weather}>
            <Text style={s.wT}>☀️ 34°</Text>
            <Text style={s.wSub}>H:35° L:27°</Text>
          </View>
        </View>

        <View style={s.logged}>
          <View style={s.logAv}><Text style={s.logAvT}>S</Text></View>
          <Text style={s.logTxt}>You logged today's fit</Text>
        </View>

        {/* today's look card (the outfit you wore / were suggested) */}
        <View style={s.look}>
          <View style={s.lookPhoto}>
            <View style={[s.lookBand, { backgroundColor: look.palette[0] }]} />
            <View style={[s.lookBand, { backgroundColor: look.palette[1] }]} />
            <View style={[s.lookBand, { backgroundColor: look.palette[2] }]} />
          </View>
          <View style={s.lookCap}>
            <Text style={s.lookNm}>You · {occ}</Text>
            <Text style={s.lookLoc}>📍 Delhi</Text>
          </View>
        </View>

        <View style={s.divider}><Text style={s.dividerTxt}>Today's suggestions</Text></View>

        {/* fit suggestion */}
        <View style={s.card}>
          <Text style={s.kicker}>TODAY'S FIT · {occ.toUpperCase()}</Text>
          <Text style={s.fit}>{look.fit}</Text>
          <Text style={s.fitSub}>{look.why}</Text>
          <View style={s.palette}>
            {look.palette.map((col, i) => (
              <View key={i} style={[s.sw, { backgroundColor: col }]} />
            ))}
            <Text style={s.swLab}>your colours today</Text>
          </View>
        </View>

        {/* london school drop */}
        <View style={s.card}>
          <Text style={s.kicker}>LONDON SCHOOL DROP</Text>
          <Text style={s.lesson}>{look.tip}</Text>
          <View style={s.pose}>
            <Text style={s.kicker}>POSE OF THE DAY</Text>
            <Text style={s.poseTxt}>{look.pose}</Text>
          </View>
        </View>

        <View style={{ height: 20 }} />
      </ScrollView>

      {/* bottom nav — ALTA style */}
      <View style={s.nav}>
        <Ionicons name="home" size={25} color={C.ink} />
        <Ionicons name="shirt-outline" size={25} color={C.muted} />
        <View style={s.plus}><Ionicons name="add" size={26} color="#fff" /></View>
        <Ionicons name="search" size={25} color={C.muted} />
        <View style={s.navProf}><Text style={s.navProfT}>S</Text></View>
      </View>
    </View>
  );
}

/* ---------------- styles ---------------- */
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.pink },
  scroll: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 96 },

  topbar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  side: { flexDirection: "row", alignItems: "center", gap: 12 },
  streak: { flexDirection: "row", alignItems: "center", gap: 3 },
  streakN: { fontWeight: "800", fontSize: 14, color: C.ink },
  wm: { fontWeight: "900", fontSize: 24, letterSpacing: 3, color: C.ink },
  bellDot: { position: "absolute", top: 0, right: 1, width: 7, height: 7, borderRadius: 4, backgroundColor: C.rose },

  week: { flexDirection: "row", justifyContent: "space-between", marginTop: 16 },
  day: { alignItems: "center", width: 44 },
  dl: { fontSize: 10, fontWeight: "700", color: C.muted, marginBottom: 6 },
  dlOn: { color: C.ink },
  thumb: { width: 38, height: 52, borderRadius: 10, overflow: "hidden", backgroundColor: C.pink2 },
  thumbOn: { borderWidth: 2, borderColor: C.ink },
  thumbHalf: { flex: 1 },
  thumbEmpty: { backgroundColor: "#F2E4EA", borderWidth: 1, borderColor: C.line },
  underline: { width: 24, height: 3, borderRadius: 2, backgroundColor: C.ink, marginTop: 4 },
  dnWrap: { marginTop: 4, paddingHorizontal: 7, paddingVertical: 1, borderRadius: 8 },
  dnWrapOn: { backgroundColor: C.pink2 },
  dn: { fontSize: 12, fontWeight: "600", color: C.muted },
  dnOn: { color: C.ink },

  occLabel: { fontSize: 10, letterSpacing: 2, color: C.muted, fontWeight: "700", marginTop: 22, marginBottom: 10 },
  occRow: { flexDirection: "row" },
  pill: { paddingHorizontal: 18, paddingVertical: 9, borderRadius: 20, backgroundColor: "#fff", marginRight: 9, borderWidth: 1, borderColor: C.line },
  pillOn: { backgroundColor: C.ink, borderColor: C.ink },
  pillTxt: { fontSize: 13, fontWeight: "600", color: C.ink },
  pillTxtOn: { color: "#fff" },

  ask: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9, backgroundColor: "#fff", borderRadius: 30, paddingVertical: 15, marginTop: 18 },
  askTxt: { fontWeight: "600", fontSize: 14.5, color: C.ink },

  greetRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginTop: 22 },
  greet: { fontWeight: "800", fontSize: 25, color: C.ink, lineHeight: 28 },
  weather: { alignItems: "flex-end" },
  wT: { fontSize: 15, fontWeight: "700", color: C.ink },
  wSub: { fontSize: 12.5, color: C.muted },

  logged: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16 },
  logAv: { width: 26, height: 26, borderRadius: 13, backgroundColor: C.rose, alignItems: "center", justifyContent: "center" },
  logAvT: { color: "#fff", fontSize: 12, fontWeight: "700" },
  logTxt: { fontSize: 13, color: C.muted },

  look: { backgroundColor: "#fff", borderRadius: 24, marginTop: 14, overflow: "hidden" },
  lookPhoto: { height: 260, flexDirection: "row" },
  lookBand: { flex: 1 },
  lookCap: { padding: 14, alignItems: "center" },
  lookNm: { fontWeight: "700", fontSize: 15, color: C.ink },
  lookLoc: { fontSize: 12, color: C.muted, marginTop: 2 },

  divider: { alignItems: "center", marginTop: 26, marginBottom: 4 },
  dividerTxt: { color: C.muted, fontSize: 12.5 },

  card: { backgroundColor: "#fff", borderRadius: 22, padding: 18, marginTop: 14 },
  kicker: { fontSize: 10, letterSpacing: 2, textTransform: "uppercase", color: C.roseDark, fontWeight: "700" },
  fit: { fontWeight: "700", fontSize: 19, lineHeight: 24, marginTop: 8, color: C.ink },
  fitSub: { fontSize: 12.5, color: C.muted, marginTop: 8, lineHeight: 19 },
  palette: { flexDirection: "row", alignItems: "center", gap: 9, marginTop: 14 },
  sw: { width: 34, height: 34, borderRadius: 10 },
  swLab: { fontSize: 12, color: C.muted, marginLeft: 4 },

  lesson: { fontSize: 13, lineHeight: 21, marginTop: 9, color: C.ink },
  pose: { marginTop: 14, paddingTop: 13, borderTopWidth: 1, borderTopColor: C.line, borderStyle: "dashed" },
  poseTxt: { fontSize: 12.5, lineHeight: 19, marginTop: 5, color: C.ink },

  nav: { position: "absolute", bottom: 0, left: 0, right: 0, height: 78, backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: C.line, flexDirection: "row", justifyContent: "space-around", alignItems: "center", paddingBottom: 8 },
  plus: { width: 52, height: 52, borderRadius: 26, backgroundColor: C.ink, alignItems: "center", justifyContent: "center" },
  navProf: { width: 28, height: 28, borderRadius: 14, backgroundColor: C.rose, alignItems: "center", justifyContent: "center" },
  navProfT: { color: "#fff", fontSize: 12, fontWeight: "700" },
});
