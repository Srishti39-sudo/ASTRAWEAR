/**
 * ALTIER — the app shell.
 *
 * One screen for now: Page 1, "Today's Fit". Pages 2-4 (Buy-or-not, Try, Profile) are stubs in
 * the bottom nav and not built.
 *
 * THE API RUNS ON YOUR MAC. Nothing here talks to a server you do not own: the colour, palette,
 * body, face, rules and taste engines all run locally, and Gemini is optional. EXPO_PUBLIC_ALTIER_API
 * points at the Mac's address on your wifi; off this network, put both devices on Tailscale and
 * use the Mac's Tailscale name instead.
 */
import React from "react";
import { SafeAreaView, StatusBar, StyleSheet } from "react-native";
import TodayScreen from "./screens/TodayScreen";

export default function App() {
  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="dark-content" />
      <TodayScreen userName="Srishti" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#FBECF1" },
});
