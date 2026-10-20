import os
import math
from PIL import Image, ImageDraw, ImageFilter

os.makedirs("static/icons", exist_ok=True)

def create_app_icon(size=512, maskable=False):
    # Create RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Padding
    pad = int(size * 0.1) if maskable else int(size * 0.04)
    r = int(size * 0.22) if not maskable else int(size * 0.15)
    
    # Background rounded rectangle with gradient effect
    bg_box = [pad, pad, size - pad, size - pad]
    
    # Create background mask with rounded corners
    bg_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    bg_draw.rounded_rectangle(bg_box, radius=r, fill=(15, 23, 42, 255)) # Slate 900
    
    # Top-to-bottom gentle gradient overlay
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(size):
        ratio = y / size
        # From #1e3a8a (deep blue) to #0f172a (dark slate)
        red = int(24 * (1 - ratio) + 15 * ratio)
        green = int(58 * (1 - ratio) + 23 * ratio)
        blue = int(138 * (1 - ratio) + 42 * ratio)
        g_draw.line([(0, y), (size, y)], fill=(red, green, blue, 255))
    
    # Composite gradient with rounded rect mask
    bg_layer.paste(gradient, (0, 0), bg_layer)
    img.paste(bg_layer, (0, 0), bg_layer)

    # Accent glow ring around border
    accent_box = [pad + 2, pad + 2, size - pad - 2, size - pad - 2]
    accent_draw = ImageDraw.Draw(img)
    accent_draw.rounded_rectangle(accent_box, radius=r - 2, outline=(59, 130, 246, 120), width=max(2, int(size * 0.01)))

    # Chart & AI Sparkle Coordinates
    # Scale coordinates based on size
    s = size / 512.0
    
    # Inner chart area
    cx = size // 2
    cy = size // 2

    # Draw 3 Ascending Modern 3D/Glow Chart Bars
    # Bar 1 (Left, Cyan)
    b1_x0 = int(cx - 130 * s)
    b1_x1 = int(cx - 70 * s)
    b1_y1 = int(cy + 120 * s)
    b1_y0 = int(cy + 20 * s)
    accent_draw.rounded_rectangle([b1_x0, b1_y0, b1_x1, b1_y1], radius=int(12 * s), fill=(56, 189, 248, 230)) # #38bdf8

    # Bar 2 (Middle, Royal Blue)
    b2_x0 = int(cx - 30 * s)
    b2_x1 = int(cx + 30 * s)
    b2_y1 = int(cy + 120 * s)
    b2_y0 = int(cy - 40 * s)
    accent_draw.rounded_rectangle([b2_x0, b2_y0, b2_x1, b2_y1], radius=int(12 * s), fill=(96, 165, 250, 240)) # #60a5fa

    # Bar 3 (Right, Emerald/Teal Peak)
    b3_x0 = int(cx + 70 * s)
    b3_x1 = int(cx + 130 * s)
    b3_y1 = int(cy + 120 * s)
    b3_y0 = int(cy - 100 * s)
    accent_draw.rounded_rectangle([b3_x0, b3_y0, b3_x1, b3_y1], radius=int(12 * s), fill=(52, 211, 153, 255)) # #34d399

    # Trend line connecting data points
    pts = [
        (int(cx - 100 * s), int(cy + 10 * s)),
        (int(cx), int(cy - 50 * s)),
        (int(cx + 100 * s), int(cy - 110 * s)),
        (int(cx + 130 * s), int(cy - 130 * s))
    ]
    accent_draw.line(pts, fill=(255, 255, 255, 240), width=max(3, int(6 * s)))

    # Circle nodes on trend line
    node_r = int(8 * s)
    for px, py in pts[:-1]:
        accent_draw.ellipse([px - node_r, py - node_r, px + node_r, py + node_r], fill=(255, 255, 255, 255), outline=(37, 99, 235, 255), width=max(1, int(2 * s)))

    # AI Sparkle (✨ 4-point star) at top-right
    sx = int(cx + 128 * s)
    sy = int(cy - 132 * s)
    star_r1 = int(24 * s)
    star_r2 = int(7 * s)

    star_pts = []
    for i in range(8):
        angle = i * (math.pi / 4)
        dist = star_r1 if i % 2 == 0 else star_r2
        star_pts.append((int(sx + dist * math.cos(angle)), int(sy + dist * math.sin(angle))))
    
    accent_draw.polygon(star_pts, fill=(253, 224, 71, 255)) # Yellow 300 glow
    
    # Smaller sparkle nearby
    sx2 = int(cx + 80 * s)
    sy2 = int(cy - 145 * s)
    s2_r1 = int(12 * s)
    s2_r2 = int(4 * s)
    s2_pts = []
    for i in range(8):
        angle = i * (math.pi / 4)
        dist = s2_r1 if i % 2 == 0 else s2_r2
        s2_pts.append((int(sx2 + dist * math.cos(angle)), int(sy2 + dist * math.sin(angle))))
    accent_draw.polygon(s2_pts, fill=(254, 240, 138, 230))

    return img

# Generate all required icon sizes
print("Generating PWA and App Icons...")
icon_512 = create_app_icon(512, maskable=False)
icon_512.save("static/icons/icon-512.png", "PNG")

icon_192 = create_app_icon(192, maskable=False)
icon_192.save("static/icons/icon-192.png", "PNG")

icon_apple = create_app_icon(180, maskable=False)
icon_apple.save("static/icons/apple-touch-icon.png", "PNG")

icon_maskable = create_app_icon(512, maskable=True)
icon_maskable.save("static/icons/icon-maskable.png", "PNG")

favicon = create_app_icon(64, maskable=False)
favicon.save("static/icons/favicon-64.png", "PNG")
favicon_small = create_app_icon(32, maskable=False)
favicon_small.save("static/icons/favicon.ico", "ICO")

print("All icons successfully created in static/icons/!")
