# 캐릭터 그림 만들기 (Gemini 프롬프트)

캐릭터의 **서 있는 그림 1장**(예: `hokora/sprites/reimu/idle_0.png` 또는 처음 뽑은 기준 그림)을 첨부하고,
아래 공통 프롬프트의 `[시트 내용]` 자리에 A·B·C 중 하나를 넣어 시트를 뽑습니다.
뽑은 시트는 가져오기 도구에 `--preset` 으로 넣으면 이름이 자동으로 붙습니다.

```
python tools/import_sheet.py 시트A.png <캐릭터> --preset move
python tools/import_sheet.py 시트B.png <캐릭터> --preset react
python tools/import_sheet.py 시트C.png <캐릭터> --preset life
```

| 시트 | 장면 (순서) | 누가 필요 |
| --- | --- | --- |
| A. 이동 (`move`) | 서기 2, 깜빡 1, 걷기 6 | 새 캐릭터 |
| B. 반응 (`react`) | 앉기 2, 던져짐 1, 쓰다듬기 4, 잡힘 3 | 새 캐릭터 |
| C. 생활 (`life`) | 낮잠 2, 손 흔들기 2, 특기 2, 뛰기 2, 붙잡힘 1 | 모든 캐릭터 |

**배경색**: 기본은 초록(`#00FF00`)입니다. 캐릭터에 초록이 많으면(사나에 머리, 요우무 옷) 프롬프트의 `#00FF00` 과
`green` 을 **자홍 `#FF00FF` / `magenta`** 로 바꿔서 뽑으세요. 가져오기 도구가 배경색을 알아서 판별합니다.

AI가 칸 순서를 틀리게 그리면 `--names` 로 직접 이름을 붙이고, 이상한 장면은 이름 자리에 `-` 를 써서 뺍니다.

## 공통 프롬프트

```
Using the attached image as the exact character and style reference, create ONE sprite sheet
of this same character. Keep the character identical in every frame: same face, same outfit,
same colors, same thick outline, same chibi plush proportions, same size and scale.
The head must stay the same size in every frame. Consecutive frames of one action must differ
only slightly, like frames of a real animation. Every frame is full body, facing slightly to
the viewer's right, standing on the same bottom line of its row, with clear green space
between frames so that no two frames touch or overlap. Read order: left to right, top to bottom.

[시트 내용]

Background: solid flat pure green (#00FF00) everywhere. No grid lines, no borders,
no numbers, no text, no shadows.
```

## 시트 A: 이동

```
Layout: 3 rows x 3 columns, 9 frames.
Row 1: 1. Standing still, arms relaxed. 2. Chest very slightly raised (breathing in). 3. Same as 1 with eyes closed (blink).
Row 2 (walking to the right): 4. Left foot forward touching the ground. 5. Left foot flat, body slightly lower. 6. Right foot passing under the body, body highest.
Row 3: 7. Right foot forward touching the ground. 8. Right foot flat, body slightly lower. 9. Left foot passing under the body, body highest.
```

## 시트 B: 반응

```
Layout: 3 rows: 3 frames, 4 frames, 3 frames (10 frames).
Row 1: 1. Sitting on the ground, legs stretched forward, hands on the lap. 2. Same, looking to the side. 3. Tumbling in the air, surprised face.
Row 2 (happy when petted): 4. Crouching, eyes closed in ^^ shape. 5. Jumping up, arms raised. 6. Top of the jump, very happy. 7. Landing, knees bent.
Row 3 (picked up, flailing): 8. Surprised, arms up, legs apart. 9. Arms and legs swapped. 10. Arms out to the sides.
```

## 시트 C: 생활

```
Layout: 3 rows x 3 columns, 9 frames.
Row 1:
 1. Sitting on the ground and sleeping: eyes closed, head tilted, peaceful face, small drool bubble.
 2. Same as 1, head tilted a little more (breathing out).
 3. Standing and waving the right hand high, happy smile.
Row 2:
 4. Same as 3, hand waved to the other side.
 5. [캐릭터 특기] - start of the action.
 6. [캐릭터 특기] - end of the action.
Row 3:
 7. Running fast to the right, body leaning forward, left leg forward, small sweat drop.
 8. Running fast to the right, right leg forward.
 9. Caught: flinching with surprised eyes, sweat drop, both hands up.
```

| 캐릭터 | `[캐릭터 특기]` |
| --- | --- |
| 레이무 | `Sweeping the ground with a bamboo broom` |
| 마리사 | `Holding a small bag full of gold coins with a mischievous grin` |
| 사쿠야 | `Holding up a silver pocket watch (stopping time)` |
| 치르노 | `Throwing a small ice crystal forward with a proud face` |

## 신사 장식 시트

아무 캐릭터 그림을 그림체 참고용으로 첨부합니다.

```
Using the attached image ONLY as an art style reference (thick soft dark-brown outline,
flat colors, cute chibi style), draw 9 small Japanese shrine decoration props as ONE sheet,
3 rows x 3 columns, each prop standing on its own bottom line, clear green space between them:
1. A small cherry blossom tree in full bloom. 2. A stone lantern (toro). 3. A white fox (kitsune) statue sitting.
4. An omikuji rack with white paper fortunes tied on strings. 5. An ema rack with small wooden prayer plaques.
6. A red paper umbrella with a small red bench. 7. A bamboo water basin (temizuya). 8. A wind chime hanging from a small wooden frame.
9. A big donation box (saisen-bako) with a golden coin on top.
Background: solid flat pure green (#00FF00). No text, no shadows, no grid lines.
```

## 새 캐릭터 기준 그림 (1단계)

기존 캐릭터의 서 있는 그림(예: 레이무 `idle_0.png`)을 **그림체 참고용**으로 첨부합니다.
뽑은 기준 그림을 다시 첨부해서 시트 A·B·C 를 뽑습니다.

```
The attached image is ONLY a style reference. Copy its art style exactly: chibi plush doll
proportions (very big round head, small bean-shaped body, stubby arms, round nub feet),
thick soft dark-brown outline, big sparkly eyes, cat-like mouth, soft pink blush, flat colors
with gentle shading. Do NOT copy the reference character's hair, bow, or outfit.

Draw this character instead, standing still, full body, body turned slightly to the viewer's right,
arms relaxed, feet at the bottom, centered, portrait canvas 5:6:
[캐릭터 설명]

Background: solid flat pure [BG]. No shadow, no text, no other objects.
```

| 캐릭터 | 배경 `[BG]` | `[캐릭터 특기]` |
| --- | --- | --- |
| 사나에 | `magenta (#FF00FF)` | `Waving a gohei (white paper wand) overhead, summoning a small swirl of wind (a miracle)` |
| 플랑드르 | `green (#00FF00)` | `Swinging a black twisted wand (Laevatein) with a playful fanged grin` |
| 레밀리아 | `green (#00FF00)` | `Spreading her bat wings wide and pointing forward with a proud, confident smirk` |
| 요우무 | `magenta (#FF00FF)` | `Drawing her long katana in a quick slash, with a sharp sword glint` |

**캐릭터 설명**

- 사나에: `Kochiya Sanae from Touhou Project: long bright green hair with one side lock, a white frog-shaped hair clip on the left, a white snake-shaped hair ornament wrapped around the side lock, green eyes, a white shrine maiden top with blue trim, detached white sleeves with blue trim, a blue skirt with a white frill hem, blue-and-white shoes.`
- 플랑드르: `Flandre Scarlet from Touhou Project: short blonde hair with a small side ponytail on her left, a white mob cap with a red ribbon, red eyes, a small fang, a red vest and red skirt with white frills, a white blouse with short puffy sleeves, a small yellow ascot, red shoes. Wings: two thin black branch-like wings with hanging crystal gems colored red, orange, yellow, cyan, blue and purple (NO green crystals). The wings must stay close to her body.`
- 레밀리아: `Remilia Scarlet from Touhou Project: short light lavender-blue hair, a pale pink mob cap with a red ribbon, red eyes, a small fang, a pale pink dress with short puffy sleeves, red ribbons and white frills, pink shoes, small dark purple bat wings on her back close to her body.`
- 요우무: `Konpaku Youmu from Touhou Project: short silver-white bob hair, a black hairband with a black ribbon bow, blue-gray eyes, a green vest over a white short-sleeved blouse, a green skirt, a small black bow tie, brown shoes, two katanas on her back (one long, one short). Her white ghost half (a round white wispy spirit with a short tail) floats right behind her shoulder, overlapping her body so it touches her.`

## 걷기만 다시 뽑기 (8장)

지금 캐릭터의 서 있는 그림(`hokora/sprites/<캐릭터>/idle_0.png`)을 첨부합니다.
초록 캐릭터(사나에·요우무)는 `#00FF00` / `green` 을 `#FF00FF` / `magenta` 로 바꿉니다.

```
Using the attached image as the exact character and style reference, draw a smooth 8-frame
WALK CYCLE of this same character as ONE sprite sheet.

VERY IMPORTANT - keep these identical in all 8 frames:
- The character always faces the SAME direction as the reference: body and face turned toward
  the viewer's RIGHT at the same 3/4 angle. Never turn the head or body toward the viewer or to the left.
- Same face, same expression, same outfit, same colors, same thick outline, same size and scale.
- The head stays in the same place; only a tiny up-and-down bob is allowed.
- Only the legs and arms move. Walking in place (like on a treadmill), no forward travel.

Layout: 2 rows x 4 columns, 8 frames, read left to right, top to bottom. Every frame full body,
standing on the same bottom line, with clear green space between frames so that no two frames touch.

1. Contact: right foot forward touching the ground with the heel, left foot behind, left arm forward.
2. Down: right foot flat, body slightly lower, left foot starting to lift.
3. Passing: left foot passing under the body, body at its highest, arms at the sides.
4. Up: left foot swinging forward, right heel lifting.
5. Contact: left foot forward touching the ground with the heel, right foot behind, right arm forward.
6. Down: left foot flat, body slightly lower, right foot starting to lift.
7. Passing: right foot passing under the body, body at its highest, arms at the sides.
8. Up: right foot swinging forward, left heel lifting.

Background: solid flat pure green (#00FF00) everywhere, no grid lines, no borders,
no numbers, no text, no shadows.
```

넣을 때는 옛 걷기 그림을 지우고 새 8장으로 바꿉니다.

```
python tools/import_sheet.py 걷기.png reimu --preset walk
```

8장이 아니면 `--names walk_0,walk_1,…` 로 장수에 맞게 적습니다 (`--preset walk` 없이 쓰면 옛 걷기 그림이 남으니 `--names` 앞에 옛 파일을 지우거나, 같은 장수로 뽑으세요).
