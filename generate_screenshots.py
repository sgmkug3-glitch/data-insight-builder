import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs("static/icons", exist_ok=True)

def create_screenshot(width, height, is_mobile=True):
    img = Image.new("RGBA", (width, height), (15, 23, 42, 255)) # Dark navy
    draw = ImageDraw.Draw(img)

    # Top header bar
    draw.rectangle([0, 0, width, int(height * 0.12)], fill=(30, 41, 59, 255))
    
    # Title simulation
    s = min(width, height) / 500.0
    draw.rectangle([int(20 * s), int(15 * s), int(60 * s), int(55 * s)], fill=(37, 99, 235, 255))
    
    # Content cards
    pad_x = int(width * 0.06)
    card_w = width - (pad_x * 2)
    card_y = int(height * 0.16)
    card_h = int(height * 0.28)

    draw.rounded_rectangle([pad_x, card_y, pad_x + card_w, card_y + card_h], radius=int(16 * s), fill=(255, 255, 255, 255))
    # Card 2 (Chart simulation)
    card2_y = card_y + card_h + int(20 * s)
    card2_h = int(height * 0.42)
    draw.rounded_rectangle([pad_x, card2_y, pad_x + card_w, card2_y + card2_h], radius=int(16 * s), fill=(255, 255, 255, 255))

    # Draw simulated chart bars inside Card 2
    cx = width // 2
    cy = card2_y + (card2_h // 2)
    
    num_bars = 5 if is_mobile else 8
    bw = int(card_w / (num_bars * 2.2))
    for i in range(num_bars):
        bx = pad_x + int(card_w * 0.1) + i * int(bw * 1.8)
        bh = int((card2_h * 0.25) + ((i % 4) + 1) * (card2_h * 0.12))
        by0 = card2_y + card2_h - int(card2_h * 0.15) - bh
        by1 = card2_y + card2_h - int(card2_h * 0.15)
        # Highlight color for one bar
        color = (139, 92, 246, 255) if i == (num_bars - 2) else (59, 130, 246, 255)
        draw.rounded_rectangle([bx, by0, bx + bw, by1], radius=int(6 * s), fill=color)

    return img

print("Generating PWA screenshots...")
mobile_shot = create_screenshot(750, 1334, is_mobile=True)
mobile_shot.save("static/icons/screenshot-mobile.png", "PNG")

desktop_shot = create_screenshot(1280, 800, is_mobile=False)
desktop_shot.save("static/icons/screenshot-desktop.png", "PNG")
print("Screenshots successfully generated!")
