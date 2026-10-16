import os, re, json, time, pathlib, urllib.parse, requests
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

N_SCENES = int(os.environ.get("N_SCENES", 100))

STYLE = ("flat 2D illustration, dark moody blue palette with warm orange glow, "
         "soft lighting, minimal details, vertical composition")
NO_TEXT = "no text, no letters, no captions, no watermark, no subtitles"

OUT = pathlib.Path("output")
OUT.mkdir(exist_ok=True)
PLAN = OUT / "scenes.json"
CHAR_PATH = pathlib.Path("input/character.png")
CHAR_TXT = OUT / "character.txt"


def describe_character():
    """عکس مرجع آدمک را یک بار توصیف می‌کند و نتیجه را ذخیره می‌کند."""
    if CHAR_TXT.exists():
        return CHAR_TXT.read_text(encoding="utf-8").strip()
    if not CHAR_PATH.exists():
        return "a simple round-faced cartoon character"
    img = types.Part.from_bytes(data=CHAR_PATH.read_bytes(), mime_type="image/png")
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            "Describe this cartoon character in one dense English paragraph so an "
            "image generator can redraw it identically: head shape, face style, "
            "eyes and mouth drawing style, exact colors, body shape, clothing, "
            "proportions, art style, line style. No background, no pose details.",
            img,
        ],
    )
    text = r.text.strip()
    CHAR_TXT.write_text(text, encoding="utf-8")
    return text


CHARACTER = describe_character()


def plan_scenes(script):
    """متن بلند را به صحنه‌ها و پرامپت تصویری تقسیم می‌کند."""
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
    r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    scenes = json.loads(re.sub(r"```json|```", "", r.text).strip())
    PLAN.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenes


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
