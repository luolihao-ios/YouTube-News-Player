"""產生本專案自己的向量廣播圖示與 1024px App Icon（需要 Pillow）。"""
from pathlib import Path
import json
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / "NewsLiveApp/Resources/Assets.xcassets/AppIcon.appiconset"
folder.mkdir(parents=True, exist_ok=True)
canvas = Image.new("RGB", (2048, 2048), (239, 31, 48))
draw = ImageDraw.Draw(canvas)
scale = 2
for radius in (178, 300):
    bounds = tuple(int(v * scale) for v in (512-radius, 512-radius, 512+radius, 512+radius))
    draw.arc(bounds, -51, 51, fill="white", width=43*scale)
    draw.arc(bounds, 129, 231, fill="white", width=43*scale)
draw.ellipse((435*scale,435*scale,589*scale,589*scale), fill="white")
canvas.resize((1024, 1024), Image.Resampling.LANCZOS).save(folder / "AppIcon.png")
(folder / "Contents.json").write_text(json.dumps({"images":[{"filename":"AppIcon.png","idiom":"universal","platform":"ios","size":"1024x1024"}],"info":{"author":"xcode","version":1}},indent=2), encoding="utf-8")
(folder.parent / "Contents.json").write_text('{"info":{"author":"xcode","version":1}}\n', encoding="utf-8")
(ROOT / "docs/app-icon.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect width="1024" height="1024" fill="#ef1f30"/><g fill="none" stroke="white" stroke-width="43"><path d="M624 374 A178 178 0 0 1 624 650 M400 650 A178 178 0 0 1 400 374 M701 279 A300 300 0 0 1 701 745 M323 745 A300 300 0 0 1 323 279"/></g><circle cx="512" cy="512" r="77" fill="white"/></svg>''',encoding="utf-8")
print("已產生不透明 1024×1024 App Icon。")

# macOS 的标准尺寸与 visionOS 的分层图标共用本项目的向量几何。
assets = folder.parent
mac = assets / "AppIconMac.appiconset"
mac.mkdir(exist_ok=True)
entries = []
for points in (16, 32, 128, 256, 512):
    for density in (1, 2):
        name = f"icon-{points}@{density}x.png"
        canvas.resize((points*density,points*density),Image.Resampling.LANCZOS).save(mac/name)
        entries.append({"filename":name,"idiom":"mac","size":f"{points}x{points}","scale":f"{density}x"})
(mac/"Contents.json").write_text(json.dumps({"images":entries,"info":{"author":"xcode","version":1}},indent=2),encoding="utf8")
stack = assets / "AppIconVision.solidimagestack"
stack.mkdir(exist_ok=True)
names = ["Front", "Middle", "Back"]
(stack/"Contents.json").write_text(json.dumps({"info":{"author":"xcode","version":1},"layers":[{"filename":name+".solidimagestacklayer"} for name in names]},indent=2),encoding="utf8")
for name in names:
    layer = stack / (name+".solidimagestacklayer")
    content = layer / "Content.imageset"
    content.mkdir(parents=True,exist_ok=True)
    (layer/"Contents.json").write_text('{"info":{"author":"xcode","version":1}}\n',encoding="utf8")
    if name == "Back":
        layer_image = Image.new("RGB",(2048,2048),(239,31,48))
    else:
        layer_image = Image.new("RGBA",(2048,2048),(0,0,0,0))
        layer_draw = ImageDraw.Draw(layer_image)
        if name == "Front": layer_draw.ellipse((435*2,435*2,589*2,589*2),fill="white")
        else:
            for radius in (178,300):
                bounds = tuple(value*2 for value in (512-radius,512-radius,512+radius,512+radius))
                layer_draw.arc(bounds,-51,51,fill="white",width=86)
                layer_draw.arc(bounds,129,231,fill="white",width=86)
    layer_image.resize((1024,1024),Image.Resampling.LANCZOS).save(content/"layer.png")
    (content/"Contents.json").write_text(json.dumps({"images":[{"filename":"layer.png","idiom":"vision","scale":"2x"}],"info":{"author":"xcode","version":1}},indent=2),encoding="utf8")
print("已生成 macOS 全尺寸图标与 visionOS 三层图标。")
