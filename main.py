import os, re, json, time, pathlib, urllib.parse, requests
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

N_SCENES = int(os.environ.get("N_SCENES", 100))
FORCE_MODEL = os.environ.get("TEXT_MODEL", "").strip()  # اختیاری

STYLE = ("flat 2D illustration, dark moody blue palette with warm orange glow, "
         "soft lighting, minimal details, vertical composition")
NO_TEXT = "no text, no letters, no captions, no watermark, no subtitles"

OUT = pathlib.Path("output")
OUT.mkdir(exist_ok=True)
PLAN = OUT / "scenes.json"
CHAR_PATH = pathlib.Path("input/character.png")
CHAR_TXT = OUT / "character.txt"


# ---------- پیدا کردن خودکار مدل ----------
def candidate_models():
    """لیست مدل‌های متنی در دسترس، جدیدترین اول."""
    if FORCE_MODEL:
        return [FORCE_MODEL]
    found = []
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            low = name.lower()
            if "gemini" not in low:
                continue
            if any(x in low for x in ["image", "tts", "live", "audio", "embed",
                                      "imagen", "veo", "robotics", "computer",
                                      "native", "aqa"]):
                continue
            ver = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
            ver = float(ver.group(1)) if ver else 0
            kind = 2 if "flash" in low and "lite" not in low else (1 if "flash" in low else 0)
            stable = 0 if ("preview" in low or "exp" in low) else 1
            found.append((kind, ver, stable, name))
    except Exception as e:
        print("could not list models:", e)
    found.sort(reverse=True)
    names = [n for *_, n in found]
    print("candidate models:", names[:6])
    return names


MODELS = candidate_models()


def ask_gemini(contents):
    """از اولین مدلی که کار کند جواب می‌گیرد. اگر هیچ‌کدام کار نکرد None."""
    for name in MODELS[:8]:
        try:
            r = client.models.generate_content(model=name, contents=contents)
            if r.text:
                print("used model:", name)
                return r.text
        except Exception as e:
            print(f"model {name} failed: {str(e)[:100]}")
    return None


# ---------- توصیف کاراکتر ----------
def describe_character():
    if CHAR_TXT.exists():
        return CHAR_TXT.read_text(encoding="utf-8").strip()
    default = "a simple round-faced cartoon character with orange skin and sleeves"
    if not CHAR_PATH.exists():
        return default
    mime = "image/png" if CHAR_PATH.suffix.lower() == ".png" else "image/jpeg"
    img = types.Part.from_bytes(data=CHAR_PATH.read_bytes(), mime_type=mime)
    text = ask_gemini([
        "Describe this cartoon character in one dense English paragraph so an "
        "image generator can redraw it identically: head shape, face style, "
        "eyes and mouth drawing style, exact colors, body shape, clothing, "
        "proportions, art style, line style. No background, no pose details.",
        img,
    ])
    if not text:
        return default
    CHAR_TXT.write_text(text.strip(), encoding="utf-8")
    return text.strip()


CHARACTER = describe_character()


# ---------- تقسیم متن به صحنه ----------
def split_locally(script):
    """راه اضطراری بدون هوش مصنوعی."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?؟۔\n])\s+", script) if s.strip()]
    n = min(N_SCENES, len(sents)) or 1
    size = max(1, -(-len(sents) // n))
    chunks = [" ".join(sents[i:i + size]) for i in range(0, len(sents), size)]
    return [{"id": i + 1, "image_prompt": f"Illustrate this idea visually: {c}"}
            for i, c in enumerate(chunks)]


def plan_scenes(script):
    if PLAN.exists():
        return json.loads(PLAN.read_text(encoding="utf-8"))
    prompt = f"""Split the script below into exactly {N_SCENES} sequential scenes,
covering the whole script in order. The main character is: {CHARACTER}
If a scene does not involve the character, describe a clear educational visual
(objects, icons, simple diagram) instead.
For each scene return JSON: {{"id": number, "image_prompt": "detailed English
description of ONE frame: the character's action and emotion, setting, objects,
camera framing"}}.
Return ONLY a JSON array, no markdown.

SCRIPT:
{script}"""
    scenes = None
    text = ask_gemini(prompt)
    if text:
        try:
            scenes = json.loads(re.sub(r"```json|```", "", text).strip())
        except Exception as e:
            print("bad JSON from model:", e)
    if not scenes:
        print("Using local splitting (no AI planning).")
        scenes = split_locally(script)
    PLAN.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenes


# ---------- ساخت عکس ----------
def generate_image(scene):
    path = OUT / f"frame_{scene['id']:03d}.png"
    if path.exists():
        return
    prompt = f"{STYLE}. Character: {CHARACTER}. Scene: {scene['image_prompt']}. {NO_TEXT}"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1500])
           + f"?width=768&height=1344&nologo=true&seed={scene['id']}")
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                path.write_bytes(r.content)
                return
            print(f"scene {scene['id']}: bad response {r.status_code}")
        except Exception as e:
            print(f"scene {scene['id']} error: {e}")
        time.sleep(10)


if __name__ == "__main__":
    script = open("input/script.txt", encoding="utf-8").read()
    scenes = plan_scenes(script)
    print(f"{len(scenes)} scenes planned")
    for s in scenes:
        generate_image(s)
        print("done", s["id"])
        time.sleep(5)
