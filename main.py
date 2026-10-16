import os, re, json, time, pathlib, urllib.parse, requests
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
N_SCENES = int(os.environ.get("N_SCENES", 100))

STYLE = ("flat 2D illustration, dark moody blue palette with warm orange glow, "
         "soft lighting, minimal details, vertical composition")
CHARACTER = ("a round orange-faced cartoon character with a simple orange body "
             "and long orange sleeves")
NO_TEXT = "no text, no letters, no captions, no watermark, no subtitles"

OUT = pathlib.Path("output"); OUT.mkdir(exist_ok=True)
PLAN = OUT / "scenes.json"

def plan_scenes(script):
    if PLAN.exists():
        return json.loads(PLAN.read_text(encoding="utf-8"))
    prompt = f"""Split the script into exactly {N_SCENES} sequential scenes covering
all of it. The main character is {CHARACTER}. For each scene return JSON:
{{"id": number, "image_prompt": "detailed English description of ONE frame:
the character's action, emotion, setting, objects"}}.
Return ONLY a JSON array.

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
    prompt = f"{STYLE}. {CHARACTER}. {scene['image_prompt']}. {NO_TEXT}"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + f"?width=768&height=1344&nologo=true&seed={scene['id']}")
    for _ in range(3):
        try:
            r = requests.get(url, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                path.write_bytes(r.content)
                return
        except Exception as e:
            print("error:", e)
        time.sleep(10)

if __name__ == "__main__":
    script = open("input/script.txt", encoding="utf-8").read()
    scenes = plan_scenes(script)
    for s in scenes:
        generate_image(s)
        print("done", s["id"])
        time.sleep(5)
