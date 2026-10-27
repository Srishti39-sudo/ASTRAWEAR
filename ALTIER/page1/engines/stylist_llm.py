"""
ALTIER · page1/engines/stylist_llm.py
-------------------------------------
Turns the recommender's finished explanation into a paragraph that reads like a person wrote it.

THE MODEL DOES NOT COMPOSE THE EXPLANATION. IT REPHRASES THE FRAMING AROUND IT.
    recommender.build_clauses() has already written every claim, in English, from numbers it was
    handed. This module hands those clauses to Gemini and requires the load-bearing ones back
    CHARACTER FOR CHARACTER. Gemini may add an opening, connecting words and a closing. That is
    all it may add, and what it adds is verified to contain no facts.

WHY IT IS BUILT THIS WAY, WHICH IS WORTH READING BEFORE CHANGING IT
    The first version sent Gemini a 29-line structured brief and asked it to write a paragraph.
    It wrote "the defined waist of the peplum silhouette also suits your fair depth and warm
    undertone" — a false link between a cut and a colour. Nothing in the brief said that. The
    brief simply had "undertone: warm" and "waist: defined" both in scope as loose attributes,
    and a fluent model will connect what is in scope.

    The check at the time scanned the output for hex colours, numbers and citations that were
    not in the brief. That sentence contains none of the three, so it passed. That is not a bug
    in the scan; it is the ceiling of the whole approach. Any check that looks for invented
    SPECIFICS will pass any invented GENERALITY, and a generality is a full sentence of styling
    advice with no number in it.

    The next idea was to send only the finished paragraph and check that the model returned the
    same number of sentences. That fails too, and it fails quietly. Give it the one clause
    "the square neckline is what the convention suggests for your shape" and it can return
    "the square neckline suits your undertone": one sentence in, one sentence out, count
    matches, and the same false colour-to-cut link is back. Counting maps the accounting, not
    the meaning.

    So the model is not trusted with the meaning at all. A claim-carrying sentence is copied or
    the answer is rejected. Exact reproduction is checkable with a substring search — no
    semantic judgement, no model grading a model — and a sentence that survives it verbatim
    cannot have been distorted, because it was not rewritten.

WHAT IS STILL NOT GUARANTEED, STATED PLAINLY
    The framing the model adds is free text and is checked, not proved. check_residue() rejects
    anything in it carrying a digit, a hex colour or a source name, and caps its length, so it
    cannot smuggle a measurement or a citation and cannot run to a paragraph of invented advice.
    It could still contain a contentless flourish: "this one is really you". That is a much
    smaller surface than before, and it is not zero. Do not describe this as hallucination-proof.

    The remaining lever, if even that is too much, is allow_llm=False: the clauses are joined and
    shown as written. Page 1 renders identically. It just reads a little flatter.

MODEL AND KEY
    gemini-2.5-flash, the generate model. gemini-embedding is a text-embedding model and cannot
    write prose. The key comes from GEMINI_API_KEY in a .env file, is never hardcoded, never
    logged, and never returned in a response. Retries reuse cv-service/gemini_util.py.

Usage:
    from engines import stylist_llm
    out = stylist_llm.write_todays_fit(top_look)
    print(out["text"], out["source"], out["model_added"])
"""

import argparse
import os
import re

from . import _paths

#: The generate model. Not an embedding model — see the note above.
MODEL = "gemini-2.5-flash"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Low, because this is a copying-and-connecting job, not a writing one.
TEMPERATURE = 0.3

#: gemini-2.5-flash is a THINKING model: by default it spends output tokens on internal
#: reasoning, and that spend counts against maxOutputTokens. At 400 the thinking consumed the
#: budget and the paragraph came back cut off mid-sentence. thinkingBudget 0 turns it off, which
#: is right for a job where every decision has already been made.
MAX_TOKENS = 900
THINKING_BUDGET = 0

#: The framing may be at most this fraction of the length of the clauses it wraps, with a floor
#: so a one-clause answer is not over-constrained. Not fitted to anything: it is the point past
#: which the model has stopped connecting sentences and started writing its own paragraph.
_RESIDUE_FRACTION = 0.45
_RESIDUE_FLOOR = 120

#: Source names the model must never introduce on its own. If a citation belongs in the answer
#: it is already inside a clause, where it is reproduced verbatim.
_SOURCE_NAMES = ("concept wardrobe", "kibbe", "ffit", "simmons", "istook", "devarajan",
                 "chardon", "vivaldi", "colorislab")

#: Endorsements the framing may not make. Nothing in ALTIER tells anyone an outfit is perfect
#: for them: the rules say "the convention suggests", carry a source, and carry a confidence
#: your feedback moves. A superlative in the framing quietly overrides all of that.
#:
#: This is a BLOCKLIST AND IT IS NOT EXHAUSTIVE. It catches the register rather than the idea,
#: and a model that wants to gush can do it in words not on this list. It is here because the
#: failure it covers is the one actually observed — Gemini rewrote "is tagged for" into "is
#: perfect for" the first time it was given a claim sentence to reword — and because a cheap
#: check on a small surface is worth having. It is not a guarantee, and the length cap below is
#: what actually bounds how much the model can say.
_ENDORSEMENTS = ("perfect", "ideal", "flawless", "stunning", "gorgeous", "amazing", "beautiful",
                 "guaranteed", "must-have", "you must", "you should", "definitely", "certainly",
                 "without a doubt", "can't go wrong", "cannot go wrong", "made for you")


# ---------------------------------------------------------------- key handling
def _load_env():
    """Read GEMINI_API_KEY from the environment, falling back through the project's .env files.

    Searched nearest-first so a page1-specific key wins over the shared ASTRAWEAR one. The key
    is returned, never printed, never stored on a module global, and never put in a response."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    for candidate in (os.path.join(_paths.PAGE1_ROOT, ".env"),
                      os.path.join(_paths.ALTIER_ROOT, ".env"),
                      os.path.join(_paths.ASTRAWEAR_ROOT, ".env"),
                      os.path.join(_paths.ASTRAWEAR_ROOT, "backend", ".env")):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)
            key = os.environ.get("GEMINI_API_KEY")
            if key:
                return key
    return None


def api_key_available():
    """Is a key configured? For a health check that must not reveal the key itself."""
    return bool(_load_env())


# ---------------------------------------------------------------- normalisation
#: Substitutions a language model makes without being asked. Straight quotes become curly, a
#: hyphen becomes an en dash, a space becomes a non-breaking space. None of them changes what a
#: sentence says, so matching on the raw bytes would reject correct answers for typography.
#: Everything beyond this list is a real difference and must fail.
_NORMALISE = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
    "…": "...",
}


def _norm(text):
    """Fold cosmetic typography and collapse whitespace. Meaning is untouched."""
    for bad, good in _NORMALISE.items():
        text = text.replace(bad, good)
    return " ".join(text.split())


# ---------------------------------------------------------------- the prompt
_SYSTEM = """You are ALTIER's stylist. The sentences below have already been written. Your only
job is to make them read as one warm paragraph from a person.

Sentences marked [EXACT] MUST appear in your answer CHARACTER FOR CHARACTER, in the order given.
Copy them. Do not reword them, shorten them, expand them, split them, merge them or reorder them.
Changing one word inside an [EXACT] sentence is the single failure that matters here, and the
answer will be discarded for it.

A sentence marked [FRAMING] is yours to reword freely.

You MAY add: a short opening, brief connecting words between the sentences, and at most one
short closing.

You MAY NOT add: any fact, colour, garment, number, percentage, measurement, source, rule,
reason or conclusion. Anything you add carries no information at all. It is tone only. If you
have nothing to put between two sentences, place them next to each other.

Do not explain why something suits her beyond what the sentences already say. Do not connect two
sentences with a reason of your own.

No preamble, no headings, no bullet points, no exclamation marks. Speak to her as "you"."""


def build_prompt(clauses):
    """The whole prompt. The clauses are the only input the model receives.

    Nothing else is sent — not the palette, not the measured read, not the rules table, not the
    occasion. Everything the answer may contain is already inside a clause, which is what makes
    the verbatim check sufficient rather than merely reassuring."""
    lines = []
    for clause in clauses:
        tag = "[EXACT]" if clause["load_bearing"] else "[FRAMING]"
        lines.append(f"{tag} {clause['text']}")
    return f"{_SYSTEM}\n\n--- the sentences ---\n" + "\n".join(lines)


# ---------------------------------------------------------------- verification
def check_verbatim(text, required):
    """Is every load-bearing clause reproduced exactly, in order? -> {ok, missing, out_of_order,
    residue, matched}

    `residue` is what is left of the answer once the clauses are cut out of it: exactly the text
    the model authored. That is the only part any further check needs to look at, and isolating
    it is the point of this function."""
    norm = _norm(text)
    cursor, spans = 0, []
    missing, out_of_order = [], []

    for clause in required:
        needle = _norm(clause)
        at = norm.find(needle, cursor)
        if at >= 0:
            spans.append((at, at + len(needle)))
            cursor = at + len(needle)
            continue
        # Present, but not where it should be. Reported separately from missing, because a
        # reordered answer is a different failure from a rewritten one.
        anywhere = norm.find(needle)
        if anywhere >= 0:
            out_of_order.append(clause)
            spans.append((anywhere, anywhere + len(needle)))
        else:
            missing.append(clause)

    residue = []
    last = 0
    for start, stop in sorted(spans):
        if start > last:
            residue.append(norm[last:start])
        last = max(last, stop)
    residue.append(norm[last:])

    return {
        "ok": not missing and not out_of_order,
        "missing": missing,
        "out_of_order": out_of_order,
        "matched": len(required) - len(missing),
        "residue": " ".join(" ".join(residue).split()),
    }


_DIGIT = re.compile(r"\d")
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def check_residue(residue, clause_length):
    """Is the text the model added free of claims, and short enough to be framing?

    -> {ok, problems, length, allowed_length}

    Three rules, all mechanical:
      NO DIGITS       a number in the framing is a measurement nobody computed. Every legitimate
                      number in the answer is inside a clause, and clauses are cut out before
                      this runs.
      NO SOURCE NAMES a citation in the framing attributes advice to someone who did not give it.
      NO ENDORSEMENT  "perfect for you" is a claim this system never makes anywhere else.
                      A non-exhaustive blocklist; see _ENDORSEMENTS.
      LENGTH CAPPED   past a point the model has stopped connecting sentences and is writing its
                      own paragraph, which is the behaviour this whole design exists to prevent.

    What this does NOT catch is a contentless flourish with no number and no citation in it. The
    module docstring says so. It is a much smaller surface than an open compose, and it is not
    zero."""
    problems = []
    allowed = max(_RESIDUE_FLOOR, int(_RESIDUE_FRACTION * clause_length))

    if _DIGIT.search(residue):
        problems.append("the framing contains a number, which no clause supplied")
    for hex_colour in set(_HEX.findall(residue)):
        problems.append(f"the framing contains a colour code ({hex_colour})")
    lowered = residue.lower()
    for name in _SOURCE_NAMES:
        if name in lowered:
            problems.append(f"the framing cites '{name}' on its own account")
    for word in _ENDORSEMENTS:
        if word in lowered:
            problems.append(f"the framing endorses ('{word}') — this system says what the "
                            f"convention suggests, never that something is right for you")
    if len(residue) > allowed:
        problems.append(f"the framing runs to {len(residue)} characters against a "
                        f"{allowed}-character ceiling — that is composing, not connecting")

    return {"ok": not problems, "problems": problems,
            "length": len(residue), "allowed_length": allowed}


# ---------------------------------------------------------------- the call
def _call_gemini(prompt, key, timeout=20):
    """POST to Gemini. -> (text, error). Retries transient 429/503 via cv-service/gemini_util."""
    gemini_util = _paths.load_module_from(
        os.path.join(_paths.CV_SERVICE, "gemini_util.py"), "gemini_util")

    url = _ENDPOINT.format(model=MODEL)
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": MAX_TOKENS,
                             "thinkingConfig": {"thinkingBudget": THINKING_BUDGET}},
    }

    try:
        if gemini_util is not None:
            resp = gemini_util.gemini_post(url, headers=headers, json=body, timeout=timeout)
        else:
            import requests
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except Exception as e:
        return None, f"gemini request failed: {type(e).__name__}"

    if resp is None:
        return None, "gemini returned no response"
    if resp.status_code != 200:
        # The body can echo the request; never surface it, only the status.
        return None, f"gemini returned HTTP {resp.status_code}"

    try:
        candidate = resp.json()["candidates"][0]
        parts = candidate["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        return None, "gemini response had an unexpected shape"

    # A truncated answer is a failure, not a shorter answer: it reads as a confident sentence
    # that simply stops. It would also fail the verbatim check, but saying why is more useful.
    finish = candidate.get("finishReason")
    if finish and finish not in ("STOP", "FINISH_REASON_STOP"):
        return None, f"gemini stopped early (finishReason {finish}) — the answer was truncated"

    return (text, None) if text else (None, "gemini returned empty text")


def write_todays_fit(scored_look, allow_llm=True):
    """The paragraph for page 1. Always returns something renderable.

    Takes ONLY the scored look, because the clauses on it are the only input the model gets.
    The earlier signature also accepted the profile, the palette, the occasion and the mood;
    those are gone rather than ignored, so that nothing can be handed to this function under the
    impression it will reach the model.

    -> {text, source, clauses, model_added, verbatim, residue_check, model, fallback_reason}
       source is "gemini" or "deterministic". The UI shows which, and should.
    """
    clauses = scored_look.get("clauses")
    if clauses is None:
        from .recommender import build_clauses
        clauses = build_clauses(scored_look)

    required = [c["text"] for c in clauses if c["load_bearing"]]
    deterministic = " ".join(c["text"] for c in clauses)
    clause_length = len(deterministic)

    def fall_back(why):
        return {
            "text": deterministic, "source": "deterministic",
            "clauses": clauses, "model_added": "",
            "verbatim": {"ok": True, "missing": [], "out_of_order": [],
                         "matched": len(required), "residue": ""},
            "residue_check": {"ok": True, "problems": [], "length": 0,
                              "allowed_length": 0},
            "model": None, "fallback_reason": why,
        }

    if not allow_llm:
        return fall_back("the caller asked for the clauses as written")

    key = _load_env()
    if not key:
        return fall_back("no GEMINI_API_KEY configured — set it in page1/.env")

    text, error = _call_gemini(build_prompt(clauses), key)
    if error:
        return fall_back(error)

    verbatim = check_verbatim(text, required)
    if not verbatim["ok"]:
        detail = []
        if verbatim["missing"]:
            detail.append(f"{len(verbatim['missing'])} sentence(s) were reworded or dropped")
        if verbatim["out_of_order"]:
            detail.append(f"{len(verbatim['out_of_order'])} sentence(s) were reordered")
        return fall_back("the written answer changed the sentences it was told to copy: "
                         + "; ".join(detail))

    residue_check = check_residue(verbatim["residue"], clause_length)
    if not residue_check["ok"]:
        return fall_back("the framing the model added did not pass its check: "
                         + "; ".join(residue_check["problems"]))

    return {
        "text": text, "source": "gemini",
        "clauses": clauses,
        # Exactly what the model wrote, surfaced so it can be read at a glance in a review, a
        # log or a debug screen. If this ever looks like advice, the design has slipped.
        "model_added": verbatim["residue"],
        "verbatim": verbatim, "residue_check": residue_check,
        "model": MODEL, "fallback_reason": None,
    }


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="ALTIER page 1 stylist writer (framing only)")
    ap.add_argument("--shape", default="pear")
    ap.add_argument("--skin", default="#bd9f80")
    ap.add_argument("--hair", default="#171618")
    ap.add_argument("--eye", default="#4e4748")
    ap.add_argument("--occasion", default="work")
    ap.add_argument("--mood", default="sharp")
    ap.add_argument("--special", default=None)
    ap.add_argument("--no-llm", action="store_true", help="show the clauses as written")
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()

    from . import color_engine, palette_engine, recommender
    read = color_engine.read_from_hexes(args.skin, args.hair, args.eye)
    pal = palette_engine.palette_for(read)
    profile = {"body_shape": args.shape, "contrast": read["contrast"],
               "undertone": read["undertone"], "depth": read["depth"],
               "skin_hex": read["skin_hex"], "hair_hex": read["hair_hex"],
               "eye_hex": read["eye_hex"], "palette": pal}

    top = recommender.recommend(profile, occasion=args.occasion, mood=args.mood,
                                special=args.special, k=1)["top"][0]
    out = write_todays_fit(top, allow_llm=not args.no_llm)

    if args.show_prompt:
        print("\n--- everything the model receives ---")
        print(build_prompt(out["clauses"]))

    print("\n================ ALTIER · today's fit ================")
    print(f" {top['look']['title']}   [score {top['score']:.2f}]")
    print()
    print(" " + out["text"].replace("\n", "\n "))
    print()
    print(f" written by:   {out['source']}" + (f" ({out['model']})" if out["model"] else ""))
    if out["fallback_reason"]:
        print(f" fell back:    {out['fallback_reason']}")
    if out["source"] == "gemini":
        print(f" copied exact: {out['verbatim']['matched']} of "
              f"{len([c for c in out['clauses'] if c['load_bearing']])} claim sentences")
        print(f" model wrote:  \"{out['model_added']}\"")
        print(f"               {out['residue_check']['length']} of "
              f"{out['residue_check']['allowed_length']} characters allowed, no numbers, "
              f"no sources")
    print("=" * 54 + "\n")


if __name__ == "__main__":
    main()
